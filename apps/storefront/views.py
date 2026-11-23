from django.http import Http404
from django.shortcuts import render
from django.urls import reverse

from . import sample_data as data

CHECKOUT_STEPS = [("cart", "سبد خرید"), ("info", "اطلاعات و ورود"), ("pay", "پرداخت")]
CHECKOUT_STATES = ("login", "otp", "info", "pay")


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
    step = request.GET.get("step", "login")
    if step not in CHECKOUT_STATES:
        step = "login"
    items = data.CART_ITEMS
    return render(
        request,
        "storefront/checkout.html",
        _context(
            "cart",
            step=step,
            cart_items=items,
            cart_emails=[i for i in items if i["needs_email"]],
            summary=data.cart_summary(items),
            checkout_steps=CHECKOUT_STEPS,
        ),
    )
