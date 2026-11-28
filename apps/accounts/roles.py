"""
Staff roles are Django Groups. Each milestone adds the permissions of its
new models here; `ensure_roles` runs after every migrate and is idempotent.
"""

from django.contrib.auth.models import Group, Permission

OPERATOR = "اپراتور"
FINANCE = "مدیر مالی"
MANAGER = "مدیر کل"

CATALOG_VIEW = [
    "catalog.view_category",
    "catalog.view_product",
    "catalog.view_variant",
    "catalog.view_inventoryitem",
]

CATALOG_MANAGE = [
    f"catalog.{action}_{model}"
    for model in ("category", "product", "productspec", "productfaq", "variant", "redirect")
    for action in ("view", "add", "change", "delete")
] + [
    "catalog.view_inventoryitem",
    "catalog.add_inventoryitem",
    "catalog.change_inventoryitem",
    "catalog.reveal_inventoryitem",
    "catalog.view_seller",
    "core.view_exchangerate",
    "core.add_exchangerate",
    "core.view_auditlog",
]

ROLE_PERMISSIONS = {
    OPERATOR: [
        "accounts.view_customer",
        *CATALOG_VIEW,
        "orders.view_order",
        "orders.view_manualqueueitem",
        "orders.change_manualqueueitem",
        "orders.view_delivery",
        "orders.change_delivery",
        "notifications.view_message",
        "support.view_ticket",
        "support.change_ticket",
        "support.view_warrantyclaim",
        "support.resolve_warranty",
    ],
    FINANCE: [
        "accounts.view_customer",
        *CATALOG_VIEW,
        "core.view_exchangerate",
        "orders.view_order",
        "payments.view_payment",
        "support.view_ticket",
        "support.view_warrantyclaim",
        "support.approve_refund",
        "support.view_refund",
        "support.change_refund",
        "support.reveal_card",
    ],
    MANAGER: [
        *CATALOG_MANAGE,
        "orders.view_order",
        "payments.view_payment",
        "orders.view_discountcode",
        "orders.add_discountcode",
        "orders.change_discountcode",
        "orders.delete_discountcode",
        "core.view_sitesettings",
        "core.change_sitesettings",
        "orders.view_manualqueueitem",
        "orders.change_manualqueueitem",
        "orders.view_delivery",
        "orders.change_delivery",
        "notifications.view_messagetemplate",
        "notifications.change_messagetemplate",
        "notifications.view_message",
        "support.view_ticket",
        "support.change_ticket",
        "support.view_warrantyclaim",
        "support.resolve_warranty",
        "support.view_refund",
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
