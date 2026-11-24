"""
Cart operations. A guest cart lives in the browser session; after sign-in it
is merged into the customer's cart. Prices shown here are live prices; they
are copied into the order (and frozen) only when the order is created.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q

from apps.accounts.session import get_customer
from apps.catalog.models import InventoryItem, Product, Variant

from .models import MAX_QUANTITY, Cart, CartItem

SESSION_KEY = "cart_id"


class CartError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def max_quantity(variant):
    # A private (personal-account) subscription is activated on one email.
    return 1 if variant.account_type == Variant.AccountType.PRIVATE else MAX_QUANTITY


def get_cart(request, create=False):
    customer = get_customer(request)
    if customer:
        cart = Cart.objects.filter(customer=customer).first()
        if cart is None and create:
            cart = Cart.objects.create(customer=customer)
        return cart

    cart_id = request.session.get(SESSION_KEY)
    cart = Cart.objects.filter(pk=cart_id, customer__isnull=True).first() if cart_id else None
    if cart is None and create:
        cart = Cart.objects.create()
        request.session[SESSION_KEY] = cart.pk
    return cart


def get_customer_cart(customer):
    cart, _ = Cart.objects.get_or_create(customer=customer)
    return cart


def _buyable_variant(variant_id):
    variant = (
        Variant.objects.select_related("product")
        .filter(pk=variant_id, status=Variant.Status.ACTIVE, product__status=Product.Status.ACTIVE)
        .first()
    )
    if variant is None:
        raise CartError("این کالا در حال حاضر قابل خرید نیست.")
    return variant


def renew(cart, delivery):
    """'Renew' button: put the same variant in the cart, remembering which delivery it renews."""
    item = add(cart, delivery.item.variant_id, 1, allow_existing=True)
    item.renews = delivery
    if delivery.item.account_identifier and not item.account_identifier:
        item.account_identifier = delivery.item.account_identifier
    item.save(update_fields=["renews", "account_identifier"])
    return item


def add(cart, variant_id, quantity=1, *, allow_existing=False):
    variant = _buyable_variant(variant_id)
    limit = max_quantity(variant)
    with transaction.atomic():
        item, created = CartItem.objects.select_for_update().get_or_create(
            cart=cart, variant=variant, defaults={"quantity": min(quantity, limit)}
        )
        if not created and allow_existing:
            return item
        if not created:
            if item.quantity >= limit:
                raise CartError(
                    "اشتراک اختصاصی روی یک ایمیل فعال می‌شود و فقط یک عدد از آن در سبد جا دارد."
                    if limit == 1 else f"حداکثر {limit} عدد از هر کالا در سبد جا دارد."
                )
            item.quantity = min(item.quantity + quantity, limit)
            item.save(update_fields=["quantity"])
    cart.save(update_fields=["updated_at"])
    return item


def set_quantity(cart, item_id, quantity):
    item = CartItem.objects.select_related("variant").filter(cart=cart, pk=item_id).first()
    if item is None:
        return
    if quantity <= 0:
        item.delete()
        return
    item.quantity = min(quantity, max_quantity(item.variant))
    item.save(update_fields=["quantity"])


def remove(cart, item_id):
    CartItem.objects.filter(cart=cart, pk=item_id).delete()


def clear(cart):
    cart.items.all().delete()
    cart.discount_code = ""
    cart.save(update_fields=["discount_code", "updated_at"])


def merge_guest_cart_on_login(sender, request, customer, **kwargs):
    guest_id = request.session.pop(SESSION_KEY, None)
    if not guest_id:
        return
    guest = Cart.objects.filter(pk=guest_id, customer__isnull=True).first()
    if guest is None:
        return
    target = get_customer_cart(customer)
    with transaction.atomic():
        for item in guest.items.select_related("variant"):
            existing = CartItem.objects.filter(cart=target, variant=item.variant).first()
            limit = max_quantity(item.variant)
            if existing:
                existing.quantity = min(existing.quantity + item.quantity, limit)
                existing.save(update_fields=["quantity"])
            else:
                CartItem.objects.create(cart=target, variant=item.variant, quantity=min(item.quantity, limit),
                                        account_identifier=item.account_identifier, renews=item.renews)
        if guest.discount_code and not target.discount_code:
            target.discount_code = guest.discount_code
        if guest.notification_email and not target.notification_email:
            target.notification_email = guest.notification_email
        target.save()
        guest.delete()


@dataclass
class CartLine:
    item: CartItem
    available: int

    @property
    def variant(self):
        return self.item.variant

    @property
    def product(self):
        return self.item.variant.product

    @property
    def quantity(self):
        return self.item.quantity

    @property
    def unit_price(self):
        return self.variant.price

    @property
    def line_total(self):
        return self.variant.price * self.quantity

    @property
    def line_before(self):
        compare = self.variant.compare_at_price
        unit = compare if compare and compare > self.variant.price else self.variant.price
        return unit * self.quantity

    @property
    def is_buyable(self):
        v = self.variant
        if v.status != Variant.Status.ACTIVE or v.product.status != Product.Status.ACTIVE:
            return False
        if v.delivery_type == Variant.DeliveryType.STOCK:
            return self.available >= self.quantity
        return True

    @property
    def problem(self):
        v = self.variant
        if v.status != Variant.Status.ACTIVE or v.product.status != Product.Status.ACTIVE:
            return "این کالا دیگر فروخته نمی‌شود."
        if v.delivery_type == Variant.DeliveryType.STOCK and self.available < self.quantity:
            return "موجودی کافی نیست." if self.available else "موجودی این کالا تمام شده است."
        return ""

    @property
    def needs_account(self):
        return self.variant.is_private

    @property
    def max_quantity(self):
        return max_quantity(self.variant)


@dataclass
class CartSummary:
    lines: list = field(default_factory=list)

    @property
    def count(self):
        return sum(line.quantity for line in self.lines)

    @property
    def total(self):
        return sum((line.line_total for line in self.lines), Decimal("0"))

    @property
    def total_before(self):
        return sum((line.line_before for line in self.lines), Decimal("0"))

    @property
    def profit(self):
        return self.total_before - self.total

    @property
    def has_problems(self):
        return any(not line.is_buyable for line in self.lines)

    @property
    def account_lines(self):
        return [line for line in self.lines if line.needs_account]


def summarize(cart):
    if cart is None:
        return CartSummary()
    items = (
        cart.items.select_related("variant__product")
        .annotate(available=Count("variant__inventory_items", filter=Q(variant__inventory_items__status=InventoryItem.Status.AVAILABLE)))
    )
    return CartSummary([CartLine(item, item.available) for item in items])


def item_count(request):
    cart = get_cart(request)
    if cart is None:
        return 0
    return sum(cart.items.values_list("quantity", flat=True))
