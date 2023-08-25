import uuid
import re

from onfido.webhook_event_verifier import WebhookEventVerifier
from onfido.exceptions import OnfidoInvalidSignatureError
from rehive import Rehive, APIException
from rest_framework import serializers, exceptions
from django.db import transaction, IntegrityError
from django.utils.translation import gettext_lazy as _
from drf_rehive_extras.serializers import BaseModelSerializer
from drf_rehive_extras.fields import MetadataField, TimestampField, EnumField

from config import settings
from service_onfido.enums import WebhookEvent, OnfidoDocumentType
from service_onfido.models import Company, User, DocumentType, PlatformWebhook
from service_onfido.authentication import HeaderAuthentication

from logging import getLogger


logger = getLogger('django')

# Exceptions messages from rehive.
GENERAL_DUPLICATE_EXC = "Duplicate key value violates unique constraint"
WEBHOOK_DUPLICATE_EXC = "A webhook with the url and event already exists"


class ActivateSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True)
    id = serializers.CharField(source='identifier', read_only=True)
    secret = serializers.UUIDField(read_only=True)

    def validate(self, validated_data):
        token = validated_data.get('token')
        rehive = Rehive(token)

        try:
            user = rehive.auth.get()
            groups = [g['name'] for g in user['groups']]
            if len(set(["admin", "service"]).intersection(groups)) <= 0:
                raise serializers.ValidationError(
                    {"token": ["Invalid admin user."]}
                )
        except APIException:
            raise serializers.ValidationError({"token": ["Invalid user."]})

        try:
            company = rehive.admin.company.get()
        except APIException:
            raise serializers.ValidationError({"token": ["Invalid company."]})

        validated_data['user'] = user
        validated_data['company'] = company

        return validated_data

    @transaction.atomic
    def create(self, validated_data):
        token = validated_data.get('token')
        rehive_user = validated_data.get('user')
        rehive_company = validated_data.get('company')

        rehive = Rehive(token)

        # Activate an existing company.
        try:
            company = Company.objects.get(
                identifier=rehive_company.get('id')
            )
        # If no company exists create a new new admin user and company.
        except Company.DoesNotExist:
            user = User.objects.create(
                token=token,
                identifier=uuid.UUID(rehive_user['id'])
            )
            company = Company.objects.create(
                admin=user,
                identifier=rehive_company.get('id')
            )
            user.company = company
            user.save()
        # If company existed then reactivate it.
        else:
            # If reactivating a company using a different service admin then
            # create a new user and set it as the admin.
            if str(company.admin.identifier) != rehive_user["id"]:
                user = User.objects.create(
                    token=token,
                    identifier=uuid.UUID(rehive_user['id']),
                    company=company
                )
                # Remove the token from the old admin.
                old_admin = company.admin
                old_admin.token = None
                old_admin.save()
                # Set the new admin.
                company.admin = user
                company.active = True
                company.save()
            # Else just update the admin token with the new one.
            else:
                company.admin.token = token
                company.admin.save()
                company.active = True
                company.save()

        # Add required platform webhooks to service automatically.
        platform_webhooks = [
            {
                "url": getattr(settings, 'BASE_URL') + 'webhook/',
                "event": WebhookEvent.DOCUMENT_CREATE.value,
                "secret": str(company.secret)
            },
            {
                "url": getattr(settings, 'BASE_URL') + 'webhook/',
                "event": WebhookEvent.DOCUMENT_UPDATE.value,
                "secret": str(company.secret)
            }
        ]

        for webhook in platform_webhooks:
            try:
                rehive.admin.webhooks.post(**webhook)
            except APIException as exc:
                if (hasattr(exc, 'data')
                        and (GENERAL_DUPLICATE_EXC in exc.data['message']
                        or WEBHOOK_DUPLICATE_EXC in exc.data['message'])):
                    # The webhook already exists, ignore this error.
                    pass
                else:
                    raise serializers.ValidationError(
                        {"non_field_errors":
                            ["Unable to configure event webhooks."]
                        }
                    )

        # TODO
        # Add required onfido webhooks to service automatically.
        onfido_webhooks = []

        for webhook in onfido_webhooks:
            continue

        return company


class DeactivateSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True)
    purge = serializers.BooleanField(write_only=True, required=False, default=False)

    def validate(self, validated_data):
        token = validated_data.get('token')
        rehive = Rehive(token)

        try:
            user = rehive.auth.get()
            groups = [g['name'] for g in user['groups']]
            if len(set(["admin", "service"]).intersection(groups)) <= 0:
                raise serializers.ValidationError(
                    {"token": ["Invalid admin user."]})
        except APIException:
            raise serializers.ValidationError({"token": ["Invalid user."]})

        try:
            validated_data['company'] = Company.objects.get(
                identifier=user['company']
            )
        except Company.DoesNotExist:
            raise serializers.ValidationError(
                {"token": ["Inactive company."]})

        return validated_data

    def create(self, validated_data):
        """
        Modify the create to deactivate the company.
        """

        company = validated_data.get('company')
        purge = validated_data.get('purge', False)
        if purge is True:
            company.delete()
            return validated_data
        company.active = False
        company.admin.token = None
        company.save()
        company.admin.save()

        return validated_data


class WebhookSerializer(serializers.Serializer):
    id = serializers.CharField()
    event = serializers.ChoiceField(
        choices=WebhookEvent.choices(), required=True, source='event.value'
    )
    company = serializers.CharField()
    data = serializers.JSONField()

    def validate_company(self, company):
        request = self.context['request']

        try:
            secret = HeaderAuthentication.get_auth_header(
                request, name="secret"
            )
            company = Company.objects.get(
                identifier=company, secret=secret, active=True
            )
        except (Company.DoesNotExist, ValueError):
            raise serializers.ValidationError("Invalid company.")

        return company

    def create(self, validated_data):
        id = validated_data.get('id')
        data = validated_data.get('data')
        event = validated_data['event']['value']
        company = validated_data.get('company')

        # Log a webhook event so that we have the webhooks state stored and
        # we can ensure webhooks are handled idempotently.
        try:
            webhook = PlatformWebhook.objects.create(
                identifier=id,
                company=company,
                event=WebhookEvent(event),
                data=data
            )
        except IntegrityError:
            # The webhook has already been received, do nothing.
            logger.info("Webhook already received.")
        else:
            webhook.process_async()

        return validated_data


class OnfidoWebhookSerializer(serializers.Serializer):
    payload = serializers.JSONField()

    def validate(self, validated_data):
        # Get the payload so we can find the correct secret tooken for the
        # registered webhook.
        payload = validated_data.get("payload")

        # Get the signature from the headers.
        signature = self.context['request'].META.get('HTTP_X_SHA2_SIGNATURE')

        # Check if it is a valid company that is properly configured.
        try:
            company = Company.objects.get(
                identifier=self.context.get('view').kwargs.get('company_id')
            )
        except Company.DoesNotExist:
            raise serializers.ValidationError(
                {"non_field_errors": ["Invalid company."]}
            )

        if not company.configured:
            raise serializers.ValidationError(
                {'non_field_errors': ["The company is improperly configured."]}
            )

        # TODO
        # Retrieve a secret token for the specific webhook event registered in
        # Onfido.
        try:
            secret_token = company.onfidowebhooks.get(
                event=payload.get("action")
            ).secret_token
        except OnfidoWebhook.DoesNotExist:
            raise serializers.ValidationError(
                {'non_field_errors': [
                    "The event is not registered for this company."
                ]}
            )

        # Create an instance of the Onfido webhook verifier.
        verifier = WebhookEventVerifier(secret_token)

        # Read and verify the signature using the raw request body.
        try:
            event = verifier.read_payload(
                self.context['request'].raw_body, signature
            )
        except ValueError:
            raise serializers.ValidationError(
                {'non_field_errors': ["Invalid payload."]}
            )
        except OnfidoInvalidSignatureError:
            raise serializers.ValidationError(
                {'non_field_errors': ["Invalid signature."]}
            )

        # TODO : Add company into validated_data

        return validated_data

    def create(self, validated_data):
        payload = validated_data.get("payload")
        company = validated_data.get("company")

        # Perform necessary functionality based on the payload action.
        if payload.get("action") in ("check.completed", "check.withdrawn",):
            try:
                check = Check.objects.get(
                    onfido_id=payload["object"]["id"],
                    user__company=company
                )
            # The check does not exist in the database, ignore it.
            except Check.DoesNotExist:
                logger.error(
                    "Check does not exist: {}.".format(payload["object"]["id"])
                )
            # Evaluate the check
            else:
                check.evaluate_async()

        return validated_data


# User

class CompanySerializer(BaseModelSerializer):
    id = serializers.CharField(source='identifier', read_only=True)

    class Meta:
        model = Company
        fields = ('id',)
        read_only_fields = ('id',)


# Admin

class AdminCompanySerializer(CompanySerializer):
    secret = serializers.UUIDField(read_only=True)

    class Meta:
        model = Company
        fields = ('id', 'secret',)
        read_only_fields = ('id', 'secret',)


class AdminDocumentTypeSerializer(BaseModelSerializer):
    id = serializers.CharField(read_only=True, source='identifier')
    onfido_type = EnumField(enum=OnfidoDocumentType)
    created = TimestampField(read_only=True)
    updated = TimestampField(read_only=True)

    class Meta:
        model = DocumentType
        fields = (
            'id',
            'rehive_type',
            'onfido_type',
            'created',
            'updated',
        )
        read_only_fields = (
            'id',
            'created',
            'updated',
        )

    def validate(self, validated_data):
        validated_data["company"] = self.context.get('request').user.company
        return validated_data
