from django.urls import path

from . import views

app_name = "storefront"

urlpatterns = [
    path("", views.home, name="home"),
    path("category/<str:slug>/", views.category, name="category"),
    path("product/<str:slug>/", views.product, name="product"),
    path("cart/", views.cart, name="cart"),
    path("checkout/", views.checkout, name="checkout"),
]
