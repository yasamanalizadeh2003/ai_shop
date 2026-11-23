from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_THOUSANDS_SEPARATOR = "٬"


def to_persian_digits(value):
    return str(value).translate(_FA_DIGITS)


@register.filter
def fa(value):
    """Convert latin digits in any value to Persian digits."""
    if value is None:
        return ""
    return to_persian_digits(value)


@register.filter
def price(value):
    """Format an integer amount with Persian digits and thousand separators: 2300000 -> ۲٬۳۰۰٬۰۰۰"""
    if value is None or value == "":
        return ""
    try:
        amount = Decimal(str(value)).quantize(Decimal("1"))
    except (InvalidOperation, ValueError):
        return to_persian_digits(value)
    formatted = f"{int(amount):,}".replace(",", _THOUSANDS_SEPARATOR)
    return to_persian_digits(formatted)


@register.simple_tag
def discount_percent(price_value, compare_at):
    """Percent off between the current price and the price before discount, as Persian digits."""
    try:
        current = Decimal(str(price_value))
        before = Decimal(str(compare_at))
    except (InvalidOperation, ValueError, TypeError):
        return ""
    if not before or before <= current:
        return ""
    percent = int(((before - current) * 100 / before).to_integral_value(rounding="ROUND_FLOOR"))
    return to_persian_digits(percent)
