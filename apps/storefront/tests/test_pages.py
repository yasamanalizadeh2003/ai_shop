import pytest
from django.urls import reverse

from apps.catalog.tests.factories import make_category, make_product, make_variant


@pytest.fixture
def product(db):
    p = make_product(slug="اشتراک-جمینای", title="اشتراک Gemini", category=make_category())
    make_variant(p, price=1_450_000, delivery_type="manual", delivery_deadline_hours=6)
    return p


@pytest.mark.django_db
def test_home_is_site_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'dir="rtl"' in response.content.decode()


@pytest.mark.django_db
def test_design_urls_are_gone(client):
    assert client.get("/design/").status_code == 404


def test_persian_product_url(client, product):
    assert client.get("/product/اشتراک-جمینای/").status_code == 200


@pytest.mark.django_db
def test_unknown_slugs_return_404(client):
    assert client.get(reverse("storefront:product", args=["nope"])).status_code == 404
    assert client.get(reverse("storefront:category", args=["nope"])).status_code == 404


@pytest.mark.django_db
def test_empty_cart_page(client):
    response = client.get(reverse("storefront:cart"))
    assert response.status_code == 200
    assert "خالی" in response.content.decode()


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


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["storefront:cart", "storefront:checkout"])
def test_cart_and_checkout_are_noindex(client, name):
    html = client.get(reverse(name)).content.decode()
    assert 'content="noindex, nofollow"' in html
