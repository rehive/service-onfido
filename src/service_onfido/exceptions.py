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


class OnfidoWebhookProcessingError(OnfidoError):
    default_detail = 'Onfido webhook processing error.'
    default_error_slug = 'onfido_webhook_processing_error.'


class UserProcessingError(OnfidoException):
    default_detail = 'User processing error.'
    default_error_slug = 'user_processing_error.'


class DocumentProcessingError(OnfidoException):
    default_detail = 'Document processing error.'
    default_error_slug = 'document_processing_error.'


class CheckProcessingError(OnfidoException):
    default_detail = 'Check processing error.'
    default_error_slug = 'check_processing_error.'
