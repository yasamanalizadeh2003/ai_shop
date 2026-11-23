from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from apps.core.crypto import DecryptionError

from . import inventory
from .models import Category, InventoryItem, Product, ProductFaq, ProductSpec, Redirect, Seller, Variant


@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ("name", "is_platform", "created_at")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active", "product_count")
    list_editable = ("sort_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)
    fieldsets = (
        (None, {"fields": ("name", "slug", "icon", "sort_order", "is_active")}),
        ("سئو", {"fields": ("description", "seo_title", "seo_description")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_products=Count("products"))

    @admin.display(description="تعداد محصول", ordering="_products")
    def product_count(self, obj):
        return obj._products


class SpecInline(admin.TabularInline):
    model = ProductSpec
    extra = 0


class FaqInline(admin.StackedInline):
    model = ProductFaq
    extra = 0


class VariantInline(admin.TabularInline):
    model = Variant
    extra = 0
    show_change_link = True
    fields = (
        "name", "delivery_type", "account_type", "pricing_mode", "fixed_price", "usd_price",
        "margin_percent", "price", "compare_at_price", "duration_days", "status",
    )
    readonly_fields = ("price",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "status", "is_featured", "variant_count", "updated_at")
    list_filter = ("status", "category", "is_featured")
    list_editable = ("status", "is_featured")
    search_fields = ("title", "brand", "keywords", "slug")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("related",)
    inlines = [VariantInline, SpecInline, FaqInline]
    fieldsets = (
        (None, {"fields": ("title", "brand", "slug", "category", "status", "is_featured", "sort_order")}),
        ("تصویر", {"fields": ("image", "monogram", "tint")}),
        ("محتوا", {"fields": ("short_features", "description", "usage_guide", "warranty_text", "related")}),
        ("جست‌وجو و سئو", {"fields": ("keywords", "seo_title", "seo_description")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_variants=Count("variants"))

    @admin.display(description="تنوع‌ها", ordering="_variants")
    def variant_count(self, obj):
        return obj._variants


class ImportForm(forms.Form):
    lines = forms.CharField(
        label="آیتم‌ها (هر خط یک آیتم)", required=False,
        widget=forms.Textarea(attrs={"rows": 10, "dir": "ltr", "style": "width: 100%; font-family: monospace"}),
        help_text="بخش‌های هر آیتم را با | جدا کنید؛ مثلاً: user@mail.com|password",
    )
    csv_file = forms.FileField(label="یا فایل CSV", required=False, help_text="ستون اول اطلاعات تحویل؛ ستون‌های بعدی با | به هم وصل می‌شوند.")
    purchase_price = forms.CharField(label="قیمت خرید هر آیتم (تومان)", required=False)
    expires_at = forms.DateField(label="تاریخ انقضا", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    batch_label = forms.CharField(label="برچسب محموله", required=False, max_length=60)


@admin.register(Variant)
class VariantAdmin(admin.ModelAdmin):
    list_display = ("__str__", "delivery_type", "pricing_mode", "price", "stock_display", "status")
    list_filter = ("status", "delivery_type", "pricing_mode", "account_type", "product__category")
    search_fields = ("name", "product__title")
    list_select_related = ("product",)
    readonly_fields = ("price", "stock_display", "import_link")
    autocomplete_fields = ("product",)
    fieldsets = (
        (None, {"fields": ("product", "name", "status", "sort_order")}),
        ("قیمت", {"fields": ("pricing_mode", "fixed_price", "usd_price", "margin_percent", "price", "compare_at_price")}),
        ("تحویل", {"fields": ("delivery_type", "delivery_deadline_hours", "delivery_template", "duration_days", "warranty_days")}),
        ("فرم اطلاعات مشتری", {"fields": ("account_type", "account_field_type", "account_field_help")}),
        ("انبار", {"fields": ("low_stock_threshold", "stock_display", "import_link")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _available=Count("inventory_items", filter=Q(inventory_items__status=InventoryItem.Status.AVAILABLE))
        )

    @admin.display(description="موجودی", ordering="_available")
    def stock_display(self, obj):
        if obj.delivery_type == Variant.DeliveryType.MANUAL:
            return "دستی"
        available = getattr(obj, "_available", None)
        if available is None:
            available = obj.available_count()
        color = "#c0392b" if available < obj.low_stock_threshold else "inherit"
        return format_html('<b style="color:{}">{}</b>', color, available)

    @admin.display(description="ورود انبار")
    def import_link(self, obj):
        if not obj.pk:
            return "پس از ذخیره تنوع"
        return format_html('<a class="button" href="{}">ورود آیتم‌های انبار</a>', reverse("admin:catalog_variant_import", args=[obj.pk]))

    def get_urls(self):
        return [
            path("<int:pk>/import/", self.admin_site.admin_view(self.import_view), name="catalog_variant_import"),
            *super().get_urls(),
        ]

    def import_view(self, request, pk):
        if not request.user.has_perm("catalog.add_inventoryitem"):
            raise PermissionDenied
        variant = get_object_or_404(Variant.objects.select_related("product"), pk=pk)
        preview = None
        form = ImportForm(request.POST or None, request.FILES or None)

        if request.method == "POST" and form.is_valid():
            lines = inventory.parse_lines(form.cleaned_data["lines"], form.cleaned_data["csv_file"])
            try:
                purchase_price = inventory.parse_price(form.cleaned_data["purchase_price"])
                if "confirm" in request.POST:
                    created = inventory.import_items(
                        variant, lines, user=request.user, purchase_price=purchase_price,
                        expires_at=form.cleaned_data["expires_at"], batch_label=form.cleaned_data["batch_label"],
                    )
                    messages.success(request, f"{created} آیتم به انبار «{variant}» اضافه شد. تکراری‌ها رد شدند.")
                    return redirect("admin:catalog_variant_change", variant.pk)
                preview = inventory.build_preview(variant, lines)
                if not preview.rows:
                    messages.warning(request, "هیچ آیتمی وارد نشده است.")
            except ValueError as exc:
                messages.error(request, str(exc))

        context = {
            **self.admin_site.each_context(request),
            "title": f"ورود انبار: {variant}",
            "variant": variant,
            "form": form,
            "preview": preview,
            "opts": self.model._meta,
            "normalized_lines": "\n".join(r.data for r in preview.new_rows) if preview else "",
            "counts": {s: preview.count(s) for s in ("duplicate_in_file", "duplicate_existing", "invalid")} if preview else {},
        }
        return TemplateResponse(request, "admin/catalog/variant_import.html", context)


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ("id", "variant", "status", "batch_label", "purchase_price", "expires_at", "created_at")
    list_filter = ("status", "variant__product", "batch_label")
    search_fields = ("id", "batch_label", "variant__product__title")
    list_select_related = ("variant__product",)
    readonly_fields = ("variant", "seller", "status", "purchase_price", "expires_at", "batch_label", "created_at", "created_by", "delivery_data")
    actions = ["void_selected"]
    change_form_template = "admin/catalog/inventoryitem_change_form.html"

    def has_add_permission(self, request):
        # Items are added through the variant's import page (encryption + duplicate check).
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="اطلاعات تحویل")
    def delivery_data(self, obj):
        return "•••••••• (پنهان؛ دکمه «نمایش» پایین صفحه)"

    def get_urls(self):
        return [
            path("<int:pk>/reveal/", self.admin_site.admin_view(require_POST(self.reveal_view)), name="catalog_inventoryitem_reveal"),
            *super().get_urls(),
        ]

    def reveal_view(self, request, pk):
        if not request.user.has_perm("catalog.reveal_inventoryitem"):
            raise PermissionDenied
        item = get_object_or_404(InventoryItem.objects.select_related("variant__product"), pk=pk)
        try:
            value = inventory.reveal(item, request)
        except DecryptionError:
            messages.error(request, "رمزگشایی ممکن نیست؛ کلید رمزنگاری را بررسی کنید.")
            return redirect("admin:catalog_inventoryitem_change", pk)
        context = {
            **self.admin_site.each_context(request),
            "title": f"اطلاعات تحویل آیتم #{item.pk}",
            "item": item,
            "value": value,
            "formatted": inventory.format_delivery(item.variant, value),
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/catalog/inventory_reveal.html", context)

    @admin.action(description="باطل کردن آیتم‌های موجود انتخاب‌شده", permissions=["change"])
    def void_selected(self, request, queryset):
        count = inventory.void_items(queryset, request)
        messages.success(request, f"{count} آیتم باطل شد.")


@admin.register(Redirect)
class RedirectAdmin(admin.ModelAdmin):
    list_display = ("old_path", "new_path", "created_at")
    search_fields = ("old_path", "new_path")
