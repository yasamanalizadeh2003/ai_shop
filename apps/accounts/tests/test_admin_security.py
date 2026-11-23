import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.roles import FINANCE, MANAGER, OPERATOR


@pytest.fixture
def staff(db):
    return User.objects.create_superuser("boss", "boss@example.com", "S3cure-pass!")


def _token(device):
    totp = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    return f"{totp.token():06d}"


@pytest.mark.django_db
def test_roles_exist_with_permissions():
    for name in (OPERATOR, FINANCE, MANAGER):
        group = Group.objects.get(name=name)
        assert group.permissions.filter(codename="view_customer").exists()
    assert Group.objects.get(name=MANAGER).permissions.filter(codename="change_customer").exists()
    assert not Group.objects.get(name=OPERATOR).permissions.filter(codename="change_customer").exists()


@pytest.mark.django_db
def test_admin_login_without_otp_token_is_rejected(client, staff):
    TOTPDevice.objects.create(user=staff, name="a", confirmed=True)
    client.post("/admin/login/", {"username": "boss", "password": "S3cure-pass!", "otp_token": "000000"})
    assert client.get("/admin/").status_code == 302


@pytest.mark.django_db
def test_admin_password_session_without_otp_cannot_open_admin(client, staff):
    # A plain Django login (password only) must not grant admin access.
    client.force_login(staff)
    response = client.get("/admin/")
    assert response.status_code == 302
    assert "/admin/login/" in response.url


@pytest.mark.django_db
def test_admin_login_with_valid_otp_token(client, staff):
    device = TOTPDevice.objects.create(user=staff, name="a", confirmed=True)
    client.post(
        "/admin/login/",
        {"username": "boss", "password": "S3cure-pass!", "otp_device": device.persistent_id, "otp_token": _token(device)},
    )
    assert client.get("/admin/").status_code == 200


@pytest.mark.django_db
def test_setup_admin_2fa_command(staff, capsys):
    call_command("setup_admin_2fa", "boss")
    assert TOTPDevice.objects.filter(user=staff, confirmed=True).count() == 1
    assert "otpauth://" in capsys.readouterr().out


@pytest.mark.django_db
def test_setup_admin_2fa_requires_reset_to_replace(staff):
    from django.core.management.base import CommandError

    call_command("setup_admin_2fa", "boss")
    with pytest.raises(CommandError):
        call_command("setup_admin_2fa", "boss")
    call_command("setup_admin_2fa", "boss", "--reset")
    assert TOTPDevice.objects.filter(user=staff).count() == 1


@pytest.mark.django_db
def test_customers_cannot_be_added_or_deleted_in_admin(client, staff):
    from django.contrib import admin

    from apps.accounts.models import Customer

    model_admin = admin.site._registry[Customer]
    request = type("R", (), {"user": staff})()
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_delete_permission(request)
