from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog import inventory
from apps.catalog.models import Category, Product, ProductFaq, ProductSpec, Variant
from apps.core.models import ExchangeRate

CATEGORIES = [
    ("دستیار چت", "دستیار-چت", "chat"),
    ("تولید تصویر", "تولید-تصویر", "image"),
    ("برنامه‌نویسی", "برنامه-نویسی", "code"),
    ("پژوهش و جست‌وجو", "پژوهش-و-جست-وجو", "search"),
    ("ویدیو و صدا", "ویدیو-و-صدا", "video"),
    ("اعتبار API", "اعتبار-api", "key"),
]

# title, slug, brand, monogram, tint, category slug, keywords, featured, variants
# variant: (name, delivery, account, field, mode, amount, margin, compare_at, days, stock)
PRODUCTS = [
    ("اشتراک ChatGPT Plus", "اشتراک-chatgpt-plus", "OpenAI", "GPT", "from-emerald-500 to-teal-600", "دستیار-چت",
     "chatgpt\nچت جی پی تی\nچت‌جی‌پی‌تی\nopenai\ngpt", True, [
         ("یک‌ماهه اشتراکی", "stock", "shared", "email", "fixed", 1_890_000, 0, 2_200_000, 30, 8),
         ("یک‌ماهه اختصاصی", "manual", "private", "email", "usd", 20, 15, 2_700_000, 30, 0),
         ("سه‌ماهه اختصاصی", "manual", "private", "email", "usd", 60, 12, 8_100_000, 90, 0),
     ]),
    ("اشتراک Gemini Advanced", "اشتراک-جمینای", "Google AI Pro", "G", "from-sky-500 to-indigo-600", "دستیار-چت",
     "gemini\nجمینای\nجمنای\nهوش مصنوعی گوگل\ngoogle", True, [
         ("یک‌ماهه اختصاصی", "manual", "private", "gmail", "fixed", 1_450_000, 0, 1_700_000, 30, 0),
     ]),
    ("اشتراک Claude Pro", "اشتراک-claude-pro", "Anthropic", "C", "from-orange-400 to-amber-600", "دستیار-چت",
     "claude\nکلود\nanthropic", True, [
         ("یک‌ماهه اشتراکی", "stock", "shared", "email", "usd", 20, 2, None, 30, 5),
     ]),
    ("اشتراک Midjourney Standard", "اشتراک-midjourney", "Midjourney", "MJ", "from-slate-700 to-slate-900", "تولید-تصویر",
     "midjourney\nمیدجرنی\nتولید تصویر", True, [
         ("یک‌ماهه اختصاصی", "manual", "private", "email", "fixed", 3_100_000, 0, 3_400_000, 30, 0),
     ]),
    ("اشتراک Cursor Pro", "اشتراک-cursor-pro", "Cursor", "Cu", "from-slate-700 to-slate-900", "برنامه-نویسی",
     "cursor\nکرسر\nبرنامه نویسی", True, [
         ("یک‌ماهه اشتراکی", "stock", "shared", "email", "fixed", 1_950_000, 0, None, 30, 0),
     ]),
    ("اشتراک Perplexity Pro", "اشتراک-perplexity-pro", "Perplexity", "P", "from-cyan-500 to-teal-700", "پژوهش-و-جست-وجو",
     "perplexity\nپرپلکسیتی", True, [
         ("یک‌ماهه اشتراکی", "stock", "shared", "email", "fixed", 1_650_000, 0, 1_950_000, 30, 2),
     ]),
    ("اشتراک GitHub Copilot Pro", "اشتراک-github-copilot", "GitHub", "GH", "from-violet-600 to-purple-800", "برنامه-نویسی",
     "copilot\nکوپایلوت\ngithub", False, [
         ("یک‌ماهه اختصاصی", "manual", "private", "email", "fixed", 980_000, 0, None, 30, 0),
     ]),
    ("اشتراک SuperGrok", "اشتراک-grok", "xAI", "X", "from-slate-700 to-slate-900", "دستیار-چت",
     "grok\nگراک\nxai", False, [
         ("یک‌ماهه اشتراکی", "stock", "shared", "email", "fixed", 2_400_000, 0, 2_650_000, 30, 4),
     ]),
]

FEATURES = "دسترسی به جدیدترین مدل‌ها\nساخت تصویر و تحلیل فایل\nحالت صوتی پیشرفته\nاولویت در ساعت‌های شلوغ"
FAQS = [
    ("تفاوت اکانت اشتراکی و اختصاصی چیست؟",
     "در اکانت اشتراکی اطلاعات ورود یک اکانت آماده را دریافت می‌کنید. در اکانت اختصاصی، اشتراک روی ایمیل خودتان فعال می‌شود."),
    ("بعد از پرداخت چطور اکانت را تحویل می‌گیرم؟",
     "تنوع‌های «تحویل فوری» بلافاصله در صفحه سفارش نمایش داده می‌شوند. تنوع‌های اختصاصی تا مهلت اعلام‌شده روی ایمیل شما فعال می‌شوند."),
    ("اگر اکانت مشکل پیدا کند چه می‌شود؟",
     "تا پایان گارانتی از صفحه سفارش روی «گزارش مشکل» بزنید. اکانت تعویض می‌شود یا مبلغ روزهای باقی‌مانده برمی‌گردد."),
]


class Command(BaseCommand):
    help = "Create demo categories, products, variants and inventory (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        if ExchangeRate.current() is None:
            ExchangeRate.objects.create(toman_per_usd=Decimal("100000"))

        categories = {}
        for order, (name, slug, icon) in enumerate(CATEGORIES):
            categories[slug], _ = Category.objects.get_or_create(
                slug=slug, defaults={"name": name, "icon": icon, "sort_order": order}
            )

        created_products = 0
        for order, (title, slug, brand, mono, tint, cat, keywords, featured, variants) in enumerate(PRODUCTS):
            product, created = Product.objects.get_or_create(
                slug=slug,
                defaults={
                    "title": title, "brand": brand, "monogram": mono, "tint": tint, "category": categories[cat],
                    "keywords": keywords, "is_featured": featured, "sort_order": order,
                    "status": Product.Status.ACTIVE, "short_features": FEATURES,
                    "description": f"{title} را با تحویل سریع و گارانتی تعویض بخرید. (متن نمونه؛ از پنل ویرایش کنید.)",
                    "usage_guide": "بعد از پرداخت به صفحه سفارش بروید.\nاطلاعات ورود یا وضعیت فعال‌سازی را ببینید.\nدر صورت مشکل روی «گزارش مشکل» بزنید.",
                    "warranty_text": "تعویض اکانت معیوب یا بازگشت وجه به نسبت روزهای باقی‌مانده. گارانتی با تعویض از نو شروع نمی‌شود.",
                },
            )
            if not created:
                continue
            created_products += 1
            for i, (k, v) in enumerate([("سازنده", brand), ("پلتفرم", "وب، اندروید، iOS، ویندوز و مک")]):
                ProductSpec.objects.create(product=product, name=k, value=v, sort_order=i)
            for i, (q, a) in enumerate(FAQS):
                ProductFaq.objects.create(product=product, question=q, answer=a, sort_order=i)

            for i, (name, delivery, account, field, mode, amount, margin, compare, days, stock) in enumerate(variants):
                variant = Variant.objects.create(
                    product=product, name=name, delivery_type=delivery, account_type=account,
                    account_field_type=field,
                    account_field_help="فقط حساب شخصی جیمیل؛ حساب‌های سازمانی پشتیبانی نمی‌شوند." if field == "gmail" else "",
                    pricing_mode=mode,
                    fixed_price=Decimal(amount) if mode == "fixed" else None,
                    usd_price=Decimal(amount) if mode == "usd" else None,
                    margin_percent=Decimal(margin),
                    compare_at_price=Decimal(compare) if compare else None,
                    duration_days=days, warranty_days=days,
                    delivery_deadline_hours=0 if delivery == "stock" else 3,
                    delivery_template="ایمیل: {0}\nرمز عبور: {1}" if delivery == "stock" else "",
                    sort_order=i,
                )
                if stock:
                    lines = [f"demo-{slug[-6:]}-{variant.pk}-{n}@example.com|Demo-Pass-{n:03d}" for n in range(stock)]
                    inventory.import_items(variant, lines, batch_label="دمو")

        self.stdout.write(self.style.SUCCESS(f"Done. {created_products} new products."))
