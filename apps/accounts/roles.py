"""
Staff roles are Django Groups. Each milestone adds the permissions of its
new models here; `ensure_roles` runs after every migrate and is idempotent.
"""

from django.contrib.auth.models import Group, Permission

OPERATOR = "اپراتور"
FINANCE = "مدیر مالی"
MANAGER = "مدیر کل"

ROLE_PERMISSIONS = {
    OPERATOR: [
        "accounts.view_customer",
    ],
    FINANCE: [
        "accounts.view_customer",
    ],
    MANAGER: [
        "accounts.view_customer",
        "accounts.change_customer",
        "auth.view_user",
        "auth.add_user",
        "auth.change_user",
        "auth.view_group",
        "otp_totp.view_totpdevice",
        "otp_totp.add_totpdevice",
        "otp_totp.delete_totpdevice",
    ],
}


def _permission(dotted):
    app_label, codename = dotted.split(".", 1)
    return Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()


def ensure_roles(**kwargs):
    for name, perms in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=name)
        wanted = [p for p in (_permission(d) for d in perms) if p is not None]
        group.permissions.add(*wanted)
