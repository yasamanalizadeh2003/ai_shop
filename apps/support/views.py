from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.session import get_customer
from apps.orders.models import Order, OrderItem

from . import services
from .models import Ticket


def _login_redirect(request):
    return redirect(f"{reverse('storefront:checkout')}?step=login&next={request.get_full_path()}")


def ticket_list(request):
    customer = get_customer(request)
    if not customer:
        return _login_redirect(request)
    tickets = customer.tickets.order_by("-updated_at")[:50]
    return render(request, "account/tickets.html", {"tickets": tickets, "nav": "tickets", "nav_active": "account"})


def ticket_new(request):
    customer = get_customer(request)
    if not customer:
        return _login_redirect(request)
    eligible = customer.orders.exclude(status__in=[Order.Status.EXPIRED, Order.Status.CANCELED])
    orders = eligible.order_by("-created_at")[:20]
    form = {"subject": "", "body": "", "order": request.GET.get("order", "")}
    if request.method == "POST":
        form = {k: request.POST.get(k, "") for k in ("subject", "body", "order")}
        order = eligible.filter(pk=Order.pk_from_number(form["order"])).first() if form["order"] else None
        try:
            ticket = services.open_ticket(customer, form["subject"], form["body"], order=order)
        except services.SupportError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(request, "تیکت ثبت شد. پاسخ را با پیامک خبر می‌دهیم.")
            return redirect(ticket.get_absolute_url())
    return render(request, "account/ticket_new.html", {"orders": orders, "form": form, "nav": "tickets", "nav_active": "account"})


def ticket_detail(request, pk):
    customer = get_customer(request)
    if not customer:
        return _login_redirect(request)
    ticket = Ticket.objects.filter(pk=pk, customer=customer).select_related("order").first()
    if ticket is None:
        raise Http404
    if request.method == "POST":
        try:
            if "card" in request.POST:
                refund = ticket.refunds.filter(pk=request.POST.get("refund")).first()
                if refund is None:
                    raise Http404
                services.submit_card(refund, customer, request.POST.get("card"))
                messages.success(request, "شماره کارت ثبت شد.")
            elif "close" in request.POST:
                services.close_ticket(ticket)
            else:
                services.customer_reply(ticket, customer, request.POST.get("body"))
        except services.SupportError as exc:
            messages.error(request, exc.message)
        return redirect(ticket.get_absolute_url())

    response = render(request, "account/ticket_detail.html", {
        "ticket": ticket,
        "ticket_messages": ticket.messages.all(),
        "claim": getattr(ticket, "claim", None),
        "refunds": ticket.refunds.all(),
        "nav": "tickets",
        "nav_active": "account",
    })
    response["Cache-Control"] = "no-store"
    return response


@require_POST
def report_problem(request, item_id):
    customer = get_customer(request)
    if not customer:
        return _login_redirect(request)
    try:
        claim = services.report_problem(customer, item_id, request.POST.get("body"))
    except services.SupportError as exc:
        messages.error(request, exc.message)
        item = OrderItem.objects.filter(pk=item_id, order__customer=customer).select_related("order").first()
        return redirect(item.order.get_absolute_url() if item else "orders:account_orders")
    messages.success(request, "گزارش مشکل ثبت شد. نتیجه بررسی را در همین تیکت و با پیامک اعلام می‌کنیم.")
    return redirect(claim.ticket.get_absolute_url())
