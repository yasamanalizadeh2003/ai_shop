import logging

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


def _check_database():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True
    except Exception:
        logger.exception("Health check: database unavailable")
        return False


def _check_redis():
    try:
        import redis

        client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        return bool(client.ping())
    except Exception:
        logger.warning("Health check: redis unavailable")
        return False


@never_cache
@require_GET
def health(request):
    checks = {"database": _check_database(), "redis": _check_redis()}
    healthy = all(checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status=200 if healthy else 503,
    )
