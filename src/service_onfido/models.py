import os
import uuid
import requests
import json
from logging import getLogger
from decimal import Decimal
from datetime import timedelta

from enumfields import EnumField
from rehive import Rehive, APIException
from django.db import models, transaction, IntegrityError
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.contrib.postgres.fields import ArrayField
from django_rehive_extras.models import DateModel

from config import settings
from service_onfido.exceptions import PlatformWebhookProcessingError
from service_onfido.enums import WebhookEvent, OnfidoDocumentType
from service_onfido.utils.common import (
    get_unique_filename, to_cents, truncate, from_cents
)
import service_onfido.tasks as tasks


logger = getLogger('django')


class Company(DateModel):
    identifier = models.CharField(max_length=100, unique=True)
    admin = models.OneToOneField(
        'service_onfido.User',
        related_name='admin_company',
        on_delete=models.CASCADE
    )
    secret = models.UUIDField(db_index=True, default=uuid.uuid4)
    # Stripe API keys and secrets.
    onfido_api_key = models.CharField(max_length=300, null=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.identifier

    def natural_key(self):
        return (self.identifier,)

    @property
    def configured(self):
        if (self.onfido_api_key and self.active):
            return True

        return False


class User(DateModel):
    identifier = models.UUIDField(unique=True, default=uuid.uuid4)
    token = models.CharField(max_length=200, null=True)
    company = models.ForeignKey(
        'service_onfido.Company', null=True, on_delete=models.CASCADE,
    )
    onfido_customer_id = models.CharField(
        unique=True, max_length=64, null=True
    )

    def __str__(self):
        return str(self.identifier)

    @property
    def configured(self):
        if (self.onfido_customer_id):
            return True

        return False


class PlatformWebhook(DateModel):
    # Webhook data.
    identifier = models.CharField(max_length=64, unique=True)
    company = models.ForeignKey(
        'service_onfido.Company', on_delete=models.CASCADE
    )
    event = EnumField(WebhookEvent, max_length=100, null=True, blank=True)
    data = models.JSONField(null=True, blank=True)
    # State data.
    completed = models.DateTimeField(null=True)
    failed = models.DateTimeField(null=True)
    tries = models.IntegerField(default=0)

    # Max number of retries allowed.
    MAX_RETRIES = 6

    class Meta:
        unique_together = ('identifier', 'company',)

    def __str__(self):
        return str(self.identifier)

    def process_async(self):
        tasks.process_platform_webhook.delay(self.id)

    def process(self):
        # Increment the number of tries.
        self.tries = self.tries + 1

        try:
            if self.event == WebhookEvent.DOCUMENT_CREATE:

                # TODO

                # Find if there is a mapping for the document.

                # Try and get an applicant ID (create one on onfido if necessary)
                # Ensure a location is provided?

                # For Prood of Address get a country issueing number

                # Check if it is a multi side document (
                # how do we know which side is getting uploaded
                # )
                # Maybe the document-type mapping should include an additional side field.

                # Upload the document and get an ID from onfido

                # Store the document in Document, with the correct types.

                # Update the document on rehive with metadata.


                pass
            elif self.event == WebhookEvent.DOCUMENT_UPDATE:
                pass

        except Exception as exc:
            self.failed = now() if self.tries > self.MAX_RETRIES else None
            self.save()
            logger.exception(exc)
            raise PlatformWebhookProcessingError(exc)
        else:
            self.completed = now()
            self.save()


class DocumentType(DateModel):
    """
    Map Rehive document types to onfido document types.
    """

    identifier = models.UUIDField(unique=True, default=uuid.uuid4)
    company = models.ForeignKey(
        'service_onfido.Company', on_delete=models.CASCADE
    )
    # Rehive document types are custom per company, hence the need for a
    # mapping model like this.
    rehive_type = models.CharField(max_length=64)
    # Onfido documents are always one of a known list (enum).
    onfido_type = EnumField(OnfidoDocumentType, max_length=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'rehive_type',],
                name='document_type_unique_company_rehive_type'
            ),
            models.UniqueConstraint(
                fields=['company', 'onfido_type',],
                name='document_type_unique_company_onfido_type'
            ),
        ]

    def __str__(self):
        return str(self.identifier)


class Document(DateModel):
    """
    Map Rehive documents to onfido documents.
    """

    user = models.ForeignKey(
        'service_onfido.User',
        related_name='documents',
        on_delete=models.CASCADE
    )
    rehive_id = models.CharField(max_length=64)
    onfido_id = models.CharField(max_length=64)
    type = models.ForeignKey(
        'service_onfido.DocumentType', on_delete=models.CASCADE
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'rehive_id',],
                name='document_unique_user_rehive_id'
            ),
            models.UniqueConstraint(
                fields=['user', 'onfido_id',],
                name='document_unique_user_onfido_id'
            ),
        ]

    def __str__(self):
        return str(self.identifier)

    @property
    def rehive_resource(self):
        """
        Get the resource directly from rehive.
        """

        return None

    @property
    def onfido_resource(self):
        """
        Get the resource directly from onfido.
        """

        return None

    def update_on_rehive(self, data):
        pass

    def update_on_onfido(self, data):
        pass
