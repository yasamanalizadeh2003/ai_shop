from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.models import Customer
from apps.notifications import service
from apps.notifications.models import Message, MessageTemplate
from apps.notifications.team import MemoryTeamBackend

TEHRAN = ZoneInfo("Asia/Tehran")


@pytest.fixture(autouse=True)
def _backends(settings):
    settings.TEAM_ALERT_BACKEND = "apps.notifications.team.MemoryTeamBackend"
    settings.TELEGRAM_BACKEND = "apps.notifications.channels.MemoryTelegramBackend"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    MemoryTeamBackend.outbox = []


@pytest.fixture
def web_customer(db):
    return Customer.objects.create(signup_channel="web", mobile="09121112233", last_email="me@gmail.com")


def _at_tehran(hour):
    return datetime(2026, 11, 24, hour, 0, tzinfo=TEHRAN)


@pytest.mark.django_db
def test_notify_queues_sms_and_email(web_customer):
    messages = service.notify(web_customer, "payment_success", {"order_number": 100001, "order_url": "u", "amount": "1"}, key="paid:1")
    assert {m.channel for m in messages} == {"sms", "email"}
    assert all(m.status == Message.Status.QUEUED for m in messages)


@pytest.mark.django_db
def test_same_key_is_queued_once(web_customer):
    service.notify(web_customer, "payment_success", {}, key="paid:1")
    service.notify(web_customer, "payment_success", {}, key="paid:1")
    assert Message.objects.count() == 2  # one SMS + one email, not four


@pytest.mark.django_db
def test_telegram_customer_gets_telegram_not_sms(db):
    c = Customer.objects.create(signup_channel="telegram", telegram_user_id=555)
    channels = {m.channel for m in service.notify(c, "payment_success", {}, key="paid:2")}
    assert channels == {"telegram"}


@pytest.mark.django_db
def test_reminders_can_be_switched_off_but_order_messages_cannot(web_customer):
    web_customer.notify_reminders = False
    web_customer.save()
    assert service.notify(web_customer, "expiry_reminder", {}, key="r:1") == []
    assert service.notify(web_customer, "payment_success", {}, key="p:1")


@pytest.mark.django_db
def test_send_due_sends_and_renders(web_customer, sms_outbox, monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: _at_tehran(12))
    service.notify(web_customer, "payment_success", {"order_number": 100005, "order_url": "https://x/o/100005/", "amount": "10"}, key="p:5")
    assert service.send_due() == 2
    assert "100005" in sms_outbox[-1]["params"]["text"]
    assert mail.outbox[-1].to == ["me@gmail.com"]
    assert Message.objects.filter(status=Message.Status.SENT).count() == 2


@pytest.mark.django_db
def test_non_urgent_messages_wait_for_daytime(web_customer, sms_outbox, monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: _at_tehran(23))
    service.notify(web_customer, "expiry_reminder", {"product": "X", "ends_at": "-", "renew_url": "-"}, key="r:2")
    assert service.send_due() == 0
    msg = Message.objects.filter(channel="sms").get()
    assert msg.status == Message.Status.QUEUED
    assert msg.next_attempt_at == _at_tehran(9) + timedelta(days=1)

    # Urgent messages go out at night.
    service.notify(web_customer, "payment_success", {}, key="p:night")
    assert service.send_due() == 2


@pytest.mark.django_db
def test_retries_three_times_then_fails_and_alerts(web_customer, monkeypatch, django_capture_on_commit_callbacks):
    from apps.notifications import sms

    def boom(self, mobile, template, params):
        raise sms.SmsError("provider down")

    monkeypatch.setattr(sms.MemorySmsBackend, "send_template", boom)
    MessageTemplate.objects.filter(event="payment_success").update(email_body="")
    clock = [_at_tehran(12)]
    monkeypatch.setattr(timezone, "now", lambda: clock[0])
    service.notify(web_customer, "payment_success", {}, key="p:fail")
    msg = Message.objects.get()
    for _ in range(3):
        with django_capture_on_commit_callbacks(execute=True):
            service.send_due()
        msg.refresh_from_db()
        clock[0] = msg.next_attempt_at + timedelta(seconds=1)

    assert msg.status == Message.Status.FAILED
    assert msg.attempts == 3
    assert "provider down" in msg.last_error
    assert any(a["kind"] == "message_failed" for a in MemoryTeamBackend.outbox)


@pytest.mark.django_db
def test_inactive_template_skips(web_customer):
    MessageTemplate.objects.filter(event="payment_success").update(is_active=False)
    assert service.notify(web_customer, "payment_success", {}, key="p:x") == []


def test_render_leaves_unknown_placeholders():
    assert service.render("سلام {name} {missing}", {"name": "علی"}) == "سلام علی {missing}"


@pytest.mark.parametrize("hour, quiet", [(8, True), (9, False), (20, False), (21, True), (2, True)])
def test_quiet_hours(hour, quiet):
    assert service.in_quiet_hours(_at_tehran(hour)) is quiet
