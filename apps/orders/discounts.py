from decimal import ROUND_FLOOR, Decimal

from django.utils import timezone

from .models import DiscountCode, DiscountRedemption, Order

COUNTED_STATUSES = [
    Order.Status.PENDING_PAYMENT,
    Order.Status.PAID,
    Order.Status.PROCESSING,
    Order.Status.DELIVERED,
]


class DiscountError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def normalize(code):
    return (code or "").strip().upper()


def evaluate(code, subtotal: Decimal, customer=None, *, lock=False):
    """Return (DiscountCode, amount) or raise DiscountError. Lock the row when creating an order."""
    code = normalize(code)
    qs = DiscountCode.objects.select_for_update() if lock else DiscountCode.objects
    discount = qs.filter(code=code).first()
    now = timezone.now()
    if discount is None or not discount.is_active:
        raise DiscountError("کد تخفیف معتبر نیست.")
    if discount.starts_at and now < discount.starts_at:
        raise DiscountError("زمان استفاده از این کد تخفیف هنوز نرسیده است.")
    if discount.ends_at and now > discount.ends_at:
        raise DiscountError("مهلت استفاده از این کد تخفیف تمام شده است.")
    if subtotal < discount.min_order_amount:
        raise DiscountError("مبلغ سبد برای این کد تخفیف کافی نیست.")

    used = DiscountRedemption.objects.filter(discount=discount, order__status__in=COUNTED_STATUSES)
    if discount.max_uses is not None and used.count() >= discount.max_uses:
        raise DiscountError("ظرفیت استفاده از این کد تخفیف تمام شده است.")
    if customer is not None and used.filter(customer=customer).count() >= discount.max_uses_per_customer:
        raise DiscountError("شما قبلاً از این کد تخفیف استفاده کرده‌اید.")

    if discount.kind == DiscountCode.Kind.PERCENT:
        amount = (subtotal * min(discount.value, Decimal("100")) / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_FLOOR)
    else:
        amount = discount.value
    if discount.max_discount is not None:
        amount = min(amount, discount.max_discount)
    return discount, min(amount, subtotal)
