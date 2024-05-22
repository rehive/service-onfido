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
from onfido.regions import Region
from onfido.exceptions import OnfidoInvalidSignatureError, OnfidoRequestError
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
from rest_framework import status

from config import settings
from service_onfido.exceptions import (
    PlatformWebhookProcessingError, OnfidoWebhookProcessingError,
    UserProcessingError, DocumentProcessingError, CheckProcessingError
)
from service_onfido.enums import (
    WebhookEvent, OnfidoDocumentType, CheckStatus, DocumentTypeSide,
    OnfidoDocumentReportResult
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

        # If the onfido API key is changing.
        if self.id and (self.original
                and self.onfido_api_key != self.original.onfido_api_key):
            self.configure_onfido()

        super().save(*args, **kwargs)

    @property
    def configured(self):
        """
        Check if the company is configured fully for onfido usage.
        """

        if (self.onfido_api_key
                and self.onfido_webhook_id
                and self.onfido_webhook_token
                and self.active):
            return True

        return False

    def configure_onfido(self):
        """
        Configure the company using the Onfido API key.
        """

        # If no API key is set, remove the webhook details.
        if not self.onfido_api_key:
            self.onfido_webhook_id = None
            self.onfido_webhook_token = None
            return

        onfido_api = onfido.Api(self.onfido_api_key, region=Region.EU)

        # If a webhook already exists, delete it.
        if self.onfido_webhook_id:
            try:
                onfido_api.webhook.delete(self.onfido_webhook_id)
            # Ignore 400 errors.
            except OnfidoRequestError:
                pass
            # Remove the webhook details.
            else:
                self.onfido_webhook_id = None
                self.onfido_webhook_token = None

        # Create the required webhook on Onfido.
        webhook = onfido_api.webhook.create(
            {
                "url": "{}onfido/webhook/{}/".format(
                    getattr(settings, 'BASE_URL'),
                    self.identifier
                ),
                "events": [
                    "check.withdrawn",
                    "check.completed"
                ]
            }
        )

        self.onfido_webhook_id = webhook["id"]
        self.onfido_webhook_token = webhook["token"]


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
        """
        Check if the user is configured fully for onfido usage.
        """

        if (self.onfido_id):
            return True

        return False

    @cached_property
    def platform_resource(self):
        """
        Get the resource directly from platform.
        """

        rehive = Rehive(self.company.admin.token)

        return rehive.admin.users.documents.get(self.identifier)

    @cached_property
    def onfido_resource(self):
        """
        Get the resource directly from onfido.
        """

        if not self.onfido_id:
            raise UserProcessingError("Improperly configured user")

        if not self.company.configured:
            raise UserProcessingError("Improperly configured company.")

        onfido_api = onfido.Api(self.company.onfido_api_key, region=Region.EU)

        return onfido_api.applicant.find(self.onfido_id)

    def generate_async(self):
        """
        Generate the user asynchronously.
        """

        tasks.generate_user.delay(self.id)

    def generate(self):
        """
        Generate the user.

        Generates an Onfido resource and populates the platform metadata.
        """

        if self.onfido_id:
            return

        self.generate_onfido_resource()
        self.generate_platform_resource()

    def generate_onfido_resource(self):
        """
        Generate an applicant on onfido.
        """

        if self.onfido_id:
            return

        if not self.company.configured:
            raise UserProcessingError("Improperly configured company.")

        onfido_api = onfido.Api(self.company.onfido_api_key, region=Region.EU)

        # Create customer on onfido.
        applicant = onfido_api.applicant.create({
            # TODO : Populate with the correct values.
            # Can default to dummy values as well.
            "first_name": "PLACEHOLDER",
            "last_name": "PLACEHOLDER",
            #"dob": "1984-01-01",
            #"address": {}
        })

        self.onfido_id = applicant["id"]
        self.save()

    def generate_platform_resource(self):
        """
        Generate the platform resource (Add metadata to it).
        """

        self.update_platform_resource({
            "metadata": {
                "service_onfido": {
                    "applicant": self.onfido_id
                }
            }
        })

    def update_platform_resource(self, data):
        """
        Update the platform resources with data.
        """

        rehive = Rehive(self.company.admin.token)

        rehive.admin.users.patch(str(self.identifier), **data)


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
        """
        Process the platform webhook asynchronously.
        """

        tasks.process_platform_webhook.delay(self.id)

    def process(self):
        """
        Process the platform webhook.
        """

        # Increment the number of tries.
        self.tries = self.tries + 1

        try:
            if self.event == WebhookEvent.DOCUMENT_CREATE:
                Document.objects.create_using_platform_event(
                    self.company, self.data
                )
            # FUTURE : Add functionality to handle check withdrawal.
            # updated directly in the platform.
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
        """
        Process the onfido webhook asynchronously.
        """

        tasks.process_onfido_webhook.delay(self.id)

    def process(self):
        """
        Process the onfido webhook.
        """

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
            # FUTURE : Add functionality to handle check withdrawal.
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
    Map Rehive document types to onfido document types. Also indictae the `side`
    of the document if necessary.
    """

    identifier = models.UUIDField(unique=True, default=uuid.uuid4)
    company = models.ForeignKey(
        'service_onfido.Company', on_delete=models.CASCADE
    )
    # Rehive document types have custom IDs per company, hence the need for a
    # mapping model like this.
    platform_type = models.CharField(max_length=64)
    # Onfido documents are always one of a known list (enum).
    onfido_type = EnumField(OnfidoDocumentType, max_length=100)
    # The side of the document, if this is relevant.
    side = EnumField(DocumentTypeSide, max_length=12, null=True, blank=True)

    class Meta:
        """
        Ensure that uniqueness is guaranteed across company, platform_type,
        onfido_type, and side.

        NOTE: We use conditional constraints here because NULL is a unique
        value in postgres sql.
        """

        constraints = [
            models.UniqueConstraint(
                fields=['company', 'platform_type', 'onfido_type', 'side',],
                condition=Q(side__isnull=False),
                name='unique_company_platform_type_onfido_type_side'
            ),

            models.UniqueConstraint(
                fields=['company', 'platform_type', 'onfido_type'],
                condition=Q(side__isnull=True),
                name='unique_company_platform_type_onfido_type'
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
            raise DocumentProcessingError("Improperly configured company.")

        # Ensure the event data has the necessary fields.
        try:
            document_id = data["id"]
            platform_user = data["user"]
            platform_type = data["type"]
        except KeyError:
            raise DocumentProcessingError("Invalid document event data.")

        # Find a document type using the event data.
        try:
            document_type = DocumentType.objects.get(
                platform_type=platform_type["id"], company=company
            )
        except DocumentType.DoesNotExist:
            raise DocumentProcessingError(
                "A document type mapping has not been configured."
            )

        # Find or create a user using the event data.
        user, created = User.objects.get_or_create(
            identifier=uuid.UUID(platform_user['id']), company=company
        )

        # Ensure the user's onfido resource has been generated.
        # TODO : Should this occur when the user is created for the first time.
        user.generate()

        # Create the document in the service.
        return self.create(
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

        return rehive.admin.users.documents.get(self.platform_id)

    @cached_property
    def onfido_resource(self):
        """
        Get the resource directly from onfido.
        """

        if not self.onfido_id:
            raise DocumentProcessingError("Improperly configured document.")

        if not self.user.company.configured:
            raise DocumentProcessingError("Improperly configured company.")

        onfido_api = onfido.Api(
            self.user.company.onfido_api_key, region=Region.EU
        )

        return onfido_api.document.find(self.onfido_id)

    def generate_async(self):
        """
        Generate the document asynchronously.
        """

        tasks.generate_document.delay(self.id)

    def generate(self):
        """
        Generate the document.

        Generates an Onfido resource and populates the platform metadata.
        """

        if self.onfido_id:
            return

        self.generate_onfido_resource()
        self.generate_platform_resource()

    def generate_onfido_resource(self):
        """
        Generate the onfido resources.
        """

        if self.onfido_id:
            return

        if not self.user.company.configured:
            raise DocumentProcessingError("Improperly configured company.")

        # Retrieve a file object using the Rehive resource URL.
        file_url = self.platform_resource["file"]
        res = requests.get(file_url, stream=True)
        if res.status_code != status.HTTP_200_OK:
            raise DocumentProcessingError("Invalid document file.")

        # Convert the bytes into a file.
        file = BytesIO(res.content)
        file.name = os.path.basename(file_url).split("?")[0]
        file.seek(0)

        # Generate ondifo document data.
        data = {
            "applicant_id": self.user.onfido_id,
            "type": self.type.onfido_type.value
        }
        # If the side is defined on the document add it to the `data`.
        if self.type.side:
            data["side"] = self.type.side.value

        onfido_api = onfido.Api(
            self.user.company.onfido_api_key, region=Region.EU
        )

        # Upload the document to the Onfido servers.
        onfido_document = onfido_api.document.upload(file, data)

        # Record the onfido ID on this object.
        self.onfido_id = onfido_document["id"]
        self.save()

        # Create a check
        self.attach_to_check()

    def generate_platform_resource(self):
        """
        Generate the platform resource (Add metadata to it).
        """

        self.update_platform_resource({
            "metadata": {
                "service_onfido": {
                    "applicant": self.user.onfido_id,
                    "document": self.onfido_id
                }
            }
        })

    def update_platform_resource(self, data):
        """
        Update the platform resources with data.
        """

        rehive = Rehive(self.user.company.admin.token)

        rehive.admin.users.documents.patch(self.platform_id, **data)

    @transaction.atomic
    def attach_to_check(self):
        """
        Create a check for this document.
        """

        if not self.onfido_id:
            raise DocumentProcessingError("Improperly configured document.")

        # Lock on the user to ensure only a single check can be created at a
        # time per user.
        user = User.objects.select_for_update().get(id=self.user.id)

        # Add to a check.
        # If this is a multi-side document.
        if self.type.side:
            # TODO : Generate the other side handling
            other_side = ""

            # Try and get a check containing a document of the same onfido
            # type but a different side.
            try:
                check = Check.objects.get(
                    user=self.user,
                    documents__type__onfido_type=self.type.onfido_type,
                    documents__type__side=other_side,
                )
            except Check.DoesNotExist:
                check = Check.objects.create(user=self.user, documents=[self])
            # If the document is added to an existing check, then both sides
            # are populated and the check can be set to PENDING.
            else:
                check.documents.add(self)
                check.status = CheckStatus.PENDING
                check.save()
        # If this is a single side document create a check.
        else:
            check = Check.objects.create(
                user=self.user,
                documents=[self],
                status=CheckStatus.PENDING
            )


class CheckManager(models.Manager):

    @transaction.atomic
    def create(self, documents=None, **kwargs):
        """
        Create a check and add associated documents in the same transaction.
        """

        check = super().create(**kwargs)

        if documents:
            check.documents.set(documents)

        return check


class Check(DateModel):
    """
    Map checks to onfido checks.

    Compiles multiple documents into a check that can be processed by Onfido.
    """

    identifier = models.UUIDField(unique=True, default=uuid.uuid4)
    user = models.ForeignKey(
        'service_onfido.User',
        related_name='documents',
        on_delete=models.CASCADE
    )
    onfido_id = models.CharField(max_length=64, null=True, blank=True)
    # List of documents that should be reported on.
    # FUTURE : Do we want to limit the number of documents accepted.
    documents = models.ManyToManyField('service_onfido.Document')
    # The internal status of this check, this does not store an onfido status.
    status = EnumField(
        CheckStatus, max_length=50, default=CheckStatus.INITIATING
    )

    objects = CheckManager()

    class Meta:
        constraints = [
            # Ensure that only one PROCESSING check can exist per user.
            models.UniqueConstraint(
                fields=['user', 'status'],
                condition=Q(
                    Q(status=CheckStatus.PROCESSING)
                ),
                name='unique_processing_check_per_user'
            ),
        ]

    def __str__(self):
        return str(self.identifier)

    @cached_property
    def onfido_resource(self):
        """
        Get the resource directly from onfido.
        """

        if not self.onfido_id:
            raise CheckProcessingError("Improperly configured check.")

        if not self.user.company.configured:
            raise CheckProcessingError("Improperly configured company.")

        onfido_api = onfido.Api(
            self.user.company.onfido_api_key, region=Region.EU
        )

        return onfido_api.check.find(self.onfido_id)

    @cached_property
    def onfido_report_resources(self):
        """
        Get the report resources directly from onfido.
        """

        if not self.onfido_id:
            raise CheckProcessingError("Improperly configured check.")

        if not self.user.company.configured:
            raise CheckProcessingError("Improperly configured company.")

        onfido_api = onfido.Api(
            self.user.company.onfido_api_key, region=Region.EU
        )

        return onfido_api.report.all(self.onfido_id)["reports"]

    def generate_async(self):
        """
        Generate the check asynchronously.
        """

        tasks.generate_check.delay(self.id)

    def generate(self):
        """
        Generate the check.

        Generates an Onfido resource.
        """

        if self.onfido_id:
            return

        self.generate_onfido_resource()

    @transaction.atomic
    def generate_onfido_resource(self):
        """
        Generate the onfido resources for this check.
        """

        if self.onfido_id:
            return

        if not self.user.company.configured:
            raise CheckProcessingError("Improperly configured company.")

        # Lock on the user to ensure only a single check per user can have
        # onfido resources generated at a time.
        user = User.objects.select_for_update().get(id=self.user.id)

        # Change status of this check
        self.status = CheckStatus.PROCESSING
        self.save()

        onfido_api = onfido.Api(
            self.user.company.onfido_api_key, region=Region.EU
        )

        # Generate the check.
        check = onfido_api.check.create({
            "applicant_id": self.user.onfido_id,
            "report_names": ["document"],
            "document_ids": [d.onfido_id for d in self.documents.all()]
        })

        self.onfido_id = check["id"]
        self.save()

    def evaluate_async(self):
        """
        Evaluate a check asynchronously.
        """

        tasks.evaluate_check.delay(self.id)

    @transaction.atomic
    def evaluate(self):
        """
        Evaluate a check.

        Evaluates each related check report to see if the platform needs updates.
        """

        if self.status in (CheckStatus.COMPLETE, CheckStatus.FAILED,):
            raise Exception("Check has already been evaluated.")

        # Lock on the user to ensure only a single check per user can be
        # evaluated at a time.
        user = User.objects.select_for_update().get(id=self.user.id)

        # Retrieve an onfido check resource.
        onfido_check = self.onfido_resource

        # Check whether the check is ready for evaluation.
        if onfido_check["status"] in ("complete", "withdrawn",):
            self.status = CheckStatus.COMPLETE
        else:
            raise CheckProcessingError("Check is not ready to be evaluated.")

        # Retrieve a list of reports for the check.
        onfido_reports = self.onfido_report_resources

        # Iterate through document reports and set a document_status.
        platform_document_status = None
        for report in [r for r in onfido_reports if r["name"] == "document"]:
            # If the report is complete fetch the sub_result
            if report["status"] == "complete":
                # Fetch a platform status for the report result.
                platform_document_status = OnfidoDocumentReportResult(
                    report["sub_result"]
                ).platform_document_status

        # Apply document status changes to all related documents.
        if platform_document_status:
            for d in self.documents.all():
                metadata = {
                    "service_onfido": {
                        "check": self.onfido_id
                    }
                }
                d.update_platform_resource({
                    "status": platform_document_status.value,
                    "metadata": metadata
                })

        # Save the status on the check.
        self.save()
