from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.session import get_customer
from apps.catalog.inventory import format_delivery
from apps.core import crypto
from apps.payments import services as payment_services

from . import cart as cart_ops
from . import discounts, services
from .models import Order


def _wants_json(request):
    return request.headers.get("Accept", "").startswith("application/json")


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@require_POST
def cart_add(request):
    cart = cart_ops.get_cart(request, create=True)
    try:
        cart_ops.add(cart, _int(request.POST.get("variant")), _int(request.POST.get("quantity"), 1) or 1)
    except cart_ops.CartError as exc:
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": exc.message}, status=400)
        messages.error(request, exc.message)
        return redirect(request.POST.get("next") or "storefront:cart")
    if _wants_json(request):
        return JsonResponse({"ok": True, "count": cart_ops.item_count(request)})
    return redirect("storefront:cart")


@require_POST
def cart_update(request, item_id):
    cart = cart_ops.get_cart(request)
    if cart:
        cart_ops.set_quantity(cart, item_id, _int(request.POST.get("quantity"), 1))
    return redirect("storefront:cart")


@require_POST
def cart_remove(request, item_id):
    cart = cart_ops.get_cart(request)
    if cart:
        cart_ops.remove(cart, item_id)
    return redirect("storefront:cart")


@require_POST
def apply_discount(request):
    cart = cart_ops.get_cart(request, create=True)
    code = discounts.normalize(request.POST.get("discount_code"))
    if "remove" in request.POST or not code:
        cart.discount_code = ""
        cart.save(update_fields=["discount_code"])
    else:
        summary = cart_ops.summarize(cart)
        try:
            _, amount = discounts.evaluate(code, summary.total, get_customer(request))
        except discounts.DiscountError as exc:
            messages.error(request, exc.message)
        else:
            cart.discount_code = code
            cart.save(update_fields=["discount_code"])
            messages.success(request, "کد تخفیف اعمال شد.")
    return redirect(f"{reverse('storefront:checkout')}?step=info")


@require_POST
def place_order(request):
    customer = get_customer(request)
    if not customer:
        return redirect(f"{reverse('storefront:checkout')}?step=login")
    cart = cart_ops.get_cart(request)
    if cart is None:
        return redirect("storefront:cart")

    identifiers = {}
    for key, value in request.POST.items():
        if key.startswith("account_"):
            identifiers[_int(key.removeprefix("account_"))] = value
    notification_email = request.POST.get("notification_email", "").strip()

    # Keep what the customer typed so the form is not lost on errors.
    for item in cart.items.all():
        if item.pk in identifiers:
            item.account_identifier = identifiers[item.pk].strip()[:254]
            item.save(update_fields=["account_identifier"])
    cart.notification_email = notification_email[:254]
    cart.save(update_fields=["notification_email"])

    try:
        order = services.create_order(
            customer, cart, account_identifiers=identifiers,
            notification_email=notification_email, discount_code=cart.discount_code,
        )
    except services.OutOfStock as exc:
        messages.error(request, "موجودی بعضی از کالاها همین الان تمام شد. سبد خرید را بررسی کنید؛ هیچ مبلغی کسر نشده است.")
        request.session["cart_problems"] = exc.problem_variant_ids
        return redirect("storefront:cart")
    except services.OrderError as exc:
        if "discount_code" in exc.field_errors:
            cart.discount_code = ""
            cart.save(update_fields=["discount_code"])
        request.session["checkout_errors"] = {str(k): v for k, v in exc.field_errors.items()}
        messages.error(request, exc.message)
        if exc.problem_variant_ids:
            return redirect("storefront:cart")
        return redirect(f"{reverse('storefront:checkout')}?step=info")

    return _go_to_gateway(request, order)


def _go_to_gateway(request, order):
    def callback(gateway_name):
        return request.build_absolute_uri(reverse("payments:callback", args=[gateway_name]))

    try:
        return redirect(payment_services.start_payment(order, callback))
    except payment_services.PaymentError as exc:
        messages.error(request, exc.message)
        return redirect(order.get_absolute_url())


def _owned_order(request, number):
    customer = get_customer(request)
    if not customer:
        return None
    return (
        Order.objects.filter(pk=Order.pk_from_number(number), customer=customer)
        .prefetch_related("items__inventory_item", "items__variant")
        .first()
    )


@require_POST
def order_pay(request, number):
    order = _owned_order(request, number)
    if order is None:
        raise Http404
    return _go_to_gateway(request, order)


def order_detail(request, number):
    if not get_customer(request):
        return redirect(f"{reverse('storefront:checkout')}?step=login")
    order = _owned_order(request, number)
    if order is None:
        raise Http404

    items = []
    for item in order.items.all():
        delivery = None
        if item.status == item.Status.DELIVERED and item.inventory_item_id:
            raw = crypto.decrypt(item.inventory_item.encrypted_data, f"variant:{item.variant_id}".encode())
            delivery = format_delivery(item.variant, raw)
        items.append({"item": item, "delivery": delivery})

    seconds_left = max(0, int((order.reserved_until - timezone.now()).total_seconds())) if order.is_payable else 0
    if order.is_payable and seconds_left == 0:
        services.expire_order(order.pk)
        order.refresh_from_db()

    response = render(request, "orders/detail.html", {
        "order": order,
        "items": items,
        "seconds_left": seconds_left,
        "last_payment": order.payments.order_by("-created_at").first(),
    })
    response["Cache-Control"] = "no-store"
    return response
