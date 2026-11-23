"""
Payment flow. The order's paid status is decided ONLY from the gateway's
verify response (success + exact amount), never from callback parameters.
Each gateway transaction id is unique, so repeated callbacks have one effect.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.models import SiteSettings
from apps.orders import services as order_services
from apps.orders.models import Order

from .gateways import GatewayError, get_gateway
from .models import Payment

logger = logging.getLogger(__name__)


class PaymentError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def start_payment(order: Order, callback_url_builder) -> str:
    """Create a gateway transaction for a pending order and return the URL to redirect to."""
    if not order.is_payable:
        raise PaymentError("این سفارش قابل پرداخت نیست.")
    if order.reserved_until <= timezone.now():
        order_services.expire_order(order.pk)
        raise PaymentError("مهلت پرداخت این سفارش تمام شده است. دوباره از سبد خرید اقدام کنید.")

    if order.total == 0:
        order_services.apply_payment(order.pk, amount=0, payment_ref="free")
        return order.get_absolute_url()

    gateway_name = SiteSettings.get().active_gateway
    gateway = get_gateway(gateway_name)
    payment = Payment.objects.create(order=order, gateway=gateway_name, amount=order.total)
    try:
        result = gateway.create(
            amount=order.total,
            callback_url=callback_url_builder(gateway_name),
            description=f"سفارش {order.number}",
            mobile=order.customer.mobile or "",
        )
    except GatewayError:
        logger.exception("Gateway create failed for order %s", order.pk)
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status"])
        raise PaymentError("اتصال به درگاه پرداخت برقرار نشد. چند لحظه بعد دوباره تلاش کنید.")

    payment.authority = result.authority
    payment.status = Payment.Status.PENDING
    payment.save(update_fields=["authority", "status"])
    return result.redirect_url


def verify_payment(payment_id: int) -> Payment:
    """
    Ask the gateway for the final result and apply it. Safe to call any number
    of times, from the callback or the scheduled inquiry, even concurrently.
    """
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.status in (Payment.Status.SUCCEEDED, Payment.Status.FAILED):
            return payment

        gateway = get_gateway(payment.gateway)
        result = gateway.verify(authority=payment.authority, amount=payment.amount)
        payment.verify_response = result.raw

        if not result.success:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "verify_response"])
            return payment

        if result.amount is None or result.amount != payment.amount:
            logger.error("Amount mismatch for payment %s: expected %s got %s", payment.pk, payment.amount, result.amount)
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "verify_response"])
            return payment

        payment.status = Payment.Status.SUCCEEDED
        payment.ref_id = result.ref_id
        payment.card_pan = result.card_pan
        payment.verified_at = timezone.now()
        payment.save(update_fields=["status", "ref_id", "card_pan", "verified_at", "verify_response"])
        order_services.apply_payment(payment.order_id, amount=result.amount, payment_ref=result.ref_id)
    return payment


def handle_callback(gateway_name: str, authority: str):
    """Callback parameters are used only to find the payment; the outcome comes from verify."""
    payment = Payment.objects.filter(gateway=gateway_name, authority=authority).first()
    if payment is None:
        return None
    return verify_payment(payment.pk)


def inquire_pending(min_age_minutes=2, max_age_hours=24):
    """Scheduled job: recover payments whose callback never arrived."""
    now = timezone.now()
    pending = Payment.objects.filter(
        status=Payment.Status.PENDING,
        authority__isnull=False,
        created_at__lte=now - timedelta(minutes=min_age_minutes),
        created_at__gte=now - timedelta(hours=max_age_hours),
    ).values_list("pk", flat=True)
    recovered = 0
    for pk in list(pending):
        try:
            if verify_payment(pk).status == Payment.Status.SUCCEEDED:
                recovered += 1
        except Exception:
            logger.exception("Inquiry failed for payment %s", pk)
    return recovered
