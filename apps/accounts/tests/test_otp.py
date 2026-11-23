from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts import otp
from apps.accounts.models import Customer, LoginCode

MOBILE = "09123456789"


def _last_code(outbox):
    return outbox[-1]["code"]


@pytest.mark.django_db
def test_request_code_sends_sms_and_stores_only_a_hash(sms_outbox):
    issued = otp.request_code("۰۹۱۲۳۴۵۶۷۸۹", ip_address="1.2.3.4")

    assert issued.mobile == MOBILE
    assert len(sms_outbox) == 1
    code = _last_code(sms_outbox)
    assert len(code) == 5 and code.isdigit()
    record = LoginCode.objects.get()
    assert code not in record.code_hash


@pytest.mark.django_db
def test_invalid_mobile_is_rejected(sms_outbox):
    with pytest.raises(otp.OtpError) as exc:
        otp.request_code("12345")
    assert exc.value.code == "invalid_mobile"
    assert sms_outbox == []


@pytest.mark.django_db
def test_resend_cooldown(sms_outbox):
    otp.request_code(MOBILE)
    with pytest.raises(otp.OtpError) as exc:
        otp.request_code(MOBILE)
    assert exc.value.code == "cooldown"
    assert exc.value.retry_after > 0
    assert len(sms_outbox) == 1


@pytest.mark.django_db
def test_hourly_limit_per_mobile(settings, sms_outbox):
    settings.OTP_RESEND_COOLDOWN = 0
    settings.OTP_MAX_PER_MOBILE_PER_HOUR = 3
    for _ in range(3):
        otp.request_code(MOBILE)
    with pytest.raises(otp.OtpError) as exc:
        otp.request_code(MOBILE)
    assert exc.value.code == "mobile_limit"
    assert len(sms_outbox) == 3


@pytest.mark.django_db
def test_hourly_limit_per_ip(settings, sms_outbox):
    settings.OTP_MAX_PER_IP_PER_HOUR = 2
    otp.request_code("09120000001", ip_address="5.5.5.5")
    otp.request_code("09120000002", ip_address="5.5.5.5")
    with pytest.raises(otp.OtpError) as exc:
        otp.request_code("09120000003", ip_address="5.5.5.5")
    assert exc.value.code == "ip_limit"
    # A different IP is not affected.
    otp.request_code("09120000003", ip_address="6.6.6.6")


@pytest.mark.django_db
def test_correct_code_creates_web_customer(sms_outbox):
    otp.request_code(MOBILE)
    customer = otp.verify_code(MOBILE, _last_code(sms_outbox))

    assert customer.mobile == MOBILE
    assert customer.signup_channel == Customer.Channel.WEB
    assert customer.last_login_at is not None


@pytest.mark.django_db
def test_existing_customer_signs_in_without_duplicate(settings, sms_outbox):
    settings.OTP_RESEND_COOLDOWN = 0
    otp.request_code(MOBILE)
    first = otp.verify_code(MOBILE, _last_code(sms_outbox))
    otp.request_code(MOBILE)
    second = otp.verify_code(MOBILE, _last_code(sms_outbox))

    assert first.pk == second.pk
    assert Customer.objects.count() == 1


@pytest.mark.django_db
def test_persian_digits_in_code_are_accepted(sms_outbox):
    otp.request_code(MOBILE)
    code = _last_code(sms_outbox).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    assert otp.verify_code(MOBILE, code).mobile == MOBILE


@pytest.mark.django_db
def test_code_cannot_be_reused(sms_outbox):
    otp.request_code(MOBILE)
    code = _last_code(sms_outbox)
    otp.verify_code(MOBILE, code)
    with pytest.raises(otp.OtpError) as exc:
        otp.verify_code(MOBILE, code)
    assert exc.value.code == "expired"


@pytest.mark.django_db
def test_expired_code_is_rejected(sms_outbox):
    otp.request_code(MOBILE)
    LoginCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(otp.OtpError) as exc:
        otp.verify_code(MOBILE, _last_code(sms_outbox))
    assert exc.value.code == "expired"
    assert not Customer.objects.exists()


@pytest.mark.django_db
def test_wrong_code_counts_attempts_and_locks(settings, sms_outbox):
    settings.OTP_MAX_ATTEMPTS = 3
    otp.request_code(MOBILE)
    good = _last_code(sms_outbox)
    bad = "00000" if good != "00000" else "11111"

    for expected in ("wrong_code", "wrong_code", "too_many_attempts"):
        with pytest.raises(otp.OtpError) as exc:
            otp.verify_code(MOBILE, bad)
        assert exc.value.code == expected

    # Even the right code no longer works once locked.
    with pytest.raises(otp.OtpError) as exc:
        otp.verify_code(MOBILE, good)
    assert exc.value.code == "too_many_attempts"
    assert not Customer.objects.exists()


@pytest.mark.django_db
def test_inactive_customer_cannot_sign_in(sms_outbox):
    Customer.objects.create(signup_channel="web", mobile=MOBILE, is_active=False)
    otp.request_code(MOBILE)
    with pytest.raises(otp.OtpError) as exc:
        otp.verify_code(MOBILE, _last_code(sms_outbox))
    assert exc.value.code == "inactive"


@pytest.mark.django_db
def test_sms_failure_does_not_leave_a_code(monkeypatch):
    from apps.notifications import sms

    def boom(self, mobile, code):
        raise sms.SmsError("down")

    monkeypatch.setattr(sms.MemorySmsBackend, "send_otp", boom)
    with pytest.raises(otp.OtpError) as exc:
        otp.request_code(MOBILE)
    assert exc.value.code == "sms_failed"
    assert not LoginCode.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fields",
    [
        {"signup_channel": "web"},  # web without mobile
        {"signup_channel": "telegram"},  # telegram without id
        {"signup_channel": "web", "mobile": MOBILE, "telegram_user_id": 42},  # both identities
    ],
)
def test_customer_identity_constraint(fields):
    with pytest.raises(IntegrityError):
        Customer.objects.create(**fields)


@pytest.mark.django_db
def test_telegram_customer_has_no_mobile():
    c = Customer.objects.create(signup_channel="telegram", telegram_user_id=123456)
    assert not c.can_receive_sms
