from .cart import item_count


def cart(request):
    return {"cart_count": item_count(request)}
