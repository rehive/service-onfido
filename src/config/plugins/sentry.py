import os

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration


# Sentry
# ---------------------------------------------------------------------------------------------------------------------
sentry_sdk.init(
    os.environ.get('SENTRY_DSN_KEY'),
    integrations=[DjangoIntegration(), CeleryIntegration()],
    environment=os.environ.get('SENTRY_ENV')
)
