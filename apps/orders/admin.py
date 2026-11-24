from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.core.models import AuditLog
from apps.core.templatetags.persian import jdate

from . import delivery as delivery_ops
from .models import Delivery, DiscountCode, ManualQueueItem, Order, OrderEvent, OrderItem


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class OrderItemInline(ReadOnlyInline):
    model = OrderItem
    fields = ("product_title", "variant_name", "delivery_type", "unit_price", "account_identifier", "status", "assigned_to", "delivered_at")
    readonly_fields = fields


class OrderEventInline(ReadOnlyInline):
    model = OrderEvent
    fields = ("created_at", "event", "from_status", "to_status", "actor_type", "actor_id", "note")
    readonly_fields = fields


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "customer", "channel", "status", "needs_refund", "total", "created_at", "paid_at")
    list_filter = ("status", "needs_refund", "channel")
    search_fields = ("id", "customer__mobile", "customer__telegram_user_id", "items__account_identifier")
    list_select_related = ("customer",)
    inlines = [OrderItemInline, OrderEventInline]
    readonly_fields = [f.name for f in Order._meta.fields] + ["number"]

    @admin.display(description="شماره", ordering="id")
    def number(self, obj):
        return obj.number

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class DeliverForm(forms.Form):
    note = forms.CharField(
        label="اطلاعات تحویل برای مشتری",
        widget=forms.Textarea(attrs={"rows": 5, "style": "width:100%"}),
        help_text="مثلاً «اشتراک روی ایمیل شما فعال شد» یا اطلاعات ورود اکانت. رمزنگاری ذخیره می‌شود و فقط در صفحه سفارش مشتری دیده می‌شود.",
    )
    subscription_ends_at = forms.DateTimeField(
        label="پایان اشتراک (اختیاری)", required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        help_text="خالی بماند تا از مدت تنوع حساب شود.",
    )


class RejectForm(forms.Form):
    reason = forms.CharField(label="دلیل رد", max_length=255)


@admin.register(ManualQueueItem)
class ManualQueueAdmin(admin.ModelAdmin):
    list_display = ("order_link", "product_title", "variant_name", "account_identifier", "deadline_display", "assigned_to", "actions_display")
    list_filter = ("assigned_to",)
    search_fields = ("order__id", "account_identifier", "product_title")
    list_select_related = ("order", "assigned_to")
    ordering = ("deadline_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(status=OrderItem.Status.AWAITING_DELIVERY)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="سفارش")
    def order_link(self, obj):
        return format_html('<a href="{}">{}</a>', reverse("admin:orders_order_change", args=[obj.order_id]), obj.order.number)

    @admin.display(description="مهلت تحویل", ordering="deadline_at")
    def deadline_display(self, obj):
        if not obj.deadline_at:
            return "-"
        late = obj.deadline_at < timezone.now()
        return format_html('<b style="color:{}">{}{}</b>', "#c0392b" if late else "inherit",
                           jdate(obj.deadline_at, "datetime"), " (گذشته)" if late else "")

    @admin.display(description="عملیات")
    def actions_display(self, obj):
        return format_html('<a class="button" href="{}">باز کردن</a>', reverse("admin:orders_manualqueueitem_work", args=[obj.pk]))

    def get_urls(self):
        return [path("<int:pk>/work/", self.admin_site.admin_view(self.work_view), name="orders_manualqueueitem_work"),
                *super().get_urls()]

    def work_view(self, request, pk):
        if not request.user.has_perm("orders.view_manualqueueitem"):
            raise PermissionDenied
        item = get_object_or_404(OrderItem.objects.select_related("order__customer", "variant", "assigned_to"), pk=pk)
        deliver_form = DeliverForm(request.POST if request.POST.get("action") == "deliver" else None)
        reject_form = RejectForm(request.POST if request.POST.get("action") == "reject" else None)

        if request.method == "POST":
            if not request.user.has_perm("orders.change_manualqueueitem"):
                raise PermissionDenied
            action = request.POST.get("action")
            try:
                if action == "claim":
                    delivery_ops.claim(item.pk, request.user)
                    messages.success(request, "این قلم به نام شما برداشته شد.")
                    return redirect(request.path)
                if action == "deliver" and deliver_form.is_valid():
                    delivery_ops.deliver_manual(item.pk, request.user, note=deliver_form.cleaned_data["note"],
                                                subscription_ends_at=deliver_form.cleaned_data["subscription_ends_at"])
                    messages.success(request, "تحویل ثبت شد و به مشتری اطلاع داده می‌شود.")
                    return redirect("admin:orders_manualqueueitem_changelist")
                if action == "reject" and reject_form.is_valid():
                    delivery_ops.reject_manual(item.pk, request.user, reason=reject_form.cleaned_data["reason"])
                    messages.warning(request, "قلم رد شد و سفارش به صف بازگشت وجه رفت.")
                    return redirect("admin:orders_manualqueueitem_changelist")
            except delivery_ops.DeliveryError as exc:
                messages.error(request, exc.message)

        if item.account_identifier:
            AuditLog.record(request, "view_manual_item", item)
        context = {
            **self.admin_site.each_context(request),
            "title": f"تحویل دستی: {item}",
            "item": item,
            "deliver_form": deliver_form,
            "reject_form": reject_form,
            "is_mine": item.assigned_to_id == request.user.pk,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/orders/manual_work.html", context)


class DeliveryAdminForm(forms.ModelForm):
    class Meta:
        model = Delivery
        fields = ("subscription_ends_at",)


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    form = DeliveryAdminForm
    list_display = ("item", "order_number", "delivered_at", "subscription_ends_at", "warranty_ends_at", "renewed_at")
    list_filter = ("renewed_at",)
    search_fields = ("item__order__id", "item__account_identifier")
    list_select_related = ("item__order",)
    readonly_fields = ("item", "delivered_at", "warranty_ends_at", "delivered_by", "renewed_at")
    fields = ("item", "delivered_at", "subscription_ends_at", "warranty_ends_at", "delivered_by", "renewed_at")

    @admin.display(description="سفارش")
    def order_number(self, obj):
        return obj.item.order.number

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if change and "subscription_ends_at" in form.changed_data:
            delivery_ops.update_subscription_end(obj, form.cleaned_data["subscription_ends_at"], request.user)
        else:
            super().save_model(request, obj, form, change)


@admin.register(DiscountCode)
class DiscountCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "kind", "value", "max_discount", "min_order_amount", "max_uses", "is_active", "ends_at")
    list_filter = ("is_active", "kind")
    search_fields = ("code",)
