"""
Customer notifications.

* `notify()` only enqueues; sending happens in `send_due()` (scheduled every minute).
  A failing SMS or Telegram provider therefore never blocks a purchase.
* Every message has a unique idempotency key, so running a job twice never sends twice.
* Up to 3 attempts with back-off; then the message is marked failed and the team is alerted.
* Non-urgent messages are held until 09:00–21:00 Tehran time.
* Customers may switch off reminders and marketing; order messages and login codes cannot be switched off.
* Account credentials never go into SMS or email — only a link to the order page.
"""

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifications import channels, sms, team

from .models import Message, MessageTemplate

logger = logging.getLogger(__name__)

TEHRAN = ZoneInfo("Asia/Tehran")
QUIET_START, QUIET_END = time(21, 0), time(9, 0)
MAX_ATTEMPTS = 3
BACKOFF_MINUTES = [1, 5, 15]


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def render(text, context):
    return (text or "").format_map(_SafeDict(context))


def _opted_out(customer, template):
    if template.can_opt_out == "reminders":
        return not customer.notify_reminders
    if template.can_opt_out == "marketing":
        return not customer.notify_marketing
    return False


def notify(customer, event, context=None, *, key, email=""):
    """Queue an event for every channel the customer can receive. Returns the messages created."""
    template = MessageTemplate.objects.filter(event=event, is_active=True).first()
    if template is None:
        logger.warning("No active template for event %s", event)
        return []
    if _opted_out(customer, template):
        return []

    context = {**(context or {}), "site_name": _site_name()}
    targets = []
    if customer.mobile and (template.sms_text or template.sms_template):
        targets.append((Message.Channel.SMS, customer.mobile))
    email = email or customer.last_email
    if email and template.email_body:
        targets.append((Message.Channel.EMAIL, email))
    if customer.telegram_user_id and template.telegram_text:
        targets.append((Message.Channel.TELEGRAM, str(customer.telegram_user_id)))

    created = []
    now = timezone.now()
    for channel, recipient in targets:
        try:
            with transaction.atomic():
                created.append(Message.objects.create(
                    customer=customer, event=event, channel=channel, recipient=recipient, context=context,
                    idempotency_key=f"{key}:{channel}", is_urgent=template.is_urgent, next_attempt_at=now,
                ))
        except IntegrityError:
            pass  # already queued for this key and channel
    return created


def _site_name():
    from django.conf import settings

    return settings.SITE_NAME


def in_quiet_hours(moment):
    local = moment.astimezone(TEHRAN).time()
    return local >= QUIET_START or local < QUIET_END


def next_allowed_time(moment):
    local = moment.astimezone(TEHRAN)
    target = local.replace(hour=9, minute=0, second=0, microsecond=0)
    if local.time() >= QUIET_START:
        target += timedelta(days=1)
    return target


def _deliver(message, template):
    ctx = message.context
    if message.channel == Message.Channel.SMS:
        params = {**ctx, "text": render(template.sms_text, ctx)}
        return sms.get_backend().send_template(message.recipient, template.sms_template or template.event, params).provider_message_id
    if message.channel == Message.Channel.EMAIL:
        return channels.send_email(message.recipient, render(template.email_subject, ctx), render(template.email_body, ctx))
    return channels.send_telegram(message.recipient, render(template.telegram_text, ctx))


def send_due(limit=100):
    """Scheduled job: send queued messages that are due. Safe to run concurrently."""
    now = timezone.now()
    sent = 0
    with transaction.atomic():
        batch = list(
            Message.objects.select_for_update(skip_locked=True)
            .filter(status=Message.Status.QUEUED, next_attempt_at__lte=now)
            .order_by("next_attempt_at")[:limit]
        )
        templates = {t.event: t for t in MessageTemplate.objects.filter(event__in={m.event for m in batch})}
        for message in batch:
            template = templates.get(message.event)
            if template is None or not template.is_active:
                message.status = Message.Status.SKIPPED
                message.save(update_fields=["status"])
                continue
            if not message.is_urgent and in_quiet_hours(now):
                message.next_attempt_at = next_allowed_time(now)
                message.save(update_fields=["next_attempt_at"])
                continue

            message.attempts += 1
            try:
                message.provider_message_id = str(_deliver(message, template) or "")[:100]
            except Exception as exc:
                message.last_error = str(exc)[:255]
                if message.attempts >= MAX_ATTEMPTS:
                    message.status = Message.Status.FAILED
                    transaction.on_commit(lambda m=message: team.alert(
                        "message_failed", f"ارسال {m.get_channel_display()} «{m.event}» به {m.recipient} بعد از {m.attempts} تلاش ناموفق ماند."
                    ))
                else:
                    message.next_attempt_at = now + timedelta(minutes=BACKOFF_MINUTES[message.attempts - 1])
            else:
                message.status = Message.Status.SENT
                message.sent_at = now
                sent += 1
            message.save()
    return sent
