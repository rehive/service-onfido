import logging
from datetime import timedelta

from celery import shared_task

from config import settings


logger = logging.getLogger('django')


@shared_task(acks_late=True, bind=True, default_retry_delay=60)
def process_platform_webhook(self, webhook_id):
    """
    Task for processing webhooks.
    """

    from service_onfido.models import PlatformWebhook
    from service_onfido.exceptions import PlatformWebhookProcessingError

    try:
        webhook = PlatformWebhook.objects.get(id=webhook_id)
    except PlatformWebhook.DoesNotExist:
        logger.error('Platform webhook does not exist.')
        return

    try:
        webhook.process()
    except Exception as exc:
        try:
            self.retry(
                max_retries=PlatformWebhook.MAX_RETRIES,
                exc=PlatformWebhookProcessingError
            )
        except PlatformWebhookProcessingError:
            logger.info("Platform webhook exceeded max retries.")
