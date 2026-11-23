from decimal import Decimal

import pytest

from apps.catalog.models import Variant
from apps.catalog.pricing import reprice_usd_variants, round_up_to_thousand, usd_to_toman
from apps.core.models import ExchangeRate

from .factories import make_variant


def test_spec_example():
    # 20 USD × 100,000 × 1.15 = 2,300,000
    assert usd_to_toman(Decimal("20"), Decimal("15"), Decimal("100000")) == Decimal("2300000")


@pytest.mark.parametrize(
    "amount, expected",
    [("2300000", "2300000"), ("2300001", "2301000"), ("2300999.99", "2301000"), ("1", "1000"), ("0", "0")],
)
def test_round_up_to_thousand(amount, expected):
    assert round_up_to_thousand(Decimal(amount)) == Decimal(expected)


def test_fractional_usd_rounds_up():
    # 19.99 × 100,000 × 1.1 = 2,198,900 -> 2,199,000
    assert usd_to_toman(Decimal("19.99"), Decimal("10"), Decimal("100000")) == Decimal("2199000")


def test_no_float_anywhere():
    result = usd_to_toman(Decimal("0.1"), Decimal("0"), Decimal("30000"))
    assert isinstance(result, Decimal) and result == Decimal("3000")


@pytest.mark.django_db
def test_fixed_variant_price_is_the_fixed_price():
    v = make_variant(price=1_890_000)
    assert v.price == Decimal("1890000")


@pytest.mark.django_db
def test_usd_variant_is_priced_from_current_rate():
    ExchangeRate.objects.create(toman_per_usd=Decimal("100000"))
    v = make_variant(pricing_mode=Variant.PricingMode.USD, fixed_price=None, usd_price=Decimal("20"), margin_percent=Decimal("15"))
    assert v.price == Decimal("2300000")


@pytest.mark.django_db
def test_rate_change_reprices_usd_but_not_fixed_variants():
    ExchangeRate.objects.create(toman_per_usd=Decimal("100000"))
    usd = make_variant(pricing_mode=Variant.PricingMode.USD, fixed_price=None, usd_price=Decimal("20"), margin_percent=Decimal("15"))
    fixed = make_variant(product=usd.product, price=999_000, name="ثابت")

    new_rate = ExchangeRate.objects.create(toman_per_usd=Decimal("110000"))
    assert reprice_usd_variants(new_rate) == 1

    usd.refresh_from_db()
    fixed.refresh_from_db()
    assert usd.price == Decimal("2530000")  # 20 × 110,000 × 1.15
    assert fixed.price == Decimal("999000")


@pytest.mark.django_db
def test_usd_variant_without_rate_keeps_zero_price():
    v = make_variant(pricing_mode=Variant.PricingMode.USD, fixed_price=None, usd_price=Decimal("20"))
    assert v.price == Decimal("0")


@pytest.mark.django_db
def test_pricing_constraint_requires_matching_amount():
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        make_variant(pricing_mode=Variant.PricingMode.USD, fixed_price=Decimal("1"), usd_price=None)


@pytest.mark.django_db
def test_variant_clean_messages():
    from django.core.exceptions import ValidationError

    v = Variant(pricing_mode=Variant.PricingMode.FIXED, fixed_price=None, delivery_type=Variant.DeliveryType.MANUAL, delivery_deadline_hours=0)
    with pytest.raises(ValidationError) as exc:
        v.clean()
    assert "fixed_price" in exc.value.message_dict
    assert "delivery_deadline_hours" in exc.value.message_dict
