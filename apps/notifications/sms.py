"""
SMS providers behind a common interface so the provider can be swapped
from settings without touching business code.
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class SmsError(Exception):
    pass


@dataclass(frozen=True)
class SmsResult:
    provider_message_id: str


class BaseSmsBackend:
    def send_otp(self, mobile: str, code: str) -> SmsResult:
        raise NotImplementedError

    def send_template(self, mobile: str, template: str, params: dict) -> SmsResult:
        raise NotImplementedError


class ConsoleSmsBackend(BaseSmsBackend):
    """Development backend: prints messages to the log instead of sending them."""

    def send_otp(self, mobile, code):
        logger.warning("[SMS:console] login code for %s: %s", mobile, code)
        return SmsResult(provider_message_id="console")

    def send_template(self, mobile, template, params):
        logger.warning("[SMS:console] %s -> %s %s", mobile, template, params)
        return SmsResult(provider_message_id="console")


class MemorySmsBackend(BaseSmsBackend):
    """Test backend: keeps sent messages in memory."""

    outbox: list = []

    def send_otp(self, mobile, code):
        self.outbox.append({"mobile": mobile, "code": code})
        return SmsResult(provider_message_id=f"mem-{len(self.outbox)}")

    def send_template(self, mobile, template, params):
        self.outbox.append({"mobile": mobile, "template": template, "params": params})
        return SmsResult(provider_message_id=f"mem-{len(self.outbox)}")


def get_backend() -> BaseSmsBackend:
    return import_string(settings.SMS_BACKEND)()
