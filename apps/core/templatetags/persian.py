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


@register.filter
def jdate(value, fmt="date"):
    """
    Shamsi date in Tehran time with Persian digits.
      date     -> ۱۴۰۵/۰۹/۰۳
      datetime -> ۱۴۰۵/۰۹/۰۳ ۱۴:۳۰
      long     -> ۳ آذر ۱۴۰۵
    """
    from datetime import datetime

    from django.utils import timezone

    from apps.core.jalali import MONTHS, to_jalali

    if not value:
        return ""
    if isinstance(value, datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    y, m, d = to_jalali(value)
    if fmt == "long":
        text = f"{d} {MONTHS[m - 1]} {y}"
    else:
        text = f"{y}/{m:02d}/{d:02d}"
        if fmt == "datetime" and isinstance(value, datetime):
            text += f" {value.hour:02d}:{value.minute:02d}"
    return to_persian_digits(text)


@register.filter
def days_left(value):
    """Whole days remaining until a datetime (0 if past)."""
    from django.utils import timezone

    if not value:
        return 0
    return max(0, (value - timezone.now()).days)


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
