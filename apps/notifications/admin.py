from django.contrib import admin

from .models import Message, MessageTemplate


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ("title", "event", "is_urgent", "can_opt_out", "is_active", "updated_at")
    list_filter = ("is_active", "is_urgent")
    readonly_fields = ("event",)
    fieldsets = (
        (None, {"fields": ("event", "title", "is_active", "is_urgent", "can_opt_out")}),
        ("پیامک", {"fields": ("sms_template", "sms_text")}),
        ("ایمیل", {"fields": ("email_subject", "email_body")}),
        ("تلگرام", {"fields": ("telegram_text",)}),
    )

    def has_add_permission(self, request):
        # Events are defined in code; their texts are edited here.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event", "channel", "recipient", "status", "attempts", "sent_at", "last_error")
    list_filter = ("status", "channel", "event")
    search_fields = ("recipient", "idempotency_key")
    readonly_fields = [f.name for f in Message._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
