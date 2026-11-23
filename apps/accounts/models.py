"""
Customers are kept completely separate from staff.
Staff use Django's built-in auth.User (admin panel, roles via Groups, 2FA);
customers sign in with a mobile number + SMS code (site) or are identified
by their Telegram account (bot). The two customer kinds are never merged.
"""

from django.db import models
from django.db.models import Q


class Customer(models.Model):
    class Channel(models.TextChoices):
        WEB = "web", "سایت"
        TELEGRAM = "telegram", "تلگرام"

    signup_channel = models.CharField("کانال ثبت‌نام", max_length=10, choices=Channel.choices)
    mobile = models.CharField("موبایل", max_length=11, unique=True, null=True, blank=True)
    telegram_user_id = models.BigIntegerField("شناسه تلگرام", unique=True, null=True, blank=True)
    last_email = models.EmailField("آخرین ایمیل", blank=True)
    notify_reminders = models.BooleanField("یادآوری تمدید", default=True)
    notify_marketing = models.BooleanField("پیام‌های تبلیغاتی", default=True)
    campaign = models.CharField("کمپین ورود", max_length=64, blank=True)
    is_active = models.BooleanField("فعال", default=True)
    created_at = models.DateTimeField("تاریخ ثبت‌نام", auto_now_add=True)
    last_login_at = models.DateTimeField("آخرین ورود", null=True, blank=True)

    class Meta:
        verbose_name = "مشتری"
        verbose_name_plural = "مشتریان"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                name="customer_one_identity",
                condition=(
                    Q(signup_channel="web", mobile__isnull=False, telegram_user_id__isnull=True)
                    | Q(signup_channel="telegram", telegram_user_id__isnull=False, mobile__isnull=True)
                ),
            ),
        ]

    def __str__(self):
        return self.mobile or f"tg:{self.telegram_user_id}"

    @property
    def can_receive_sms(self):
        return bool(self.mobile)


class LoginCode(models.Model):
    """One SMS login code. Only an HMAC of the code is stored."""

    mobile = models.CharField(max_length=11, db_index=True)
    code_hash = models.CharField(max_length=64)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "کد ورود"
        verbose_name_plural = "کدهای ورود"
        indexes = [models.Index(fields=["ip_address", "created_at"])]

    def __str__(self):
        return f"{self.mobile} @ {self.created_at:%Y-%m-%d %H:%M}"
