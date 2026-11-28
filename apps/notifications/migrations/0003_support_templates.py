from django.db import migrations

NEW = [
    {
        "event": "ticket_answered", "title": "پاسخ تیکت", "is_urgent": True, "can_opt_out": "",
        "sms_text": "{site_name}: به تیکت «{subject}» پاسخ داده شد. {ticket_url}",
        "email_subject": "پاسخ تیکت #{ticket_id}",
        "email_body": "به تیکت «{subject}» پاسخ داده شد:\n{ticket_url}\n\n{site_name}",
        "telegram_text": "💬 به تیکت «{subject}» پاسخ داده شد.",
    },
    {
        "event": "warranty_result", "title": "نتیجه گارانتی", "is_urgent": True, "can_opt_out": "",
        "sms_text": "{site_name}: نتیجه گزارش مشکل «{product}»: {result}. {ticket_url}",
        "email_subject": "نتیجه گارانتی «{product}»",
        "email_body": "نتیجه بررسی گزارش مشکل «{product}»: {result}\nجزئیات:\n{ticket_url}\n\n{site_name}",
        "telegram_text": "🛡 نتیجه گارانتی «{product}»: {result}",
    },
    {
        "event": "refund_paid", "title": "واریز بازگشت وجه", "is_urgent": True, "can_opt_out": "",
        "sms_text": "{site_name}: مبلغ {amount} تومان سفارش {order_number} واریز شد. پیگیری: {tracking_number}",
        "email_subject": "واریز بازگشت وجه سفارش {order_number}",
        "email_body": "مبلغ {amount} تومان بابت سفارش {order_number} به کارت شما واریز شد.\nشماره پیگیری: {tracking_number}\n\n{site_name}",
        "telegram_text": "💳 مبلغ {amount} تومان واریز شد. پیگیری: {tracking_number}",
    },
]

REFUND_REQUIRED = {
    "sms_text": "{site_name}: مبلغ {amount} تومان سفارش {order_number} به کارت شما برمی‌گردد. شماره کارت را ثبت کنید: {ticket_url}",
    "email_body": "مبلغ {amount} تومان بابت سفارش {order_number} به کارت شما برمی‌گردد.\nلطفاً شماره کارت را در این صفحه ثبت کنید:\n{ticket_url}\n\n{site_name}",
    "telegram_text": "مبلغ {amount} تومان سفارش {order_number} برمی‌گردد. شماره کارت را ثبت کنید.",
}


def apply(apps, schema_editor):
    MessageTemplate = apps.get_model("notifications", "MessageTemplate")
    for data in NEW:
        MessageTemplate.objects.get_or_create(event=data["event"], defaults=data)
    MessageTemplate.objects.filter(event="refund_required").update(**REFUND_REQUIRED)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0002_default_templates")]

    operations = [migrations.RunPython(apply, migrations.RunPython.noop)]
