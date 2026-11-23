"""
Temporary sample catalog used by the storefront pages until the real
catalog, cart and checkout (M2/M3) replace it.
"""

CATEGORIES = [
    {"slug": "دستیار-چت", "name": "دستیار چت", "icon": "chat", "count": 12},
    {"slug": "تولید-تصویر", "name": "تولید تصویر", "icon": "image", "count": 6},
    {"slug": "برنامه-نویسی", "name": "برنامه‌نویسی", "icon": "code", "count": 7},
    {"slug": "پژوهش-و-جست-وجو", "name": "پژوهش و جست‌وجو", "icon": "search", "count": 4},
    {"slug": "ویدیو-و-صدا", "name": "ویدیو و صدا", "icon": "video", "count": 5},
    {"slug": "اعتبار-api", "name": "اعتبار API", "icon": "key", "count": 3},
]

PRODUCTS = [
    {
        "slug": "اشتراک-chatgpt-plus",
        "title": "اشتراک ChatGPT Plus",
        "subtitle": "OpenAI",
        "mono": "GPT",
        "tint": "from-emerald-500 to-teal-600",
        "price": 1_890_000,
        "compare_at": 2_200_000,
        "instant": True,
        "in_stock": True,
        "duration": "۱ ماهه",
    },
    {
        "slug": "اشتراک-جمینای",
        "title": "اشتراک Gemini Advanced",
        "subtitle": "Google AI Pro",
        "mono": "G",
        "tint": "from-sky-500 to-indigo-600",
        "price": 1_450_000,
        "compare_at": 1_700_000,
        "instant": False,
        "in_stock": True,
        "duration": "۱ ماهه",
    },
    {
        "slug": "اشتراک-claude-pro",
        "title": "اشتراک Claude Pro",
        "subtitle": "Anthropic",
        "mono": "C",
        "tint": "from-orange-400 to-amber-600",
        "price": 2_050_000,
        "compare_at": None,
        "instant": True,
        "in_stock": True,
        "duration": "۱ ماهه",
    },
    {
        "slug": "اشتراک-midjourney",
        "title": "اشتراک Midjourney Standard",
        "subtitle": "Midjourney",
        "mono": "MJ",
        "tint": "from-slate-700 to-slate-900",
        "price": 3_100_000,
        "compare_at": 3_400_000,
        "instant": False,
        "in_stock": True,
        "duration": "۱ ماهه",
    },
    {
        "slug": "اشتراک-cursor-pro",
        "title": "اشتراک Cursor Pro",
        "subtitle": "Cursor",
        "mono": "Cu",
        "tint": "from-zinc-600 to-neutral-800",
        "price": 1_950_000,
        "compare_at": None,
        "instant": True,
        "in_stock": False,
        "duration": "۱ ماهه",
    },
    {
        "slug": "اشتراک-perplexity-pro",
        "title": "اشتراک Perplexity Pro",
        "subtitle": "Perplexity",
        "mono": "P",
        "tint": "from-cyan-500 to-teal-700",
        "price": 1_650_000,
        "compare_at": 1_950_000,
        "instant": True,
        "in_stock": True,
        "duration": "۱ ماهه",
    },
    {
        "slug": "اشتراک-github-copilot",
        "title": "اشتراک GitHub Copilot Pro",
        "subtitle": "GitHub",
        "mono": "GH",
        "tint": "from-violet-600 to-purple-800",
        "price": 980_000,
        "compare_at": None,
        "instant": False,
        "in_stock": True,
        "duration": "۱ ماهه",
    },
    {
        "slug": "اشتراک-grok",
        "title": "اشتراک SuperGrok",
        "subtitle": "xAI",
        "mono": "X",
        "tint": "from-neutral-800 to-black",
        "price": 2_400_000,
        "compare_at": 2_650_000,
        "instant": True,
        "in_stock": True,
        "duration": "۱ ماهه",
    },
]

PRODUCT_DETAIL = {
    **PRODUCTS[0],
    "category": CATEGORIES[0],
    "rating": None,
    "short_features": [
        "دسترسی به جدیدترین مدل‌های OpenAI",
        "ساخت تصویر و تحلیل فایل",
        "حالت صوتی پیشرفته",
        "اولویت در ساعت‌های شلوغ",
    ],
    "variants": [
        {
            "id": 1,
            "name": "یک‌ماهه اشتراکی",
            "price": 1_890_000,
            "compare_at": 2_200_000,
            "delivery": "stock",
            "delivery_label": "تحویل فوری",
            "account_type": "shared",
            "warranty": "گارانتی ۳۰ روزه",
            "in_stock": True,
        },
        {
            "id": 2,
            "name": "یک‌ماهه اختصاصی",
            "price": 2_490_000,
            "compare_at": 2_700_000,
            "delivery": "manual",
            "delivery_label": "فعال‌سازی روی ایمیل شما، حداکثر ۳ ساعت",
            "account_type": "private",
            "warranty": "گارانتی ۳۰ روزه",
            "in_stock": True,
        },
        {
            "id": 3,
            "name": "سه‌ماهه اختصاصی",
            "price": 6_900_000,
            "compare_at": 8_100_000,
            "delivery": "manual",
            "delivery_label": "فعال‌سازی روی ایمیل شما، حداکثر ۳ ساعت",
            "account_type": "private",
            "warranty": "گارانتی ۹۰ روزه",
            "in_stock": False,
        },
    ],
    "specs": [
        ("سازنده", "OpenAI"),
        ("نوع اکانت", "اشتراکی یا اختصاصی (بسته به تنوع)"),
        ("مدت اشتراک", "۳۰ یا ۹۰ روز"),
        ("روش تحویل", "اطلاعات ورود در صفحه سفارش / فعال‌سازی روی ایمیل شما"),
        ("پلتفرم", "وب، اندروید، iOS، ویندوز و مک"),
    ],
    "faqs": [
        (
            "تفاوت اکانت اشتراکی و اختصاصی چیست؟",
            "در اکانت اشتراکی اطلاعات ورود یک اکانت آماده را دریافت می‌کنید. در اکانت اختصاصی، اشتراک روی ایمیل خودتان فعال می‌شود و تاریخچه گفت‌وگوها فقط مال شماست.",
        ),
        (
            "بعد از پرداخت چطور اکانت را تحویل می‌گیرم؟",
            "تنوع‌های «تحویل فوری» بلافاصله در صفحه سفارش نمایش داده می‌شوند. تنوع‌های اختصاصی حداکثر تا مهلت اعلام‌شده روی ایمیل شما فعال می‌شوند و با پیامک خبر می‌دهیم.",
        ),
        (
            "اگر اکانت مشکل پیدا کند چه می‌شود؟",
            "تا پایان گارانتی از صفحه سفارش روی «گزارش مشکل» بزنید. اکانت تعویض می‌شود یا مبلغ روزهای باقی‌مانده به کارت شما برمی‌گردد.",
        ),
    ],
}

CART_ITEMS = [
    {"product": PRODUCTS[0], "variant": PRODUCT_DETAIL["variants"][1], "needs_email": True, "email_type": "email"},
    {
        "product": PRODUCTS[1],
        "variant": {"name": "یک‌ماهه اختصاصی", "price": 1_450_000, "compare_at": 1_700_000, "delivery_label": "حداکثر ۶ ساعت"},
        "needs_email": True,
        "email_type": "gmail",
    },
    {
        "product": PRODUCTS[5],
        "variant": {"name": "یک‌ماهه اشتراکی", "price": 1_650_000, "compare_at": 1_950_000, "delivery_label": "تحویل فوری"},
        "needs_email": False,
    },
]


def get_category(slug):
    return next((c for c in CATEGORIES if c["slug"] == slug), None)


def get_product(slug):
    if slug == PRODUCT_DETAIL["slug"]:
        return PRODUCT_DETAIL
    base = next((p for p in PRODUCTS if p["slug"] == slug), None)
    if base is None:
        return None
    variant = {
        "id": 1,
        "name": "یک‌ماهه اشتراکی",
        "price": base["price"],
        "compare_at": base["compare_at"],
        "delivery": "stock" if base["instant"] else "manual",
        "delivery_label": "تحویل فوری" if base["instant"] else "فعال‌سازی حداکثر ۶ ساعت",
        "account_type": "shared",
        "warranty": "گارانتی ۳۰ روزه",
        "in_stock": base["in_stock"],
    }
    return {**PRODUCT_DETAIL, **base, "variants": [variant]}


def cart_summary(items):
    total_before = sum((i["variant"].get("compare_at") or i["variant"]["price"]) for i in items)
    total = sum(i["variant"]["price"] for i in items)
    return {"count": len(items), "total_before": total_before, "total": total, "profit": total_before - total}
