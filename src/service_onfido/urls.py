from django.urls import re_path
from rest_framework.urlpatterns import format_suffix_patterns

from . import views


urlpatterns = (
    # Public
    re_path(r'^activate/$', views.ActivateView.as_view(), name='activate'),
    re_path(r'^deactivate/$', views.DeactivateView.as_view(), name='deactivate'),
    re_path(r'^webhook/$', views.WebhookView.as_view(), name='webhook'),

    # Onfido webhooks
    re_path(
        r'^onfido/webhook/(?P<company_id>\w+)/$',
        views.OnfidoWebhookView.as_view(),
        name='onfido-webhook-view'
    ),

    # Admin
    re_path(
        r'^admin/company/$',
        views.AdminCompanyView.as_view(),
        name='admin-company-view'
    ),
    re_path(
        r'^admin/document-types/$',
        views.AdminListDocumentTypeView.as_view(),
        name='admin-document-type-list'
    ),
    re_path(
        r'^admin/document-types/(?P<identifier>([a-zA-Z0-9\_\-]+))/$',
        views.AdminDocumentTypeView.as_view(),
        name='admin-documen-type-view'
    ),

    # Admin list documents
    # Admin retrieve documents
    # Admin list checks
    # Admin retrieve checks
)

urlpatterns = format_suffix_patterns(urlpatterns)
