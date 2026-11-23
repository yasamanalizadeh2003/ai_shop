import pytest

from apps.notifications.sms import MemorySmsBackend


@pytest.fixture(autouse=True)
def _test_settings(settings):
    settings.SMS_BACKEND = "apps.notifications.sms.MemorySmsBackend"
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    MemorySmsBackend.outbox = []
    yield


@pytest.fixture
def sms_outbox():
    return MemorySmsBackend.outbox
