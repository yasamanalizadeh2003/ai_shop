import time

from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.session import get_customer
from apps.accounts.views import PENDING_MOBILE_KEY, RESEND_AT_KEY

from . import sample_data as data

CHECKOUT_STEPS = [("cart", "سبد خرید"), ("info", "اطلاعات و ورود"), ("pay", "پرداخت")]


def _context(nav_active=None, **extra):
    return {"categories": data.CATEGORIES, "cart_count": len(data.CART_ITEMS), "nav_active": nav_active, **extra}


def home(request):
    products = data.PRODUCTS
    return render(
        request,
        "storefront/home.html",
        _context(
            "home",
            best_sellers=products[:6],
            discounted=[p for p in products if p["compare_at"]],
        ),
    )


def category(request, slug):
    cat = data.get_category(slug)
    if cat is None:
        raise Http404
    crumbs = [("خانه", reverse("storefront:home")), (cat["name"], None)]
    return render(
        request,
        "storefront/category.html",
        _context("categories", category=cat, products=data.PRODUCTS, crumbs=crumbs),
    )


def product(request, slug):
    item = data.get_product(slug)
    if item is None:
        raise Http404
    cat = item["category"]
    crumbs = [
        ("خانه", reverse("storefront:home")),
        (cat["name"], reverse("storefront:category", args=[cat["slug"]])),
        (item["title"], None),
    ]
    related = [p for p in data.PRODUCTS if p["slug"] != slug][:5]
    return render(request, "storefront/product.html", _context(product=item, related=related, crumbs=crumbs))


def cart(request):
    items = data.CART_ITEMS
    return render(
        request,
        "storefront/cart.html",
        _context("cart", cart_items=items, summary=data.cart_summary(items), checkout_steps=CHECKOUT_STEPS),
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
    items = data.CART_ITEMS
    return render(
        request,
        "storefront/checkout.html",
        _context(
            "cart",
            step=step,
            pending_mobile=pending_mobile,
            entered_mobile=request.session.get("otp_entered_mobile", ""),
            resend_in=resend_in,
            code_length=settings.OTP_CODE_LENGTH,
            otp_slots=range(settings.OTP_CODE_LENGTH),
            cart_items=items,
            cart_emails=[i for i in items if i["needs_email"]],
            summary=data.cart_summary(items),
            checkout_steps=CHECKOUT_STEPS,
        ),
    )
