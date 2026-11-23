from decimal import Decimal

from apps.core.templatetags.persian import discount_percent, fa, price


def test_fa_converts_digits():
    assert fa("30 روز") == "۳۰ روز"
    assert fa(None) == ""


def test_price_uses_persian_digits_and_separator():
    assert price(2300000) == "۲٬۳۰۰٬۰۰۰"
    assert price(Decimal("1000")) == "۱٬۰۰۰"
    assert price(0) == "۰"
    assert price(None) == ""


def test_discount_percent():
    assert discount_percent(850000, 1000000) == "۱۵"
    assert discount_percent(1000000, 1000000) == ""
    assert discount_percent(1000000, None) == ""
