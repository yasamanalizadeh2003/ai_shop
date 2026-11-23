import pytest

from apps.accounts.models import Customer
from apps.catalog import inventory
from apps.catalog.tests.factories import make_product, make_variant
from apps.notifications.team import MemoryTeamBackend
from apps.orders.models import Cart, CartItem


@pytest.fixture(autouse=True)
def _team(settings):
    settings.TEAM_ALERT_BACKEND = "apps.notifications.team.MemoryTeamBackend"
    MemoryTeamBackend.outbox = []


_counter = {"n": 0}


def make_customer(channel="web"):
    _counter["n"] += 1
    n = _counter["n"]
    if channel == "telegram":
        return Customer.objects.create(signup_channel="telegram", telegram_user_id=900000 + n)
    return Customer.objects.create(signup_channel="web", mobile=f"0912{n:07d}")


def make_cart(customer, *lines):
    cart = Cart.objects.create(customer=customer)
    for variant, qty, *rest in lines:
        CartItem.objects.create(cart=cart, variant=variant, quantity=qty, account_identifier=rest[0] if rest else "")
    return cart


@pytest.fixture
def stock_variant(db):
    variant = make_variant(make_product(slug="gpt", title="ChatGPT"), price=1_000_000, low_stock_threshold=0)
    inventory.import_items(variant, [f"user{i}@x.com|pw{i}" for i in range(10)])
    return variant


@pytest.fixture
def manual_variant(db):
    return make_variant(make_product(slug="gem", title="Gemini"), price=500_000, delivery_type="manual",
                        delivery_deadline_hours=3, account_type="private", account_field_type="gmail")
