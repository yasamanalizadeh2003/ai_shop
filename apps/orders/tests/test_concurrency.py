"""
Mandatory spec tests: concurrent purchases never sell an inventory item twice.
These run real threads against PostgreSQL (row locks are what is being tested).
"""

import threading

import pytest
from django.db import connection, connections

from apps.catalog import inventory
from apps.catalog.models import InventoryItem
from apps.catalog.tests.factories import make_product, make_variant
from apps.orders import services
from apps.orders.models import Order, OrderItem

from .conftest import make_cart, make_customer

pytestmark = pytest.mark.skipif(connection.vendor != "postgresql", reason="needs PostgreSQL row locking")


def _run_concurrently(carts):
    barrier = threading.Barrier(len(carts))
    results = []
    lock = threading.Lock()

    def worker(customer, cart, channel):
        try:
            barrier.wait()
            order = services.create_order(customer, cart, channel=channel)
            outcome = ("ok", order.pk)
        except services.OutOfStock:
            outcome = ("out_of_stock", None)
        except Exception as exc:  # pragma: no cover - surfaced in the assertion message
            outcome = ("error", repr(exc))
        finally:
            connections.close_all()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, args=args) for args in carts]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def _assert_no_double_sale(variant, expected_orders):
    reserved_ids = list(OrderItem.objects.filter(variant=variant, inventory_item__isnull=False).values_list("inventory_item_id", flat=True))
    assert len(reserved_ids) == expected_orders
    assert len(set(reserved_ids)) == len(reserved_ids), "an inventory item was assigned to two orders"
    assert InventoryItem.objects.filter(variant=variant, status=InventoryItem.Status.RESERVED).count() == expected_orders
    assert InventoryItem.objects.filter(variant=variant, status=InventoryItem.Status.AVAILABLE).count() == 0


@pytest.mark.django_db(transaction=True)
def test_50_concurrent_purchases_on_10_items():
    variant = make_variant(make_product(slug="c50", title="C50"), price=1_000_000, low_stock_threshold=0)
    inventory.import_items(variant, [f"item{i}|pw" for i in range(10)])

    carts = []
    for _ in range(50):
        customer = make_customer()
        carts.append((customer, make_cart(customer, (variant, 1)), Order.Channel.WEB))

    results = _run_concurrently(carts)

    errors = [r for r in results if r[0] == "error"]
    assert not errors, errors
    assert sum(1 for r in results if r[0] == "ok") == 10
    assert sum(1 for r in results if r[0] == "out_of_stock") == 40
    assert Order.objects.count() == 10
    _assert_no_double_sale(variant, 10)


@pytest.mark.django_db(transaction=True)
def test_5_web_and_5_telegram_concurrent_purchases_on_6_items():
    variant = make_variant(make_product(slug="c6", title="C6"), price=1_000_000, low_stock_threshold=0)
    inventory.import_items(variant, [f"item{i}|pw" for i in range(6)])

    carts = []
    for channel in ["web"] * 5 + ["telegram"] * 5:
        customer = make_customer(channel)
        carts.append((customer, make_cart(customer, (variant, 1)), channel))

    results = _run_concurrently(carts)

    assert not [r for r in results if r[0] == "error"]
    assert sum(1 for r in results if r[0] == "ok") == 6
    _assert_no_double_sale(variant, 6)
