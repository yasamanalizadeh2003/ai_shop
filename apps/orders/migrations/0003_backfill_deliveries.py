from datetime import timedelta

from django.db import migrations


def backfill(apps, schema_editor):
    """Items delivered before the Delivery table existed get their dates from delivered_at."""
    OrderItem = apps.get_model("orders", "OrderItem")
    Delivery = apps.get_model("orders", "Delivery")
    for item in OrderItem.objects.filter(status="delivered", delivery__isnull=True, delivered_at__isnull=False):
        Delivery.objects.create(
            item=item,
            delivered_at=item.delivered_at,
            subscription_ends_at=item.delivered_at + timedelta(days=item.duration_days),
            warranty_ends_at=item.delivered_at + timedelta(days=item.warranty_days),
        )


class Migration(migrations.Migration):
    dependencies = [("orders", "0002_manualqueueitem_orderitem_assigned_to_and_more")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
