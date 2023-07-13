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
from service_onfido.exceptions import (
    PlatformWebhookProcessingError
)
from service_onfido.enums import (
    WebhookEvent
)
from service_onfido.utils.common import (
    get_unique_filename, to_cents, truncate, from_cents
)
import service_onfido.tasks as tasks


logger = getLogger('django')


class Company(DateModel):
    identifier = models.CharField(max_length=100, unique=True, db_index=True)
    admin = models.OneToOneField(
        'service_onfido.User',
        related_name='admin_company',
        on_delete=models.CASCADE
    )
    secret = models.UUIDField(db_index=True, default=uuid.uuid4)
    manager_groups = ArrayField(
        models.CharField(max_length=80),
        size=10,
        null=True,
        blank=True,
        default=list
    )
    active = models.BooleanField(default=True)
    # Payout rules for the company.
    payout_exclusion_period = models.IntegerField(default=0)
    # Automated payout rules for the company.
    payout_day = models.IntegerField(default=4)
    payout_hour = models.IntegerField(default=0)

    def __str__(self):
        return self.identifier

    def natural_key(self):
        return (self.identifier,)


class User(DateModel):
    identifier = models.UUIDField(
        unique=True, db_index=True, default=uuid.uuid4
    )
    token = models.CharField(max_length=200, null=True)
    company = models.ForeignKey(
        'service_onfido.Company', null=True, on_delete=models.CASCADE,
    )

    def __str__(self):
        return str(self.identifier)


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
            logger.info("Do stuff here!")
        except Exception as exc:
            self.failed = now() if self.tries > self.MAX_RETRIES else None
            self.save()
            logger.exception(exc)
            raise PlatformWebhookProcessingError(exc)
        else:
            self.completed = now()
            self.save()
