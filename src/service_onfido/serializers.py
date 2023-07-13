import uuid
import re

from rehive import Rehive, APIException
from rest_framework import serializers, exceptions
from django.db import transaction, IntegrityError
from django.utils.translation import gettext_lazy as _
from drf_rehive_extras.serializers import (
    BaseModelSerializer, DestroyModelSerializer
)
from drf_rehive_extras.fields import MetadataField, TimestampField, EnumField

from config import settings
from service_onfido.enums import (
    WebhookEvent
)
from service_onfido.models import (
    Company, User, PlatformWebhook
)
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

    def delete(self):
        company = self.validated_data['company']
        purge = self.validated_data.get('purge', False)
        if purge is True:
            company.delete()
            return
        company.active = False
        company.admin.token = None
        company.save()
        company.admin.save()


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
