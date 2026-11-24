from django.conf import settings

from .models import SiteSettings


def site(request):
    return {"SITE_NAME": settings.SITE_NAME, "site_settings": SiteSettings.get()}
