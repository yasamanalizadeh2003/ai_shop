from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.contrib.sitemaps.views import sitemap
from django.views.decorators.cache import cache_page
from django_otp.admin import OTPAdminSite

from apps.core import views as core_views
from apps.storefront.sitemaps import SITEMAPS

if settings.ADMIN_REQUIRE_2FA:
    admin.site.__class__ = OTPAdminSite

admin.site.site_header = f"پنل مدیریت {settings.SITE_NAME}"
admin.site.site_title = settings.SITE_NAME
admin.site.index_title = "مدیریت فروشگاه"
# The collapsible app sidebar steals a third of the width on laptops and squeezes wide forms.
admin.site.enable_nav_sidebar = False

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", core_views.health, name="health"),
    path("sitemap.xml", cache_page(60 * 60)(sitemap), {"sitemaps": SITEMAPS}, name="sitemap"),
    path("accounts/", include("apps.accounts.urls")),
    path("payments/", include("apps.payments.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.storefront.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
