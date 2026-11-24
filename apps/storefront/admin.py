from django.contrib import admin

from .models import HomeBanner


@admin.register(HomeBanner)
class HomeBannerAdmin(admin.ModelAdmin):
    list_display = ("title", "link", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
