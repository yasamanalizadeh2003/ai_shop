import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from apps.accounts.roles import MANAGER, OPERATOR
from apps.catalog import inventory
from apps.catalog.models import InventoryItem
from apps.core.models import AuditLog

from .factories import make_variant


@pytest.fixture
def admin_user(db, settings):
    settings.ADMIN_REQUIRE_2FA = False  # 2FA itself is covered in accounts tests
    return User.objects.create_superuser("boss", "b@x.com", "pw")


def _staff(username, role):
    user = User.objects.create_user(username, password="pw", is_staff=True)
    user.groups.add(Group.objects.get(name=role))
    return user


def _otp_login(client, user):
    """Log in and mark the session as OTP-verified, as the admin requires."""
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device = TOTPDevice.objects.create(user=user, name="t", confirmed=True)
    client.force_login(user)
    session = client.session
    session["otp_device_id"] = device.persistent_id
    session.save()


@pytest.mark.django_db
def test_import_preview_then_confirm(client, admin_user):
    _otp_login(client, admin_user)
    variant = make_variant()
    url = reverse("admin:catalog_variant_import", args=[variant.pk])

    preview = client.post(url, {"lines": "a@x.com|1\nb@x.com|2\na@x.com|1", "batch_label": "B1"})
    assert preview.status_code == 200
    assert len(preview.context["preview"].new_rows) == 2
    assert InventoryItem.objects.count() == 0  # nothing saved before confirm

    confirm = client.post(url, {"lines": preview.context["normalized_lines"], "batch_label": "B1", "confirm": "1"})
    assert confirm.status_code == 302
    assert InventoryItem.objects.filter(batch_label="B1").count() == 2


@pytest.mark.django_db
def test_import_csv_upload(client, admin_user):
    from django.core.files.uploadedfile import SimpleUploadedFile

    _otp_login(client, admin_user)
    variant = make_variant()
    url = reverse("admin:catalog_variant_import", args=[variant.pk])
    csv_file = SimpleUploadedFile("items.csv", b"data,pass\nu1,p1\nu2,p2\n", content_type="text/csv")
    preview = client.post(url, {"csv_file": csv_file})
    assert [r.data for r in preview.context["preview"].new_rows] == ["u1|p1", "u2|p2"]


@pytest.mark.django_db
def test_operator_cannot_import(client):
    operator = _staff("op", OPERATOR)
    _otp_login(client, operator)
    variant = make_variant()
    assert client.post(reverse("admin:catalog_variant_import", args=[variant.pk]), {"lines": "x"}).status_code == 403


@pytest.mark.django_db
def test_reveal_requires_permission_and_post(client):
    variant = make_variant()
    inventory.import_items(variant, ["secret@x.com|pw"])
    item = InventoryItem.objects.get()
    url = reverse("admin:catalog_inventoryitem_reveal", args=[item.pk])

    operator = _staff("op", OPERATOR)
    _otp_login(client, operator)
    assert client.post(url).status_code == 403

    manager = _staff("mgr", MANAGER)
    _otp_login(client, manager)
    assert client.get(url).status_code == 405
    response = client.post(url)
    assert response.status_code == 200
    assert "secret@x.com" in response.content.decode()
    assert AuditLog.objects.filter(action="reveal_delivery_data", actor=manager).count() == 1


@pytest.mark.django_db
def test_inventory_list_never_shows_plaintext(client, admin_user):
    _otp_login(client, admin_user)
    variant = make_variant()
    inventory.import_items(variant, ["visible-secret@x.com|pw"])
    item = InventoryItem.objects.get()

    assert "visible-secret" not in client.get(reverse("admin:catalog_inventoryitem_changelist")).content.decode()
    assert "visible-secret" not in client.get(reverse("admin:catalog_inventoryitem_change", args=[item.pk])).content.decode()


@pytest.mark.django_db
def test_product_page_warns_about_empty_stock(client, admin_user):
    _otp_login(client, admin_user)
    variant = make_variant(name="یک ماهه")
    url = reverse("admin:catalog_product_change", args=[variant.product_id])

    html = client.get(url).content.decode()
    assert "انبارش خالی است" in html
    assert "انبار خالی — در سایت «ناموجود» است" in html
    assert "ناموجود: یک ماهه" in client.get(reverse("admin:catalog_product_changelist")).content.decode()

    inventory.import_items(variant, ["a|1"])
    html = client.get(url).content.decode()
    assert "انبارش خالی است" not in html
    assert "1 عدد موجود" in html


@pytest.mark.django_db
def test_manual_variant_has_no_stock_warning(client, admin_user):
    _otp_login(client, admin_user)
    variant = make_variant(delivery_type="manual", delivery_deadline_hours=3)
    html = client.get(reverse("admin:catalog_product_change", args=[variant.product_id])).content.decode()
    assert "انبارش خالی است" not in html
    assert "انبار لازم نیست" in html


@pytest.mark.django_db
def test_exchange_rate_admin_reprices(client, admin_user):
    from decimal import Decimal

    from apps.catalog.models import Variant
    from apps.core.models import ExchangeRate

    _otp_login(client, admin_user)
    ExchangeRate.objects.create(toman_per_usd=Decimal("100000"))
    v = make_variant(pricing_mode=Variant.PricingMode.USD, fixed_price=None, usd_price=Decimal("10"), margin_percent=Decimal("0"))
    assert v.price == Decimal("1000000")

    client.post(reverse("admin:core_exchangerate_add"), {"toman_per_usd": "120000"})
    v.refresh_from_db()
    assert v.price == Decimal("1200000")
