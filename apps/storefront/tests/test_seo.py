import io
import json
import re
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.catalog import inventory
from apps.catalog.models import Product, ProductFaq
from apps.catalog.tests.factories import make_category, make_product, make_variant
from apps.core.models import SiteSettings
from apps.core.richtext import render, sanitize


def jsonld(html):
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    return [json.loads(b) for b in blocks]


def by_type(objects, kind):
    return next(o for o in objects if o["@type"] == kind)


@pytest.fixture
def product(db):
    cat = make_category()
    p = make_product(slug="اشتراک-جمینای", title="اشتراک Gemini", category=cat, brand="Google",
                     description="<p>توضیح <strong>بلند</strong></p>")
    stock = make_variant(p, price=1_450_000, name="یک‌ماهه")
    inventory.import_items(stock, ["a|1"])
    make_variant(p, price=4_000_000, name="سه‌ماهه")  # stock variant without inventory
    ProductFaq.objects.create(product=p, question="سؤال؟", answer="<p>جواب <em>کامل</em></p>")
    return p


def test_product_jsonld(client, product):
    html = client.get(product.get_absolute_url()).content.decode()
    data = jsonld(html)

    p = by_type(data, "Product")
    assert p["name"] == "اشتراک Gemini"
    assert p["brand"]["name"] == "Google"
    assert "aggregateRating" not in p and "review" not in p  # no fake ratings
    offers = {o["name"]: o for o in p["offers"]}
    assert offers["یک‌ماهه"]["price"] == "14500000"  # Toman × 10 = IRR
    assert offers["یک‌ماهه"]["priceCurrency"] == "IRR"
    assert offers["یک‌ماهه"]["availability"].endswith("InStock")
    assert offers["سه‌ماهه"]["availability"].endswith("OutOfStock")

    crumbs = by_type(data, "BreadcrumbList")["itemListElement"]
    assert [c["name"] for c in crumbs] == ["خانه", "دستیار چت", "اشتراک Gemini"]
    assert all(c["item"].startswith("http") for c in crumbs)

    faq = by_type(data, "FAQPage")["mainEntity"][0]
    assert faq["name"] == "سؤال؟"
    assert faq["acceptedAnswer"]["text"] == "جواب کامل"  # plain text, no HTML


def test_jsonld_cannot_break_out_of_script(client, product):
    Product.objects.filter(pk=product.pk).update(title="</script><script>alert(1)</script>")
    html = client.get(product.get_absolute_url()).content.decode()
    assert "<script>alert(1)" not in html
    assert jsonld(html)  # still valid JSON


def test_open_graph_and_canonical(client, product):
    html = client.get(product.get_absolute_url()).content.decode()
    assert '<meta property="og:type" content="product">' in html
    assert 'property="og:image" content="http' in html
    assert re.search(r'<link rel="canonical" href="http://testserver/product/', html)
    assert 'name="twitter:card"' in html


def test_home_has_organization_and_search_action(client, db):
    data = jsonld(client.get("/").content.decode())
    assert by_type(data, "Organization")["logo"].endswith("logo-512.png")
    assert "search_term_string" in by_type(data, "WebSite")["potentialAction"]["target"]


def test_category_breadcrumb_jsonld(client, product):
    html = client.get(reverse("storefront:category", args=[product.category.slug])).content.decode()
    assert by_type(jsonld(html), "BreadcrumbList")


def test_prices_and_text_without_javascript(client, product):
    html = client.get(product.get_absolute_url()).content.decode()
    body = html.split("<main", 1)[1]
    assert "۱٬۴۵۰٬۰۰۰" in body
    assert "<strong>بلند</strong>" in body  # rich description rendered server-side


def test_sitemap_lists_active_pages_only(client, product):
    make_product(slug="draft-one", title="draft", status=Product.Status.DRAFT)
    xml = client.get("/sitemap.xml").content.decode()
    assert "<loc>http://testserver/</loc>" in xml
    assert "%D8%AC%D9%85%DB%8C%D9%86%D8%A7%DB%8C" in xml or "جمینای" in xml
    assert "draft-one" not in xml
    assert "<lastmod>" in xml


def test_robots_txt(client, db):
    text = client.get("/robots.txt").content.decode()
    for path in ("/admin/", "/cart/", "/checkout/", "/account/", "/search/"):
        assert f"Disallow: {path}" in text
    assert "Sitemap: http://testserver/sitemap.xml" in text


@pytest.mark.parametrize("url", ["/cart/", "/checkout/", "/search/?q=gemini"])
def test_private_pages_are_noindex(client, product, url):
    assert "noindex" in client.get(url).content.decode()


def test_custom_404(client, db, settings):
    settings.DEBUG = False
    response = client.get("/no-such-page/")
    assert response.status_code == 404
    assert "پیدا نشد" in response.content.decode()


def test_search_console_and_analytics_tags(client, db):
    s = SiteSettings.get()
    s.search_console_verification = "abc123"
    s.analytics_id = "G-TEST123"
    s.save()
    html = client.get("/").content.decode()
    assert '<meta name="google-site-verification" content="abc123">' in html
    assert "googletagmanager.com/gtag/js?id=G-TEST123" in html


def test_no_analytics_by_default(client, db):
    assert "googletagmanager" not in client.get("/").content.decode()


def test_home_banners_and_text_from_panel(client, db):
    from apps.storefront.models import HomeBanner

    HomeBanner.objects.all().delete()
    HomeBanner.objects.create(title="بنر تست", highlight="خط دوم", link="/x/")
    s = SiteSettings.get()
    s.home_text = "<p>متن <strong>سئو</strong> از پنل</p>"
    s.save()
    html = client.get("/").content.decode()
    assert "بنر تست" in html and "خط دوم" in html
    assert "<strong>سئو</strong>" in html
    assert re.search(r"<h1[^>]*>\s*بنر تست", html)  # first banner is the page heading


# ---------- rich text safety ----------

def test_sanitize_strips_dangerous_markup():
    dirty = '<p onclick="x()">hi<script>alert(1)</script><a href="javascript:evil()">x</a><img src=x onerror=y></p>'
    clean = sanitize(dirty)
    assert "script" not in clean and "onclick" not in clean and "javascript:" not in clean and "<img" not in clean
    assert "<p>hi" in clean


def test_render_keeps_allowed_formatting_and_converts_plain_text():
    assert render("<h2>عنوان</h2><ul><li>یک</li></ul>") == "<h2>عنوان</h2><ul><li>یک</li></ul>"
    assert render("خط اول\n\nخط دوم") == "<p>خط اول</p>\n\n<p>خط دوم</p>"
    assert "&lt;b&gt;" in render("متن با <b> بدون پاراگراف")  # plain text is escaped


@pytest.mark.django_db
def test_admin_save_sanitizes_rich_text():
    cat = make_category()
    field = Product._meta.get_field("description")
    cleaned = field.clean('<p>ok</p><script>bad()</script>', Product(category=cat))
    assert "script" not in cleaned and "<p>ok</p>" in cleaned


# ---------- images ----------

def _png(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, "PNG")
    return SimpleUploadedFile("photo.png", buf.getvalue(), content_type="image/png")


@pytest.mark.django_db
def test_uploaded_image_becomes_square_webp(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = make_product(slug="img", title="img")
    p.image = _png(1600, 900)
    p.save()
    p.refresh_from_db()
    assert p.image.name.endswith(".webp")
    assert (p.image_width, p.image_height) == (800, 800)
    with Image.open(p.image.path) as img:
        assert img.format == "WEBP" and img.size == (800, 800)
