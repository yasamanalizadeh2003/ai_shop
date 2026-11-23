from decimal import ROUND_CEILING, Decimal

from django.db import transaction

from apps.core.models import ExchangeRate

ROUND_TO = Decimal("1000")


class PricingError(Exception):
    pass


def round_up_to_thousand(amount: Decimal) -> Decimal:
    return (amount / ROUND_TO).to_integral_value(rounding=ROUND_CEILING) * ROUND_TO


def usd_to_toman(usd_price: Decimal, margin_percent: Decimal, toman_per_usd: Decimal) -> Decimal:
    """20 USD × 100,000 × 1.15 = 2,300,000 — always rounded UP to the next 1,000 Toman."""
    raw = Decimal(usd_price) * Decimal(toman_per_usd) * (Decimal("1") + Decimal(margin_percent) / Decimal("100"))
    return round_up_to_thousand(raw)


def compute_price(variant, rate: ExchangeRate | None = None) -> Decimal:
    if variant.pricing_mode == variant.PricingMode.FIXED:
        if variant.fixed_price is None:
            raise PricingError("Fixed price is missing.")
        return Decimal(variant.fixed_price)

    if variant.usd_price is None:
        raise PricingError("USD price is missing.")
    rate = rate or ExchangeRate.current()
    if rate is None:
        raise PricingError("No exchange rate has been set.")
    return usd_to_toman(variant.usd_price, variant.margin_percent, rate.toman_per_usd)


def reprice_usd_variants(rate: ExchangeRate | None = None) -> int:
    """Recalculate every USD-priced variant. Prices already copied into orders are not touched."""
    from .models import Variant

    rate = rate or ExchangeRate.current()
    if rate is None:
        return 0
    count = 0
    with transaction.atomic():
        for variant in Variant.objects.select_for_update().filter(pricing_mode=Variant.PricingMode.USD):
            new_price = compute_price(variant, rate)
            if new_price != variant.price:
                variant.price = new_price
                variant.save(update_fields=["price", "updated_at"])
            count += 1
    return count
