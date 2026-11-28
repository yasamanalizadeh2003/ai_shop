"""
Tickets, warranty claims and refunds. All rules live here; views and the bot only call these.

Warranty outcomes (spec §4):
* replace  – operator; a fresh item is delivered, the old one is voided; the warranty does NOT restart.
* refund   – finance manager; proportional to the remaining days (editable), paid to the customer's card.
* reject   – operator; the reason is shown to the customer.

Refunds: the customer gives the destination card inside the ticket; it is stored encrypted and erased
as soon as the payout is recorded with a tracking number. Creating or paying a refund twice has one effect.
"""

import math
from decimal import ROUND_FLOOR, Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.inventory import check_low_stock
from apps.catalog.models import InventoryItem, Variant
from apps.core import crypto
from apps.core.models import AuditLog
from apps.notifications import team
from apps.notifications.service import notify
from apps.orders.models import Order, OrderEvent, OrderItem

from . import cards
from .models import Refund, Ticket, TicketMessage, WarrantyClaim

MAX_BODY = 4000


class SupportError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _url(path):
    return settings.SITE_URL.rstrip("/") + path


def _clean_body(body):
    body = cards.scrub((body or "").strip())[:MAX_BODY]
    if not body:
        raise SupportError("متن پیام را بنویسید.")
    return body


def _system_message(ticket, body):
    TicketMessage.objects.create(ticket=ticket, author_type=TicketMessage.Author.SYSTEM, body=body)


def _staff_event(order, event, staff, item=None, note=""):
    OrderEvent.objects.create(order=order, item=item, event=event, actor_type=OrderEvent.Actor.STAFF,
                              actor_id=str(staff.pk) if staff else "", note=note[:255])


# ---------- tickets ----------

def open_ticket(customer, subject, body, *, order=None, kind=Ticket.Kind.GENERAL):
    subject = (subject or "").strip()[:150]
    if not subject:
        raise SupportError("موضوع تیکت را بنویسید.")
    body = _clean_body(body)
    if order is not None and order.customer_id != customer.pk:
        raise SupportError("این سفارش متعلق به شما نیست.")
    with transaction.atomic():
        ticket = Ticket.objects.create(customer=customer, subject=subject, order=order, kind=kind)
        TicketMessage.objects.create(ticket=ticket, author_type=TicketMessage.Author.CUSTOMER, body=body)
    transaction.on_commit(lambda: team.alert("ticket", f"تیکت جدید #{ticket.pk}: {subject}"))
    return ticket


def customer_reply(ticket, customer, body):
    if ticket.customer_id != customer.pk:
        raise SupportError("این تیکت متعلق به شما نیست.")
    if ticket.status == Ticket.Status.CLOSED:
        raise SupportError("این تیکت بسته شده است؛ اگر مشکل ادامه دارد تیکت جدید باز کنید.")
    body = _clean_body(body)
    with transaction.atomic():
        TicketMessage.objects.create(ticket=ticket, author_type=TicketMessage.Author.CUSTOMER, body=body)
        ticket.status = Ticket.Status.OPEN
        ticket.save(update_fields=["status", "updated_at"])
    return ticket


def staff_reply(ticket, staff, body, *, close=False):
    body = _clean_body(body)
    with transaction.atomic():
        TicketMessage.objects.create(ticket=ticket, author_type=TicketMessage.Author.STAFF, staff=staff, body=body)
        ticket.status = Ticket.Status.CLOSED if close else Ticket.Status.ANSWERED
        ticket.save(update_fields=["status", "updated_at"])
        message_count = ticket.messages.count()
        transaction.on_commit(lambda: notify(
            ticket.customer, "ticket_answered",
            {"ticket_id": ticket.pk, "subject": ticket.subject, "ticket_url": _url(ticket.get_absolute_url())},
            key=f"ticket_answered:{ticket.pk}:{message_count}",
        ))
    return ticket


def close_ticket(ticket):
    ticket.status = Ticket.Status.CLOSED
    ticket.save(update_fields=["status", "updated_at"])
    return ticket


# ---------- warranty ----------

def report_problem(customer, item_id, body):
    """'Report a problem' on a delivered item: opens a warranty ticket while the warranty lasts."""
    item = (OrderItem.objects.select_related("order", "delivery")
            .filter(pk=item_id, order__customer=customer).first())
    if item is None:
        raise SupportError("این قلم پیدا نشد.")
    delivery = getattr(item, "delivery", None)
    if item.status != OrderItem.Status.DELIVERED or delivery is None:
        raise SupportError("فقط برای اقلام تحویل‌شده می‌توان گزارش مشکل ثبت کرد.")
    if delivery.warranty_ends_at <= timezone.now():
        raise SupportError("مهلت گارانتی این قلم تمام شده است. می‌توانید تیکت عمومی ثبت کنید.")
    if item.claims.filter(status__in=[WarrantyClaim.Status.PENDING, WarrantyClaim.Status.REFUND_REQUESTED]).exists():
        raise SupportError("برای این قلم یک درخواست گارانتی در حال بررسی است.")

    body = _clean_body(body)
    with transaction.atomic():
        ticket = Ticket.objects.create(customer=customer, order=item.order, kind=Ticket.Kind.WARRANTY,
                                       subject=f"گزارش مشکل: {item.product_title} · {item.variant_name}")
        TicketMessage.objects.create(ticket=ticket, author_type=TicketMessage.Author.CUSTOMER, body=body)
        claim = WarrantyClaim.objects.create(ticket=ticket, order_item=item)
        OrderEvent.objects.create(order=item.order, item=item, event="warranty_claim", actor_type=OrderEvent.Actor.CUSTOMER,
                                  actor_id=str(customer.pk))
    transaction.on_commit(lambda: team.alert("ticket", f"گزارش مشکل گارانتی #{ticket.pk}: {item}"))
    return claim


def _lock_pending_claim(claim_id, *allowed):
    claim = WarrantyClaim.objects.select_for_update(of=("self",)).select_related("ticket", "order_item__order").get(pk=claim_id)
    if claim.status not in (allowed or (WarrantyClaim.Status.PENDING,)):
        raise SupportError("این درخواست گارانتی قبلاً نتیجه گرفته است.")
    return claim


def _notify_result(claim, result_text):
    item = claim.order_item
    notify(
        claim.ticket.customer, "warranty_result",
        {"product": item.product_title, "result": result_text, "ticket_url": _url(claim.ticket.get_absolute_url())},
        key=f"warranty_result:{claim.pk}",
    )


def replace_item(claim_id, staff, *, note=""):
    """Operator replaces the item. Stock items get a fresh inventory item; manual items get new delivery info."""
    from apps.orders.delivery import _note_aad

    with transaction.atomic():
        claim = _lock_pending_claim(claim_id)
        item = OrderItem.objects.select_for_update(of=("self",)).select_related("delivery", "variant").get(pk=claim.order_item_id)
        now = timezone.now()

        if item.delivery_type == Variant.DeliveryType.STOCK:
            new = (InventoryItem.objects.select_for_update(skip_locked=True)
                   .filter(variant_id=item.variant_id, status=InventoryItem.Status.AVAILABLE).order_by("id").first())
            if new is None:
                raise SupportError("موجودی این تنوع تمام شده است؛ انبار را شارژ کنید یا درخواست را به مدیر مالی ارجاع دهید.")
            old_id = item.inventory_item_id
            InventoryItem.objects.filter(pk=old_id).update(status=InventoryItem.Status.VOIDED)
            new.status = InventoryItem.Status.SOLD
            new.save(update_fields=["status"])
            # Detach the old item first: the link is one-to-one.
            OrderItem.objects.filter(pk=item.pk).update(inventory_item=None)
            OrderItem.objects.filter(pk=item.pk).update(inventory_item=new)
            claim.old_inventory_item_id, claim.new_inventory_item = old_id, new
            transaction.on_commit(lambda: check_low_stock(item.variant_id))
        else:
            note = (note or "").strip()
            if not note:
                raise SupportError("اطلاعات تحویل جدید را بنویسید.")
            item.delivery.encrypted_note = crypto.encrypt(note, _note_aad(item))
            item.delivery.save(update_fields=["encrypted_note"])

        # The warranty does not restart: Delivery.warranty_ends_at is left untouched.
        claim.status, claim.resolved_by, claim.resolved_at = WarrantyClaim.Status.REPLACED, staff, now
        claim.resolution_note = "اکانت تعویض شد."
        claim.save()
        _system_message(claim.ticket, "اکانت شما تعویض شد. اطلاعات جدید در صفحه سفارش نمایش داده می‌شود.")
        claim.ticket.status = Ticket.Status.ANSWERED
        claim.ticket.save(update_fields=["status", "updated_at"])
        _staff_event(item.order, "warranty_replaced", staff, item=item)
        transaction.on_commit(lambda: _notify_result(claim, "اکانت تعویض شد"))
    return claim


def reject_claim(claim_id, staff, *, reason):
    reason = (reason or "").strip()
    if not reason:
        raise SupportError("دلیل رد را بنویسید؛ برای مشتری نمایش داده می‌شود.")
    with transaction.atomic():
        claim = _lock_pending_claim(claim_id, WarrantyClaim.Status.PENDING, WarrantyClaim.Status.REFUND_REQUESTED)
        claim.status, claim.resolved_by, claim.resolved_at = WarrantyClaim.Status.REJECTED, staff, timezone.now()
        claim.resolution_note = reason[:255]
        claim.save()
        _system_message(claim.ticket, f"درخواست گارانتی رد شد. دلیل: {reason}")
        claim.ticket.status = Ticket.Status.ANSWERED
        claim.ticket.save(update_fields=["status", "updated_at"])
        _staff_event(claim.order_item.order, "warranty_rejected", staff, item=claim.order_item, note=reason)
        transaction.on_commit(lambda: _notify_result(claim, "درخواست رد شد"))
    return claim


def refer_to_finance(claim_id, staff, *, note=""):
    with transaction.atomic():
        claim = _lock_pending_claim(claim_id)
        claim.status = WarrantyClaim.Status.REFUND_REQUESTED
        claim.resolution_note = (note or "")[:255]
        claim.save(update_fields=["status", "resolution_note"])
        _staff_event(claim.order_item.order, "warranty_refund_requested", staff, item=claim.order_item, note=note)
    transaction.on_commit(lambda: team.alert("refund_required", f"درخواست گارانتی #{claim.ticket_id} برای بازگشت وجه به مدیر مالی ارجاع شد."))
    return claim


def paid_share(item):
    """What the customer actually paid for this unit (order discounts spread proportionally)."""
    order = item.order
    if not order.subtotal:
        return Decimal("0")
    return (item.unit_price * order.total / order.subtotal).quantize(Decimal("1"), rounding=ROUND_FLOOR)


def prorated_refund(item, now=None):
    """Refund for the remaining whole days of the subscription, based on what was paid."""
    now = now or timezone.now()
    delivery = getattr(item, "delivery", None)
    if delivery is None or not item.duration_days:
        return paid_share(item)
    remaining_days = max(0, math.ceil((delivery.subscription_ends_at - now).total_seconds() / 86400))
    remaining_days = min(remaining_days, item.duration_days)
    return (paid_share(item) * remaining_days / item.duration_days).quantize(Decimal("1"), rounding=ROUND_FLOOR)


def approve_warranty_refund(claim_id, staff, *, amount=None):
    """Finance manager decides a refund for a warranty claim (default: prorated, editable)."""
    with transaction.atomic():
        claim = _lock_pending_claim(claim_id, WarrantyClaim.Status.PENDING, WarrantyClaim.Status.REFUND_REQUESTED)
        item = claim.order_item
        suggested = prorated_refund(item)
        amount = Decimal(amount) if amount not in (None, "") else suggested
        if amount <= 0 or amount > paid_share(item):
            raise SupportError("مبلغ بازگشت باید بیشتر از صفر و حداکثر برابر مبلغ پرداختی این قلم باشد.")
        refund = create_refund(item.order, item=item, amount=amount, reason=Refund.Reason.WARRANTY,
                               key=f"claim:{claim.pk}", ticket=claim.ticket)
        claim.status, claim.refund = WarrantyClaim.Status.REFUNDED, refund
        claim.resolved_by, claim.resolved_at = staff, timezone.now()
        claim.save()
        _staff_event(item.order, "warranty_refund_approved", staff, item=item, note=f"{amount:,} تومان")
        transaction.on_commit(lambda: _notify_result(claim, f"بازگشت {amount:,} تومان"))
    return refund


# ---------- refunds ----------

def create_refund(order, *, amount, reason, key, item=None, ticket=None):
    """Create a refund (idempotent by key) and ask the customer for a destination card inside a ticket."""
    existing = Refund.objects.filter(key=key).first()
    if existing:
        return existing
    with transaction.atomic():
        if ticket is None:
            ticket = Ticket.objects.create(customer=order.customer, order=order, kind=Ticket.Kind.REFUND,
                                           subject=f"بازگشت وجه سفارش {order.number}")
        try:
            with transaction.atomic():
                refund = Refund.objects.create(order=order, order_item=item, ticket=ticket, reason=reason,
                                               amount=amount, key=key)
        except IntegrityError:
            return Refund.objects.get(key=key)
        _system_message(ticket, f"مبلغ {amount:,} تومان به کارت شما برمی‌گردد. لطفاً شماره کارت ۱۶ رقمی به نام خودتان را در همین صفحه وارد کنید.")
        ticket.status = Ticket.Status.ANSWERED
        ticket.save(update_fields=["status", "updated_at"])
    transaction.on_commit(lambda: notify(
        order.customer, "refund_required",
        {"order_number": order.number, "amount": f"{amount:,}", "order_url": _url(order.get_absolute_url()),
         "ticket_url": _url(ticket.get_absolute_url())},
        key=f"refund_required:{refund.pk}", email=order.notification_email,
    ))
    return refund


def submit_card(refund, customer, raw_card):
    if refund.order.customer_id != customer.pk:
        raise SupportError("این درخواست متعلق به شما نیست.")
    if refund.status not in (Refund.Status.AWAITING_CARD, Refund.Status.READY):
        raise SupportError("این بازگشت وجه دیگر منتظر شماره کارت نیست.")
    try:
        digits = cards.normalize_card(raw_card)
    except cards.InvalidCard as exc:
        raise SupportError(str(exc))
    with transaction.atomic():
        refund = Refund.objects.select_for_update().get(pk=refund.pk)
        refund.card_encrypted = crypto.encrypt(digits, f"refund:{refund.pk}".encode())
        refund.card_masked = cards.mask(digits)
        refund.status = Refund.Status.READY
        refund.save(update_fields=["card_encrypted", "card_masked", "status"])
        if refund.ticket_id:
            _system_message(refund.ticket, f"شماره کارت {refund.card_masked} ثبت شد. پس از واریز، شماره پیگیری اعلام می‌شود.")
    transaction.on_commit(lambda: team.alert("refund_ready", f"{refund}: شماره کارت ثبت شد و آماده واریز است."))
    return refund


def reveal_card(refund, request):
    if not refund.card_encrypted:
        return ""
    value = crypto.decrypt(refund.card_encrypted, f"refund:{refund.pk}".encode())
    AuditLog.record(request, "reveal_refund_card", refund)
    return value


def mark_refund_paid(refund_id, staff, *, tracking_number, method=Refund.Method.MANUAL):
    tracking_number = (tracking_number or "").strip()
    if not tracking_number:
        raise SupportError("شماره پیگیری واریز را وارد کنید.")
    with transaction.atomic():
        refund = Refund.objects.select_for_update(of=("self",)).select_related("order", "order_item", "ticket").get(pk=refund_id)
        if refund.status == Refund.Status.PAID:
            return refund
        if method == Refund.Method.MANUAL and refund.status != Refund.Status.READY:
            raise SupportError("برای واریز دستی، مشتری باید ابتدا شماره کارت را ثبت کند.")
        now = timezone.now()
        refund.status, refund.method, refund.tracking_number = Refund.Status.PAID, method, tracking_number[:60]
        refund.paid_by, refund.paid_at = staff, now
        refund.card_encrypted = None  # erased after payout (spec §3)
        refund.save()

        order = Order.objects.select_for_update().get(pk=refund.order_id)
        if refund.order_item_id:
            OrderItem.objects.filter(pk=refund.order_item_id).update(status=OrderItem.Status.REFUNDED)
            _staff_event(order, "item_refunded", staff, item=refund.order_item, note=f"{refund.amount:,} / {tracking_number}")
        else:
            order.items.exclude(status=OrderItem.Status.DELIVERED).update(status=OrderItem.Status.REFUNDED)
        open_items = order.items.exclude(status__in=[OrderItem.Status.REFUNDED, OrderItem.Status.CANCELED]).exists()
        if (not refund.order_item_id or not open_items) and order.status != Order.Status.REFUNDED:
            old = order.status
            order.status = Order.Status.REFUNDED
            order.save(update_fields=["status", "updated_at"])
            OrderEvent.objects.create(order=order, event="refunded", from_status=old, to_status=order.status,
                                      actor_type=OrderEvent.Actor.STAFF, actor_id=str(staff.pk), note=tracking_number[:255])
        if not Refund.objects.filter(order=order).exclude(status__in=[Refund.Status.PAID, Refund.Status.CANCELED]).exists():
            order.needs_refund = False
            order.save(update_fields=["needs_refund", "updated_at"])

        if refund.ticket_id:
            _system_message(refund.ticket, f"مبلغ {refund.amount:,} تومان به کارت {refund.card_masked or ''} واریز شد. شماره پیگیری: {tracking_number}")
            refund.ticket.status = Ticket.Status.CLOSED
            refund.ticket.save(update_fields=["status", "updated_at"])
        transaction.on_commit(lambda: notify(
            order.customer, "refund_paid",
            {"order_number": order.number, "amount": f"{refund.amount:,}", "tracking_number": tracking_number},
            key=f"refund_paid:{refund.pk}", email=order.notification_email,
        ))
    return refund
