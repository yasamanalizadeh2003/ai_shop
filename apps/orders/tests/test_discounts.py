from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.orders import discounts, services
from apps.orders.models import DiscountCode

from .conftest import make_cart, make_customer


def code(**kwargs):
    defaults = {"code": "save10", "kind": "percent", "value": Decimal("10")}
    defaults.update(kwargs)
    return DiscountCode.objects.create(**defaults)


@pytest.mark.django_db
def test_percent_with_cap():
    code(max_discount=Decimal("50000"))
    _, amount = discounts.evaluate("SAVE10", Decimal("1000000"))
    assert amount == Decimal("50000")


@pytest.mark.django_db
def test_code_is_case_insensitive_and_trimmed():
    code()
    _, amount = discounts.evaluate("  save10 ", Decimal("200000"))
    assert amount == Decimal("20000")


@pytest.mark.django_db
def test_fixed_amount_never_exceeds_subtotal():
    code(code="BIG", kind="amount", value=Decimal("5000000"))
    _, amount = discounts.evaluate("big", Decimal("1000000"))
    assert amount == Decimal("1000000")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"is_active": False}, "معتبر نیست"),
        ({"ends_at": timezone.now() - timedelta(days=1)}, "تمام شده"),
        ({"starts_at": timezone.now() + timedelta(days=1)}, "نرسیده"),
        ({"min_order_amount": Decimal("5000000")}, "کافی نیست"),
    ],
)
def test_invalid_codes(kwargs, message):
    code(**kwargs)
    with pytest.raises(discounts.DiscountError) as exc:
        discounts.evaluate("save10", Decimal("1000000"))
    assert message in exc.value.message


@pytest.mark.django_db
def test_unknown_code():
    with pytest.raises(discounts.DiscountError):
        discounts.evaluate("nope", Decimal("1"))


@pytest.mark.django_db
def test_discount_applied_to_order_and_usage_limits(stock_variant):
    code(max_uses=1, max_uses_per_customer=1)
    customer = make_customer()
    order = services.create_order(customer, make_cart(customer, (stock_variant, 1)), discount_code="save10")
    assert order.discount_amount == Decimal("100000")
    assert order.total == Decimal("900000")

    other = make_customer()
    with pytest.raises(services.OrderError) as exc:
        services.create_order(other, make_cart(other, (stock_variant, 1)), discount_code="save10")
    assert "ظرفیت" in exc.value.field_errors["discount_code"]


@pytest.mark.django_db
def test_expired_order_frees_the_discount_use(stock_variant):
    code(max_uses=1)
    customer = make_customer()
    order = services.create_order(customer, make_cart(customer, (stock_variant, 1)), discount_code="save10")
    services.expire_order(order.pk)

    other = make_customer()
    assert services.create_order(other, make_cart(other, (stock_variant, 1)), discount_code="save10").discount_amount > 0


@pytest.mark.django_db
def test_free_order_after_full_discount(stock_variant, django_capture_on_commit_callbacks):
    from apps.payments.services import start_payment

    code(code="FREE", kind="percent", value=Decimal("100"))
    customer = make_customer()
    order = services.create_order(customer, make_cart(customer, (stock_variant, 1)), discount_code="free")
    assert order.total == 0
    with django_capture_on_commit_callbacks(execute=True):
        url = start_payment(order, lambda g: "/cb/")
    order.refresh_from_db()
    assert url == order.get_absolute_url()
    assert order.status == "delivered"
