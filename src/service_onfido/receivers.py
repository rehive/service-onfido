from django.dispatch import receiver
from django.db.models.signals import post_save, m2m_changed

from service_onfido.models import Document, Check
from service_onfido import tasks


@receiver(post_save, sender=Document)
def document_post_save(sender, instance, created, **kwargs):
    """
    Fire off functionality when a document is saved.
    """

    # Check if data was loaded from fixtures.
    if kwargs.get('raw', False):
        return

    if created:
        instance.generate_async()


@receiver(post_save, sender=Check)
def check_post_save(sender, instance, created, **kwargs):
    """
    Fire off functionality when a check is saved.
    """

    # Only pending, complete or failed checks are evaluated.
    if instance.status not in (
                CheckStatus.PENDING, CheckStatus.COMPLETE, CheckStatus.FAILED
            ):
        return

    # Get the first check that is currently processing.
    processing_check = Check.objects.filter(
        status=CheckStatus.PROCESSING,
        user=instance.user
    ).order_by("created").first()

    # Get the next pending check (the one that must be processed next).
    next_pending_check = Check.objects.filter(
        status=CheckStatus.PENDING,
        user=instance.user
    ).order_by("created").first()

    # There is an already processing check.
    # OR there is no next pending check to process.
    if processing_check or not next_pending_check:
        return

    # Generate the onfido resource (transitions the check to processing).
    next_pending_check.generate_async()
