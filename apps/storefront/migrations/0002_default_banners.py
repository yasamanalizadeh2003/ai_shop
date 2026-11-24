from django.db import migrations

BANNERS = [
    {"title": "ChatGPT Plus", "highlight": "با تحویل فوری", "badge": "پرفروش‌ترین اشتراک ماه",
     "link": "/product/اشتراک-chatgpt-plus/", "style": "navy", "sort_order": 0},
    {"title": "Gemini Advanced", "highlight": "تا ۱۵٪ تخفیف", "badge": "فعال‌سازی روی جیمیل خودتان",
     "link": "/product/اشتراک-جمینای/", "style": "midnight", "sort_order": 1},
]


def create(apps, schema_editor):
    HomeBanner = apps.get_model("storefront", "HomeBanner")
    if not HomeBanner.objects.exists():
        for data in BANNERS:
            HomeBanner.objects.create(**data)


class Migration(migrations.Migration):
    dependencies = [("storefront", "0001_initial")]

    operations = [migrations.RunPython(create, migrations.RunPython.noop)]
