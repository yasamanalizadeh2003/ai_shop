from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from apps.core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", core_views.health, name="health"),
]

if settings.DEBUG:
    from apps.core import mockups

    urlpatterns += [
        path("design/", mockups.index, name="design-index"),
        path("design/<str:name>/", mockups.page, name="design-page"),
        path("design/<str:name>/preview/", mockups.preview, name="design-preview"),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
