import os
import uuid
import requests
import json
from logging import getLogger
from decimal import Decimal
from datetime import timedelta

import onfido
from onfido.exceptions import OnfidoInvalidSignatureError
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
                Document.objects.create_from_event(
                    self.company, self.data
                )

            # elif self.event == WebhookEvent.DOCUMENT_UPDATE:
            #     pass

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
    platform_type = models.CharField(max_length=64)
    # Onfido documents are always one of a known list (enum).
    onfido_type = EnumField(OnfidoDocumentType, max_length=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'platform_type',],
                name='document_type_unique_company_platform_type'
            ),
            models.UniqueConstraint(
                fields=['company', 'onfido_type',],
                name='document_type_unique_company_onfido_type'
            ),
        ]

    def __str__(self):
        return str(self.identifier)


class DocumentManager(models.Manager):

    def create_from_event(self, company, data):
        # Ensure the event data has the necessary fields.
        try:
            document_id = data["id"]
            platform_user = data["user"]
            platform_type = data["type"]
        except KeyError:
            raise ValueError("Invalid document event data.")

        # Find a document type using the event data.
        try:
            document_type = DocumentType.objects.get(
                platform_type=platform_type["id"], company=company
            )
        except DocumentType.DoesNotExist:
            raise ValueError("A document type mapping has not been configured.")

        # Find (or create) a user using the event data.
        user, created = User.objects.get_or_create(
            identifier=uuid.UUID(platform_user['id']), company=company
        )
        # Ensure a customer ID exists on the user.
        user.generate_onfido_customer()

        # Instantiate the Onfido API.
        onfido_api = onfido.Api(company.onfido_api_key)
        # Generate a file to upload.
        request_file = open("sample_document.png", "rb")
        # Upload the document to the Onfido servers.
        onfido_document = onfido_api.document.upload(
            request_file,
            {
                "applicant_id": user.onfido_customer_id,
                "type": document_type.onfido_type
            }
        )

        # Create the document in this service.
        return self.create(
            user=user,
            platform_id=document_id,
            onfido_id=onfido_document["id"],
            type=document_type
        )

        # Post process: Apply metadata to the platform document.
        # Post process: Generate an onfido check.

    # TODO
    # Check if it is a multi side document
    # Maybe the document-type mapping should include an additional side field.


class Document(DateModel):
    """
    Map Rehive documents to onfido documents.
    """

    user = models.ForeignKey(
        'service_onfido.User',
        related_name='documents',
        on_delete=models.CASCADE
    )
    platform_id = models.CharField(max_length=64)
    onfido_id = models.CharField(max_length=64)
    type = models.ForeignKey(
        'service_onfido.DocumentType', on_delete=models.CASCADE
    )

    objects = DocumentManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'platform_id',],
                name='document_unique_user_platform_id'
            ),
            models.UniqueConstraint(
                fields=['user', 'onfido_id',],
                name='document_unique_user_onfido_id'
            ),
        ]

    def __str__(self):
        return str(self.identifier)

    @property
    def platform_resource(self):
        """
        Get the resource directly from platform.
        """

        rehive = Rehive(self.user.company.admin.token)

        resource = rehive.admin.users.documents.get(self.platform_id)

        return resource

    @property
    def onfido_resource(self):
        """
        Get the resource directly from onfido.
        """

        onfido_api = onfido.Api(self.user.company.onfido_api_key)

        resource = onfido_api.document.find(self.onfido_id)

        return resource

    def update_on_platform(self, data):
        pass

    def update_on_onfido(self, data):
        pass
