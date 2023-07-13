from django.urls import re_path
from rest_framework.urlpatterns import format_suffix_patterns

from . import views


urlpatterns = (
    # Public
    re_path(r'^activate/$', views.ActivateView.as_view(), name='activate'),
    re_path(r'^deactivate/$', views.DeactivateView.as_view(), name='deactivate'),
    re_path(r'^webhook/$', views.WebhookView.as_view(), name='webhook'),

    # Admin
    re_path(
        r'^admin/company/$',
        views.AdminCompanyView.as_view(), name='admin-company-view'
    ),
)

urlpatterns = format_suffix_patterns(urlpatterns)
