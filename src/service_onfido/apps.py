from django.apps import AppConfig


class ServiceOnfidoAppConfig(AppConfig):
    name = 'service_onfido'

    def ready(self):
        import service_onfido.receivers
        import config.schema
