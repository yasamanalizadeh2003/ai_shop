from celery import shared_task

from . import delivery, services


@shared_task
def expire_reservations():
    return services.expire_due_orders()


@shared_task
def send_expiry_reminders():
    return delivery.send_expiry_reminders()


@shared_task
def send_expiry_notices():
    return delivery.send_expiry_notices()


@shared_task
def alert_overdue_manual_items():
    return delivery.alert_overdue_manual()
