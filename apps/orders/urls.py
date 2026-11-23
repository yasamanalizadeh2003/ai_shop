from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/item/<int:item_id>/quantity/", views.cart_update, name="cart_update"),
    path("cart/item/<int:item_id>/remove/", views.cart_remove, name="cart_remove"),
    path("cart/discount/", views.apply_discount, name="apply_discount"),
    path("checkout/place-order/", views.place_order, name="place_order"),
    path("orders/<int:number>/", views.order_detail, name="detail"),
    path("orders/<int:number>/pay/", views.order_pay, name="pay"),
]
