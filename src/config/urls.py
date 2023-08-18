from django.urls import include, path, re_path
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from drf_spectacular.views import (
    SpectacularJSONAPIView, SpectacularSwaggerView, SpectacularRedocView
)

from service_onfido.urls import urlpatterns


admin.autodiscover()

urlpatterns = [
    # Administration
    re_path(r'^admin/', admin.site.urls),

    # Documentation
    re_path(
        r'^schema.json$',
        SpectacularJSONAPIView.as_view(
            api_version='1',
            urlconf=urlpatterns,
            custom_settings={
                'TITLE': 'Onfido Service API',
                'DESCRIPTION': """
The **Onfido Service API** is used for managing KYC in Rehive using Onfido.
                    """,
                'VERSION': '1',
            }
        ),
        name='schema'
    ),
    re_path(
        r'^swagger/?$',
        SpectacularSwaggerView.as_view(url_name='schema'),
        name='swagger-ui'
    ),
    re_path(
        r'^/?$',
        SpectacularRedocView.as_view(url_name='schema'),
        name='redoc-ui'
    ),

    # API
    re_path(
        r'^api/',
        include(
            ('service_onfido.urls', 'service_onfido'),
            namespace='service_onfido'
        )
    ),
]
