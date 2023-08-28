import os
import uuid
import requests
import json
import mimetypes
from logging import getLogger
from decimal import Decimal
from datetime import timedelta
from io import BytesIO, BufferedReader

import onfido
from onfido.exceptions import OnfidoInvalidSignatureError
from enumfields import EnumField
from rehive import Rehive, APIException
from django.db import models, transaction, IntegrityError
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.contrib.postgres.fields import ArrayField
from django_rehive_extras.models import DateModel, StateModel
from django.utils.functional import cached_property
from django.core.files.uploadedfile import InMemoryUploadedFile

from config import settings
from service_onfido.exceptions import (
    PlatformWebhookProcessingError, OnfidoWebhookProcessingError
)
from service_onfido.enums import (
    WebhookEvent, OnfidoDocumentType, CheckStatus, DocumentStatus
)
from service_onfido.utils.common import (
    get_unique_filename, to_cents, truncate, from_cents
)
import service_onfido.tasks as tasks


logger = getLogger('django')


class Company(DateModel, StateModel):
    identifier = models.CharField(max_length=100, unique=True)
    admin = models.OneToOneField(
        'service_onfido.User',
        related_name='admin_company',
        on_delete=models.CASCADE
    )
    secret = models.UUIDField(db_index=True, default=uuid.uuid4)
    active = models.BooleanField(default=True)
    # Onfido API keys and secrets.
    onfido_api_key = models.CharField(max_length=300, null=True)
    # Onfido webhook details
    onfido_webhook_id = models.CharField(max_length=64, null=True)
    onfido_webhook_token = models.CharField(max_length=300, null=True)

    def __str__(self):
        return self.identifier

    @transaction.atomic
    def save(self, *args, **kwargs):
        """
        Configure webhooks.
        """

        super().save(*args, **kwargs)

        # If the onfido API key is changing.
        if self.id and (self.original
                and self.onfido_api_key != self.original.onfido_api_key):
            self.configure_onfido()

    def natural_key(self):
        return (self.identifier,)

    @property
    def configured(self):
        if (self.onfido_api_key
                and self.onfido_webhook_id
                and self.onfido_webhook_token
                and self.active):
            return True

        return False

    def configure_onfido(self):
        """
        Configure Onfido using the API key.
        """

        # If no API key is set, remove the webhook details.
        if not self.onfido_api_key:
            self.onfido_webhook_id = None
            self.onfido_webhook_token = None
            self.save()
            return

        onfido_api = onfido.Api(self.onfido_api_key)

        # If a webhook already exists, delete it.
        if self.onfido_webhook_id:
            try:
                api.webhook.delete(self.onfido_webhook_id)
            # Ignore 400 errors.
            except OnfidoRequestError:
                pass
            # Remove the webhook details.
            else:
                self.onfido_webhook_id = None
                self.onfido_webhook_token = None
                self.save()

        # Create the required webhook on Onfido.
        webhook = onfido_api.webhook.create(
            {
                "url": getattr(settings, 'BASE_URL') + 'onfido/webhook/',
                "events": [
                    "check.withdrawn",
                    "check.completed"
                ]
            }
        )

        self.onfido_webhook_id = webhook["id"]
        self.onfido_webhook_token = webhook["token"]
        self.save()


class User(DateModel):
    identifier = models.UUIDField(unique=True, default=uuid.uuid4)
    token = models.CharField(max_length=200, null=True)
    company = models.ForeignKey(
        'service_onfido.Company', null=True, on_delete=models.CASCADE,
    )
    onfido_id = models.CharField(
        unique=True, max_length=64, null=True
    )

    def __str__(self):
        return str(self.identifier)

    @property
    def configured(self):
        if (self.onfido_id):
            return True

        return False

    @cached_property
    def platform_resource(self):
        """
        Get the resource directly from platform.
        """

        rehive = Rehive(self.company.admin.token)

        resource = rehive.admin.users.documents.get(self.identifier)

        return resource

    @cached_property
    def onfido_resource(self):
        """
        Get the resource directly from onfido.
        """

        if not self.onfido_id:
            raise Exception("Improperly configured user")

        if not self.company.configured:
            raise Exception("Improperly configured company.")

        onfido_api = onfido.Api(self.company.onfido_api_key)

        resource = onfido_api.applicant.find(self.onfido_id)

        return resource

    def generate_onfido_applicant(self):
        """
        Generate a customer on onfido.
        """

        if self.onfido_id:
            return

        if not self.company.configured:
            raise Exception("Improperly configured company.")

        onfido_api = onfido.Api(self.company.onfido_api_key)

        # Create customer on onfido.
        applicant = api.applicant.create({
            # TODO : Populate with the correct values.
            # Can default to dummy values as well.
            "first_name": "Jane",
            "last_name": "Doe",
            #"dob": "1984-01-01",
            #"address": {}
        })

        self.onfido_id = applicant["id"]
        self.save()


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
                Document.objects.create_using_platform_event(
                    self.company, self.data
                )
            # TODO : Add functionality to override statuses OR withdraw checks
            # if the status is updated directly in the platform.
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


class OnfidoWebhook(DateModel):
    # Webhook data.
    identifier = models.CharField(max_length=64, unique=True)
    company = models.ForeignKey(
        'service_onfido.Company', on_delete=models.CASCADE
    )
    payload = models.JSONField(null=True, blank=True)
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
        tasks.process_onfido_webhook.delay(self.id)

    def process(self):
        # Increment the number of tries.
        self.tries = self.tries + 1

        try:
            # Perform necessary functionality based on the payload action.
            if self.payload.get("action") in "check.completed":
                # Try and get a check in the service database.
                try:
                    check = Check.objects.get(
                        onfido_id=payload["object"]["id"],
                        user__company=self.company
                    )
                except Check.DoesNotExist:
                    pass
                # Evaluate the check if it exists.
                else:
                    check.evaluate_async()
            # TODO : Add functionality to withdraw checks and fail the
            # associated documents.
            # elif self.payload.get("action") in "check.withdrawn":
            #     pass

        except Exception as exc:
            self.failed = now() if self.tries > self.MAX_RETRIES else None
            self.save()
            logger.exception(exc)
            raise OnfidoWebhookProcessingError(exc)
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

    @transaction.atomic
    def create_using_platform_event(self, company, data):
        """
        Create a document using event data from the platform.
        """

        if not company.configured:
            raise Exception("Improperly configured company.")

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

        # Find or create a user using the event data.
        user, created = User.objects.get_or_create(
            identifier=uuid.UUID(platform_user['id']), company=company
        )

        # Create the document in this service.
        document = self.create(
            user=user, platform_id=document_id, type=document_type
        )


class Document(DateModel):
    """
    Map Rehive documents to onfido documents.
    """

    identifier = models.UUIDField(unique=True, default=uuid.uuid4)
    user = models.ForeignKey(
        'service_onfido.User',
        related_name='user_documents',
        on_delete=models.CASCADE
    )
    platform_id = models.CharField(max_length=64)
    onfido_id = models.CharField(max_length=64, null=True, blank=True)
    type = models.ForeignKey(
        'service_onfido.DocumentType', on_delete=models.CASCADE
    )
    status = EnumField(
        DocumentStatus, max_length=50, default=DocumentStatus.PENDING
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

    @cached_property
    def platform_resource(self):
        """
        Get the resource directly from platform.
        """

        rehive = Rehive(self.user.company.admin.token)

        resource = rehive.admin.users.documents.get(self.platform_id)

        return resource

    @cached_property
    def onfido_resource(self):
        """
        Get the resource directly from onfido.
        """

        if not self.onfido_id:
            raise Exception("Improperly configured document.")

        if not self.user.company.configured:
            raise Exception("Improperly configured company.")

        onfido_api = onfido.Api(self.user.company.onfido_api_key)

        resource = onfido_api.document.find(self.onfido_id)

        return resource

    def generate_async(self):
        """
        Generate the document async.
        """

        tasks.generate_document.delay(self.id)

    def generate(self):
        """
        Generate the necessary onfido details and upload the file.
        """

        # Generate an onfido applicant if one has not been generated yet.
        self.user.generate_onfido_applicant()

        # Retrieve a file object using the Rehive resource URL.
        res = requests.get(self.platform_resource["file"], stream=True)
        if res.status_code != status.HTTP_200_OK:
            raise Exception("Invalid document file.")

        # Convert the file into an in memory upload file.
        content_type = res.headers.get('content-type', 'image/png')
        file = BufferedReader(
            InMemoryUploadedFile(
                BytesIO(res.content),
                '',
                os.path.basename(self.platform_resource["file"]),
                content_type,
                len(res.content),
                'utf8'
            )
        )

        # Upload the document to the Onfido servers.
        onfido_document = onfido_api.document.upload(
            file,
            {
                "applicant_id": user.onfido_id,
                "type": document_type.onfido_type
            }
        )

        # Record the onfido ID on this object.
        self.onfido_id = onfido_document["id"]
        self.save()

        # TODO : Should this generate the check here as well.

    def transition_async(self, status):
        """
        Process the status async.
        """

        tasks.transition_document.delay(self.id, status)

    def transition(self, status):
        """
        Transition the status of the document.
        """

        if self.status == status:
            return

        rehive = Rehive(self.user.company.admin.token)

        """

        Populate metadata with onfido ID on PLATFORM

        Create a check if necessary and add document to it.

        Add document to an existing check if a front/back document.

        Update the PLATFORM document when the document is updated.

        """

        # Transition to PENDING and populate metadata.
        # TODO : Only link this once the check is complete.
        if status in (DocumentStatus.PENDING,):
            # Update on the platform.
            rehive.admin.users.documents.patch(
                self.platform_id,
                metadata={
                    "service_onfido": {
                        "document": {
                            "id": self.onfido_id,
                            "applicant_id": self.user.onfido_id,
                        }
                    }
                }
            )

        # If final status is changed, modify on the platform.
        if status in (DocumentStatus.VERIFIED, DocumentStatus.DECLINED):
            # Update on the platform.
            rehive.admin.users.documents.patch(
                self.platform_id, status=status.value
            )

        # Update the document status.
        self.status = status
        self.save()


class Check(DateModel):
    """
    Map checks to onfido checks.

    Compiles multiple documents into a check that can be processed later.
    """

    identifier = models.UUIDField(unique=True, default=uuid.uuid4)
    user = models.ForeignKey(
        'service_onfido.User',
        related_name='documents',
        on_delete=models.CASCADE
    )
    onfido_id = models.CharField(max_length=64)
    # List of documents that should be reported on.
    # TODO : Do we want to limit the number of documents accepted.
    documents = models.ManyToManyField('service_onfido.Document')
    status = EnumField(
        CheckStatus, max_length=50, default=CheckStatus.PENDING
    )

    def __str__(self):
        return str(self.identifier)

    @cached_property
    def onfido_resource(self):
        """
        Get the resource directly from onfido.
        """

        if not self.onfido_id:
            raise Exception("Improperly configured check.")

        if not self.user.company.configured:
            raise Exception("Improperly configured company.")

        onfido_api = onfido.Api(self.user.company.onfido_api_key)

        resource = onfido_api.check.find(self.onfido_id)

        return resource

    def generate_async(self):
        """
        Generate the check async.
        """

        tasks.generate_check.delay(self.id)

    def generate(self):
        """
        Generate the check by creating it in onfido.
        """

        if self.onfido_id:
            raise Exception("Check has already been generated.")

        if not self.user.company.configured:
            raise Exception("Improperly configured company.")

        # Change status of this check
        self.status = CheckStatus.PROCESSING
        self.save()

        onfido_api = onfido.Api(self.user.company.onfido_api_key)

        # Generate the check.
        check = api.check.create({
            "applicant_id": self.user.onfido_id,
            "report_names": ["document"],
            "document_ids": [d.onfido_id for d in self.documents.all()]
        })

        self.onfido_id = check["id"]
        self.save()

    def evaluate_async(self):
        """
        Evaluate a check async.
        """

        tasks.evaluate_check.delay(self.id)

    def evaluate(self):
        """
        Evaluate a check after it is updated on Onfido.
        """

        if self.onfido_id:
            raise Exception(
                "Cannot evaluate a check that has not been generated."
            )

        if not self.user.company.configured:
            raise Exception("Improperly configured company.")

        # Get the onfido object.
        onfido_check = self.onfido_resource

        # Check if statuses need to change.
        if onfido_check["result"] == "consider":
            new_status = CheckStatus.CONSIDER
            document_status = DocumentStatus.DECLINED
        elif onfido_check["result"] == "clear":
            new_status = CheckStatus.CLEAR
            document_status = DocumentStatus.VERIFIED
        else:
            new_status = None
            document_status = None

        # Check if thie check has been evaluated already.
        if not new_status or self.status == new_status:
            return

        # Apply document status changes to all related documents.
        for d in self.documents.all():
            d.transition(document_status)

        # Update the checks status.
        self.status = new_status
        self.save()
