from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class ExchangeRate(models.Model):
    """USD -> Toman rate history. Append-only; the latest row is the current rate."""

    toman_per_usd = models.DecimalField(
        "نرخ دلار (تومان)", max_digits=15, decimal_places=0, validators=[MinValueValidator(Decimal("1"))]
    )
    created_at = models.DateTimeField("زمان ثبت", auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="ثبت‌کننده", null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        verbose_name = "نرخ دلار"
        verbose_name_plural = "نرخ‌های دلار"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.toman_per_usd:,} تومان"

    @classmethod
    def current(cls):
        return cls.objects.order_by("-created_at", "-id").first()


class AuditLog(models.Model):
    """Append-only record of sensitive staff actions (e.g. revealing delivery data)."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, verbose_name="کارمند")
    action = models.CharField("عملیات", max_length=64, db_index=True)
    object_type = models.CharField("نوع", max_length=64)
    object_id = models.CharField("شناسه", max_length=64)
    detail = models.CharField("توضیح", max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField("زمان", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "لاگ عملیات"
        verbose_name_plural = "لاگ عملیات"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} {self.object_type}#{self.object_id}"

    @classmethod
    def record(cls, request, action, obj, detail=""):
        user = getattr(request, "user", None)
        return cls.objects.create(
            actor=user if user is not None and user.is_authenticated else None,
            action=action,
            object_type=obj._meta.label_lower,
            object_id=str(obj.pk),
            detail=detail[:255],
            ip_address=request.META.get("REMOTE_ADDR") if request else None,
        )
