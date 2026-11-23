from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django_otp.admin import OTPAdminSite

from apps.core import views as core_views

if settings.ADMIN_REQUIRE_2FA:
    admin.site.__class__ = OTPAdminSite

admin.site.site_header = f"پنل مدیریت {settings.SITE_NAME}"
admin.site.site_title = settings.SITE_NAME
admin.site.index_title = "مدیریت فروشگاه"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", core_views.health, name="health"),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.storefront.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
