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
    # TODO : There are more types, Onfido just documents them badly. We should
    # search the documents to try and find all types.


class CheckStatus(Enum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETE = 'complete'
    FAILED = 'failed'


class PlatformDocumentStatus(Enum):
    OBSOLETE = 'obsolete'
    DECLINED = 'declined'
    PENDING = 'pending'
    INCOMPLETE = 'incomplete'
    VERIFIED = 'verified'


class OnfidoReportResult(Enum):
    CLEAR = 'clear'
    CONSIDER = 'consider'
    UNIDENTIFIED = 'unidentifier'


class OnfidoDocumentReportResult(Enum):
    CLEAR = 'clear'
    REJECTED = 'rejected'
    SUSPECTED = 'suspected'
    CAUTION = 'caution'

    @staticmethod
    def get_platform_document_status(enum):
        """
        Map a onfido report result to a platform status.
        """

        key_map = {
            OnfidoDocumentReportResult.CLEAR: PlatformDocumentStatus.VERIFIED,
            OnfidoDocumentReportResult.REJECTED: PlatformDocumentStatus.DECLINED,
            OnfidoDocumentReportResult.SUSPECTED: PlatformDocumentStatus.DECLINED,
            OnfidoDocumentReportResult.CAUTION : PlatformDocumentStatus.DECLINED,
        }
        return key_map[self]
