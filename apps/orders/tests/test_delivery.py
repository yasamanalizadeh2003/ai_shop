from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.notifications.models import Message
from apps.notifications.team import MemoryTeamBackend
from apps.orders import cart as cart_ops
from apps.orders import delivery, services
from apps.orders.models import Delivery, Order, OrderItem

from .conftest import make_cart, make_customer


@pytest.fixture
def operator(db):
    return User.objects.create_user("op1", is_staff=True)


def _paid_order(variant, *, account=None, customer=None):
    customer = customer or make_customer()
    cart = make_cart(customer, (variant, 1))
    ids = {cart.items.get().pk: account} if account else {}
    order = services.create_order(customer, cart, account_identifiers=ids)
    services.apply_payment(order.pk, amount=order.total)
    order.refresh_from_db()
    return order


@pytest.mark.django_db
def test_stock_delivery_has_subscription_and_warranty_dates(stock_variant):
    order = _paid_order(stock_variant)
    d = Delivery.objects.get(item__order=order)
    assert d.subscription_ends_at - d.delivered_at == timedelta(days=30)
    assert d.warranty_ends_at - d.delivered_at == timedelta(days=30)
    assert delivery.delivery_text(d.item).startswith("user")


@pytest.mark.django_db
def test_payment_queues_paid_and_delivered_messages(stock_variant):
    order = _paid_order(stock_variant)
    events = set(Message.objects.filter(customer=order.customer).values_list("event", flat=True))
    assert events == {"payment_success", "item_delivered"}


@pytest.mark.django_db
def test_sms_never_contains_credentials(stock_variant, sms_outbox):
    order = _paid_order(stock_variant)
    from apps.notifications.service import send_due

    send_due()
    secret = delivery.delivery_text(order.items.get())
    for sent in sms_outbox:
        assert "pw" not in sent["params"]["text"]
        assert secret not in sent["params"]["text"]
        assert str(order.number) in sent["params"]["text"] or "تحویل" in sent["params"]["text"]


@pytest.mark.django_db
def test_manual_item_gets_deadline(manual_variant):
    order = _paid_order(manual_variant, account="a@gmail.com")
    item = order.items.get()
    assert item.status == OrderItem.Status.AWAITING_DELIVERY
    assert item.deadline_at - order.paid_at == timedelta(hours=3)


@pytest.mark.django_db
def test_operator_claims_and_delivers(manual_variant, operator):
    order = _paid_order(manual_variant, account="a@gmail.com")
    item = order.items.get()

    delivery.claim(item.pk, operator)
    custom_end = timezone.now() + timedelta(days=31)
    delivery.deliver_manual(item.pk, operator, note="اشتراک روی a@gmail.com فعال شد", subscription_ends_at=custom_end)

    item.refresh_from_db()
    order.refresh_from_db()
    assert item.status == OrderItem.Status.DELIVERED and item.assigned_to == operator
    assert order.status == Order.Status.DELIVERED
    assert item.delivery.subscription_ends_at == custom_end
    assert delivery.delivery_text(item) == "اشتراک روی a@gmail.com فعال شد"
    assert b"a@gmail.com" not in bytes(item.delivery.encrypted_note)  # stored encrypted
    assert order.events.filter(event="item_delivered", actor_type="staff").exists()


@pytest.mark.django_db
def test_another_operator_cannot_take_a_claimed_item(manual_variant, operator):
    other = User.objects.create_user("op2", is_staff=True)
    item = _paid_order(manual_variant, account="a@gmail.com").items.get()
    delivery.claim(item.pk, operator)
    with pytest.raises(delivery.DeliveryError):
        delivery.claim(item.pk, other)
    with pytest.raises(delivery.DeliveryError):
        delivery.deliver_manual(item.pk, other, note="x")


@pytest.mark.django_db
def test_delivery_requires_a_note_and_happens_once(manual_variant, operator):
    item = _paid_order(manual_variant, account="a@gmail.com").items.get()
    with pytest.raises(delivery.DeliveryError):
        delivery.deliver_manual(item.pk, operator, note="  ")
    delivery.deliver_manual(item.pk, operator, note="done")
    with pytest.raises(delivery.DeliveryError):
        delivery.deliver_manual(item.pk, operator, note="again")


@pytest.mark.django_db
def test_reject_sends_order_to_refund_queue(manual_variant, operator, django_capture_on_commit_callbacks):
    order = _paid_order(manual_variant, account="a@gmail.com")
    with django_capture_on_commit_callbacks(execute=True):
        delivery.reject_manual(order.items.get().pk, operator, reason="حساب سازمانی است")
    order.refresh_from_db()
    assert order.needs_refund
    assert order.items.get().status == OrderItem.Status.CANCELED
    assert any(a["kind"] == "refund_required" for a in MemoryTeamBackend.outbox)


@pytest.mark.django_db
def test_overdue_alert_once(manual_variant):
    item = _paid_order(manual_variant, account="a@gmail.com").items.get()
    OrderItem.objects.filter(pk=item.pk).update(deadline_at=timezone.now() - timedelta(minutes=1))
    MemoryTeamBackend.outbox = []
    assert delivery.alert_overdue_manual() == 1
    assert delivery.alert_overdue_manual() == 0
    assert [a["kind"] for a in MemoryTeamBackend.outbox] == ["delivery_overdue"]


@pytest.mark.django_db
def test_expiry_reminder_job_twice_sends_one_sms(stock_variant, sms_outbox):
    """Spec test: running the reminder job twice sends exactly one SMS."""
    from apps.notifications.service import send_due

    order = _paid_order(stock_variant)
    send_due()  # flush purchase messages
    sms_outbox.clear()
    Delivery.objects.filter(item__order=order).update(subscription_ends_at=timezone.now() + timedelta(days=2))

    delivery.send_expiry_reminders()
    delivery.send_expiry_reminders()
    from unittest import mock
    from zoneinfo import ZoneInfo

    # A daytime moment after the messages were queued (reminders are not sent at night).
    tomorrow = timezone.now().astimezone(ZoneInfo("Asia/Tehran")) + timedelta(days=1)
    noon = tomorrow.replace(hour=12, minute=0, second=0, microsecond=0)
    with mock.patch("apps.notifications.service.timezone.now", return_value=noon):
        send_due()
        send_due()

    reminders = [s for s in sms_outbox if s.get("template") == "expiry_reminder"]
    assert len(reminders) == 1


@pytest.mark.django_db
def test_no_reminder_for_renewed_or_far_subscriptions(stock_variant):
    order = _paid_order(stock_variant)
    d = Delivery.objects.get(item__order=order)
    Delivery.objects.filter(pk=d.pk).update(subscription_ends_at=timezone.now() + timedelta(days=10))
    assert delivery.send_expiry_reminders() == 0
    Delivery.objects.filter(pk=d.pk).update(subscription_ends_at=timezone.now() + timedelta(days=1), renewed_at=timezone.now())
    assert delivery.send_expiry_reminders() == 0


@pytest.mark.django_db
def test_expired_notice_on_last_day(stock_variant):
    order = _paid_order(stock_variant)
    Delivery.objects.filter(item__order=order).update(subscription_ends_at=timezone.now() - timedelta(hours=1))
    assert delivery.send_expiry_notices() > 0
    assert delivery.send_expiry_notices() == 0


@pytest.mark.django_db
def test_renewal_marks_old_delivery(stock_variant):
    order = _paid_order(stock_variant)
    old = Delivery.objects.get(item__order=order)
    customer = order.customer

    cart = cart_ops.get_customer_cart(customer)
    cart_ops.renew(cart, old)
    assert cart.items.get().renews == old

    new_order = services.create_order(customer, cart)
    services.apply_payment(new_order.pk, amount=new_order.total)
    old.refresh_from_db()
    assert old.renewed_at is not None
    assert delivery.send_expiry_reminders() == 0


@pytest.mark.django_db
def test_operator_can_change_subscription_end(stock_variant, operator):
    d = Delivery.objects.get(item__order=_paid_order(stock_variant))
    new_end = timezone.now() + timedelta(days=60)
    delivery.update_subscription_end(d, new_end, operator)
    d.refresh_from_db()
    assert d.subscription_ends_at == new_end
    assert d.item.order.events.filter(event="subscription_end_changed").exists()
