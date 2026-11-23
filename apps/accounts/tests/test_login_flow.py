import pytest
from django.urls import reverse

from apps.accounts.models import Customer
from apps.accounts.session import SESSION_KEY, customer_logged_in

MOBILE = "09123456789"
CHECKOUT = reverse("storefront:checkout")


def _login(client, outbox, mobile=MOBILE):
    client.post(reverse("accounts:request_code"), {"mobile": mobile})
    code = outbox[-1]["code"]
    return client.post(reverse("accounts:verify_code"), {"d": list(code)})


@pytest.mark.django_db
def test_checkout_shows_login_for_guests(client):
    response = client.get(CHECKOUT)
    assert response.status_code == 200
    assert response.context["step"] == "login"


@pytest.mark.django_db
@pytest.mark.parametrize("step", ["info", "pay"])
def test_guests_cannot_reach_info_or_pay(client, step):
    response = client.get(CHECKOUT, {"step": step})
    assert response.status_code == 302
    assert response.url.endswith("?step=login")


@pytest.mark.django_db
def test_full_login_flow(client, sms_outbox):
    response = client.post(reverse("accounts:request_code"), {"mobile": "۰۹۱۲ ۳۴۵ ۶۷۸۹"})
    assert response.url.endswith("?step=otp")

    page = client.get(CHECKOUT, {"step": "otp"})
    assert page.context["step"] == "otp"
    assert page.context["pending_mobile"] == MOBILE

    code = sms_outbox[-1]["code"]
    response = client.post(reverse("accounts:verify_code"), {"d": list(code)})
    assert response.status_code == 302
    assert response.url.endswith("?step=info")

    customer = Customer.objects.get(mobile=MOBILE)
    assert client.session[SESSION_KEY] == customer.pk

    page = client.get(CHECKOUT, {"step": "info"})
    assert page.status_code == 200
    assert page.context["customer"] == customer


@pytest.mark.django_db
def test_session_key_rotates_on_login(client, sms_outbox):
    client.get(CHECKOUT)
    client.post(reverse("accounts:request_code"), {"mobile": MOBILE})
    before = client.session.session_key
    client.post(reverse("accounts:verify_code"), {"d": list(sms_outbox[-1]["code"])})
    assert client.session.session_key != before


@pytest.mark.django_db
def test_logged_in_customer_skips_login_step(client, sms_outbox):
    _login(client, sms_outbox)
    response = client.get(CHECKOUT)
    assert response.status_code == 302
    assert response.url.endswith("?step=info")


@pytest.mark.django_db
def test_wrong_code_stays_on_otp_step_with_error(client, sms_outbox):
    client.post(reverse("accounts:request_code"), {"mobile": MOBILE})
    good = sms_outbox[-1]["code"]
    bad = "00000" if good != "00000" else "11111"
    response = client.post(reverse("accounts:verify_code"), {"d": list(bad)}, follow=True)
    assert response.context["step"] == "otp"
    assert "اشتباه" in response.content.decode()
    assert SESSION_KEY not in client.session


@pytest.mark.django_db
def test_invalid_mobile_shows_error(client):
    response = client.post(reverse("accounts:request_code"), {"mobile": "123"}, follow=True)
    assert response.context["step"] == "login"
    assert "معتبر نیست" in response.content.decode()


@pytest.mark.django_db
def test_verify_without_pending_mobile_is_rejected(client):
    response = client.post(reverse("accounts:verify_code"), {"code": "12345"})
    assert response.url.endswith("?step=login")


@pytest.mark.django_db
def test_logout(client, sms_outbox):
    _login(client, sms_outbox)
    client.post(reverse("accounts:logout"))
    assert SESSION_KEY not in client.session
    assert client.get(CHECKOUT, {"step": "info"}).status_code == 302


@pytest.mark.django_db
def test_logout_requires_post(client):
    assert client.get(reverse("accounts:logout")).status_code == 405


@pytest.mark.django_db
def test_login_signal_is_sent(client, sms_outbox):
    received = []

    def handler(sender, request, customer, **kwargs):
        received.append(customer.mobile)

    customer_logged_in.connect(handler)
    try:
        _login(client, sms_outbox)
    finally:
        customer_logged_in.disconnect(handler)
    assert received == [MOBILE]


@pytest.mark.django_db
def test_open_redirect_is_blocked(client, sms_outbox):
    client.post(reverse("accounts:request_code"), {"mobile": MOBILE})
    response = client.post(
        reverse("accounts:verify_code"), {"d": list(sms_outbox[-1]["code"]), "next": "https://evil.example/"}
    )
    assert response.url.endswith("?step=info")


@pytest.mark.django_db
def test_staff_session_is_not_a_customer(admin_client):
    response = admin_client.get(CHECKOUT)
    assert response.context["customer"] is None
