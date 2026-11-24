import time
from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.accounts.session import get_customer
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.views import LOGIN_NEXT_KEY, PENDING_MOBILE_KEY, RESEND_AT_KEY
from apps.catalog import selectors
from apps.catalog.models import Category
from apps.core.templatetags.persian import price as fa_price
from apps.core.models import SiteSettings
from apps.orders import cart as cart_ops
from apps.orders import discounts

from . import seo
from .models import HomeBanner

CHECKOUT_STEPS = [("cart", "سبد خرید"), ("info", "اطلاعات و ورود"), ("pay", "پرداخت")]
FILTER_KEYS = ("in_stock", "instant", "duration", "min_price", "max_price")


def _context(request, nav_active=None, **extra):
    return {
        "categories": selectors.active_categories(),
        "nav_active": nav_active,
        **extra,
    }


def home(request):
    site = SiteSettings.get()
    return render(
        request,
        "storefront/home.html",
        _context(
            request,
            "home",
            banners=HomeBanner.objects.filter(is_active=True),
            best_sellers=selectors.featured_cards(),
            discounted=selectors.discounted_cards(),
            site=site,
            seo_title=site.home_seo_title or f"{settings.SITE_NAME} | خرید اشتراک ChatGPT، Gemini و سرویس‌های هوش مصنوعی",
            seo_description=site.home_seo_description
            or "خرید امن اشتراک و اکانت سرویس‌های هوش مصنوعی با تحویل فوری، گارانتی تعویض و پشتیبانی.",
            canonical_url=request.build_absolute_uri("/"),
            jsonld=seo.as_script(seo.organization(request), seo.website(request)),
        ),
    )


@require_GET
def robots_txt(request):
    lines = [
        "User-agent: *",
        *[f"Disallow: {p}" for p in ("/admin/", "/cart/", "/checkout/", "/account/", "/orders/", "/payments/", "/search/", "/accounts/", "/renew/")],
        "",
        f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")


def category(request, slug):
    cat = get_object_or_404(Category, slug=slug, is_active=True)
    products, filters = selectors.category_cards(cat, request.GET)

    filter_items = [(k, request.GET.getlist(k)) for k in FILTER_KEYS if any(request.GET.getlist(k))]
    base = cat.get_absolute_url()
    sort_links = []
    for key, label in selectors.SORTS:
        query = urlencode([*((k, v) for k, vals in filter_items for v in vals), ("sort", key)])
        sort_links.append((key, label, f"{base}?{query}"))

    crumbs = [("خانه", reverse("storefront:home")), (cat.name, None)]
    canonical = request.build_absolute_uri(base)
    active_count = sum(
        [filters["in_stock"], filters["instant"], bool(filters["durations"]),
         filters["min_price"] is not None or filters["max_price"] is not None]
    )
    return render(
        request,
        "storefront/category.html",
        _context(
            request,
            "categories",
            category=cat,
            products=products,
            filters=filters,
            has_filters=bool(filter_items),
            active_filter_count=active_count,
            filter_query_items=filter_items,
            sort_links=sort_links,
            sorts=selectors.SORTS,
            duration_buckets=selectors.DURATION_BUCKETS,
            crumbs=crumbs,
            seo_title=cat.seo_title or f"خرید اشتراک {cat.name} | {settings.SITE_NAME}",
            seo_description=cat.seo_description or f"خرید اشتراک {cat.name} با تحویل فوری و گارانتی از {settings.SITE_NAME}.",
            canonical_url=canonical,
            jsonld=seo.as_script(seo.breadcrumbs(request, crumbs, canonical)),
        ),
    )


def product(request, slug):
    card = selectors.product_detail(slug)
    if card is None:
        raise Http404
    selected = card.buyable[0] if card.buyable else card.variants[0]
    cat = card.product.category
    seo_description = card.product.seo_description or (
        f"خرید {card.title} از {fa_price(card.price)} تومان، {selected.delivery_label} و {selected.warranty_label}."
    )
    crumbs = [("خانه", reverse("storefront:home")), (cat.name, cat.get_absolute_url()), (card.title, None)]
    canonical = request.build_absolute_uri(card.product.get_absolute_url())
    image_url = seo.product_image_url(request, card.product)
    return render(
        request,
        "storefront/product.html",
        _context(
            request,
            product=card,
            selected=selected,
            related=selectors.related_cards(card),
            crumbs=crumbs,
            seo_title=card.product.seo_title or f"خرید {card.title} | {settings.SITE_NAME}",
            seo_description=seo_description,
            canonical_url=canonical,
            og_image=image_url,
            og_type="product",
            jsonld=seo.as_script(
                seo.product(request, card, image_url),
                seo.breadcrumbs(request, crumbs, canonical),
                seo.faq(card.product.faqs.all()),
            ),
        ),
    )


def search(request):
    q = request.GET.get("q", "").strip()[:100]
    return render(
        request,
        "storefront/search.html",
        _context(request, search_query=q, products=selectors.search_cards(q)),
    )


@require_GET
def search_suggest(request):
    q = request.GET.get("q", "").strip()[:100]
    results = [
        {
            "title": c.title,
            "url": c.product.get_absolute_url(),
            "price": f"{fa_price(c.price)} تومان" if c.in_stock else "ناموجود",
        }
        for c in selectors.search_cards(q, limit=8)
    ]
    return JsonResponse({"results": results})


def _discount_preview(cart, summary, customer):
    if not cart or not cart.discount_code or not summary.lines:
        return None, Decimal("0")
    try:
        _, amount = discounts.evaluate(cart.discount_code, summary.total, customer)
        return cart.discount_code, amount
    except discounts.DiscountError:
        return None, Decimal("0")


def cart(request):
    cart_obj = cart_ops.get_cart(request)
    summary = cart_ops.summarize(cart_obj)
    problems = set(request.session.pop("cart_problems", []))
    return render(
        request,
        "storefront/cart.html",
        _context(request, "cart", summary=summary, cart_items=summary.lines, problem_ids=problems,
                 checkout_steps=CHECKOUT_STEPS),
    )


def checkout(request):
    customer = get_customer(request)
    step = request.GET.get("step", "")
    pending_mobile = request.session.get(PENDING_MOBILE_KEY)

    nxt = request.GET.get("next")
    if customer:
        if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
            return redirect(nxt)
        # Signed-in customers skip the login steps.
        if step != "info":
            return redirect(f"{reverse('storefront:checkout')}?step=info")
    else:
        if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
            request.session[LOGIN_NEXT_KEY] = nxt
        if step == "info":
            return redirect(f"{reverse('storefront:checkout')}?step=login")
        if step == "otp" and not pending_mobile:
            step = "login"
        if step not in ("login", "otp"):
            step = "otp" if pending_mobile else "login"

    cart_obj = cart_ops.get_cart(request)
    summary = cart_ops.summarize(cart_obj)
    if customer and summary.has_problems:
        return redirect("storefront:cart")
    code, discount_amount = _discount_preview(cart_obj, summary, customer)

    resend_in = max(0, request.session.get(RESEND_AT_KEY, 0) - int(time.time()))
    return render(
        request,
        "storefront/checkout.html",
        _context(
            request,
            "cart",
            step=step,
            pending_mobile=pending_mobile,
            entered_mobile=request.session.get("otp_entered_mobile", ""),
            resend_in=resend_in,
            code_length=settings.OTP_CODE_LENGTH,
            otp_slots=range(settings.OTP_CODE_LENGTH),
            cart=cart_obj,
            summary=summary if summary.lines else None,
            cart_items=summary.lines,
            discount_code=code,
            discount_amount=discount_amount,
            payable=summary.total - discount_amount,
            errors=request.session.pop("checkout_errors", {}),
            checkout_steps=CHECKOUT_STEPS,
        ),
    )
