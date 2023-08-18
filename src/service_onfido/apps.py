from django.apps import AppConfig


class ServiceOnfidoAppConfig(AppConfig):
    name = 'service_onfido'

    def ready(self):
        import config.schema
