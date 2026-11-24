from django.db import migrations

TEMPLATES = [
    {
        "event": "payment_success", "title": "پرداخت موفق", "is_urgent": True, "can_opt_out": "",
        "sms_text": "{site_name}: پرداخت سفارش {order_number} انجام شد. جزئیات و اطلاعات تحویل: {order_url}",
        "email_subject": "پرداخت سفارش {order_number} انجام شد",
        "email_body": "پرداخت سفارش {order_number} به مبلغ {amount} تومان با موفقیت انجام شد.\nجزئیات سفارش و اطلاعات تحویل:\n{order_url}\n\n{site_name}",
        "telegram_text": "✅ پرداخت سفارش {order_number} انجام شد.",
    },
    {
        "event": "item_delivered", "title": "تحویل قلم", "is_urgent": True, "can_opt_out": "",
        "sms_text": "{site_name}: «{product}» تحویل شد. اطلاعات در صفحه سفارش: {order_url}",
        "email_subject": "«{product}» تحویل شد",
        "email_body": "«{product} — {variant}» از سفارش {order_number} تحویل شد.\nاطلاعات تحویل فقط در صفحه سفارش نمایش داده می‌شود:\n{order_url}\n\n{site_name}",
        "telegram_text": "📦 «{product}» تحویل شد.",
    },
    {
        "event": "expiry_reminder", "title": "یادآوری انقضا (۳ روز قبل)", "is_urgent": False, "can_opt_out": "reminders",
        "sms_text": "{site_name}: اشتراک «{product}» در {ends_at} تمام می‌شود. تمدید: {renew_url}",
        "email_subject": "اشتراک «{product}» به‌زودی تمام می‌شود",
        "email_body": "اشتراک «{product}» در {ends_at} تمام می‌شود.\nبرای تمدید:\n{renew_url}\n\n{site_name}",
        "telegram_text": "⏳ اشتراک «{product}» در {ends_at} تمام می‌شود.",
    },
    {
        "event": "subscription_expired", "title": "پایان اشتراک", "is_urgent": False, "can_opt_out": "reminders",
        "sms_text": "{site_name}: اشتراک «{product}» امروز تمام شد. تمدید: {renew_url}",
        "email_subject": "اشتراک «{product}» تمام شد",
        "email_body": "اشتراک «{product}» امروز تمام شد.\nبرای تمدید:\n{renew_url}\n\n{site_name}",
        "telegram_text": "اشتراک «{product}» امروز تمام شد.",
    },
    {
        "event": "refund_required", "title": "بازگشت وجه لازم", "is_urgent": True, "can_opt_out": "",
        "sms_text": "{site_name}: موجودی سفارش {order_number} تمام شده بود. مبلغ {amount} تومان به کارت شما برمی‌گردد. {order_url}",
        "email_subject": "بازگشت وجه سفارش {order_number}",
        "email_body": "پرداخت سفارش {order_number} بعد از پایان مهلت رزرو رسید و موجودی تمام شده بود.\nمبلغ {amount} تومان به کارت شما برمی‌گردد.\n{order_url}\n\n{site_name}",
        "telegram_text": "مبلغ سفارش {order_number} به کارت شما برمی‌گردد.",
    },
]


def create(apps, schema_editor):
    MessageTemplate = apps.get_model("notifications", "MessageTemplate")
    for data in TEMPLATES:
        MessageTemplate.objects.get_or_create(event=data["event"], defaults=data)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0001_initial")]

    operations = [migrations.RunPython(create, migrations.RunPython.noop)]
