"""
Order lifecycle. All business rules for orders live here; the site and the
bot only call these functions.

Guarantees:
* An inventory item is never sold twice: items are picked with
  SELECT ... FOR UPDATE SKIP LOCKED inside one transaction.
* If any line lacks stock, no order is created and no reservation remains.
* Prices are copied into the order and never change afterwards.
* Applying a payment twice has a single effect.
"""

import logging
import re
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from apps.catalog.inventory import check_low_stock
from apps.catalog.models import InventoryItem, Product, Variant
from apps.core.models import SiteSettings
from apps.notifications import team

from . import discounts
from .cart import summarize
from .models import DiscountRedemption, Order, OrderEvent, OrderItem

logger = logging.getLogger(__name__)

GMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@gmail\.com$", re.IGNORECASE)


class OrderError(Exception):
    def __init__(self, message, *, field_errors=None, problem_variant_ids=None):
        super().__init__(message)
        self.message = message
        self.field_errors = field_errors or {}
        self.problem_variant_ids = problem_variant_ids or []


class OutOfStock(OrderError):
    pass


def validate_account_identifier(variant, value):
    """Backend-only validation of the account email required by private variants."""
    value = (value or "").strip()
    if not value:
        return None, "وارد کردن این فیلد الزامی است."
    try:
        validate_email(value)
    except ValidationError:
        return None, "آدرس ایمیل معتبر نیست."
    if variant.account_field_type == Variant.AccountField.GMAIL and not GMAIL_RE.match(value):
        return None, "فقط آدرس‌های ‎@gmail.com‎ پذیرفته می‌شوند."
    return value.lower(), None


def log_event(order, event, *, item=None, from_status="", to_status="", actor_type=OrderEvent.Actor.SYSTEM, actor_id="", note=""):
    OrderEvent.objects.create(
        order=order, item=item, event=event, from_status=from_status, to_status=to_status,
        actor_type=actor_type, actor_id=str(actor_id or ""), note=note[:255],
    )


def _reserve_stock(variant_id, quantity):
    """Lock `quantity` available items of a variant; returns them or raises OutOfStock."""
    items = list(
        InventoryItem.objects.select_for_update(skip_locked=True)
        .filter(variant_id=variant_id, status=InventoryItem.Status.AVAILABLE)
        .order_by("id")[:quantity]
    )
    if len(items) < quantity:
        raise OutOfStock("موجودی یکی از کالاها کافی نیست.", problem_variant_ids=[variant_id])
    InventoryItem.objects.filter(pk__in=[i.pk for i in items]).update(status=InventoryItem.Status.RESERVED)
    return items


def create_order(customer, cart, *, channel=Order.Channel.WEB, account_identifiers=None,
                 notification_email="", discount_code=""):
    """Validate the cart, reserve stock for all lines and create a pending_payment order."""
    account_identifiers = account_identifiers or {}
    summary = summarize(cart)
    if not summary.lines:
        raise OrderError("سبد خرید شما خالی است.")

    unavailable = [line.variant.pk for line in summary.lines
                   if line.variant.status != Variant.Status.ACTIVE or line.product.status != Product.Status.ACTIVE]
    if unavailable:
        raise OrderError("بعضی از کالاهای سبد دیگر فروخته نمی‌شوند.", problem_variant_ids=unavailable)

    field_errors, identifiers = {}, {}
    for line in summary.account_lines:
        value, error = validate_account_identifier(line.variant, account_identifiers.get(line.item.pk))
        if error:
            field_errors[line.item.pk] = error
        identifiers[line.item.pk] = value
    notification_email = (notification_email or "").strip()
    if notification_email:
        try:
            validate_email(notification_email)
        except ValidationError:
            field_errors["notification_email"] = "ایمیل اطلاع‌رسانی معتبر نیست."
    if field_errors:
        raise OrderError("لطفاً خطاهای فرم را برطرف کنید.", field_errors=field_errors)

    minutes = SiteSettings.get().reservation_minutes
    with transaction.atomic():
        subtotal = summary.total
        discount, discount_amount = None, Decimal("0")
        if discount_code:
            try:
                discount, discount_amount = discounts.evaluate(discount_code, subtotal, customer, lock=True)
            except discounts.DiscountError as exc:
                raise OrderError(exc.message, field_errors={"discount_code": exc.message})

        order = Order.objects.create(
            customer=customer, channel=channel, subtotal=subtotal, discount_amount=discount_amount,
            total=subtotal - discount_amount, discount_code=discount, notification_email=notification_email,
            reserved_until=timezone.now() + timedelta(minutes=minutes),
        )
        for line in summary.lines:
            variant = line.variant
            reserved = []
            if variant.delivery_type == Variant.DeliveryType.STOCK:
                reserved = _reserve_stock(variant.pk, line.quantity)
            for n in range(line.quantity):
                OrderItem.objects.create(
                    order=order, variant=variant, seller_id=variant.seller_id,
                    product_title=variant.product.title, variant_name=variant.name,
                    delivery_type=variant.delivery_type, unit_price=variant.price,
                    compare_at_price=variant.compare_at_price, duration_days=variant.duration_days,
                    warranty_days=variant.warranty_days,
                    account_identifier=identifiers.get(line.item.pk) or "",
                    inventory_item=reserved[n] if reserved else None,
                )
        if discount:
            DiscountRedemption.objects.create(discount=discount, order=order, customer=customer, amount=discount_amount)
        log_event(order, "created", to_status=order.status, actor_type=OrderEvent.Actor.CUSTOMER, actor_id=customer.pk)

    # Remember the latest account email for next time.
    last = next((v for v in identifiers.values() if v), None)
    if last and last != customer.last_email:
        customer.last_email = last
        customer.save(update_fields=["last_email"])
    return order


def _release_reservations(order):
    item_ids = list(order.items.filter(inventory_item__isnull=False).values_list("inventory_item_id", flat=True))
    InventoryItem.objects.filter(pk__in=item_ids, status=InventoryItem.Status.RESERVED).update(
        status=InventoryItem.Status.AVAILABLE
    )
    order.items.update(inventory_item=None, status=OrderItem.Status.CANCELED)


def expire_order(order_id, *, reason="expired"):
    """Release the reservation of an unpaid order. Cart items stay in the cart."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.status != Order.Status.PENDING_PAYMENT:
            return False
        _release_reservations(order)
        old = order.status
        order.status = Order.Status.CANCELED if reason == "canceled" else Order.Status.EXPIRED
        order.save(update_fields=["status", "updated_at"])
        log_event(order, reason, from_status=old, to_status=order.status)
    return True


def expire_due_orders():
    due = Order.objects.filter(status=Order.Status.PENDING_PAYMENT, reserved_until__lt=timezone.now()).values_list("pk", flat=True)
    return sum(1 for pk in list(due) if expire_order(pk))


def _rereserve(order):
    """Money arrived after the reservation expired: try once more to reserve stock."""
    for item in order.items.select_related("variant"):
        if item.delivery_type == Variant.DeliveryType.STOCK:
            item.inventory_item = _reserve_stock(item.variant_id, 1)[0]
        item.status = OrderItem.Status.AWAITING_PAYMENT
        item.save(update_fields=["inventory_item", "status"])


def apply_payment(order_id, *, amount, payment_ref=""):
    """
    Mark an order paid after a verified payment of the exact amount.
    Idempotent: calling it again for an already-paid order does nothing.
    Returns the order.
    """
    from apps.notifications import sms

    refund_needed = False
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.paid_at is not None:
            return order
        if Decimal(amount) != order.total:
            raise OrderError("مبلغ پرداخت با مبلغ سفارش برابر نیست.")

        old = order.status
        if order.status in (Order.Status.EXPIRED, Order.Status.CANCELED):
            try:
                with transaction.atomic():
                    _rereserve(order)
            except OutOfStock:
                refund_needed = True

        order.paid_at = timezone.now()
        order.status = Order.Status.PAID
        order.needs_refund = refund_needed
        order.save(update_fields=["paid_at", "status", "needs_refund", "updated_at"])
        log_event(order, "paid", from_status=old, to_status=order.status, actor_type=OrderEvent.Actor.GATEWAY,
                  note=f"ref {payment_ref}" + (" — بازگشت وجه لازم" if refund_needed else ""))

        if not refund_needed:
            _fulfill(order)
            from .cart import clear
            from .models import Cart

            cart = Cart.objects.filter(customer_id=order.customer_id).first()
            if cart is not None:
                clear(cart)

    if refund_needed:
        team.alert("refund_required", f"پرداخت {order} بعد از انقضای رزرو رسید و موجودی نبود؛ بازگشت وجه لازم است.")
        if order.customer.can_receive_sms:
            try:
                sms.get_backend().send_template(order.customer.mobile, "refund_required", {"order": order.number})
            except Exception:
                logger.exception("SMS failed for refund_required %s", order.pk)
    return order


def _fulfill(order):
    """Stock items are delivered immediately; manual items go to the operator queue."""
    now = timezone.now()
    manual = 0
    touched_variants = set()
    for item in order.items.select_related("inventory_item"):
        if item.delivery_type == Variant.DeliveryType.STOCK and item.inventory_item_id:
            InventoryItem.objects.filter(pk=item.inventory_item_id).update(status=InventoryItem.Status.SOLD)
            item.status, item.delivered_at = OrderItem.Status.DELIVERED, now
            touched_variants.add(item.variant_id)
        else:
            item.status = OrderItem.Status.AWAITING_DELIVERY
            manual += 1
        item.save(update_fields=["status", "delivered_at"])
        log_event(order, "item_" + item.status, item=item, to_status=item.status)

    old = order.status
    order.status = Order.Status.PROCESSING if manual else Order.Status.DELIVERED
    order.save(update_fields=["status", "updated_at"])
    log_event(order, "fulfillment", from_status=old, to_status=order.status)
    for variant_id in touched_variants:
        transaction.on_commit(lambda vid=variant_id: check_low_stock(vid))
    if manual:
        transaction.on_commit(lambda: team.alert("manual_order", f"{order}: {manual} قلم منتظر تحویل دستی است."))
