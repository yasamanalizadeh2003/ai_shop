from django.db import models

from apps.orders.models import Order

TOMAN = {"max_digits": 15, "decimal_places": 0}


class Payment(models.Model):
    class Status(models.TextChoices):
        INITIATED = "initiated", "ایجاد شده"
        PENDING = "pending", "در انتظار بازگشت از درگاه"
        SUCCEEDED = "succeeded", "موفق"
        FAILED = "failed", "ناموفق"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments", verbose_name="سفارش")
    gateway = models.CharField("درگاه", max_length=30)
    authority = models.CharField("شناسه تراکنش درگاه", max_length=100, unique=True, null=True, blank=True)
    amount = models.DecimalField("مبلغ (تومان)", **TOMAN)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.INITIATED, db_index=True)
    ref_id = models.CharField("شماره پیگیری", max_length=100, blank=True)
    card_pan = models.CharField("کارت (ماسک‌شده)", max_length=32, blank=True)
    verify_response = models.JSONField("پاسخ verify", null=True, blank=True)
    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True, db_index=True)
    verified_at = models.DateTimeField("زمان تأیید", null=True, blank=True)

    class Meta:
        verbose_name = "پرداخت"
        verbose_name_plural = "پرداخت‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.gateway} {self.authority or self.pk}"


class MockTransaction(models.Model):
    """State kept by the development mock gateway (stands in for the bank's side)."""

    authority = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(**TOMAN)
    callback_url = models.CharField(max_length=500)
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
