from django.contrib import admin

from .models import DiscountCode, Order, OrderEvent, OrderItem


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class OrderItemInline(ReadOnlyInline):
    model = OrderItem
    fields = ("product_title", "variant_name", "delivery_type", "unit_price", "account_identifier", "status", "inventory_item", "delivered_at")
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


@admin.register(DiscountCode)
class DiscountCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "kind", "value", "max_discount", "min_order_amount", "max_uses", "is_active", "ends_at")
    list_filter = ("is_active", "kind")
    search_fields = ("code",)
