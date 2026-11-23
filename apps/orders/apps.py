from django.apps import AppConfig


class OrdersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.orders"
    verbose_name = "سفارش‌ها"

    def ready(self):
        from apps.accounts.session import customer_logged_in

        from .cart import merge_guest_cart_on_login

        customer_logged_in.connect(merge_guest_cart_on_login, dispatch_uid="orders.merge_cart")
