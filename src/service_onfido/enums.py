from enumfields.enums import Enum


class WebhookEvent(Enum):
    TRANSACTION_CREATE = 'transaction.create'
    CURRENCY_CREATE = 'currency.create'
    CURRENCY_UPDATE = 'currency.update'
    USER_UPDATE = 'user.update'

    class Labels:
        TRANSACTION_CREATE = 'transaction.create'
        CURRENCY_CREATE = 'currency.create'
        CURRENCY_UPDATE = 'currency.update'
