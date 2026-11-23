import re

import pytest
from django.urls import reverse

from apps.accounts.models import Customer
from apps.accounts.session import SESSION_KEY
from apps.orders.models import Cart, CartItem, Order
from apps.payments.models import Payment

from .conftest import make_customer

MOBILE = "09125550000"


def _login(client, outbox, mobile=MOBILE):
    client.post(reverse("accounts:request_code"), {"mobile": mobile})
    client.post(reverse("accounts:verify_code"), {"d": list(outbox[-1]["code"])})
    return Customer.objects.get(mobile=mobile)


def _add(client, variant, json=True):
    headers = {"HTTP_ACCEPT": "application/json"} if json else {}
    return client.post(reverse("orders:cart_add"), {"variant": variant.pk}, **headers)


@pytest.mark.django_db
def test_guest_can_add_to_cart_and_see_it(client, stock_variant):
    response = _add(client, stock_variant)
    assert response.json() == {"ok": True, "count": 1}
    page = client.get(reverse("storefront:cart"))
    assert page.context["summary"].count == 1
    assert "ChatGPT" in page.content.decode()


@pytest.mark.django_db
def test_cart_page_with_discounted_item_shows_profit(client, stock_variant):
    from decimal import Decimal

    stock_variant.compare_at_price = Decimal("1200000")
    stock_variant.save()
    _add(client, stock_variant)
    page = client.get(reverse("storefront:cart"))
    assert page.status_code == 200
    assert "سود شما" in page.content.decode()
    assert page.context["summary"].profit == Decimal("200000")


@pytest.mark.django_db
def test_private_variant_limited_to_one(client, manual_variant):
    _add(client, manual_variant)
    response = _add(client, manual_variant)
    assert response.status_code == 400
    assert "یک ایمیل" in response.json()["error"]


@pytest.mark.django_db
def test_shared_variant_quantity_limit(client, stock_variant):
    for _ in range(5):
        _add(client, stock_variant)
    assert _add(client, stock_variant).status_code == 400


@pytest.mark.django_db
def test_inactive_variant_cannot_be_added(client, stock_variant):
    stock_variant.status = "inactive"
    stock_variant.save()
    assert _add(client, stock_variant).status_code == 400


@pytest.mark.django_db
def test_guest_cart_merges_into_account_cart_on_login(client, stock_variant, manual_variant, sms_outbox):
    customer = Customer.objects.create(signup_channel="web", mobile=MOBILE)
    account_cart = Cart.objects.create(customer=customer)
    CartItem.objects.create(cart=account_cart, variant=stock_variant, quantity=2)

    _add(client, stock_variant)
    _add(client, manual_variant)
    _login(client, sms_outbox)

    items = {i.variant_id: i.quantity for i in Cart.objects.get(customer=customer).items.all()}
    assert items == {stock_variant.pk: 3, manual_variant.pk: 1}
    assert Cart.objects.filter(customer__isnull=True).count() == 0


@pytest.mark.django_db
def test_update_and_remove(client, stock_variant):
    _add(client, stock_variant)
    item = CartItem.objects.get()
    client.post(reverse("orders:cart_update", args=[item.pk]), {"quantity": 3})
    item.refresh_from_db()
    assert item.quantity == 3
    client.post(reverse("orders:cart_remove", args=[item.pk]))
    assert not CartItem.objects.exists()


@pytest.mark.django_db
def test_cannot_touch_someone_elses_cart_item(client, stock_variant):
    other = make_customer()
    cart = Cart.objects.create(customer=other)
    item = CartItem.objects.create(cart=cart, variant=stock_variant, quantity=1)
    _add(client, stock_variant)  # own guest cart
    client.post(reverse("orders:cart_remove", args=[item.pk]))
    assert CartItem.objects.filter(pk=item.pk).exists()


@pytest.mark.django_db
def test_full_purchase_flow(client, stock_variant, manual_variant, sms_outbox):
    _add(client, stock_variant)
    _add(client, manual_variant)
    customer = _login(client, sms_outbox)

    info = client.get(reverse("storefront:checkout"), {"step": "info"})
    assert info.status_code == 200
    manual_item = CartItem.objects.get(variant=manual_variant)

    # Invalid gmail is rejected by the backend and the typed value is kept.
    bad = client.post(reverse("orders:place_order"), {f"account_{manual_item.pk}": "me@company.com"}, follow=True)
    assert "gmail" in bad.content.decode()
    assert Order.objects.count() == 0
    manual_item.refresh_from_db()
    assert manual_item.account_identifier == "me@company.com"

    response = client.post(reverse("orders:place_order"), {f"account_{manual_item.pk}": "me@gmail.com"})
    order = Order.objects.get()
    payment = Payment.objects.get()
    assert response.url == reverse("payments:mock_gateway", args=[payment.authority])

    # The bank page: choose "success" -> redirected to our callback.
    with pytest.MonkeyPatch.context() as mp:
        from django.conf import settings
        mp.setattr(settings, "DEBUG", True)
        bank = client.post(response.url, {"result": "success"})
    assert "/payments/callback/mock/" in bank.url

    final = client.get(bank.url, follow=True)
    order.refresh_from_db()
    assert order.status == Order.Status.PROCESSING  # the manual item still needs delivery
    html = final.content.decode()
    assert "پرداخت موفق" in html
    assert re.search(r"user\d@x\.com", html), "stock delivery data is shown to the owner"
    assert Cart.objects.get(customer=customer).items.count() == 0


@pytest.mark.django_db
def test_out_of_stock_at_checkout_returns_to_cart(client, stock_variant, sms_outbox):
    _add(client, stock_variant)
    _login(client, sms_outbox)
    from apps.catalog.models import InventoryItem
    InventoryItem.objects.update(status=InventoryItem.Status.SOLD)

    response = client.post(reverse("orders:place_order"), follow=True)
    assert response.request["PATH_INFO"] == reverse("storefront:cart")
    assert "هیچ مبلغی کسر نشده" in response.content.decode()
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_order_page_is_private(client, stock_variant, sms_outbox):
    from apps.orders import services

    owner = make_customer()
    from .conftest import make_cart
    order = services.create_order(owner, make_cart(owner, (stock_variant, 1)))
    _login(client, sms_outbox)
    assert client.get(order.get_absolute_url()).status_code == 404


@pytest.mark.django_db
def test_guest_order_page_redirects_to_login(client, stock_variant):
    assert client.get(reverse("orders:detail", args=[100001])).status_code == 302


@pytest.mark.django_db
def test_discount_code_in_checkout(client, stock_variant, sms_outbox):
    from decimal import Decimal

    from apps.orders.models import DiscountCode

    DiscountCode.objects.create(code="OFF", kind="amount", value=Decimal("100000"))
    _add(client, stock_variant)
    _login(client, sms_outbox)
    client.post(reverse("orders:apply_discount"), {"discount_code": "off"})
    page = client.get(reverse("storefront:checkout"), {"step": "info"})
    assert page.context["payable"] == Decimal("900000")

    client.post(reverse("orders:place_order"))
    assert Order.objects.get().total == Decimal("900000")


@pytest.mark.django_db
def test_mock_gateway_disabled_in_production(client, order_with_payment=None):
    assert client.get(reverse("payments:mock_gateway", args=["X"])).status_code == 404
