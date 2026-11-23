from decimal import Decimal

from apps.catalog.models import Category, Product, Variant


def make_category(slug="دستیار-چت", name="دستیار چت"):
    return Category.objects.get_or_create(slug=slug, defaults={"name": name, "icon": "chat"})[0]


def make_product(slug="اشتراک-تست", title="اشتراک تست", category=None, **kwargs):
    defaults = {"status": Product.Status.ACTIVE, "brand": "Test", "monogram": "T"}
    defaults.update(kwargs)
    return Product.objects.create(slug=slug, title=title, category=category or make_category(), **defaults)


def make_variant(product=None, price=1_000_000, **kwargs):
    defaults = {
        "name": "یک‌ماهه",
        "pricing_mode": Variant.PricingMode.FIXED,
        "fixed_price": Decimal(price),
        "delivery_type": Variant.DeliveryType.STOCK,
    }
    defaults.update(kwargs)
    return Variant.objects.create(product=product or make_product(), **defaults)
