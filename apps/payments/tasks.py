from celery import shared_task

from . import services


@shared_task
def inquire_pending_payments():
    return services.inquire_pending()
