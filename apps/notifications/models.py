from django.db import models


class MessageTemplate(models.Model):
    """Per-event texts, editable from the admin. Placeholders use {name} syntax."""

    event = models.CharField("رویداد", max_length=40, unique=True)
    title = models.CharField("عنوان", max_length=100)
    is_urgent = models.BooleanField(
        "فوری", default=True, help_text="پیام‌های غیرفوری فقط بین ۹ صبح تا ۹ شب به وقت تهران ارسال می‌شوند."
    )
    can_opt_out = models.CharField(
        "قابل خاموش شدن", max_length=12, blank=True,
        choices=[("", "خیر"), ("reminders", "یادآوری‌ها"), ("marketing", "تبلیغاتی")],
    )
    sms_template = models.CharField(
        "شناسه قالب پیامک نزد سرویس‌دهنده", max_length=60, blank=True,
        help_text="پیامک‌های خدماتی با روش قالبی سرویس‌دهنده ارسال می‌شوند تا به فیلتر تبلیغاتی نخورند.",
    )
    sms_text = models.TextField("متن پیامک", blank=True, help_text="هرگز اطلاعات اکانت را در پیامک نگذارید؛ فقط لینک صفحه سفارش.")
    email_subject = models.CharField("موضوع ایمیل", max_length=150, blank=True)
    email_body = models.TextField("متن ایمیل", blank=True)
    telegram_text = models.TextField("متن پیام تلگرام", blank=True)
    is_active = models.BooleanField("فعال", default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "قالب پیام"
        verbose_name_plural = "قالب‌های پیام"
        ordering = ["event"]

    def __str__(self):
        return f"{self.title} ({self.event})"


class Message(models.Model):
    """One outgoing message on one channel. Sent from a queue with retries."""

    class Channel(models.TextChoices):
        SMS = "sms", "پیامک"
        EMAIL = "email", "ایمیل"
        TELEGRAM = "telegram", "تلگرام"

    class Status(models.TextChoices):
        QUEUED = "queued", "در صف"
        SENT = "sent", "ارسال شد"
        FAILED = "failed", "ناموفق"
        SKIPPED = "skipped", "رد شد"

    customer = models.ForeignKey("accounts.Customer", on_delete=models.CASCADE, related_name="messages", verbose_name="مشتری")
    event = models.CharField("رویداد", max_length=40, db_index=True)
    channel = models.CharField("کانال", max_length=10, choices=Channel.choices)
    recipient = models.CharField("گیرنده", max_length=254)
    context = models.JSONField("داده‌ها", default=dict)
    idempotency_key = models.CharField(max_length=120, unique=True)
    is_urgent = models.BooleanField(default=True)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True)
    attempts = models.PositiveSmallIntegerField("تلاش‌ها", default=0)
    next_attempt_at = models.DateTimeField(db_index=True)
    last_error = models.CharField("آخرین خطا", max_length=255, blank=True)
    provider_message_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)
    sent_at = models.DateTimeField("زمان ارسال", null=True, blank=True)

    class Meta:
        verbose_name = "پیام ارسالی"
        verbose_name_plural = "صف پیام‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event} → {self.get_channel_display()} {self.recipient}"
