from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import InventoryItem
from apps.orders import services as order_services
from apps.orders.models import Order, OrderEvent
from apps.orders.tests.conftest import make_cart, make_customer
from apps.payments import services
from apps.payments.models import MockTransaction, Payment


@pytest.fixture
def order(stock_variant):
    customer = make_customer()
    return order_services.create_order(customer, make_cart(customer, (stock_variant, 1)))


def _start(order):
    url = services.start_payment(order, lambda g: f"http://testserver/payments/callback/{g}/")
    payment = Payment.objects.get(order=order)
    return url, payment


def _bank_pays(payment, amount=None):
    MockTransaction.objects.filter(authority=payment.authority).update(paid=True, **({"amount": amount} if amount else {}))


@pytest.mark.django_db
def test_start_payment_creates_pending_payment(order):
    url, payment = _start(order)
    assert payment.status == Payment.Status.PENDING
    assert payment.amount == order.total
    assert url == reverse("payments:mock_gateway", args=[payment.authority])


@pytest.mark.django_db
def test_successful_verify_marks_order_paid(order):
    _, payment = _start(order)
    _bank_pays(payment)
    payment = services.verify_payment(payment.pk)
    order.refresh_from_db()
    assert payment.status == Payment.Status.SUCCEEDED and payment.ref_id
    assert order.status == Order.Status.DELIVERED


@pytest.mark.django_db
def test_duplicate_callback_has_one_effect(client, order):
    """Spec test: a repeated gateway return has a single effect."""
    _, payment = _start(order)
    _bank_pays(payment)
    url = reverse("payments:callback", args=["mock"])
    for _ in range(3):
        assert client.get(url, {"Authority": payment.authority, "Status": "OK"}).status_code == 302

    assert Payment.objects.filter(status=Payment.Status.SUCCEEDED).count() == 1
    assert OrderEvent.objects.filter(order=order, event="paid").count() == 1
    assert InventoryItem.objects.filter(status=InventoryItem.Status.SOLD).count() == 1


@pytest.mark.django_db
def test_callback_status_param_cannot_fake_success(client, order):
    _, payment = _start(order)  # bank never confirms
    client.get(reverse("payments:callback", args=["mock"]), {"Authority": payment.authority, "Status": "OK"})
    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == Payment.Status.FAILED
    assert order.status == Order.Status.PENDING_PAYMENT


@pytest.mark.django_db
def test_amount_mismatch_from_gateway_is_rejected(order):
    _, payment = _start(order)
    _bank_pays(payment, amount=1000)
    payment = services.verify_payment(payment.pk)
    order.refresh_from_db()
    assert payment.status == Payment.Status.FAILED
    assert order.paid_at is None


@pytest.mark.django_db
def test_failed_payment_allows_retry(order):
    _, first = _start(order)
    services.verify_payment(first.pk)  # not paid -> failed
    order.refresh_from_db()
    assert order.is_payable

    services.start_payment(order, lambda g: "http://testserver/cb/")
    second = Payment.objects.filter(order=order).exclude(pk=first.pk).get()
    _bank_pays(second)
    services.verify_payment(second.pk)
    order.refresh_from_db()
    assert order.status == Order.Status.DELIVERED


@pytest.mark.django_db
def test_inquiry_recovers_payment_without_callback(order):
    _, payment = _start(order)
    _bank_pays(payment)
    Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(minutes=5))

    assert services.inquire_pending() == 1
    order.refresh_from_db()
    assert order.status == Order.Status.DELIVERED
    assert services.inquire_pending() == 0  # nothing left to recover


@pytest.mark.django_db
def test_expired_order_cannot_start_payment(order):
    Order.objects.filter(pk=order.pk).update(reserved_until=timezone.now() - timedelta(seconds=1))
    order.refresh_from_db()
    with pytest.raises(services.PaymentError):
        services.start_payment(order, lambda g: "/cb/")
    order.refresh_from_db()
    assert order.status == Order.Status.EXPIRED


@pytest.mark.django_db
def test_unknown_authority_is_404(client, db):
    assert client.get(reverse("payments:callback", args=["mock"]), {"Authority": "nope"}).status_code == 404


@pytest.mark.django_db
def test_authority_is_unique(order):
    from django.db import IntegrityError

    _, payment = _start(order)
    with pytest.raises(IntegrityError):
        Payment.objects.create(order=order, gateway="mock", amount=1, authority=payment.authority)
