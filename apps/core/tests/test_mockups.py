import pytest
from django.test import override_settings
from django.urls import clear_url_caches, reverse

from apps.core.mockups import PAGES


@pytest.fixture(autouse=True)
def _debug_urls(settings):
    settings.DEBUG = True
    import importlib

    import config.urls

    clear_url_caches()
    importlib.reload(config.urls)
    yield
    clear_url_caches()


@pytest.mark.parametrize("name", list(PAGES))
def test_mockup_pages_render(client, name):
    response = client.get(reverse("design-page", args=[name]))
    assert response.status_code == 200
    assert 'dir="rtl"' in response.content.decode()


@pytest.mark.parametrize("step", ["login", "otp", "info", "pay"])
def test_checkout_steps_render(client, step):
    response = client.get(reverse("design-page", args=["checkout"]), {"step": step})
    assert response.status_code == 200


def test_prices_are_rendered_server_side_with_persian_digits(client):
    html = client.get(reverse("design-page", args=["product"])).content.decode()
    assert "۱٬۸۹۰٬۰۰۰" in html


def test_cart_and_checkout_are_noindex(client):
    for name in ("cart", "checkout"):
        html = client.get(reverse("design-page", args=[name])).content.decode()
        assert 'content="noindex, nofollow"' in html


def test_unknown_mockup_returns_404(client):
    assert client.get("/design/nope/").status_code == 404


@override_settings(DEBUG=False)
def test_mockups_are_not_routed_in_production():
    import importlib

    import config.urls

    clear_url_caches()
    importlib.reload(config.urls)
    names = {getattr(p, "name", None) for p in config.urls.urlpatterns}
    assert "design-page" not in names
