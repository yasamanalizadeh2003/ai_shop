import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from apps.accounts.roles import FINANCE, OPERATOR
from apps.accounts.session import SESSION_KEY
from apps.orders import services as order_services
from apps.orders.tests.conftest import make_cart, make_customer
from apps.support.models import Refund, Ticket, WarrantyClaim

VALID_CARD = "6037997599999993"


def _login_customer(client, customer):
    session = client.session
    session[SESSION_KEY] = customer.pk
    session.save()


def _staff(username, role):
    user = User.objects.create_user(username, password="pw", is_staff=True)
    user.groups.add(Group.objects.get(name=role))
    return user


def _otp_login(client, user):
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device = TOTPDevice.objects.create(user=user, name="t", confirmed=True)
    client.force_login(user)
    session = client.session
    session["otp_device_id"] = device.persistent_id
    session.save()


@pytest.fixture
def paid_order(stock_variant):
    customer = make_customer()
    order = order_services.create_order(customer, make_cart(customer, (stock_variant, 1)))
    order_services.apply_payment(order.pk, amount=order.total)
    return order


@pytest.mark.django_db
def test_report_problem_button_on_order_page(client, paid_order):
    _login_customer(client, paid_order.customer)
    item = paid_order.items.get()
    html = client.get(paid_order.get_absolute_url()).content.decode()
    assert reverse("support:report_problem", args=[item.pk]) in html

    response = client.post(reverse("support:report_problem", args=[item.pk]), {"body": "کار نمی‌کند"})
    claim = WarrantyClaim.objects.get()
    assert response.url == claim.ticket.get_absolute_url()
    page = client.get(response.url).content.decode()
    assert "کار نمی‌کند" in page and "در حال بررسی" in page


@pytest.mark.django_db
def test_new_ticket_list_and_reply(client, paid_order):
    _login_customer(client, paid_order.customer)
    response = client.post(reverse("support:ticket_new"), {"subject": "سؤال", "body": "سلام", "order": paid_order.number})
    ticket = Ticket.objects.get()
    assert ticket.order == paid_order
    assert "سؤال" in client.get(reverse("support:tickets")).content.decode()
    client.post(ticket.get_absolute_url(), {"body": "پیام دوم"})
    assert ticket.messages.count() == 2


@pytest.mark.django_db
def test_ticket_pages_are_private(client, paid_order):
    owner_ticket = Ticket.objects.create(customer=paid_order.customer, subject="x")
    stranger = make_customer()
    _login_customer(client, stranger)
    assert client.get(owner_ticket.get_absolute_url()).status_code == 404


@pytest.mark.django_db
def test_guests_are_sent_to_login(client, db):
    response = client.get(reverse("support:tickets"))
    assert response.status_code == 302 and "step=login" in response.url


@pytest.mark.django_db
def test_customer_submits_card_on_ticket_page(client, paid_order):
    from apps.support.services import create_refund

    refund = create_refund(paid_order, amount=paid_order.total, reason=Refund.Reason.LATE_PAYMENT, key="t:1")
    _login_customer(client, paid_order.customer)
    page = client.get(refund.ticket.get_absolute_url()).content.decode()
    assert "ثبت شماره کارت" in page
    client.post(refund.ticket.get_absolute_url(), {"refund": refund.pk, "card": VALID_CARD})
    refund.refresh_from_db()
    assert refund.status == Refund.Status.READY
    assert VALID_CARD not in client.get(refund.ticket.get_absolute_url()).content.decode()


@pytest.mark.django_db
def test_operator_replaces_from_admin_but_cannot_approve_refund(client, paid_order):
    from apps.support.services import report_problem

    claim = report_problem(paid_order.customer, paid_order.items.get().pk, "x")
    operator = _staff("op", OPERATOR)
    _otp_login(client, operator)
    url = reverse("admin:support_ticket_work", args=[claim.ticket_id])
    html = client.get(url).content.decode()
    assert "تعویض و اطلاع به مشتری" in html and "تأیید بازگشت وجه" not in html

    assert client.post(url, {"action": "approve_refund"}).status_code == 403
    client.post(url, {"action": "replace"})
    claim.refresh_from_db()
    assert claim.status == WarrantyClaim.Status.REPLACED


@pytest.mark.django_db
def test_finance_pays_refund_from_admin(client, paid_order):
    from apps.support.services import create_refund, submit_card

    refund = create_refund(paid_order, amount=paid_order.total, reason=Refund.Reason.LATE_PAYMENT, key="t:2")
    submit_card(refund, paid_order.customer, VALID_CARD)
    finance = _staff("fin", FINANCE)
    _otp_login(client, finance)

    assert str(paid_order.number) in client.get(reverse("admin:support_refund_changelist")).content.decode()
    url = reverse("admin:support_refund_pay", args=[refund.pk])
    assert VALID_CARD in client.post(url, {"action": "reveal"}).content.decode()
    client.post(url, {"action": "pay", "tracking_number": "BANK-1", "method": "manual"})
    refund.refresh_from_db()
    assert refund.status == Refund.Status.PAID and refund.card_encrypted is None


@pytest.mark.django_db
def test_operator_cannot_open_refund_queue(client, paid_order):
    operator = _staff("op2", OPERATOR)
    _otp_login(client, operator)
    from apps.support.services import create_refund

    refund = create_refund(paid_order, amount=paid_order.total, reason=Refund.Reason.LATE_PAYMENT, key="t:3")
    assert client.get(reverse("admin:support_refund_pay", args=[refund.pk])).status_code == 403


@pytest.mark.django_db
def test_quality_report(client, paid_order):
    from apps.support.services import replace_item, report_problem

    admin = User.objects.create_superuser("boss", "b@x.com", "pw")
    claim = report_problem(paid_order.customer, paid_order.items.get().pk, "x")
    replace_item(claim.pk, admin)
    _otp_login(client, admin)
    html = client.get(reverse("admin:support_quality_report")).content.decode()
    assert "ChatGPT" in html and "100.0٪" in html
