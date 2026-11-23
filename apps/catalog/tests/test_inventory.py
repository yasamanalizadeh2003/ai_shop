import io

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, connection
from django.test import RequestFactory

from apps.catalog import inventory
from apps.catalog.models import InventoryItem, Seller
from apps.core.models import AuditLog
from apps.notifications.team import MemoryTeamBackend

from .factories import make_product, make_variant


@pytest.fixture(autouse=True)
def team_outbox(settings):
    settings.TEAM_ALERT_BACKEND = "apps.notifications.team.MemoryTeamBackend"
    MemoryTeamBackend.outbox = []
    return MemoryTeamBackend.outbox


@pytest.fixture
def staff_request(db):
    request = RequestFactory().post("/")
    request.user = User.objects.create_user("op", is_staff=True)
    return request


@pytest.mark.django_db
def test_every_record_has_platform_seller():
    variant = make_variant()
    platform = Seller.platform()
    assert variant.seller == platform and variant.product.seller == platform
    inventory.import_items(variant, ["a|1"])
    assert InventoryItem.objects.get().seller == platform


@pytest.mark.django_db
def test_import_encrypts_and_skips_duplicates(django_capture_on_commit_callbacks):
    variant = make_variant()
    with django_capture_on_commit_callbacks(execute=True):
        created = inventory.import_items(variant, ["a@x.com|p1", "b@x.com|p2", "a@x.com|p1", ""])
    assert created == 2

    with django_capture_on_commit_callbacks(execute=True):
        created_again = inventory.import_items(variant, ["a@x.com|p1", "c@x.com|p3"])
    assert created_again == 1
    assert InventoryItem.objects.filter(variant=variant).count() == 3

    raw = bytes(InventoryItem.objects.first().encrypted_data)
    assert b"@x.com" not in raw


@pytest.mark.django_db
def test_same_item_allowed_in_another_variant():
    v1 = make_variant()
    v2 = make_variant(product=v1.product, name="دیگر")
    assert inventory.import_items(v1, ["same|1"]) == 1
    assert inventory.import_items(v2, ["same|1"]) == 1


@pytest.mark.django_db
def test_database_rejects_duplicate_fingerprint():
    variant = make_variant()
    inventory.import_items(variant, ["dup"])
    item = InventoryItem.objects.get()
    with pytest.raises(IntegrityError):
        InventoryItem.objects.create(variant=variant, encrypted_data=b"x", fingerprint=item.fingerprint)


@pytest.mark.django_db
def test_preview_reports_each_status():
    variant = make_variant()
    inventory.import_items(variant, ["old"])
    preview = inventory.build_preview(variant, ["new", "new", "old", "x" * 2001])
    assert [r.status for r in preview.rows] == ["new", "duplicate_in_file", "duplicate_existing", "invalid"]
    assert len(preview.new_rows) == 1


def test_parse_lines_from_csv_and_text():
    csv_file = io.BytesIO("data,password\nu1@x.com,p1\nu2@x.com, p2 \n".encode("utf-8-sig"))
    lines = inventory.parse_lines("u3@x.com|p3\n", csv_file)
    assert lines == ["u1@x.com|p1", "u2@x.com|p2", "u3@x.com|p3"]


def test_parse_price():
    assert str(inventory.parse_price("1,200,000")) == "1200000"
    assert inventory.parse_price("") is None
    with pytest.raises(ValueError):
        inventory.parse_price("abc")


@pytest.mark.django_db
def test_reveal_is_audited(staff_request):
    variant = make_variant()
    inventory.import_items(variant, ["user@x.com|pass"])
    item = InventoryItem.objects.get()

    assert inventory.reveal(item, staff_request) == "user@x.com|pass"
    log = AuditLog.objects.get()
    assert log.action == "reveal_delivery_data"
    assert log.actor == staff_request.user
    assert log.object_id == str(item.pk)


@pytest.mark.django_db
def test_format_delivery_template():
    variant = make_variant(delivery_template="ایمیل: {0}\nرمز: {1}")
    assert inventory.format_delivery(variant, "a@x.com|pw") == "ایمیل: a@x.com\nرمز: pw"
    # A broken template falls back to the raw value instead of crashing.
    variant.delivery_template = "{5}"
    assert inventory.format_delivery(variant, "a|b") == "a|b"


@pytest.mark.django_db
def test_void_only_touches_available_items(staff_request):
    variant = make_variant(low_stock_threshold=0)
    inventory.import_items(variant, ["1", "2"])
    first, second = InventoryItem.objects.order_by("id")
    second.status = InventoryItem.Status.SOLD
    second.save()

    assert inventory.void_items(InventoryItem.objects.all(), staff_request) == 1
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == InventoryItem.Status.VOIDED
    assert second.status == InventoryItem.Status.SOLD
    assert AuditLog.objects.filter(action="void_inventory_item").count() == 1


@pytest.mark.django_db
def test_low_stock_alert_fires_once_and_rearms(team_outbox, django_capture_on_commit_callbacks, staff_request):
    variant = make_variant(low_stock_threshold=3)
    with django_capture_on_commit_callbacks(execute=True):
        inventory.import_items(variant, ["1", "2"])
    assert len(team_outbox) == 1 and team_outbox[0]["kind"] == "low_stock"

    # Still low: no second alert.
    with django_capture_on_commit_callbacks(execute=True):
        inventory.import_items(variant, ["3"])
    assert len(team_outbox) == 1

    # Refilled above the threshold re-arms the alert...
    with django_capture_on_commit_callbacks(execute=True):
        inventory.import_items(variant, ["4", "5"])
    variant.refresh_from_db()
    assert variant.low_stock_alerted is False

    # ...so dropping again alerts again.
    ids = list(InventoryItem.objects.filter(variant=variant).values_list("pk", flat=True)[:3])
    with django_capture_on_commit_callbacks(execute=True):
        inventory.void_items(InventoryItem.objects.filter(pk__in=ids), staff_request)
    assert len(team_outbox) == 2


@pytest.mark.django_db
def test_manual_variants_never_alert(team_outbox):
    variant = make_variant(delivery_type="manual", delivery_deadline_hours=3)
    inventory.check_low_stock(variant.pk)
    assert team_outbox == []


@pytest.mark.django_db
def test_alert_failure_does_not_break_import(settings, django_capture_on_commit_callbacks):
    settings.TEAM_ALERT_BACKEND = "does.not.Exist"
    variant = make_variant(low_stock_threshold=5)
    with django_capture_on_commit_callbacks(execute=True):
        assert inventory.import_items(variant, ["1"]) == 1


@pytest.mark.django_db
def test_seed_catalog_is_idempotent():
    from django.core.management import call_command

    call_command("seed_catalog")
    count = InventoryItem.objects.count()
    call_command("seed_catalog")
    assert InventoryItem.objects.count() == count > 0
