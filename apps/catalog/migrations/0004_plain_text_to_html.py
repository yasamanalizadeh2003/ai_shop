import re
from html import escape

from django.db import migrations

_HAS_TAG = re.compile(r"<\s*(p|br|ul|ol|h2|h3|blockquote|strong|em|a)\b", re.IGNORECASE)


def to_html(text):
    if not text or _HAS_TAG.search(text):
        return text
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return "".join("<p>" + escape(p).replace("\n", "<br>") + "</p>" for p in paragraphs)


def convert(apps, schema_editor):
    """Existing plain-text SEO fields become paragraphs so the rich editor opens them nicely."""
    for model, field in (("Category", "description"), ("Product", "description"), ("ProductFaq", "answer")):
        Model = apps.get_model("catalog", model)
        for obj in Model.objects.exclude(**{field: ""}):
            new = to_html(getattr(obj, field))
            if new != getattr(obj, field):
                Model.objects.filter(pk=obj.pk).update(**{field: new})


class Migration(migrations.Migration):
    dependencies = [("catalog", "0003_product_image_height_product_image_width_and_more")]

    operations = [migrations.RunPython(convert, migrations.RunPython.noop)]
