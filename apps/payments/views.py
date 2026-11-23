from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt

from . import services
from .models import MockTransaction, Payment


@csrf_exempt  # Gateways post back from their own domain.
def callback(request, gateway):
    params = request.POST or request.GET
    authority = params.get("Authority") or params.get("authority") or params.get("trackId") or ""
    payment = services.handle_callback(gateway, authority)
    if payment is None:
        raise Http404

    order = payment.order
    if payment.status == Payment.Status.SUCCEEDED:
        order.refresh_from_db()
        if order.needs_refund:
            messages.warning(request, "پرداخت انجام شد اما موجودی سفارش تمام شده بود. مبلغ به کارت شما برمی‌گردد و با پیامک خبر می‌دهیم.")
        else:
            messages.success(request, f"پرداخت موفق بود. شماره پیگیری: {payment.ref_id}")
    else:
        messages.error(request, "پرداخت ناموفق بود یا لغو شد. اگر مبلغی کسر شده باشد، حداکثر تا ۷۲ ساعت به حساب شما برمی‌گردد.")
    return redirect(order.get_absolute_url())


def mock_gateway(request, authority):
    """Stand-in for a bank payment page. Only available in DEBUG."""
    if not settings.DEBUG:
        raise Http404
    tx = get_object_or_404(MockTransaction, authority=authority)
    if request.method == "POST":
        ok = request.POST.get("result") == "success"
        if ok:
            tx.paid = True
            tx.save(update_fields=["paid"])
        query = urlencode({"Authority": tx.authority, "Status": "OK" if ok else "NOK"})
        return redirect(f"{tx.callback_url}?{query}")
    return render(request, "payments/mock_gateway.html", {"tx": tx})
