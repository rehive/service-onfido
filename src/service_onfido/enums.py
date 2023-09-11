from enumfields.enums import Enum


class WebhookEvent(Enum):
    DOCUMENT_CREATE = 'document.create'
    DOCUMENT_UPDATE = 'document.update'
    USER_UPDATE = 'user.update'


class DocumentTypeSide(Enum):
    FRONT = "front"
    BACK = "back"


class OnfidoDocumentType(Enum):
    NATIONAL_IDENTITY_CARD = 'national_identity_card'
    DRIVING_LICENCE = 'driving_licence'
    PASSPORT = 'passport'
    VOTER_ID = 'voter_id'
    WORK_PERMIT = 'work_permit'
    # TODO : Do we want to support UNKNOWN in some way?
    # TODO : There are clearly more types, Onfido just documents them badly.


class CheckStatus(Enum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    CONSIDER = 'consider'
    CLEAR = 'clear'


class DocumentStatus(Enum):
    PENDING = 'pending'
    DECLINED = 'declined'
    VERIFIED = 'verified'
