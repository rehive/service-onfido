from urllib.parse import urlencode, unquote

from rest_framework import serializers, exceptions
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from drf_rehive_extras.generics import *

from config import settings
from service_onfido.authentication import *
from service_onfido.serializers import *
from service_onfido.models import *


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
    permission_classes = (AllowAny,)
    serializer_class = WebhookSerializer


"""
Admin Endpoints
"""

class AdminCompanyView(RetrieveUpdateAPIView):
    serializer_class = AdminCompanySerializer
    authentication_classes = (AdminAuthentication,)

    def get_object(self):
        return self.request.user.company
