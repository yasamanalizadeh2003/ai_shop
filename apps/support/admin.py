from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from apps.catalog.models import InventoryItem
from apps.orders.models import OrderItem

from . import services
from .models import Refund, Ticket, WarrantyClaim


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "kind", "status", "customer", "order", "updated_at", "open_link")
    list_filter = ("status", "kind")
    search_fields = ("id", "subject", "customer__mobile", "order__id")
    list_select_related = ("customer", "order")
    ordering = ("status", "-updated_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return redirect("admin:support_ticket_work", int(object_id))

    @admin.display(description="")
    def open_link(self, obj):
        return format_html('<a class="button" href="{}">باز کردن</a>', reverse("admin:support_ticket_work", args=[obj.pk]))

    def get_urls(self):
        return [path("<int:pk>/work/", self.admin_site.admin_view(self.work_view), name="support_ticket_work"),
                *super().get_urls()]

    def work_view(self, request, pk):
        if not request.user.has_perm("support.view_ticket"):
            raise PermissionDenied
        ticket = get_object_or_404(Ticket.objects.select_related("customer", "order"), pk=pk)
        claim = WarrantyClaim.objects.filter(ticket=ticket).select_related("order_item__delivery").first()

        if request.method == "POST":
            action = request.POST.get("action")
            needed = {
                "reply": "support.change_ticket", "close": "support.change_ticket",
                "replace": "support.resolve_warranty", "reject": "support.resolve_warranty",
                "refer": "support.resolve_warranty", "approve_refund": "support.approve_refund",
            }.get(action)
            if not needed or not request.user.has_perm(needed):
                raise PermissionDenied
            try:
                if action == "reply":
                    services.staff_reply(ticket, request.user, request.POST.get("body"), close=bool(request.POST.get("close_after")))
                    messages.success(request, "پاسخ ارسال شد و به مشتری اطلاع داده می‌شود.")
                elif action == "close":
                    services.close_ticket(ticket)
                elif action == "replace":
                    services.replace_item(claim.pk, request.user, note=request.POST.get("note"))
                    messages.success(request, "تعویض انجام شد.")
                elif action == "reject":
                    services.reject_claim(claim.pk, request.user, reason=request.POST.get("reason"))
                    messages.warning(request, "درخواست گارانتی رد شد.")
                elif action == "refer":
                    services.refer_to_finance(claim.pk, request.user, note=request.POST.get("note"))
                    messages.info(request, "به مدیر مالی ارجاع شد.")
                elif action == "approve_refund":
                    services.approve_warranty_refund(claim.pk, request.user, amount=request.POST.get("amount") or None)
                    messages.success(request, "بازگشت وجه تأیید شد و به صف واریز رفت.")
            except services.SupportError as exc:
                messages.error(request, exc.message)
            return redirect(request.path)

        context = {
            **self.admin_site.each_context(request),
            "title": f"تیکت #{ticket.pk}: {ticket.subject}",
            "ticket": ticket,
            "ticket_messages": ticket.messages.select_related("staff"),
            "claim": claim,
            "suggested_refund": services.prorated_refund(claim.order_item) if claim else None,
            "max_refund": services.paid_share(claim.order_item) if claim else None,
            "refunds": ticket.refunds.all(),
            "can_resolve": request.user.has_perm("support.resolve_warranty"),
            "can_approve": request.user.has_perm("support.approve_refund"),
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/support/ticket_work.html", context)


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "reason", "amount", "status", "card_masked", "created_at", "pay_link")
    list_filter = ("status", "reason")
    search_fields = ("order__id", "tracking_number", "card_masked")
    list_select_related = ("order",)
    readonly_fields = [f.name for f in Refund._meta.fields if f.name != "card_encrypted"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="")
    def pay_link(self, obj):
        if obj.status == Refund.Status.PAID:
            return obj.tracking_number
        return format_html('<a class="button" href="{}">ثبت واریز</a>', reverse("admin:support_refund_pay", args=[obj.pk]))

    def get_urls(self):
        return [
            path("<int:pk>/pay/", self.admin_site.admin_view(self.pay_view), name="support_refund_pay"),
            path("quality/", self.admin_site.admin_view(self.quality_view), name="support_quality_report"),
            *super().get_urls(),
        ]

    def pay_view(self, request, pk):
        if not request.user.has_perm("support.change_refund"):
            raise PermissionDenied
        refund = get_object_or_404(Refund.objects.select_related("order__customer", "order_item", "ticket"), pk=pk)
        card = None
        if request.method == "POST":
            action = request.POST.get("action")
            if action == "reveal":
                if not request.user.has_perm("support.reveal_card"):
                    raise PermissionDenied
                card = services.reveal_card(refund, request)
            elif action == "pay":
                try:
                    services.mark_refund_paid(refund.pk, request.user, tracking_number=request.POST.get("tracking_number"),
                                              method=request.POST.get("method") or Refund.Method.MANUAL)
                except services.SupportError as exc:
                    messages.error(request, exc.message)
                    return redirect(request.path)
                messages.success(request, "واریز ثبت شد، شماره کارت پاک شد و به مشتری اطلاع داده می‌شود.")
                return redirect("admin:support_refund_changelist")
        context = {
            **self.admin_site.each_context(request),
            "title": f"واریز بازگشت وجه #{refund.pk}",
            "refund": refund,
            "card": card,
            "methods": Refund.Method.choices,
            "can_reveal": request.user.has_perm("support.reveal_card"),
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/support/refund_pay.html", context)

    def quality_view(self, request):
        if not request.user.has_perm("support.view_warrantyclaim"):
            raise PermissionDenied
        delivered = Q(status__in=[OrderItem.Status.DELIVERED, OrderItem.Status.REFUNDED])
        by_product = (
            OrderItem.objects.filter(delivered)
            .values("variant__product__title")
            .annotate(
                delivered=Count("id"),
                replaced=Count("claims", filter=Q(claims__status=WarrantyClaim.Status.REPLACED), distinct=True),
                refunded=Count("claims", filter=Q(claims__status=WarrantyClaim.Status.REFUNDED), distinct=True),
            )
            .order_by("-delivered")
        )
        sold = InventoryItem.objects.filter(status__in=[InventoryItem.Status.SOLD, InventoryItem.Status.VOIDED])
        by_batch = []
        for row in sold.exclude(batch_label="").values("batch_label").annotate(sold=Count("id")).order_by("batch_label"):
            claims = WarrantyClaim.objects.filter(old_inventory_item__batch_label=row["batch_label"])
            refunds = WarrantyClaim.objects.filter(status=WarrantyClaim.Status.REFUNDED,
                                                   order_item__inventory_item__batch_label=row["batch_label"])
            by_batch.append({**row, "replaced": claims.count(), "refunded": refunds.count()})

        def pct(part, whole):
            return round(100 * part / whole, 1) if whole else 0

        rows = [{**r, "replaced_pct": pct(r["replaced"], r["delivered"]), "refunded_pct": pct(r["refunded"], r["delivered"])}
                for r in by_product]
        batches = [{**r, "replaced_pct": pct(r["replaced"], r["sold"]), "refunded_pct": pct(r["refunded"], r["sold"])}
                   for r in by_batch]
        context = {**self.admin_site.each_context(request), "title": "گزارش کیفیت: تعویض و بازگشت وجه",
                   "rows": rows, "batches": batches, "opts": self.model._meta}
        return TemplateResponse(request, "admin/support/quality.html", context)

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), "quality_url": reverse("admin:support_quality_report")}
        return super().changelist_view(request, extra_context)


@admin.register(WarrantyClaim)
class WarrantyClaimAdmin(admin.ModelAdmin):
    list_display = ("id", "order_item", "status", "resolved_by", "resolved_at", "created_at", "ticket_link")
    list_filter = ("status",)
    list_select_related = ("order_item", "resolved_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="تیکت")
    def ticket_link(self, obj):
        return format_html('<a href="{}">#{}</a>', reverse("admin:support_ticket_work", args=[obj.ticket_id]), obj.ticket_id)
