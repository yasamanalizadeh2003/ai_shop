from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog import inventory
from apps.catalog.models import InventoryItem
from apps.catalog.tests.factories import make_product, make_variant
from apps.notifications.team import MemoryTeamBackend
from apps.orders import services
from apps.orders.models import Order, OrderEvent, OrderItem

from .conftest import make_cart, make_customer


@pytest.mark.django_db
def test_create_order_copies_prices_and_reserves(stock_variant):
    customer = make_customer()
    cart = make_cart(customer, (stock_variant, 2))
    order = services.create_order(customer, cart)

    assert order.status == Order.Status.PENDING_PAYMENT
    assert order.total == Decimal("2000000")
    assert order.items.count() == 2
    assert all(i.unit_price == Decimal("1000000") for i in order.items.all())
    assert InventoryItem.objects.filter(status=InventoryItem.Status.RESERVED).count() == 2
    assert order.reserved_until > timezone.now() + timedelta(minutes=14)
    assert order.items.first().seller_id == stock_variant.seller_id


@pytest.mark.django_db
def test_order_price_is_frozen(stock_variant):
    customer = make_customer()
    order = services.create_order(customer, make_cart(customer, (stock_variant, 1)))
    stock_variant.fixed_price = Decimal("5000000")
    stock_variant.save()
    order.refresh_from_db()
    assert order.total == Decimal("1000000")
    assert order.items.get().unit_price == Decimal("1000000")


@pytest.mark.django_db
def test_two_line_cart_with_one_out_of_stock_creates_nothing(stock_variant):
    """Spec test: no order is created and no reservation remains."""
    empty = make_variant(make_product(slug="empty", title="Empty"), price=100_000)
    customer = make_customer()
    cart = make_cart(customer, (stock_variant, 1), (empty, 1))

    with pytest.raises(services.OutOfStock) as exc:
        services.create_order(customer, cart)

    assert exc.value.problem_variant_ids == [empty.pk]
    assert Order.objects.count() == 0
    assert OrderItem.objects.count() == 0
    assert InventoryItem.objects.filter(status=InventoryItem.Status.RESERVED).count() == 0
    assert cart.items.count() == 2  # cart left untouched


@pytest.mark.django_db
def test_quantity_larger_than_stock_fails(stock_variant):
    customer = make_customer()
    with pytest.raises(services.OutOfStock):
        services.create_order(customer, make_cart(customer, (stock_variant, 11)))
    assert InventoryItem.objects.filter(status=InventoryItem.Status.RESERVED).count() == 0


@pytest.mark.django_db
def test_private_item_requires_valid_gmail(manual_variant):
    customer = make_customer()
    cart = make_cart(customer, (manual_variant, 1))
    item_id = cart.items.get().pk

    for value, message in [("", "الزامی"), ("not-an-email", "معتبر نیست"), ("ali@company.com", "gmail")]:
        with pytest.raises(services.OrderError) as exc:
            services.create_order(customer, cart, account_identifiers={item_id: value})
        assert message in exc.value.field_errors[item_id]
    assert Order.objects.count() == 0

    order = services.create_order(customer, cart, account_identifiers={item_id: " Ali.Rezaei@Gmail.com "})
    assert order.items.get().account_identifier == "ali.rezaei@gmail.com"
    customer.refresh_from_db()
    assert customer.last_email == "ali.rezaei@gmail.com"


@pytest.mark.django_db
def test_empty_cart_and_inactive_variant(stock_variant):
    customer = make_customer()
    with pytest.raises(services.OrderError):
        services.create_order(customer, make_cart(customer))

    stock_variant.status = "inactive"
    stock_variant.save()
    other = make_customer()
    with pytest.raises(services.OrderError) as exc:
        services.create_order(other, make_cart(other, (stock_variant, 1)))
    assert exc.value.problem_variant_ids == [stock_variant.pk]


@pytest.mark.django_db
def test_expiry_releases_reservation_and_keeps_cart(stock_variant):
    customer = make_customer()
    cart = make_cart(customer, (stock_variant, 3))
    order = services.create_order(customer, cart)
    Order.objects.filter(pk=order.pk).update(reserved_until=timezone.now() - timedelta(seconds=1))

    assert services.expire_due_orders() == 1
    order.refresh_from_db()
    assert order.status == Order.Status.EXPIRED
    assert InventoryItem.objects.filter(status=InventoryItem.Status.AVAILABLE).count() == 10
    assert cart.items.count() == 1
    assert not order.items.filter(inventory_item__isnull=False).exists()
    # Running again does nothing.
    assert services.expire_due_orders() == 0


@pytest.mark.django_db
def test_apply_payment_delivers_stock_items(stock_variant, django_capture_on_commit_callbacks):
    customer = make_customer()
    cart = make_cart(customer, (stock_variant, 1))
    order = services.create_order(customer, cart)
    with django_capture_on_commit_callbacks(execute=True):
        services.apply_payment(order.pk, amount=order.total)

    order.refresh_from_db()
    item = order.items.get()
    assert order.status == Order.Status.DELIVERED and order.paid_at
    assert item.status == OrderItem.Status.DELIVERED and item.delivered_at
    assert item.inventory_item.status == InventoryItem.Status.SOLD
    assert cart.items.count() == 0  # cart is cleared only after payment


@pytest.mark.django_db
def test_manual_items_go_to_processing_and_alert_team(manual_variant, django_capture_on_commit_callbacks):
    customer = make_customer()
    cart = make_cart(customer, (manual_variant, 1, "a@gmail.com"))
    order = services.create_order(customer, cart, account_identifiers={cart.items.get().pk: "a@gmail.com"})
    with django_capture_on_commit_callbacks(execute=True):
        services.apply_payment(order.pk, amount=order.total)
    order.refresh_from_db()
    assert order.status == Order.Status.PROCESSING
    assert order.items.get().status == OrderItem.Status.AWAITING_DELIVERY
    assert any(m["kind"] == "manual_order" for m in MemoryTeamBackend.outbox)


@pytest.mark.django_db
def test_apply_payment_twice_has_one_effect(stock_variant):
    customer = make_customer()
    order = services.create_order(customer, make_cart(customer, (stock_variant, 1)))
    services.apply_payment(order.pk, amount=order.total)
    events = OrderEvent.objects.filter(order=order).count()
    services.apply_payment(order.pk, amount=order.total)
    assert OrderEvent.objects.filter(order=order).count() == events
    assert InventoryItem.objects.filter(status=InventoryItem.Status.SOLD).count() == 1


@pytest.mark.django_db
def test_apply_payment_rejects_wrong_amount(stock_variant):
    customer = make_customer()
    order = services.create_order(customer, make_cart(customer, (stock_variant, 1)))
    with pytest.raises(services.OrderError):
        services.apply_payment(order.pk, amount=order.total - 1)
    order.refresh_from_db()
    assert order.paid_at is None


@pytest.mark.django_db
def test_payment_after_expiry_without_stock_goes_to_refund_queue(stock_variant, django_capture_on_commit_callbacks):
    """Spec test: money after the reservation expired and no stock -> refund queue + SMS."""
    from apps.notifications.models import Message
    from apps.support.models import Refund

    customer = make_customer()
    late = services.create_order(customer, make_cart(customer, (stock_variant, 1)))
    services.expire_order(late.pk)
    # Someone else buys the whole stock meanwhile.
    other = make_customer()
    services.create_order(other, make_cart(other, (stock_variant, 10)))

    with django_capture_on_commit_callbacks(execute=True):
        services.apply_payment(late.pk, amount=late.total)
    late.refresh_from_db()
    assert late.needs_refund is True
    assert late.paid_at is not None
    assert not late.items.filter(inventory_item__isnull=False).exists()
    assert any(m["kind"] == "refund_required" for m in MemoryTeamBackend.outbox)

    refund = Refund.objects.get(order=late)  # in the finance manager's queue
    assert refund.amount == late.total and refund.reason == Refund.Reason.LATE_PAYMENT
    assert refund.status == Refund.Status.AWAITING_CARD
    assert Message.objects.filter(customer=customer, event="refund_required", channel="sms").exists()


@pytest.mark.django_db
def test_payment_after_expiry_with_stock_rereserves_and_delivers(stock_variant):
    customer = make_customer()
    order = services.create_order(customer, make_cart(customer, (stock_variant, 1)))
    services.expire_order(order.pk)
    services.apply_payment(order.pk, amount=order.total)
    order.refresh_from_db()
    assert order.needs_refund is False
    assert order.status == Order.Status.DELIVERED
    assert order.items.get().inventory_item.status == InventoryItem.Status.SOLD


@pytest.mark.django_db
def test_order_events_are_append_only(stock_variant):
    customer = make_customer()
    order = services.create_order(customer, make_cart(customer, (stock_variant, 1)))
    event = order.events.first()
    assert event.event == "created"
    event.note = "changed"
    with pytest.raises(ValueError):
        event.save()
    with pytest.raises(ValueError):
        event.delete()


@pytest.mark.django_db
def test_reservation_minutes_come_from_settings(stock_variant):
    from apps.core.models import SiteSettings

    s = SiteSettings.get()
    s.reservation_minutes = 30
    s.save()
    customer = make_customer()
    order = services.create_order(customer, make_cart(customer, (stock_variant, 1)))
    assert order.reserved_until > timezone.now() + timedelta(minutes=29)
