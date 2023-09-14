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


# @receiver(m2m_changed, sender=Check.documents.through)
# def check_documents_post_save(
#         sender, instance, action, reverse, pk_set, **kwargs):
#     """
#     Fire off functionality when a document is saved on a check.
#     """

#     # No need to synchronize on fixture load.
#     if kwargs.get('raw', False):
#         return

#     if len(pk_set) == 0:
#         return

#     if action == "post_add":
#         instance.do_thing()
