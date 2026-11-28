from django.db import models
from django.urls import reverse

TOMAN = {"max_digits": 15, "decimal_places": 0}


class Ticket(models.Model):
    class Kind(models.TextChoices):
        GENERAL = "general", "عمومی"
        WARRANTY = "warranty", "گارانتی"
        REFUND = "refund", "بازگشت وجه"

    class Status(models.TextChoices):
        OPEN = "open", "باز"
        ANSWERED = "answered", "پاسخ داده شده"
        CLOSED = "closed", "بسته"

    customer = models.ForeignKey("accounts.Customer", on_delete=models.PROTECT, related_name="tickets", verbose_name="مشتری")
    kind = models.CharField("نوع", max_length=10, choices=Kind.choices, default=Kind.GENERAL, db_index=True)
    subject = models.CharField("موضوع", max_length=150)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    order = models.ForeignKey("orders.Order", null=True, blank=True, on_delete=models.SET_NULL, verbose_name="سفارش")
    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین تغییر", auto_now=True, db_index=True)

    class Meta:
        verbose_name = "تیکت"
        verbose_name_plural = "تیکت‌ها"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"#{self.pk} {self.subject}"

    def get_absolute_url(self):
        return reverse("support:ticket", args=[self.pk])


class TicketMessage(models.Model):
    class Author(models.TextChoices):
        CUSTOMER = "customer", "مشتری"
        STAFF = "staff", "پشتیبانی"
        SYSTEM = "system", "سیستم"

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    author_type = models.CharField(max_length=10, choices=Author.choices)
    staff = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    body = models.TextField("متن")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "پیام تیکت"
        verbose_name_plural = "پیام‌های تیکت"
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.get_author_type_display()}: {self.body[:40]}"


class Refund(models.Model):
    """One payout to a customer's card. The finance manager's queue."""

    class Reason(models.TextChoices):
        LATE_PAYMENT = "late_payment", "پرداخت بعد از انقضای رزرو"
        ITEM_REJECTED = "item_rejected", "قلم توسط اپراتور رد شد"
        WARRANTY = "warranty", "گارانتی"

    class Status(models.TextChoices):
        AWAITING_CARD = "awaiting_card", "منتظر شماره کارت مشتری"
        READY = "ready", "آماده واریز"
        PAID = "paid", "واریز شد"
        CANCELED = "canceled", "لغو شد"

    class Method(models.TextChoices):
        MANUAL = "manual", "واریز دستی"
        GATEWAY = "gateway", "برگشت از درگاه"

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="refunds", verbose_name="سفارش")
    order_item = models.ForeignKey("orders.OrderItem", null=True, blank=True, on_delete=models.PROTECT,
                                   related_name="refunds", verbose_name="قلم")
    ticket = models.ForeignKey(Ticket, null=True, blank=True, on_delete=models.SET_NULL, related_name="refunds", verbose_name="تیکت")
    reason = models.CharField("دلیل", max_length=20, choices=Reason.choices)
    amount = models.DecimalField("مبلغ (تومان)", **TOMAN)
    status = models.CharField("وضعیت", max_length=15, choices=Status.choices, default=Status.AWAITING_CARD, db_index=True)
    key = models.CharField(max_length=60, unique=True, help_text="Prevents creating the same refund twice.")
    card_encrypted = models.BinaryField(null=True, blank=True, editable=False)
    card_masked = models.CharField("کارت", max_length=19, blank=True)
    method = models.CharField("روش", max_length=10, choices=Method.choices, blank=True)
    tracking_number = models.CharField("شماره پیگیری", max_length=60, blank=True)
    paid_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="واریزکننده")
    paid_at = models.DateTimeField("زمان واریز", null=True, blank=True)
    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "بازگشت وجه"
        verbose_name_plural = "صف بازگشت وجه"
        ordering = ["created_at"]
        permissions = [("reveal_card", "Can reveal the destination card number")]

    def __str__(self):
        return f"بازگشت {self.amount:,} تومان · {self.order}"


class WarrantyClaim(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در حال بررسی"
        REPLACED = "replaced", "تعویض شد"
        REFUND_REQUESTED = "refund_requested", "ارجاع به مدیر مالی"
        REFUNDED = "refunded", "بازگشت وجه"
        REJECTED = "rejected", "رد شد"

    ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE, related_name="claim", verbose_name="تیکت")
    order_item = models.ForeignKey("orders.OrderItem", on_delete=models.PROTECT, related_name="claims", verbose_name="قلم")
    status = models.CharField("وضعیت", max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    resolution_note = models.CharField("توضیح نتیجه", max_length=255, blank=True)
    old_inventory_item = models.ForeignKey("catalog.InventoryItem", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    new_inventory_item = models.ForeignKey("catalog.InventoryItem", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    refund = models.OneToOneField(Refund, null=True, blank=True, on_delete=models.SET_NULL, related_name="claim")
    resolved_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "درخواست گارانتی"
        verbose_name_plural = "درخواست‌های گارانتی"
        ordering = ["-created_at"]
        permissions = [
            ("resolve_warranty", "Can replace or reject warranty claims"),
            ("approve_refund", "Can approve warranty refunds"),
        ]

    def __str__(self):
        return f"گارانتی {self.order_item}"
