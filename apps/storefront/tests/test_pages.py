import pytest
from django.urls import reverse

from apps.storefront import sample_data as data


def test_home_is_site_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'dir="rtl"' in response.content.decode()


def test_design_urls_are_gone(client):
    assert client.get("/design/").status_code == 404
    assert client.get("/design/home/").status_code == 404


@pytest.mark.parametrize("slug", [c["slug"] for c in data.CATEGORIES])
def test_category_pages_render(client, slug):
    assert client.get(reverse("storefront:category", args=[slug])).status_code == 200


@pytest.mark.parametrize("slug", [p["slug"] for p in data.PRODUCTS])
def test_product_pages_render(client, slug):
    assert client.get(reverse("storefront:product", args=[slug])).status_code == 200


def test_persian_product_url(client):
    response = client.get("/product/اشتراک-جمینای/")
    assert response.status_code == 200


def test_unknown_slugs_return_404(client):
    assert client.get(reverse("storefront:product", args=["nope"])).status_code == 404
    assert client.get(reverse("storefront:category", args=["nope"])).status_code == 404


def test_prices_are_rendered_server_side_with_persian_digits(client):
    html = client.get(reverse("storefront:product", args=["اشتراک-chatgpt-plus"])).content.decode()
    assert "۱٬۸۹۰٬۰۰۰" in html


@pytest.mark.django_db
@pytest.mark.parametrize("step", ["login", "otp", "bogus"])
def test_checkout_guest_steps_render(client, step):
    assert client.get(reverse("storefront:checkout"), {"step": step}).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("step", ["info", "pay"])
def test_checkout_customer_steps_render(client, step):
    from apps.accounts.models import Customer
    from apps.accounts.session import SESSION_KEY

    customer = Customer.objects.create(signup_channel="web", mobile="09123456789")
    session = client.session
    session[SESSION_KEY] = customer.pk
    session.save()
    assert client.get(reverse("storefront:checkout"), {"step": step}).status_code == 200


@pytest.mark.parametrize("name", ["storefront:cart", "storefront:checkout"])
def test_cart_and_checkout_are_noindex(client, name):
    html = client.get(reverse(name)).content.decode()
    assert 'content="noindex, nofollow"' in html
