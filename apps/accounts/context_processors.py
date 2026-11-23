from .session import get_customer


def customer(request):
    return {"customer": get_customer(request)}
