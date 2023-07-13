from django_rehive_extras.exceptions import DjangoBaseException


class OnfidoException(DjangoBaseException):
    """
    Base exception for rehive_platform errors.
    """

    pass


class OnfidoError(OnfidoException):
    default_detail = 'A onfido error occurred.'
    default_error_slug = 'onfido_error'


class PlatformWebhookProcessingError(OnfidoError):
    default_detail = 'Platform webhook processing error.'
    default_error_slug = 'platform_webhook_processing_error.'
