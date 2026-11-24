"""
Django settings for the AI subscription shop.

All environment-specific values (secrets, database, redis) are read from
environment variables or a local `.env` file. See `.env.example`.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    # third party
    "rest_framework",
    "django_celery_beat",
    "django_otp",
    "django_otp.plugins.otp_totp",
    # local
    "apps.core",
    "apps.accounts",
    "apps.notifications",
    "apps.catalog",
    "apps.orders",
    "apps.payments",
    "apps.storefront",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "apps.accounts.session.CustomerMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.catalog.middleware.RedirectFallbackMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
                "apps.accounts.context_processors.customer",
                "apps.orders.context_processors.cart",
            ],
            "builtins": ["apps.core.templatetags.persian"],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

SITE_NAME = env("SITE_NAME", default="هوشینو")

# Customer SMS login
OTP_CODE_LENGTH = 5
OTP_TTL_SECONDS = env.int("OTP_TTL_SECONDS", default=120)
OTP_RESEND_COOLDOWN = env.int("OTP_RESEND_COOLDOWN", default=120)
OTP_MAX_ATTEMPTS = env.int("OTP_MAX_ATTEMPTS", default=5)
OTP_MAX_PER_MOBILE_PER_HOUR = env.int("OTP_MAX_PER_MOBILE_PER_HOUR", default=5)
OTP_MAX_PER_IP_PER_HOUR = env.int("OTP_MAX_PER_IP_PER_HOUR", default=20)

SITE_URL = env("SITE_URL", default="http://127.0.0.1:8000")

SMS_BACKEND = env("SMS_BACKEND", default="apps.notifications.sms.ConsoleSmsBackend")
TELEGRAM_BACKEND = env("TELEGRAM_BACKEND", default="apps.notifications.channels.LogTelegramBackend")
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@localhost")
TEAM_ALERT_BACKEND = env("TEAM_ALERT_BACKEND", default="apps.notifications.team.LogTeamBackend")

# Two-factor authentication (TOTP) is required for the admin panel.
ADMIN_REQUIRE_2FA = env.bool("ADMIN_REQUIRE_2FA", default=True)
OTP_TOTP_ISSUER = SITE_NAME

SESSION_COOKIE_AGE = 60 * 60 * 24 * 30

# Database: PostgreSQL in every real environment (row-level locking is required).
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization: Persian UI, all timestamps stored in UTC.
LANGUAGE_CODE = "fa-ir"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Cache / queue
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = None
CELERY_TIMEZONE = "UTC"
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    "expire-reservations": {"task": "apps.orders.tasks.expire_reservations", "schedule": 60.0},
    "inquire-pending-payments": {"task": "apps.payments.tasks.inquire_pending_payments", "schedule": 180.0},
    "send-due-messages": {"task": "apps.notifications.tasks.send_due_messages", "schedule": 60.0},
    "expiry-reminders": {"task": "apps.orders.tasks.send_expiry_reminders", "schedule": 3600.0},
    "expiry-notices": {"task": "apps.orders.tasks.send_expiry_notices", "schedule": 3600.0},
    "overdue-manual-items": {"task": "apps.orders.tasks.alert_overdue_manual_items", "schedule": 300.0},
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# Encryption key for delivery data and sensitive fields (AES-256-GCM).
# Must be a base64-encoded 32-byte key. Never stored in the database.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY")

# Security hardening when not in debug mode.
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
