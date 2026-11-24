"""
Structured data (JSON-LD) and Open Graph helpers.
Prices are stored in Toman; schema.org needs ISO 4217, so IRR = Toman × 10.
No ratings are emitted: there are no real reviews yet.
"""

import json

from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import mark_safe

from apps.core.richtext import to_plain


def absolute(request, path):
    return request.build_absolute_uri(path)


def to_irr(toman):
    return str(int(toman) * 10)


_JSON_ESCAPES = {ord("<"): "\\u003C", ord(">"): "\\u003E", ord("&"): "\\u0026"}


def as_script(*objects):
    """Serialize JSON-LD safely for embedding inside <script> (same escaping as Django's json_script)."""
    blocks = []
    for obj in objects:
        if not obj:
            continue
        payload = json.dumps(obj, ensure_ascii=False).translate(_JSON_ESCAPES)
        blocks.append(f'<script type="application/ld+json">{payload}</script>')
    return mark_safe("\n".join(blocks))


def organization(request):
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": settings.SITE_NAME,
        "url": absolute(request, "/"),
        "logo": absolute(request, static("img/logo-512.png")),
    }


def website(request):
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": settings.SITE_NAME,
        "url": absolute(request, "/"),
        "potentialAction": {
            "@type": "SearchAction",
            "target": absolute(request, "/search/?q={search_term_string}"),
            "query-input": "required name=search_term_string",
        },
    }


def breadcrumbs(request, crumbs, current_url):
    items = []
    for position, (name, url) in enumerate(crumbs, start=1):
        items.append({
            "@type": "ListItem",
            "position": position,
            "name": name,
            "item": absolute(request, url) if url else current_url,
        })
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}


def product(request, card, image_url):
    p = card.product
    offers = []
    for v in card.variants:
        offers.append({
            "@type": "Offer",
            "name": v.name,
            "sku": f"V{v.obj.pk}",
            "price": to_irr(v.price),
            "priceCurrency": "IRR",
            "availability": "https://schema.org/InStock" if v.in_stock else "https://schema.org/OutOfStock",
            "url": absolute(request, p.get_absolute_url()),
            "itemCondition": "https://schema.org/NewCondition",
            "seller": {"@type": "Organization", "name": settings.SITE_NAME},
        })
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": p.title,
        "description": to_plain(p.seo_description or p.description)[:500] or p.title,
        "sku": f"P{p.pk}",
        "url": absolute(request, p.get_absolute_url()),
        "image": [image_url],
        "category": p.category.name,
        "offers": offers,
    }
    if p.brand:
        data["brand"] = {"@type": "Brand", "name": p.brand}
    return data


def faq(faqs):
    faqs = list(faqs)
    if not faqs:
        return None
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": f.question, "acceptedAnswer": {"@type": "Answer", "text": to_plain(f.answer)}}
            for f in faqs
        ],
    }


def product_image_url(request, product):
    if product.image:
        return absolute(request, product.image.url)
    return absolute(request, static("img/og-default.png"))
