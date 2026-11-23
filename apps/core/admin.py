from django.contrib import admin, messages

from .models import AuditLog, ExchangeRate


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("toman_per_usd", "created_at", "created_by")
    fields = ("toman_per_usd",)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        from apps.catalog.pricing import reprice_usd_variants

        obj.created_by = request.user
        super().save_model(request, obj, form, change)
        count = reprice_usd_variants(obj)
        messages.info(request, f"قیمت {count} تنوع دلاری با نرخ جدید به‌روز شد.")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "object_id", "detail", "ip_address")
    list_filter = ("action", "object_type")
    search_fields = ("object_id", "detail", "actor__username")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
