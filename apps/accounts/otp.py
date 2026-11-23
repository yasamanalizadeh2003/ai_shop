"""
SMS login codes: issuing (with rate limits) and verification.
Validation happens only here; the site and bot just show the result.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifications import sms

from .models import Customer, LoginCode
from .phone import InvalidMobile, normalize_mobile


class OtpError(Exception):
    def __init__(self, code, message, retry_after=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after


@dataclass(frozen=True)
class IssuedCode:
    mobile: str
    expires_at: object
    resend_after: int


def _hash(mobile, code):
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"{mobile}:{code}".encode(), hashlib.sha256).hexdigest()


def _generate_code():
    length = settings.OTP_CODE_LENGTH
    return f"{secrets.randbelow(10**length):0{length}d}"


def request_code(raw_mobile, ip_address=None):
    try:
        mobile = normalize_mobile(raw_mobile)
    except InvalidMobile:
        raise OtpError("invalid_mobile", "شماره موبایل معتبر نیست. نمونه درست: ۰۹۱۲۳۴۵۶۷۸۹")

    now = timezone.now()
    hour_ago = now - timedelta(hours=1)

    last = LoginCode.objects.filter(mobile=mobile).order_by("-created_at").first()
    if last:
        wait = settings.OTP_RESEND_COOLDOWN - int((now - last.created_at).total_seconds())
        if wait > 0:
            raise OtpError("cooldown", "کد قبلی هنوز معتبر است. کمی صبر کنید و دوباره درخواست دهید.", retry_after=wait)

    if LoginCode.objects.filter(mobile=mobile, created_at__gte=hour_ago).count() >= settings.OTP_MAX_PER_MOBILE_PER_HOUR:
        raise OtpError("mobile_limit", "تعداد درخواست کد برای این شماره زیاد بوده است. یک ساعت دیگر تلاش کنید.")

    if ip_address and (
        LoginCode.objects.filter(ip_address=ip_address, created_at__gte=hour_ago).count()
        >= settings.OTP_MAX_PER_IP_PER_HOUR
    ):
        raise OtpError("ip_limit", "تعداد درخواست‌ها زیاد بوده است. کمی بعد دوباره تلاش کنید.")

    code = _generate_code()
    record = LoginCode.objects.create(
        mobile=mobile,
        code_hash=_hash(mobile, code),
        ip_address=ip_address,
        expires_at=now + timedelta(seconds=settings.OTP_TTL_SECONDS),
    )
    try:
        sms.get_backend().send_otp(mobile, code)
    except sms.SmsError:
        record.delete()
        raise OtpError("sms_failed", "ارسال پیامک با خطا روبه‌رو شد. چند لحظه بعد دوباره تلاش کنید.")

    return IssuedCode(mobile=mobile, expires_at=record.expires_at, resend_after=settings.OTP_RESEND_COOLDOWN)


def verify_code(raw_mobile, code):
    """Check the latest code for this mobile and return the (possibly new) web customer."""
    try:
        mobile = normalize_mobile(raw_mobile)
    except InvalidMobile:
        raise OtpError("invalid_mobile", "شماره موبایل معتبر نیست.")

    code = str(code or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    now = timezone.now()

    # Errors are raised only after the transaction commits, so a wrong
    # attempt is always persisted (raising inside would roll it back).
    error = None
    with transaction.atomic():
        record = (
            LoginCode.objects.select_for_update()
            .filter(mobile=mobile, used_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if record is None or record.expires_at <= now:
            error = OtpError("expired", "کد منقضی شده است. کد جدید دریافت کنید.")
        elif record.attempts >= settings.OTP_MAX_ATTEMPTS:
            error = OtpError("too_many_attempts", "تعداد تلاش‌ها بیش از حد مجاز است. کد جدید دریافت کنید.")
        elif not hmac.compare_digest(record.code_hash, _hash(mobile, code)):
            record.attempts += 1
            record.save(update_fields=["attempts"])
            left = settings.OTP_MAX_ATTEMPTS - record.attempts
            if left <= 0:
                error = OtpError("too_many_attempts", "تعداد تلاش‌ها بیش از حد مجاز است. کد جدید دریافت کنید.")
            else:
                error = OtpError("wrong_code", f"کد وارد شده اشتباه است. {left} تلاش دیگر باقی مانده.")
        else:
            record.used_at = now
            record.save(update_fields=["used_at"])
    if error:
        raise error

    customer = _get_or_create_web_customer(mobile)
    if not customer.is_active:
        raise OtpError("inactive", "این حساب غیرفعال شده است. با پشتیبانی تماس بگیرید.")
    customer.last_login_at = now
    customer.save(update_fields=["last_login_at"])
    return customer


def _get_or_create_web_customer(mobile):
    try:
        customer, _ = Customer.objects.get_or_create(
            mobile=mobile, defaults={"signup_channel": Customer.Channel.WEB}
        )
    except IntegrityError:
        customer = Customer.objects.get(mobile=mobile)
    return customer
