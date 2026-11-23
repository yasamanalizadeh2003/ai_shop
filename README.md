# ai_shop

فروشگاه اشتراک سرویس‌های هوش مصنوعی (فاز ۱: تک‌فروشنده، سایت + ربات تلگرام).

- سند الزامات: [`docs/spec.md`](docs/spec.md)
- دستورالعمل توسعه: [`docs/CLAUDE.md`](docs/CLAUDE.md)

## استک

Django 5.2 (قالب‌های سمت سرور + Tailwind)، Django REST Framework، PostgreSQL 16، Celery + Redis، Docker Compose.

## اجرای محلی (ویندوز، بدون Docker)

پیش‌نیاز: Python 3.13، Node.js 20+، PostgreSQL 16، Redis (یا Memurai روی ویندوز).

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
npm install
npm run build:css        # هنگام توسعه: npm run watch:css
copy .env.example .env   # سپس مقادیر را پر کنید
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py seed_catalog   # اختیاری: محصولات و انبار نمونه
.\.venv\Scripts\python manage.py runserver
```

- سایت: http://127.0.0.1:8000/
- پنل ادمین: http://127.0.0.1:8000/admin/
- سلامت سرویس: http://127.0.0.1:8000/health
- در حالت توسعه، کد ورود پیامکی به‌جای ارسال، در لاگ سرور (ترمینال runserver) چاپ می‌شود.

### ورود دومرحله‌ای پنل ادمین

ورود به `/admin/` علاوه بر رمز، کد ۶ رقمی اپلیکیشن Authenticator را می‌خواهد. برای هر کارمند یک بار:

```powershell
.\.venv\Scripts\python manage.py setup_admin_2fa <username> --png qr.png
```

QR را با Google Authenticator یا Microsoft Authenticator اسکن کنید (برای جایگزینی دستگاه: `--reset`).

### پرداخت در حالت توسعه

درگاه فعال از «تنظیمات سایت» در پنل انتخاب می‌شود. درگاه آزمایشی (فقط با DEBUG=True) یک صفحه محلی با دو دکمه «پرداخت موفق / ناموفق» نشان می‌دهد.

انقضای رزروها (هر دقیقه) و استعلام پرداخت‌های معلق (هر ۳ دقیقه) کار کارگر پس‌زمینه است؛ برای اجرای آن‌ها worker و beat را هم اجرا کنید.

- کارگر پس‌زمینه: `.\.venv\Scripts\celery -A config worker -l info --pool=solo`
- زمان‌بند: `.\.venv\Scripts\celery -A config beat -l info`

## تست

```powershell
.\.venv\Scripts\pytest
```

## اجرا با Docker

```bash
docker compose up -d --build
docker compose exec backend pytest
```
