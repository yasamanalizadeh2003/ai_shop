"""
Customer session handling, independent of Django's staff authentication,
so a staff member signed in to the admin and a customer never share identity.
"""

from django.dispatch import Signal
from django.utils.functional import SimpleLazyObject

from .models import Customer

SESSION_KEY = "_customer_id"

# Sent after a customer signs in; the cart app merges the guest cart on it.
customer_logged_in = Signal()


def login_customer(request, customer):
    request.session.cycle_key()
    request.session[SESSION_KEY] = customer.pk
    request.customer = customer
    customer_logged_in.send(sender=Customer, request=request, customer=customer)


def logout_customer(request):
    request.session.pop(SESSION_KEY, None)
    request.session.cycle_key()
    request.customer = None


def _load(request):
    pk = request.session.get(SESSION_KEY)
    if not pk:
        return None
    customer = Customer.objects.filter(pk=pk, is_active=True).first()
    if customer is None:
        request.session.pop(SESSION_KEY, None)
    return customer


class CustomerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.customer = SimpleLazyObject(lambda: _load(request))
        return self.get_response(request)


def get_customer(request):
    customer = getattr(request, "customer", None)
    # Unwrap the lazy object so `if customer:` works as expected.
    return customer if customer else None
