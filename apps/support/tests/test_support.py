from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog import inventory
from apps.catalog.models import InventoryItem
from apps.core.models import AuditLog
from apps.notifications.models import Message
from apps.orders import delivery, services as order_services
from apps.orders.models import Delivery, Order, OrderItem
from apps.orders.tests.conftest import make_cart, make_customer
from apps.support import cards, services
from apps.support.models import Refund, Ticket, TicketMessage, WarrantyClaim

VALID_CARD = "6037997599999993"  # passes Luhn


@pytest.fixture
def staff(db):
    return User.objects.create_user("op", is_staff=True)


def _paid(variant, *, account=None, customer=None, discount=None):
    customer = customer or make_customer()
    cart = make_cart(customer, (variant, 1))
    ids = {cart.items.get().pk: account} if account else {}
    order = order_services.create_order(customer, cart, account_identifiers=ids, discount_code=discount or "")
    order_services.apply_payment(order.pk, amount=order.total)
    order.refresh_from_db()
    return order


# ---------- cards ----------

@pytest.mark.parametrize("raw", ["6037997599999993", "6037-9975-9999-9993", "۶۰۳۷ ۹۹۷۵ ۹۹۹۹ ۹۹۹۳"])
def test_card_normalization(raw):
    assert cards.normalize_card(raw) == VALID_CARD


@pytest.mark.parametrize("raw", ["", "1234", "6037997599999999", "abcd"])
def test_invalid_cards(raw):
    with pytest.raises(cards.InvalidCard):
        cards.normalize_card(raw)


def test_card_numbers_are_scrubbed_from_messages():
    assert cards.scrub(f"کارت من {VALID_CARD} است") == "کارت من 603799******9993 است"
    assert cards.scrub("سفارش 1234567890123456") == "سفارش 1234567890123456"  # not a valid card, untouched


# ---------- tickets ----------

@pytest.mark.django_db
def test_general_ticket_flow(staff, django_capture_on_commit_callbacks):
    customer = make_customer()
    ticket = services.open_ticket(customer, "سؤال", f"کارتم {VALID_CARD}")
    assert ticket.status == Ticket.Status.OPEN
    assert VALID_CARD not in ticket.messages.get().body

    with django_capture_on_commit_callbacks(execute=True):
        services.staff_reply(ticket, staff, "پاسخ پشتیبانی")
    ticket.refresh_from_db()
    assert ticket.status == Ticket.Status.ANSWERED
    assert Message.objects.filter(customer=customer, event="ticket_answered").exists()

    services.customer_reply(ticket, customer, "ممنون، یک سؤال دیگر")
    ticket.refresh_from_db()
    assert ticket.status == Ticket.Status.OPEN

    services.close_ticket(ticket)
    with pytest.raises(services.SupportError):
        services.customer_reply(ticket, customer, "باز هم")


@pytest.mark.django_db
def test_customer_cannot_use_someone_elses_ticket_or_order(stock_variant):
    owner, other = make_customer(), make_customer()
    ticket = services.open_ticket(owner, "x", "y")
    with pytest.raises(services.SupportError):
        services.customer_reply(ticket, other, "hi")
    order = _paid(stock_variant, customer=owner)
    with pytest.raises(services.SupportError):
        services.open_ticket(other, "x", "y", order=order)


# ---------- warranty ----------

@pytest.mark.django_db
def test_report_problem_requires_delivered_item_within_warranty(stock_variant, manual_variant):
    order = _paid(stock_variant)
    item = order.items.get()
    claim = services.report_problem(order.customer, item.pk, "وارد نمی‌شود")
    assert claim.ticket.kind == Ticket.Kind.WARRANTY and claim.status == WarrantyClaim.Status.PENDING

    with pytest.raises(services.SupportError):  # one open claim at a time
        services.report_problem(order.customer, item.pk, "دوباره")

    other = _paid(stock_variant)
    Delivery.objects.filter(item__order=other).update(warranty_ends_at=timezone.now() - timedelta(minutes=1))
    with pytest.raises(services.SupportError):
        services.report_problem(other.customer, other.items.get().pk, "دیر")

    waiting = _paid(manual_variant, account="a@gmail.com")  # not delivered yet
    with pytest.raises(services.SupportError):
        services.report_problem(waiting.customer, waiting.items.get().pk, "x")

    stranger = make_customer()
    with pytest.raises(services.SupportError):
        services.report_problem(stranger, item.pk, "x")


@pytest.mark.django_db
def test_replace_stock_item_voids_old_and_keeps_warranty(stock_variant, staff):
    order = _paid(stock_variant)
    item = order.items.get()
    old_inv = item.inventory_item
    warranty_end = item.delivery.warranty_ends_at
    old_text = delivery.delivery_text(item)

    claim = services.report_problem(order.customer, item.pk, "خراب است")
    services.replace_item(claim.pk, staff)

    item.refresh_from_db()
    old_inv.refresh_from_db()
    claim.refresh_from_db()
    assert old_inv.status == InventoryItem.Status.VOIDED
    assert item.inventory_item.status == InventoryItem.Status.SOLD
    assert item.inventory_item_id != old_inv.pk
    assert delivery.delivery_text(item) != old_text
    assert item.delivery.warranty_ends_at == warranty_end  # warranty does not restart
    assert claim.status == WarrantyClaim.Status.REPLACED
    assert claim.old_inventory_item == old_inv and claim.new_inventory_item == item.inventory_item

    with pytest.raises(services.SupportError):  # already resolved
        services.replace_item(claim.pk, staff)


@pytest.mark.django_db
def test_replace_without_stock_fails_cleanly(stock_variant, staff):
    order = _paid(stock_variant)
    InventoryItem.objects.filter(status=InventoryItem.Status.AVAILABLE).update(status=InventoryItem.Status.VOIDED)
    claim = services.report_problem(order.customer, order.items.get().pk, "x")
    with pytest.raises(services.SupportError):
        services.replace_item(claim.pk, staff)
    claim.refresh_from_db()
    assert claim.status == WarrantyClaim.Status.PENDING


@pytest.mark.django_db
def test_replace_manual_item_updates_delivery_note(manual_variant, staff):
    order = _paid(manual_variant, account="a@gmail.com")
    item = order.items.get()
    delivery.deliver_manual(item.pk, staff, note="فعال شد")
    claim = services.report_problem(order.customer, item.pk, "قطع شد")
    with pytest.raises(services.SupportError):
        services.replace_item(claim.pk, staff, note="")
    services.replace_item(claim.pk, staff, note="دوباره فعال شد")
    item.refresh_from_db()
    assert delivery.delivery_text(item) == "دوباره فعال شد"


@pytest.mark.django_db
def test_reject_requires_reason_and_tells_customer(stock_variant, staff):
    order = _paid(stock_variant)
    claim = services.report_problem(order.customer, order.items.get().pk, "x")
    with pytest.raises(services.SupportError):
        services.reject_claim(claim.pk, staff, reason=" ")
    services.reject_claim(claim.pk, staff, reason="اکانت سالم است")
    claim.refresh_from_db()
    assert claim.status == WarrantyClaim.Status.REJECTED
    assert "اکانت سالم است" in claim.ticket.messages.last().body


@pytest.mark.django_db
def test_prorated_refund(stock_variant):
    order = _paid(stock_variant)  # 1,000,000 for 30 days
    item = order.items.get()
    Delivery.objects.filter(item=item).update(subscription_ends_at=timezone.now() + timedelta(days=12, hours=1))
    item.refresh_from_db()
    assert services.prorated_refund(item) == Decimal("433333")  # 13 remaining days (partial day counts)
    Delivery.objects.filter(item=item).update(subscription_ends_at=timezone.now() - timedelta(days=1))
    item.refresh_from_db()
    assert services.prorated_refund(item) == 0


@pytest.mark.django_db
def test_prorated_refund_respects_order_discount(stock_variant):
    from apps.orders.models import DiscountCode

    DiscountCode.objects.create(code="HALF", kind="percent", value=Decimal("50"))
    order = _paid(stock_variant, discount="half")
    item = order.items.get()
    assert services.paid_share(item) == Decimal("500000")
    assert services.prorated_refund(item) <= Decimal("500000")


@pytest.mark.django_db
def test_full_warranty_refund_flow(stock_variant, staff, django_capture_on_commit_callbacks):
    order = _paid(stock_variant)
    item = order.items.get()
    customer = order.customer
    claim = services.report_problem(customer, item.pk, "کار نمی‌کند")

    services.refer_to_finance(claim.pk, staff)
    finance = User.objects.create_user("fin", is_staff=True)
    with pytest.raises(services.SupportError):  # more than what was paid
        services.approve_warranty_refund(claim.pk, finance, amount=Decimal("2000000"))
    with django_capture_on_commit_callbacks(execute=True):
        refund = services.approve_warranty_refund(claim.pk, finance, amount=Decimal("300000"))
    assert refund.status == Refund.Status.AWAITING_CARD and refund.ticket == claim.ticket

    with pytest.raises(services.SupportError):  # cannot pay before a card is given
        services.mark_refund_paid(refund.pk, finance, tracking_number="T1")

    with pytest.raises(services.SupportError):
        services.submit_card(refund, customer, "1234")
    services.submit_card(refund, customer, VALID_CARD)
    refund.refresh_from_db()
    assert refund.status == Refund.Status.READY
    assert refund.card_masked == "603799******9993"
    assert VALID_CARD.encode() not in bytes(refund.card_encrypted)

    request = RequestFactory().post("/")
    request.user = finance
    assert services.reveal_card(refund, request) == VALID_CARD
    assert AuditLog.objects.filter(action="reveal_refund_card", actor=finance).exists()

    with django_capture_on_commit_callbacks(execute=True):
        services.mark_refund_paid(refund.pk, finance, tracking_number="TRK-778")
    refund.refresh_from_db()
    item.refresh_from_db()
    order.refresh_from_db()
    assert refund.status == Refund.Status.PAID and refund.card_encrypted is None  # card erased after payout
    assert item.status == OrderItem.Status.REFUNDED
    assert order.status == Order.Status.REFUNDED
    assert Message.objects.filter(customer=customer, event="refund_paid").exists()
    assert claim.ticket.messages.filter(body__contains="TRK-778").exists()

    # Paying twice has one effect.
    services.mark_refund_paid(refund.pk, finance, tracking_number="OTHER")
    refund.refresh_from_db()
    assert refund.tracking_number == "TRK-778"


@pytest.mark.django_db
def test_create_refund_is_idempotent(stock_variant):
    order = _paid(stock_variant)
    a = services.create_refund(order, amount=Decimal("10"), reason=Refund.Reason.LATE_PAYMENT, key="order:x")
    b = services.create_refund(order, amount=Decimal("10"), reason=Refund.Reason.LATE_PAYMENT, key="order:x")
    assert a.pk == b.pk
    assert Refund.objects.count() == 1 and Ticket.objects.filter(kind=Ticket.Kind.REFUND).count() == 1


@pytest.mark.django_db
def test_rejected_manual_item_creates_refund(manual_variant, staff):
    order = _paid(manual_variant, account="a@gmail.com")
    delivery.reject_manual(order.items.get().pk, staff, reason="ممکن نیست")
    refund = Refund.objects.get(order=order)
    assert refund.reason == Refund.Reason.ITEM_REJECTED and refund.amount == Decimal("500000")


@pytest.mark.django_db
def test_late_payment_refund_closes_needs_refund_flag(stock_variant, staff):
    customer = make_customer()
    late = order_services.create_order(customer, make_cart(customer, (stock_variant, 1)))
    order_services.expire_order(late.pk)
    other = make_customer()
    order_services.create_order(other, make_cart(other, (stock_variant, 10)))
    order_services.apply_payment(late.pk, amount=late.total)

    refund = Refund.objects.get(order=late)
    services.submit_card(refund, customer, VALID_CARD)
    services.mark_refund_paid(refund.pk, staff, tracking_number="T9")
    late.refresh_from_db()
    assert late.needs_refund is False and late.status == Order.Status.REFUNDED
