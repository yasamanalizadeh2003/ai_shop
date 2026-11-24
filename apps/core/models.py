from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django_prose_editor.fields import ProseEditorField

from .richtext import EXTENSIONS


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


class SiteSettings(models.Model):
    """Singleton for settings editable from the admin panel."""

    GATEWAYS = [("mock", "درگاه آزمایشی")]

    active_gateway = models.CharField("درگاه پرداخت فعال", max_length=30, choices=GATEWAYS, default="mock")
    reservation_minutes = models.PositiveSmallIntegerField(
        "مهلت رزرو سفارش (دقیقه)", default=15, validators=[MinValueValidator(5)]
    )
    # SEO / analytics
    home_seo_title = models.CharField("عنوان سئوی صفحه اصلی", max_length=70, blank=True)
    home_seo_description = models.CharField("توضیح متای صفحه اصلی", max_length=170, blank=True)
    home_text_title = models.CharField("تیتر متن صفحه اصلی", max_length=120, blank=True,
                                       default="خرید اشتراک هوش مصنوعی با تحویل فوری")
    home_text = ProseEditorField("متن سئوی صفحه اصلی", blank=True, extensions=EXTENSIONS, sanitize=True)
    search_console_verification = models.CharField(
        "کد تأیید Search Console", max_length=100, blank=True, help_text="فقط مقدار content تگ متای google-site-verification"
    )
    analytics_id = models.CharField("شناسه Google Analytics (GA4)", max_length=30, blank=True, help_text="مثلاً G-XXXXXXX")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تنظیمات سایت"
        verbose_name_plural = "تنظیمات سایت"

    def __str__(self):
        return "تنظیمات سایت"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


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
