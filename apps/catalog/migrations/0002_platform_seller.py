from django.db import migrations


def create_platform_seller(apps, schema_editor):
    Seller = apps.get_model("catalog", "Seller")
    if not Seller.objects.filter(is_platform=True).exists():
        Seller.objects.create(name="فروشگاه اصلی", is_platform=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = [migrations.RunPython(create_platform_seller, migrations.RunPython.noop)]
