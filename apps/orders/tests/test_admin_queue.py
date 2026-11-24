import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from apps.accounts.roles import FINANCE, OPERATOR
from apps.orders import services
from apps.orders.models import OrderItem

from .conftest import make_cart, make_customer


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
def waiting_item(manual_variant):
    customer = make_customer()
    cart = make_cart(customer, (manual_variant, 1))
    order = services.create_order(customer, cart, account_identifiers={cart.items.get().pk: "x@gmail.com"})
    services.apply_payment(order.pk, amount=order.total)
    return order.items.get()


@pytest.mark.django_db
def test_operator_sees_queue_and_delivers(client, waiting_item):
    operator = _staff("op", OPERATOR)
    _otp_login(client, operator)

    changelist = client.get(reverse("admin:orders_manualqueueitem_changelist"))
    assert changelist.status_code == 200
    assert "x@gmail.com" in changelist.content.decode()

    url = reverse("admin:orders_manualqueueitem_work", args=[waiting_item.pk])
    assert client.get(url).status_code == 200
    client.post(url, {"action": "claim"})
    response = client.post(url, {"action": "deliver", "note": "فعال شد"})
    assert response.status_code == 302

    waiting_item.refresh_from_db()
    assert waiting_item.status == OrderItem.Status.DELIVERED
    assert waiting_item.assigned_to == operator
    # Delivered items leave the queue.
    assert "x@gmail.com" not in client.get(reverse("admin:orders_manualqueueitem_changelist")).content.decode()


@pytest.mark.django_db
def test_finance_cannot_work_the_queue(client, waiting_item):
    finance = _staff("fin", FINANCE)
    _otp_login(client, finance)
    assert client.get(reverse("admin:orders_manualqueueitem_work", args=[waiting_item.pk])).status_code == 403
