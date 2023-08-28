from django.dispatch import receiver
from django.db.models.signals import post_save

from service_onfido.models import Document
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
