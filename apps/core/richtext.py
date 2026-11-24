"""
Rich text for SEO content (category text, product description, FAQ answers, home text).
Edited with django-prose-editor; sanitized on save AND again when rendered.
"""

import re

import nh3
from django.utils.html import linebreaks

EXTENSIONS = {
    "Bold": True,
    "Italic": True,
    "Underline": True,
    "Heading": {"levels": [2, 3]},
    "BulletList": True,
    "OrderedList": True,
    "ListItem": True,
    "Blockquote": True,
    "HardBreak": True,
    "Link": {"enableTarget": False, "protocols": ["http", "https", "mailto"]},
}

ALLOWED_TAGS = {"p", "br", "strong", "em", "u", "h2", "h3", "ul", "ol", "li", "blockquote", "a"}
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}

_HAS_TAG = re.compile(r"<\s*(p|br|ul|ol|h2|h3|blockquote|strong|em|a)\b", re.IGNORECASE)


def sanitize(html: str) -> str:
    return nh3.clean(
        html or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener",
    )


def render(value: str) -> str:
    """Sanitized HTML. Older plain-text values are turned into paragraphs."""
    value = value or ""
    if not _HAS_TAG.search(value):
        return linebreaks(value, autoescape=True)
    return sanitize(value)


def to_plain(value: str) -> str:
    return " ".join(nh3.clean(value or "", tags=set()).split())
