import logging
from datetime import timedelta

from celery import shared_task

from config import settings


logger = logging.getLogger('django')


@shared_task(acks_late=True, bind=True, default_retry_delay=60)
def process_platform_webhook(self, webhook_id):
    """
    Task for processing platform webhooks.
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


@shared_task(acks_late=True, bind=True, default_retry_delay=60)
def process_onfido_webhook(self, webhook_id):
    """
    Task for processing onfido webhooks.
    """

    from service_onfido.models import OnfidoWebhook
    from service_onfido.exceptions import OnfidoWebhookProcessingError

    try:
        webhook = OnfidoWebhook.objects.get(id=webhook_id)
    except OnfidoWebhook.DoesNotExist:
        logger.error('Onfido webhook does not exist.')
        return

    try:
        webhook.process()
    except Exception as exc:
        try:
            self.retry(
                max_retries=OnfidoWebhook.MAX_RETRIES,
                exc=OnfidoWebhookProcessingError
            )
        except OnfidoWebhookProcessingError:
            logger.info("Onfido webhook exceeded max retries.")


@shared_task(acks_late=True, bind=True, default_retry_delay=10)
def generate_user(self, user_id):
    """
    Task for generating users.
    """

    from service_onfido.models import User

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error('User does not exist.')
        return

    user.generate()


@shared_task(acks_late=True, bind=True, default_retry_delay=10)
def generate_document(self, document_id):
    """
    Task for generating documents.
    """

    from service_onfido.models import Document

    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error('Document does not exist.')
        return

    document.generate()


@shared_task(acks_late=True, bind=True, default_retry_delay=10)
def generate_check(self, check_id):
    """
    Task for generating checks.
    """

    from service_onfido.models import Check

    try:
        check = Check.objects.get(id=check_id)
    except Check.DoesNotExist:
        logger.error('Check does not exist.')
        return

    check.generate()


@shared_task(acks_late=True, bind=True, default_retry_delay=10)
def evaluate_check(self, check_id):
    """
    Task for evaluating checks.
    """

    from service_onfido.models import Check

    try:
        check = Check.objects.get(id=check_id)
    except Check.DoesNotExist:
        logger.error('Check does not exist.')
        return

    check.evaluate()
