import json
from urllib.parse import urlencode, unquote

from rest_framework import serializers, exceptions
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.parsers import BaseParser, ParseError
from rest_framework.renderers import JSONRenderer
from drf_rehive_extras.generics import *

from config import settings
from service_onfido.authentication import *
from service_onfido.serializers import *
from service_onfido.models import *


logger = getLogger('django')


"""
Parsers
"""

class RawJSONParser(BaseParser):
    media_type = 'application/json'
    renderer_class = JSONRenderer

    def parse(self, stream, media_type=None, parser_context=None):
        parser_context = parser_context or {}
        encoding = parser_context.get('encoding', settings.DEFAULT_CHARSET)
        request = parser_context.get('request')
        try:
            data = stream.read().decode(encoding)
            # setting a 'body' alike custom attr with raw POST content
            setattr(request, 'raw_body', data)
            return json.loads(data)
        except ValueError as exc:
            raise ParseError('JSON parse error - %s' % exc)


"""
Activation Endpoints
"""

class ActivateView(CreateAPIView):
    permission_classes = (AllowAny, )
    serializer_class = ActivateSerializer


class DeactivateView(CreateAPIView):
    permission_classes = (AllowAny, )
    serializer_class = DeactivateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.delete()
        return Response({'status': 'success'})


class WebhookView(CreateAPIView):
    """
    Rehive platform webhooks.
    """

    permission_classes = (AllowAny,)
    serializer_class = WebhookSerializer


class OnfidoWebhookView(CreateAPIView):
    """
    Onfido webhooks.
    """

    permission_classes = (AllowAny,)
    serializer_class = OnfidoWebhookSerializer
    parser_classes = (RawJSONParser,)


"""
Admin Endpoints
"""

class AdminCompanyView(RetrieveUpdateAPIView):
    serializer_class = AdminCompanySerializer
    authentication_classes = (AdminAuthentication,)

    def get_object(self):
        return self.request.user.company


class AdminListDocumentTypeView(ListCreateAPIView):
    serializer_class = AdminDocumentTypeSerializer
    authentication_classes = (AdminAuthentication,)

    def get_queryset(self):
        return DocumentType.objects.filter(
            company=self.request.user.company
        ).order_by('-created')


class AdminDocumentTypeView(RetrieveAPIView):
    serializer_class = AdminDocumentTypeSerializer
    authentication_classes = (AdminAuthentication,)

    def get_object(self):
        try:
            return DocumentType.objects.get(
                identifier=self.kwargs.get('identifier'),
                company=self.request.user.company
            )
        except DocumentType.DoesNotExist:
            raise exceptions.NotFound()
