from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("__str__", "signup_channel", "last_email", "is_active", "created_at", "last_login_at")
    list_filter = ("signup_channel", "is_active", "notify_reminders", "notify_marketing")
    search_fields = ("mobile", "telegram_user_id", "last_email")
    readonly_fields = ("signup_channel", "mobile", "telegram_user_id", "created_at", "last_login_at", "campaign")
    fields = (
        ("signup_channel", "is_active"),
        ("mobile", "telegram_user_id"),
        "last_email",
        ("notify_reminders", "notify_marketing"),
        "campaign",
        ("created_at", "last_login_at"),
    )

    def has_add_permission(self, request):
        # Customers sign up themselves via SMS code or Telegram.
        return False

    def has_delete_permission(self, request, obj=None):
        return False
