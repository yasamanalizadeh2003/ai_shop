from celery import shared_task

from . import services


@shared_task
def expire_reservations():
    return services.expire_due_orders()
