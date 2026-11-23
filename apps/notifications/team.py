"""
Internal alerts for the team (low stock, manual orders, ...).
The Telegram group backend arrives with the bot (M7); until then alerts are logged.
"""

import logging

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class LogTeamBackend:
    def send(self, kind, text):
        logger.warning("[TEAM:%s] %s", kind, text)


class MemoryTeamBackend:
    outbox: list = []

    def send(self, kind, text):
        self.outbox.append({"kind": kind, "text": text})


def alert(kind, text):
    try:
        import_string(settings.TEAM_ALERT_BACKEND)().send(kind, text)
    except Exception:
        # A failing alert channel must never break the caller.
        logger.exception("Team alert failed: %s", kind)
