from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse

from apps.accounts.models import Customer
from apps.catalog.models import InventoryItem, Seller, Variant

TOMAN = {"max_digits": 15, "decimal_places": 0}
MAX_QUANTITY = 5


class Cart(models.Model):
    """A signed-in customer's cart, or a guest cart bound to the browser session."""

    customer = models.OneToOneField(Customer, null=True, blank=True, on_delete=models.CASCADE, related_name="cart")
    notification_email = models.EmailField(blank=True)
    discount_code = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "سبد خرید"
        verbose_name_plural = "سبدهای خرید"

    def __str__(self):
        return f"Cart #{self.pk}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE)
    quantity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(MAX_QUANTITY)])
    account_identifier = models.CharField(max_length=254, blank=True)
    renews = models.ForeignKey("Delivery", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at", "id"]
        constraints = [models.UniqueConstraint(fields=["cart", "variant"], name="cart_unique_variant")]

    def __str__(self):
        return f"{self.variant} × {self.quantity}"


class DiscountCode(models.Model):
    class Kind(models.TextChoices):
        PERCENT = "percent", "درصدی"
        AMOUNT = "amount", "مبلغ ثابت"

    code = models.CharField("کد", max_length=40, unique=True, help_text="بزرگی و کوچکی حروف مهم نیست.")
    kind = models.CharField("نوع", max_length=10, choices=Kind.choices, default=Kind.PERCENT)
    value = models.DecimalField("مقدار", max_digits=15, decimal_places=0, validators=[MinValueValidator(Decimal("1"))],
                                help_text="درصد (۱ تا ۱۰۰) یا مبلغ تومانی")
    max_discount = models.DecimalField("سقف تخفیف (تومان)", **TOMAN, null=True, blank=True)
    min_order_amount = models.DecimalField("حداقل مبلغ سبد (تومان)", **TOMAN, default=Decimal("0"))
    starts_at = models.DateTimeField("شروع", null=True, blank=True)
    ends_at = models.DateTimeField("پایان", null=True, blank=True)
    max_uses = models.PositiveIntegerField("سقف کل استفاده", null=True, blank=True)
    max_uses_per_customer = models.PositiveIntegerField("سقف استفاده هر مشتری", default=1)
    is_active = models.BooleanField("فعال", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "کد تخفیف"
        verbose_name_plural = "کدهای تخفیف"

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "در انتظار پرداخت"
        EXPIRED = "expired", "منقضی شده"
        CANCELED = "canceled", "لغو شده"
        PAID = "paid", "پرداخت شده"
        PROCESSING = "processing", "در حال تحویل"
        DELIVERED = "delivered", "تحویل شده"
        REFUNDED = "refunded", "بازگشت وجه شده"

    class Channel(models.TextChoices):
        WEB = "web", "سایت"
        TELEGRAM = "telegram", "تلگرام"

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders", verbose_name="مشتری")
    channel = models.CharField("کانال", max_length=10, choices=Channel.choices, default=Channel.WEB)
    status = models.CharField("وضعیت", max_length=20, choices=Status.choices, default=Status.PENDING_PAYMENT, db_index=True)
    needs_refund = models.BooleanField("بازگشت وجه لازم", default=False, db_index=True)
    subtotal = models.DecimalField("جمع اقلام", **TOMAN)
    discount_amount = models.DecimalField("تخفیف", **TOMAN, default=Decimal("0"))
    total = models.DecimalField("مبلغ قابل پرداخت", **TOMAN)
    discount_code = models.ForeignKey(DiscountCode, null=True, blank=True, on_delete=models.PROTECT, verbose_name="کد تخفیف")
    notification_email = models.EmailField("ایمیل اطلاع‌رسانی", blank=True)
    reserved_until = models.DateTimeField("مهلت رزرو")
    paid_at = models.DateTimeField("زمان پرداخت", null=True, blank=True)
    created_at = models.DateTimeField("زمان ثبت", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(name="order_total_consistent", condition=Q(total__gte=0) & Q(discount_amount__gte=0)),
        ]

    def __str__(self):
        return f"سفارش {self.number}"

    @property
    def number(self):
        return 100000 + self.pk if self.pk else None

    @classmethod
    def pk_from_number(cls, number):
        try:
            return int(number) - 100000
        except (TypeError, ValueError):
            return None

    def get_absolute_url(self):
        return reverse("orders:detail", args=[self.number])

    @property
    def is_payable(self):
        return self.status == self.Status.PENDING_PAYMENT


class OrderItem(models.Model):
    """One unit of a variant. Each unit has its own delivery status and inventory item."""

    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", "در انتظار پرداخت"
        AWAITING_DELIVERY = "awaiting_delivery", "در انتظار تحویل"
        DELIVERED = "delivered", "تحویل شده"
        CANCELED = "canceled", "لغو شده"
        REFUNDED = "refunded", "بازگشت وجه شده"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(Variant, on_delete=models.PROTECT)
    seller = models.ForeignKey(Seller, on_delete=models.PROTECT)
    product_title = models.CharField(max_length=150)
    variant_name = models.CharField(max_length=80)
    delivery_type = models.CharField(max_length=10, choices=Variant.DeliveryType.choices)
    unit_price = models.DecimalField(**TOMAN)
    compare_at_price = models.DecimalField(**TOMAN, null=True, blank=True)
    duration_days = models.PositiveIntegerField()
    warranty_days = models.PositiveIntegerField()
    account_identifier = models.CharField(max_length=254, blank=True)
    inventory_item = models.OneToOneField(
        InventoryItem, null=True, blank=True, on_delete=models.PROTECT, related_name="order_item"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AWAITING_PAYMENT, db_index=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    # Manual delivery queue
    deadline_at = models.DateTimeField("مهلت تحویل", null=True, blank=True, db_index=True)
    assigned_to = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                    verbose_name="اپراتور")
    claimed_at = models.DateTimeField("زمان برداشتن", null=True, blank=True)
    overdue_alerted = models.BooleanField(default=False)
    renews = models.ForeignKey("Delivery", null=True, blank=True, on_delete=models.SET_NULL, related_name="renewed_by_items")

    class Meta:
        verbose_name = "قلم سفارش"
        verbose_name_plural = "اقلام سفارش"
        ordering = ["id"]

    def __str__(self):
        return f"{self.product_title} · {self.variant_name}"


class ManualQueueItem(OrderItem):
    """Admin view of order items waiting for an operator to deliver them."""

    class Meta:
        proxy = True
        verbose_name = "قلم منتظر تحویل دستی"
        verbose_name_plural = "صف تحویل دستی"


class Delivery(models.Model):
    """A delivered unit: when its subscription and warranty end, and whether it was renewed."""

    item = models.OneToOneField(OrderItem, on_delete=models.CASCADE, related_name="delivery", verbose_name="قلم")
    delivered_at = models.DateTimeField("زمان تحویل")
    subscription_ends_at = models.DateTimeField("پایان اشتراک", db_index=True)
    warranty_ends_at = models.DateTimeField("پایان گارانتی")
    encrypted_note = models.BinaryField("اطلاعات تحویل دستی (رمزنگاری‌شده)", null=True, blank=True, editable=False)
    delivered_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                     verbose_name="تحویل‌دهنده")
    renewed_at = models.DateTimeField("زمان تمدید", null=True, blank=True)

    class Meta:
        verbose_name = "تحویل"
        verbose_name_plural = "تحویل‌ها"
        ordering = ["-delivered_at"]

    def __str__(self):
        return f"تحویل {self.item}"


class OrderEvent(models.Model):
    """Append-only history of every status change, with time and actor."""

    class Actor(models.TextChoices):
        SYSTEM = "system", "سیستم"
        CUSTOMER = "customer", "مشتری"
        STAFF = "staff", "کارمند"
        GATEWAY = "gateway", "درگاه"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    item = models.ForeignKey(OrderItem, null=True, blank=True, on_delete=models.CASCADE, related_name="events")
    event = models.CharField(max_length=40)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    actor_type = models.CharField(max_length=10, choices=Actor.choices, default=Actor.SYSTEM)
    actor_id = models.CharField(max_length=40, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "رویداد سفارش"
        verbose_name_plural = "تاریخچه سفارش"
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.event}: {self.from_status} → {self.to_status}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Order events are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Order events are append-only.")


class DiscountRedemption(models.Model):
    discount = models.ForeignKey(DiscountCode, on_delete=models.PROTECT, related_name="redemptions")
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="redemption")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    amount = models.DecimalField(**TOMAN)
    created_at = models.DateTimeField(auto_now_add=True)
