"""
Delivery and after-sale: creating Delivery records, the manual operator queue,
renewals, and the scheduled expiry reminders / overdue alerts.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core import crypto
from apps.core.templatetags.persian import jdate
from apps.notifications import team
from apps.notifications.service import notify

from .models import Delivery, Order, OrderEvent, OrderItem


class DeliveryError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def absolute(path):
    return settings.SITE_URL.rstrip("/") + path


def _note_aad(item):
    return f"order_item:{item.pk}".encode()


def create_delivery(item, *, now=None, staff=None, note="", subscription_ends_at=None):
    """Create the Delivery for an item. Warranty is counted from the first delivery and never restarts."""
    now = now or timezone.now()
    return Delivery.objects.create(
        item=item,
        delivered_at=now,
        subscription_ends_at=subscription_ends_at or now + timedelta(days=item.duration_days),
        warranty_ends_at=now + timedelta(days=item.warranty_days),
        encrypted_note=crypto.encrypt(note, _note_aad(item)) if note else None,
        delivered_by=staff,
    )


def delivery_text(item):
    """Plain delivery info for the item's owner (stock credentials or the operator's note)."""
    from apps.catalog.inventory import format_delivery

    if item.inventory_item_id:
        raw = crypto.decrypt(item.inventory_item.encrypted_data, f"variant:{item.variant_id}".encode())
        return format_delivery(item.variant, raw)
    delivery = getattr(item, "delivery", None)
    if delivery and delivery.encrypted_note:
        return crypto.decrypt(delivery.encrypted_note, _note_aad(item))
    return ""


def notify_item_delivered(item):
    order = item.order
    notify(
        order.customer, "item_delivered",
        {"order_number": order.number, "product": item.product_title, "variant": item.variant_name,
         "order_url": absolute(order.get_absolute_url())},
        key=f"delivered:{item.pk}", email=order.notification_email,
    )


def _refresh_order_status(order):
    pending = order.items.filter(status=OrderItem.Status.AWAITING_DELIVERY).exists()
    delivered = order.items.filter(status=OrderItem.Status.DELIVERED).exists()
    if not pending and delivered and order.status in (Order.Status.PAID, Order.Status.PROCESSING):
        old = order.status
        order.status = Order.Status.DELIVERED
        order.save(update_fields=["status", "updated_at"])
        OrderEvent.objects.create(order=order, event="fulfillment", from_status=old, to_status=order.status)


def _staff_event(item, event, staff, **kwargs):
    OrderEvent.objects.create(
        order=item.order, item=item, event=event, actor_type=OrderEvent.Actor.STAFF, actor_id=str(staff.pk), **kwargs
    )


def claim(item_id, staff):
    with transaction.atomic():
        item = OrderItem.objects.select_for_update().get(pk=item_id)
        if item.status != OrderItem.Status.AWAITING_DELIVERY:
            raise DeliveryError("این قلم دیگر منتظر تحویل نیست.")
        if item.assigned_to_id and item.assigned_to_id != staff.pk:
            raise DeliveryError(f"این قلم را {item.assigned_to} برداشته است.")
        if item.assigned_to_id == staff.pk:
            return item
        item.assigned_to, item.claimed_at = staff, timezone.now()
        item.save(update_fields=["assigned_to", "claimed_at"])
        _staff_event(item, "claimed", staff)
    return item


def deliver_manual(item_id, staff, *, note, subscription_ends_at=None):
    """Operator completes a manual item: stores the (encrypted) delivery info and informs the customer."""
    note = (note or "").strip()
    if not note:
        raise DeliveryError("اطلاعات تحویل یا توضیح فعال‌سازی را وارد کنید.")
    with transaction.atomic():
        item = OrderItem.objects.select_for_update().select_related("order__customer").get(pk=item_id)
        if item.status != OrderItem.Status.AWAITING_DELIVERY:
            raise DeliveryError("این قلم دیگر منتظر تحویل نیست.")
        if item.assigned_to_id and item.assigned_to_id != staff.pk:
            raise DeliveryError(f"این قلم را {item.assigned_to} برداشته است.")
        now = timezone.now()
        create_delivery(item, now=now, staff=staff, note=note, subscription_ends_at=subscription_ends_at)
        old = item.status
        item.status, item.delivered_at = OrderItem.Status.DELIVERED, now
        item.assigned_to = item.assigned_to or staff
        item.save(update_fields=["status", "delivered_at", "assigned_to"])
        _staff_event(item, "item_delivered", staff, from_status=old, to_status=item.status)
        _mark_renewal(item, now)
        _refresh_order_status(item.order)
        transaction.on_commit(lambda: notify_item_delivered(item))
    return item


def reject_manual(item_id, staff, *, reason):
    """Operator cannot fulfil the item: it is cancelled and the order goes to the finance refund queue."""
    reason = (reason or "").strip()
    if not reason:
        raise DeliveryError("دلیل رد را بنویسید.")
    with transaction.atomic():
        item = OrderItem.objects.select_for_update().select_related("order").get(pk=item_id)
        if item.status != OrderItem.Status.AWAITING_DELIVERY:
            raise DeliveryError("این قلم دیگر منتظر تحویل نیست.")
        old = item.status
        item.status = OrderItem.Status.CANCELED
        item.save(update_fields=["status"])
        _staff_event(item, "item_rejected", staff, from_status=old, to_status=item.status, note=reason)
        order = Order.objects.select_for_update().get(pk=item.order_id)
        order.needs_refund = True
        order.save(update_fields=["needs_refund", "updated_at"])
        _refresh_order_status(order)
        transaction.on_commit(lambda: team.alert("refund_required", f"{order}: قلم «{item}» رد شد ({reason}). بازگشت وجه لازم است."))
    return item


def update_subscription_end(delivery, new_end, staff):
    old = delivery.subscription_ends_at
    delivery.subscription_ends_at = new_end
    delivery.save(update_fields=["subscription_ends_at"])
    _staff_event(delivery.item, "subscription_end_changed", staff, note=f"{old:%Y-%m-%d} → {new_end:%Y-%m-%d}")


def _mark_renewal(item, now):
    if item.renews_id:
        Delivery.objects.filter(pk=item.renews_id, renewed_at__isnull=True).update(renewed_at=now)


# ---------- scheduled jobs ----------

def send_expiry_reminders(days_before=3):
    """Once per delivery, N days before the subscription ends, unless it was already renewed."""
    now = timezone.now()
    due = Delivery.objects.select_related("item__order__customer").filter(
        renewed_at__isnull=True,
        item__status=OrderItem.Status.DELIVERED,
        subscription_ends_at__gt=now,
        subscription_ends_at__lte=now + timedelta(days=days_before),
    )
    count = 0
    for d in due:
        order = d.item.order
        count += len(notify(
            order.customer, "expiry_reminder",
            {"product": d.item.product_title, "ends_at": jdate(d.subscription_ends_at, "long"),
             "renew_url": absolute(order.get_absolute_url())},
            key=f"reminder:{d.pk}", email=order.notification_email,
        ))
    return count


def send_expiry_notices():
    """On the day a subscription ends (not renewed)."""
    now = timezone.now()
    due = Delivery.objects.select_related("item__order__customer").filter(
        renewed_at__isnull=True,
        item__status=OrderItem.Status.DELIVERED,
        subscription_ends_at__lte=now,
        subscription_ends_at__gt=now - timedelta(days=1),
    )
    count = 0
    for d in due:
        order = d.item.order
        count += len(notify(
            order.customer, "subscription_expired",
            {"product": d.item.product_title, "renew_url": absolute(order.get_absolute_url())},
            key=f"expired:{d.pk}", email=order.notification_email,
        ))
    return count


def alert_overdue_manual():
    """Tell the team once when a manual item passes its delivery deadline."""
    now = timezone.now()
    overdue = list(OrderItem.objects.filter(
        status=OrderItem.Status.AWAITING_DELIVERY, deadline_at__lt=now, overdue_alerted=False
    ).select_related("order"))
    for item in overdue:
        OrderItem.objects.filter(pk=item.pk).update(overdue_alerted=True)
        team.alert("delivery_overdue", f"مهلت تحویل «{item}» در {item.order} گذشته است.")
    return len(overdue)
