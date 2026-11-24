from datetime import timedelta

from django.db import migrations


def backfill(apps, schema_editor):
    """Manual items paid before deadlines existed: deadline = paid_at + the variant's delivery hours."""
    OrderItem = apps.get_model("orders", "OrderItem")
    for item in OrderItem.objects.filter(status="awaiting_delivery", deadline_at__isnull=True).select_related("order", "variant"):
        if item.order.paid_at:
            item.deadline_at = item.order.paid_at + timedelta(hours=item.variant.delivery_deadline_hours or 24)
            item.save(update_fields=["deadline_at"])


class Migration(migrations.Migration):
    dependencies = [("orders", "0003_backfill_deliveries")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
