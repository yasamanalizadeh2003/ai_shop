"""Email and Telegram senders behind small interfaces (Telegram arrives with the bot in M7)."""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class SendError(Exception):
    pass


def send_email(to, subject, body):
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
    except Exception as exc:
        raise SendError(str(exc)) from exc
    return "email"


class LogTelegramBackend:
    def send(self, chat_id, text):
        logger.warning("[TELEGRAM:log] %s: %s", chat_id, text)
        return "log"


class MemoryTelegramBackend:
    outbox: list = []

    def send(self, chat_id, text):
        self.outbox.append({"chat_id": chat_id, "text": text})
        return f"mem-{len(self.outbox)}"


def send_telegram(chat_id, text):
    try:
        return import_string(settings.TELEGRAM_BACKEND)().send(chat_id, text)
    except Exception as exc:
        raise SendError(str(exc)) from exc
