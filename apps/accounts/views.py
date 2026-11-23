import time

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import otp
from .session import login_customer, logout_customer

PENDING_MOBILE_KEY = "otp_mobile"
RESEND_AT_KEY = "otp_resend_at"


def _client_ip(request):
    return request.META.get("REMOTE_ADDR")


def _safe_next(request, default):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return nxt
    return default


def _checkout_url(step):
    return f"{reverse('storefront:checkout')}?step={step}"


@require_POST
def request_code(request):
    raw = request.POST.get("mobile") or request.session.get(PENDING_MOBILE_KEY, "")
    try:
        issued = otp.request_code(raw, ip_address=_client_ip(request))
    except otp.OtpError as exc:
        messages.error(request, exc.message)
        if exc.code == "cooldown" and request.session.get(PENDING_MOBILE_KEY):
            return redirect(_checkout_url("otp"))
        request.session["otp_entered_mobile"] = raw
        return redirect(_checkout_url("login"))

    request.session[PENDING_MOBILE_KEY] = issued.mobile
    request.session[RESEND_AT_KEY] = int(time.time()) + issued.resend_after
    request.session.pop("otp_entered_mobile", None)
    return redirect(_checkout_url("otp"))


@require_POST
def verify_code(request):
    mobile = request.session.get(PENDING_MOBILE_KEY)
    if not mobile:
        messages.error(request, "ابتدا شماره موبایل خود را وارد کنید.")
        return redirect(_checkout_url("login"))

    code = "".join(request.POST.getlist("d")) or request.POST.get("code", "")
    try:
        customer = otp.verify_code(mobile, code)
    except otp.OtpError as exc:
        messages.error(request, exc.message)
        if exc.code in ("expired", "too_many_attempts"):
            return redirect(_checkout_url("otp") + "&expired=1")
        return redirect(_checkout_url("otp"))

    login_customer(request, customer)
    request.session.pop(PENDING_MOBILE_KEY, None)
    request.session.pop(RESEND_AT_KEY, None)
    return redirect(_safe_next(request, _checkout_url("info")))


@require_POST
def change_mobile(request):
    request.session.pop(PENDING_MOBILE_KEY, None)
    request.session.pop(RESEND_AT_KEY, None)
    return redirect(_checkout_url("login"))


@require_POST
def logout(request):
    logout_customer(request)
    messages.success(request, "از حساب خود خارج شدید.")
    return redirect("storefront:home")
