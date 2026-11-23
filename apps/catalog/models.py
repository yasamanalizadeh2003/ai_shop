from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse

TOMAN = {"max_digits": 15, "decimal_places": 0}
USD = {"max_digits": 18, "decimal_places": 6}


class Seller(models.Model):
    """Phase 1 has a single platform seller; the FK exists everywhere so phase 2 needs no rewrite."""

    name = models.CharField("نام", max_length=100)
    is_platform = models.BooleanField("فروشگاه اصلی", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "فروشنده"
        verbose_name_plural = "فروشندگان"
        constraints = [
            models.UniqueConstraint(fields=["is_platform"], condition=Q(is_platform=True), name="single_platform_seller"),
        ]

    def __str__(self):
        return self.name

    @classmethod
    def platform(cls):
        return cls.objects.get(is_platform=True)


def default_seller_id():
    return Seller.objects.filter(is_platform=True).values_list("pk", flat=True).first()


class SeoFields(models.Model):
    seo_title = models.CharField("عنوان سئو", max_length=70, blank=True, help_text="خالی بماند تا خودکار ساخته شود.")
    seo_description = models.CharField("توضیح متا", max_length=170, blank=True)

    class Meta:
        abstract = True


class Category(SeoFields):
    ICONS = [
        ("chat", "چت"),
        ("image", "تصویر"),
        ("code", "کد"),
        ("search", "جست‌وجو"),
        ("video", "ویدیو"),
        ("key", "کلید / API"),
        ("box", "جعبه"),
    ]

    name = models.CharField("نام", max_length=80)
    slug = models.SlugField("نامک", max_length=120, unique=True, allow_unicode=True)
    icon = models.CharField("آیکون", max_length=20, choices=ICONS, default="box")
    description = models.TextField("متن سئوی دسته", blank=True)
    sort_order = models.PositiveIntegerField("ترتیب", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "دسته"
        verbose_name_plural = "دسته‌ها"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("storefront:category", args=[self.slug])


class Product(SeoFields):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        ACTIVE = "active", "فعال"
        ARCHIVED = "archived", "بایگانی"

    TINTS = [
        ("from-emerald-500 to-teal-600", "سبز"),
        ("from-sky-500 to-indigo-600", "آبی"),
        ("from-orange-400 to-amber-600", "نارنجی"),
        ("from-slate-700 to-slate-900", "تیره"),
        ("from-violet-600 to-purple-800", "بنفش"),
        ("from-cyan-500 to-teal-700", "فیروزه‌ای"),
        ("from-rose-500 to-red-700", "قرمز"),
        ("from-brand-600 to-brand-900", "سرمه‌ای"),
    ]

    seller = models.ForeignKey(Seller, on_delete=models.PROTECT, default=default_seller_id, verbose_name="فروشنده")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products", verbose_name="دسته")
    title = models.CharField("عنوان", max_length=150)
    brand = models.CharField("سازنده / زیرعنوان", max_length=60, blank=True, help_text="مثلاً OpenAI")
    slug = models.SlugField("نامک", max_length=160, unique=True, allow_unicode=True)
    keywords = models.TextField(
        "کلیدواژه‌های جست‌وجو",
        blank=True,
        help_text="نام‌های هم‌معنی، هر کدام در یک خط؛ مثلاً: جمینای، gemini، هوش مصنوعی گوگل",
    )
    image = models.ImageField("تصویر", upload_to="products/", blank=True)
    monogram = models.CharField("حروف جایگزین تصویر", max_length=4, blank=True, help_text="وقتی تصویر ندارد؛ مثلاً GPT")
    tint = models.CharField("رنگ جایگزین تصویر", max_length=60, choices=TINTS, default=TINTS[-1][0])
    short_features = models.TextField("ویژگی‌های کوتاه", blank=True, help_text="هر ویژگی در یک خط")
    description = models.TextField("توضیحات", blank=True)
    usage_guide = models.TextField("راهنمای استفاده", blank=True)
    warranty_text = models.TextField("متن گارانتی", blank=True)
    related = models.ManyToManyField("self", blank=True, verbose_name="محصولات مشابه")
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    is_featured = models.BooleanField("نمایش در پرفروش‌ها", default=False)
    sort_order = models.PositiveIntegerField("ترتیب", default=0)
    search_text = models.TextField(editable=False, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "محصول"
        verbose_name_plural = "محصولات"
        ordering = ["sort_order", "-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("storefront:product", args=[self.slug])

    @property
    def mono(self):
        return self.monogram or self.title[:2]

    @property
    def feature_list(self):
        return [line.strip() for line in self.short_features.splitlines() if line.strip()]

    @property
    def keyword_list(self):
        return [k.strip() for k in self.keywords.replace("،", "\n").replace(",", "\n").splitlines() if k.strip()]


class ProductSpec(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="specs")
    name = models.CharField("عنوان", max_length=80)
    value = models.CharField("مقدار", max_length=255)
    sort_order = models.PositiveIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name = "مشخصه"
        verbose_name_plural = "مشخصات"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class ProductFaq(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="faqs")
    question = models.CharField("پرسش", max_length=255)
    answer = models.TextField("پاسخ")
    sort_order = models.PositiveIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name = "پرسش"
        verbose_name_plural = "پرسش‌ها"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.question


class Variant(models.Model):
    class DeliveryType(models.TextChoices):
        STOCK = "stock", "خودکار از انبار"
        MANUAL = "manual", "دستی توسط اپراتور"

    class AccountType(models.TextChoices):
        SHARED = "shared", "اشتراکی"
        PRIVATE = "private", "اختصاصی (روی ایمیل مشتری)"

    class AccountField(models.TextChoices):
        GMAIL = "gmail", "جیمیل (فقط ‎@gmail.com‎)"
        EMAIL = "email", "ایمیل (هر ایمیل معتبر)"

    class PricingMode(models.TextChoices):
        FIXED = "fixed", "قیمت ثابت تومانی"
        USD = "usd", "قیمت دلاری با درصد حاشیه"

    class Status(models.TextChoices):
        ACTIVE = "active", "فعال"
        INACTIVE = "inactive", "غیرفعال"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants", verbose_name="محصول")
    seller = models.ForeignKey(Seller, on_delete=models.PROTECT, default=default_seller_id, verbose_name="فروشنده")
    name = models.CharField("نام", max_length=80, help_text="مثلاً «یک‌ماهه اختصاصی»")
    delivery_type = models.CharField("نوع تحویل", max_length=10, choices=DeliveryType.choices, default=DeliveryType.STOCK)
    account_type = models.CharField("نوع اکانت", max_length=10, choices=AccountType.choices, default=AccountType.SHARED)
    account_field_type = models.CharField(
        "نوع فیلد شناسه اکانت", max_length=10, choices=AccountField.choices, default=AccountField.EMAIL,
        help_text="فقط برای اکانت اختصاصی؛ برای محصولات گوگل «جیمیل» را انتخاب کنید.",
    )
    account_field_help = models.CharField(
        "راهنمای فیلد اکانت", max_length=200, blank=True,
        help_text="مثلاً: فقط حساب شخصی جیمیل؛ حساب‌های سازمانی پشتیبانی نمی‌شوند.",
    )

    pricing_mode = models.CharField("روش قیمت‌گذاری", max_length=10, choices=PricingMode.choices, default=PricingMode.FIXED)
    fixed_price = models.DecimalField("قیمت ثابت (تومان)", **TOMAN, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    usd_price = models.DecimalField("قیمت دلاری", **USD, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    margin_percent = models.DecimalField(
        "درصد حاشیه", max_digits=5, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("500"))],
    )
    price = models.DecimalField("قیمت فروش فعلی (تومان)", **TOMAN, default=Decimal("0"), editable=False)
    compare_at_price = models.DecimalField("قیمت قبل از تخفیف (تومان)", **TOMAN, null=True, blank=True)

    duration_days = models.PositiveIntegerField("مدت اشتراک (روز)", default=30)
    warranty_days = models.PositiveIntegerField("مدت گارانتی (روز)", default=30)
    delivery_deadline_hours = models.PositiveIntegerField("مهلت تحویل (ساعت)", default=0, help_text="برای تحویل دستی")
    delivery_template = models.TextField(
        "قالب نمایش اطلاعات تحویل", blank=True, help_text="مثلاً: ایمیل: {0} / رمز: {1}  (بخش‌های هر آیتم با | جدا می‌شوند)"
    )
    low_stock_threshold = models.PositiveIntegerField("آستانه هشدار موجودی", default=3)
    low_stock_alerted = models.BooleanField(default=False, editable=False)

    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    sort_order = models.PositiveIntegerField("ترتیب", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تنوع"
        verbose_name_plural = "تنوع‌ها"
        ordering = ["sort_order", "id"]
        constraints = [
            models.CheckConstraint(
                name="variant_pricing_complete",
                condition=Q(pricing_mode="fixed", fixed_price__isnull=False) | Q(pricing_mode="usd", usd_price__isnull=False),
            ),
        ]

    def __str__(self):
        return f"{self.product.title} · {self.name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        if self.pricing_mode == self.PricingMode.FIXED and self.fixed_price is None:
            errors["fixed_price"] = "برای قیمت ثابت، مبلغ تومانی را وارد کنید."
        if self.pricing_mode == self.PricingMode.USD and self.usd_price is None:
            errors["usd_price"] = "برای قیمت دلاری، مبلغ دلاری را وارد کنید."
        if self.delivery_type == self.DeliveryType.MANUAL and not self.delivery_deadline_hours:
            errors["delivery_deadline_hours"] = "برای تحویل دستی، مهلت تحویل را مشخص کنید."
        if errors:
            raise ValidationError(errors)

    @property
    def delivery_label(self):
        from apps.core.templatetags.persian import to_persian_digits as fa

        if self.delivery_type == self.DeliveryType.STOCK:
            return "تحویل فوری"
        if self.is_private:
            return f"فعال‌سازی روی ایمیل شما، حداکثر {fa(self.delivery_deadline_hours)} ساعت"
        return f"تحویل حداکثر {fa(self.delivery_deadline_hours)} ساعت"

    @property
    def warranty_label(self):
        from apps.core.templatetags.persian import to_persian_digits as fa

        return f"گارانتی {fa(self.warranty_days)} روزه" if self.warranty_days else "بدون گارانتی"

    @property
    def is_private(self):
        return self.account_type == self.AccountType.PRIVATE

    @property
    def is_instant(self):
        return self.delivery_type == self.DeliveryType.STOCK

    def available_count(self):
        return self.inventory_items.filter(status=InventoryItem.Status.AVAILABLE).count()


class InventoryItem(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "موجود"
        RESERVED = "reserved", "رزرو شده"
        SOLD = "sold", "فروخته شده"
        VOIDED = "voided", "باطل شده"

    variant = models.ForeignKey(Variant, on_delete=models.PROTECT, related_name="inventory_items", verbose_name="تنوع")
    seller = models.ForeignKey(Seller, on_delete=models.PROTECT, default=default_seller_id, verbose_name="فروشنده")
    encrypted_data = models.BinaryField("اطلاعات تحویل (رمزنگاری‌شده)", editable=False)
    fingerprint = models.CharField(max_length=64, editable=False)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.AVAILABLE, db_index=True)
    purchase_price = models.DecimalField("قیمت خرید (تومان)", **TOMAN, null=True, blank=True)
    expires_at = models.DateField("انقضا", null=True, blank=True)
    batch_label = models.CharField("برچسب محموله", max_length=60, blank=True, db_index=True)
    created_at = models.DateTimeField("زمان ورود", auto_now_add=True)
    created_by = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.SET_NULL, editable=False, verbose_name="واردکننده"
    )

    class Meta:
        verbose_name = "آیتم انبار"
        verbose_name_plural = "انبار"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["variant", "fingerprint"], name="inventory_unique_per_variant"),
        ]
        permissions = [("reveal_inventoryitem", "Can reveal delivery data")]

    def __str__(self):
        return f"#{self.pk} · {self.variant}"


class Redirect(models.Model):
    """Permanent (301) redirects, created automatically when a slug changes."""

    old_path = models.CharField("آدرس قدیم", max_length=300, unique=True)
    new_path = models.CharField("آدرس جدید", max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "هدایت ۳۰۱"
        verbose_name_plural = "هدایت‌های ۳۰۱"

    def __str__(self):
        return f"{self.old_path} → {self.new_path}"
