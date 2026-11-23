from decimal import Decimal

import pytest
from django.urls import reverse

from apps.catalog import inventory
from apps.catalog.models import Product, Redirect

from .factories import make_category, make_product, make_variant


@pytest.fixture
def catalog(db):
    cat = make_category()
    gpt = make_product(slug="اشتراک-chatgpt-plus", title="اشتراک ChatGPT Plus", category=cat,
                       keywords="chatgpt\nچت جی پی تی", is_featured=True)
    v1 = make_variant(gpt, price=1_890_000, compare_at_price=Decimal("2200000"), name="یک‌ماهه اشتراکی")
    inventory.import_items(v1, ["a|1", "b|2"])
    make_variant(gpt, price=2_490_000, name="یک‌ماهه اختصاصی", delivery_type="manual", delivery_deadline_hours=3,
                 account_type="private", duration_days=30)

    gem = make_product(slug="اشتراک-جمینای", title="اشتراک Gemini Advanced", category=cat,
                       keywords="gemini\nجمینای\nهوش مصنوعی گوگل")
    make_variant(gem, price=1_450_000, delivery_type="manual", delivery_deadline_hours=6, duration_days=90)

    empty = make_product(slug="اشتراک-ناموجود", title="اشتراک کرسر", category=cat)
    make_variant(empty, price=900_000)  # stock variant with no inventory

    make_product(slug="پیش-نویس", title="پیش‌نویس", category=cat, status=Product.Status.DRAFT)
    return {"cat": cat, "gpt": gpt, "gem": gem, "empty": empty}


def test_home_lists_real_products(client, catalog):
    html = client.get("/").content.decode()
    assert "اشتراک ChatGPT Plus" in html
    assert "پیش‌نویس" not in html


def test_home_works_with_empty_catalog(client, db):
    assert client.get("/").status_code == 200


def test_product_page_shows_price_server_side(client, catalog):
    response = client.get(reverse("storefront:product", args=["اشتراک-chatgpt-plus"]))
    html = response.content.decode()
    assert response.status_code == 200
    assert "۱٬۸۹۰٬۰۰۰" in html
    assert 'rel="canonical"' in html


def test_draft_product_is_404(client, catalog):
    assert client.get(reverse("storefront:product", args=["پیش-نویس"])).status_code == 404


def test_out_of_stock_card(client, catalog):
    html = client.get(reverse("storefront:product", args=["اشتراک-ناموجود"])).content.decode()
    assert "ناموجود" in html


def test_category_filters(client, catalog):
    url = reverse("storefront:category", args=[catalog["cat"].slug])
    titles = lambda r: [c.title for c in r.context["products"]]  # noqa: E731

    all_products = client.get(url)
    assert set(titles(all_products)) == {"اشتراک ChatGPT Plus", "اشتراک Gemini Advanced", "اشتراک کرسر"}
    assert titles(all_products)[-1] == "اشتراک کرسر"  # out of stock last

    assert titles(client.get(url, {"in_stock": "1"})) == ["اشتراک ChatGPT Plus", "اشتراک Gemini Advanced"]
    assert titles(client.get(url, {"instant": "1"})) == ["اشتراک ChatGPT Plus"]
    assert titles(client.get(url, {"duration": "3"})) == ["اشتراک Gemini Advanced"]
    assert titles(client.get(url, {"min_price": "1500000"})) == ["اشتراک ChatGPT Plus"]
    assert titles(client.get(url, {"max_price": "1500000", "in_stock": "1"})) == ["اشتراک Gemini Advanced"]


def test_category_sorting(client, catalog):
    url = reverse("storefront:category", args=[catalog["cat"].slug])
    cheap = [c.title for c in client.get(url, {"sort": "cheap", "in_stock": "1"}).context["products"]]
    assert cheap == ["اشتراک Gemini Advanced", "اشتراک ChatGPT Plus"]
    expensive = [c.title for c in client.get(url, {"sort": "expensive", "in_stock": "1"}).context["products"]]
    assert expensive == ["اشتراک ChatGPT Plus", "اشتراک Gemini Advanced"]


def test_filtered_category_is_noindex(client, catalog):
    url = reverse("storefront:category", args=[catalog["cat"].slug])
    assert "noindex" not in client.get(url).content.decode()
    assert "noindex" in client.get(url, {"instant": "1"}).content.decode()


@pytest.mark.parametrize("q", ["جمینای", "gemini", "GEMINI", "هوش مصنوعی گوگل", "هوش مصنوعي گوگل"])
def test_search_by_synonyms(client, catalog, q):
    titles = [c.title for c in client.get(reverse("storefront:search"), {"q": q}).context["products"]]
    assert titles == ["اشتراک Gemini Advanced"]


def test_search_suggest_json(client, catalog):
    data = client.get(reverse("storefront:search_suggest"), {"q": "چت جی"}).json()
    assert data["results"][0]["title"] == "اشتراک ChatGPT Plus"
    assert data["results"][0]["url"] == catalog["gpt"].get_absolute_url()


def test_search_requires_two_characters(client, catalog):
    assert client.get(reverse("storefront:search_suggest"), {"q": "g"}).json() == {"results": []}


def test_search_page_is_noindex(client, catalog):
    assert "noindex" in client.get(reverse("storefront:search"), {"q": "gemini"}).content.decode()


def test_slug_change_creates_301(client, catalog):
    gpt = catalog["gpt"]
    old_url = gpt.get_absolute_url()
    gpt.slug = "چت-جی-پی-تی-پلاس"
    gpt.save()

    from urllib.parse import unquote

    response = client.get(old_url)
    assert response.status_code == 301
    assert unquote(response.url) == "/product/چت-جی-پی-تی-پلاس/"
    assert client.get(response.url).status_code == 200


def test_redirect_chains_are_flattened(catalog):
    gpt = catalog["gpt"]
    for slug in ("v2", "v3"):
        gpt.slug = slug
        gpt.save()
    assert set(Redirect.objects.values_list("new_path", flat=True)) == {"/product/v3/"}
    # Going back to an old slug removes the loop.
    gpt.slug = "v2"
    gpt.save()
    assert not Redirect.objects.filter(old_path="/product/v2/").exists()


def test_category_slug_change_redirects(client, catalog):
    cat = catalog["cat"]
    old = cat.get_absolute_url()
    cat.slug = "چت"
    cat.save()
    assert client.get(old).status_code == 301
