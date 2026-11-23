"""
Inventory: bulk import with duplicate detection, revealing delivery data
(always audited), voiding, and low-stock alerts.
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.core import crypto
from apps.core.models import AuditLog
from apps.notifications import team

from .models import InventoryItem, Variant

MAX_IMPORT_ROWS = 5000


@dataclass
class ImportRow:
    line_no: int
    data: str
    fingerprint: str
    status: str = "new"  # new | duplicate_in_file | duplicate_existing | invalid
    error: str = ""


@dataclass
class ImportPreview:
    rows: list = field(default_factory=list)

    @property
    def new_rows(self):
        return [r for r in self.rows if r.status == "new"]

    def count(self, status):
        return sum(1 for r in self.rows if r.status == status)


def parse_lines(text: str = "", csv_file=None) -> list[str]:
    """One item per line, or the first column of a CSV (a header row named `data` is skipped)."""
    items = []
    if csv_file is not None:
        raw = csv_file.read()
        content = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
        for i, row in enumerate(csv.reader(io.StringIO(content))):
            if not row:
                continue
            if i == 0 and row[0].strip().lower() in ("data", "delivery_data", "اطلاعات"):
                continue
            items.append("|".join(cell.strip() for cell in row if cell.strip()))
    if text:
        items.extend(text.splitlines())
    return [" ".join(item.split()) for item in items]


def build_preview(variant: Variant, lines: list[str]) -> ImportPreview:
    preview = ImportPreview()
    scope = f"variant:{variant.pk}"
    seen = set()
    for no, line in enumerate(lines, start=1):
        if not line:
            continue
        fp = crypto.fingerprint(line, scope)
        row = ImportRow(line_no=no, data=line, fingerprint=fp)
        if len(line) > 2000:
            row.status, row.error = "invalid", "بیش از ۲۰۰۰ کاراکتر"
        elif fp in seen:
            row.status = "duplicate_in_file"
        seen.add(fp)
        preview.rows.append(row)

    if len(preview.rows) > MAX_IMPORT_ROWS:
        raise ValueError(f"حداکثر {MAX_IMPORT_ROWS} آیتم در هر بار ورود مجاز است.")

    existing = set(
        InventoryItem.objects.filter(variant=variant, fingerprint__in=[r.fingerprint for r in preview.rows]).values_list(
            "fingerprint", flat=True
        )
    )
    for row in preview.rows:
        if row.status == "new" and row.fingerprint in existing:
            row.status = "duplicate_existing"
    return preview


def parse_price(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("٬", "")).quantize(Decimal("1"))
    except InvalidOperation:
        raise ValueError("قیمت خرید نامعتبر است.")


@transaction.atomic
def import_items(variant: Variant, lines: list[str], *, user=None, purchase_price=None,
                 expires_at: date | None = None, batch_label: str = "") -> int:
    """Encrypt and store new items. Duplicates (in file or already stored) are skipped. Returns count created."""
    preview = build_preview(variant, lines)
    scope = f"variant:{variant.pk}"
    objs = [
        InventoryItem(
            variant=variant,
            seller_id=variant.seller_id,
            encrypted_data=crypto.encrypt(row.data, scope.encode()),
            fingerprint=row.fingerprint,
            purchase_price=purchase_price,
            expires_at=expires_at,
            batch_label=batch_label,
            created_by=user,
        )
        for row in preview.new_rows
    ]
    # The unique (variant, fingerprint) constraint also protects concurrent imports.
    before = InventoryItem.objects.filter(variant=variant).count()
    InventoryItem.objects.bulk_create(objs, ignore_conflicts=True)
    created = InventoryItem.objects.filter(variant=variant).count() - before
    transaction.on_commit(lambda: check_low_stock(variant.pk))
    return created


def reveal(item: InventoryItem, request) -> str:
    """Decrypt delivery data. Every call is written to the audit log."""
    value = crypto.decrypt(item.encrypted_data, f"variant:{item.variant_id}".encode())
    AuditLog.record(request, "reveal_delivery_data", item)
    return value


def format_delivery(variant: Variant, data: str) -> str:
    template = variant.delivery_template.strip()
    if not template:
        return data
    parts = [p.strip() for p in data.split("|")]
    try:
        return template.format(*parts)
    except (IndexError, KeyError, ValueError):
        return data


@transaction.atomic
def void_items(queryset, request) -> int:
    count = 0
    for item in queryset.select_for_update().filter(status=InventoryItem.Status.AVAILABLE):
        item.status = InventoryItem.Status.VOIDED
        item.save(update_fields=["status"])
        AuditLog.record(request, "void_inventory_item", item)
        count += 1
    for variant_id in set(queryset.values_list("variant_id", flat=True)):
        transaction.on_commit(lambda vid=variant_id: check_low_stock(vid))
    return count


def check_low_stock(variant_id: int) -> None:
    """Alert once when stock drops below the threshold; re-arm when it is refilled."""
    with transaction.atomic():
        variant = Variant.objects.select_for_update().select_related("product").get(pk=variant_id)
        if variant.delivery_type != Variant.DeliveryType.STOCK or variant.status != Variant.Status.ACTIVE:
            return
        available = variant.available_count()
        low = available < variant.low_stock_threshold
        if low and not variant.low_stock_alerted:
            variant.low_stock_alerted = True
            variant.save(update_fields=["low_stock_alerted"])
            transaction.on_commit(
                lambda: team.alert("low_stock", f"موجودی «{variant}» به {available} رسید (آستانه {variant.low_stock_threshold}).")
            )
        elif not low and variant.low_stock_alerted:
            variant.low_stock_alerted = False
            variant.save(update_fields=["low_stock_alerted"])
