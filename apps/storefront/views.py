import time
from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.accounts.session import get_customer
from apps.accounts.views import PENDING_MOBILE_KEY, RESEND_AT_KEY
from apps.catalog import selectors
from apps.catalog.models import Category
from apps.core.templatetags.persian import price as fa_price

CHECKOUT_STEPS = [("cart", "سبد خرید"), ("info", "اطلاعات و ورود"), ("pay", "پرداخت")]
FILTER_KEYS = ("in_stock", "instant", "duration", "min_price", "max_price")


def _context(request, nav_active=None, **extra):
    return {
        "categories": selectors.active_categories(),
        "cart_count": 0,  # The real cart arrives in M3.
        "nav_active": nav_active,
        **extra,
    }


def home(request):
    return render(
        request,
        "storefront/home.html",
        _context(
            request,
            "home",
            best_sellers=selectors.featured_cards(),
            discounted=selectors.discounted_cards(),
        ),
    )


def category(request, slug):
    cat = get_object_or_404(Category, slug=slug, is_active=True)
    products, filters = selectors.category_cards(cat, request.GET)

    filter_items = [(k, request.GET.getlist(k)) for k in FILTER_KEYS if any(request.GET.getlist(k))]
    base = cat.get_absolute_url()
    sort_links = []
    for key, label in selectors.SORTS:
        query = urlencode([*((k, v) for k, vals in filter_items for v in vals), ("sort", key)])
        sort_links.append((key, label, f"{base}?{query}"))

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
            crumbs=[("خانه", reverse("storefront:home")), (cat.name, None)],
            seo_title=cat.seo_title or f"خرید اشتراک {cat.name} | {settings.SITE_NAME}",
            seo_description=cat.seo_description or f"خرید اشتراک {cat.name} با تحویل فوری و گارانتی از {settings.SITE_NAME}.",
            canonical_url=request.build_absolute_uri(base),
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
    return render(
        request,
        "storefront/product.html",
        _context(
            request,
            product=card,
            selected=selected,
            related=selectors.related_cards(card),
            crumbs=[
                ("خانه", reverse("storefront:home")),
                (cat.name, cat.get_absolute_url()),
                (card.title, None),
            ],
            seo_title=card.product.seo_title or f"خرید {card.title} | {settings.SITE_NAME}",
            seo_description=seo_description,
            canonical_url=request.build_absolute_uri(card.product.get_absolute_url()),
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


def cart(request):
    return render(
        request,
        "storefront/cart.html",
        _context(request, "cart", cart_items=[], summary=None, checkout_steps=CHECKOUT_STEPS),
    )


def checkout(request):
    customer = get_customer(request)
    step = request.GET.get("step", "")
    pending_mobile = request.session.get(PENDING_MOBILE_KEY)

    if customer:
        # Signed-in customers skip the login steps.
        if step not in ("info", "pay"):
            return redirect(f"{reverse('storefront:checkout')}?step=info")
    else:
        if step in ("info", "pay"):
            return redirect(f"{reverse('storefront:checkout')}?step=login")
        if step == "otp" and not pending_mobile:
            step = "login"
        if step not in ("login", "otp"):
            step = "otp" if pending_mobile else "login"

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
            cart_items=[],
            cart_emails=[],
            summary=None,
            checkout_steps=CHECKOUT_STEPS,
        ),
    )
