"""
Read-side queries for the storefront. Templates never touch inventory
or pricing rules directly; they get ready-to-render cards from here.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, Prefetch, Q

from .models import Category, InventoryItem, Product, Variant

DURATION_BUCKETS = [
    ("1", "یک‌ماهه", 1, 45),
    ("3", "سه‌ماهه", 46, 120),
    ("6", "شش‌ماهه", 121, 270),
    ("12", "یک‌ساله", 271, 10_000),
]

SORTS = [
    ("popular", "پرفروش‌ترین"),
    ("cheap", "ارزان‌ترین"),
    ("expensive", "گران‌ترین"),
    ("discount", "بیشترین تخفیف"),
    ("newest", "جدیدترین"),
]


@dataclass
class VariantView:
    obj: Variant
    available: int

    @property
    def in_stock(self):
        if self.obj.delivery_type == Variant.DeliveryType.MANUAL:
            return True
        return self.available > 0

    def __getattr__(self, name):
        return getattr(self.obj, name)


@dataclass
class ProductCard:
    product: Product
    variants: list = field(default_factory=list)

    def __getattr__(self, name):
        return getattr(self.product, name)

    @property
    def buyable(self):
        return [v for v in self.variants if v.in_stock]

    @property
    def in_stock(self):
        return bool(self.buyable)

    @property
    def cheapest(self):
        pool = self.buyable or self.variants
        return min(pool, key=lambda v: v.price) if pool else None

    @property
    def price(self):
        return self.cheapest.price if self.cheapest else None

    @property
    def compare_at(self):
        c = self.cheapest
        return c.compare_at_price if c and c.compare_at_price and c.compare_at_price > c.price else None

    @property
    def instant(self):
        return any(v.in_stock and v.obj.delivery_type == Variant.DeliveryType.STOCK for v in self.variants)

    @property
    def discount_ratio(self):
        if not self.compare_at:
            return Decimal("0")
        return (self.compare_at - self.price) / self.compare_at

    @property
    def mono(self):
        return self.product.monogram or self.product.title[:2]

    @property
    def subtitle(self):
        return self.product.brand

    @property
    def durations(self):
        return {v.obj.duration_days for v in self.variants}


def _variants_prefetch():
    qs = (
        Variant.objects.filter(status=Variant.Status.ACTIVE)
        .annotate(available=Count("inventory_items", filter=Q(inventory_items__status=InventoryItem.Status.AVAILABLE)))
        .order_by("sort_order", "id")
    )
    return Prefetch("variants", queryset=qs, to_attr="active_variants")


def _cards(queryset):
    products = queryset.filter(status=Product.Status.ACTIVE).select_related("category").prefetch_related(_variants_prefetch())
    cards = []
    for p in products:
        variants = [VariantView(v, v.available) for v in p.active_variants]
        if variants:
            cards.append(ProductCard(p, variants))
    return cards


def active_categories():
    return list(Category.objects.filter(is_active=True))


def featured_cards(limit=12):
    cards = _cards(Product.objects.filter(is_featured=True))
    if not cards:
        cards = _cards(Product.objects.all())
    return cards[:limit]


def discounted_cards(limit=12):
    cards = [c for c in _cards(Product.objects.all()) if c.compare_at and c.in_stock]
    return sorted(cards, key=lambda c: c.discount_ratio, reverse=True)[:limit]


def category_cards(category, params):
    cards = _cards(Product.objects.filter(category=category))
    return filter_and_sort(cards, params)


def parse_filters(params):
    def to_int(v):
        try:
            return int(str(v).replace(",", "").replace("٬", "")) if v not in (None, "") else None
        except ValueError:
            return None

    return {
        "in_stock": params.get("in_stock") == "1",
        "instant": params.get("instant") == "1",
        "durations": [d for d in params.getlist("duration") if d in {b[0] for b in DURATION_BUCKETS}],
        "min_price": to_int(params.get("min_price")),
        "max_price": to_int(params.get("max_price")),
        "sort": params.get("sort") if params.get("sort") in dict(SORTS) else "popular",
    }


def filter_and_sort(cards, params):
    f = parse_filters(params)
    out = []
    for c in cards:
        if f["in_stock"] and not c.in_stock:
            continue
        if f["instant"] and not c.instant:
            continue
        if f["durations"]:
            ranges = [(lo, hi) for key, _, lo, hi in DURATION_BUCKETS if key in f["durations"]]
            if not any(lo <= d <= hi for d in c.durations for lo, hi in ranges):
                continue
        if f["min_price"] is not None and (c.price is None or c.price < f["min_price"]):
            continue
        if f["max_price"] is not None and (c.price is None or c.price > f["max_price"]):
            continue
        out.append(c)

    sort = f["sort"]
    if sort == "cheap":
        out.sort(key=lambda c: c.price or 0)
    elif sort == "expensive":
        out.sort(key=lambda c: c.price or 0, reverse=True)
    elif sort == "discount":
        out.sort(key=lambda c: c.discount_ratio, reverse=True)
    elif sort == "newest":
        out.sort(key=lambda c: c.product.created_at, reverse=True)
    else:
        out.sort(key=lambda c: (not c.product.is_featured, c.product.sort_order))
    # Out-of-stock products always go last.
    out.sort(key=lambda c: not c.in_stock)
    return out, f


def product_detail(slug):
    product = (
        Product.objects.filter(slug=slug, status=Product.Status.ACTIVE)
        .select_related("category")
        .prefetch_related("specs", "faqs", _variants_prefetch())
        .first()
    )
    if product is None:
        return None
    return ProductCard(product, [VariantView(v, v.available) for v in product.active_variants])


def related_cards(card, limit=8):
    related = list(card.product.related.all().values_list("pk", flat=True))
    qs = Product.objects.filter(pk__in=related) if related else Product.objects.filter(category=card.product.category)
    return [c for c in _cards(qs.exclude(pk=card.product.pk))][:limit]


_ARABIC = str.maketrans({"ي": "ی", "ك": "ک", "\u200c": " "})


def normalize_query(q):
    return " ".join(str(q or "").translate(_ARABIC).lower().split())


def search_cards(q, limit=None):
    q = normalize_query(q)
    if len(q) < 2:
        return []
    query = Q()
    for term in q.split():
        query &= Q(search_text__icontains=term)
    cards = _cards(Product.objects.filter(query))
    cards.sort(key=lambda c: not c.in_stock)
    return cards[:limit] if limit else cards
