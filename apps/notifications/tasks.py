from celery import shared_task

from . import service


@shared_task
def send_due_messages():
    return service.send_due()
