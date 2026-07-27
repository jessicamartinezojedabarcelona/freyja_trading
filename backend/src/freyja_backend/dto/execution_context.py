import uuid

from pydantic import BaseModel

from freyja_backend.db.models.capability import (
    ActivationStatus,
    CredentialsStatus,
    ExecutionEnvironment,
    OwnerAuthorizationStatus,
    VenuePermissionStatus,
)
from freyja_backend.dto.catalog import ProductTypeRef
from freyja_backend.dto.provider import VenueOut

# Read-only external contract for ExecutionContext (POINT1-CAPABILITY-001,
# corrected by POINT1-CAPABILITY-API-CORRECTION-001). Never includes
# credentials, tokens, or secret material — only the opaque account_key and
# status enums, passed through verbatim (never coerced into a single
# can_trade boolean). venue_permission_status is the broker's own reported
# permission/availability, normalized by Freyja — never an internal
# jurisdiction/regulatory determination; Freyja does not model or expose
# jurisdiction, client classification, or regulatory-rule evidence.


class ExecutionContextOut(BaseModel):
    id: uuid.UUID
    account_key: str
    venue: VenueOut
    product_type: ProductTypeRef
    execution_environment: ExecutionEnvironment
    credentials_status: CredentialsStatus
    venue_permission_status: VenuePermissionStatus
    owner_authorization_status: OwnerAuthorizationStatus
    activation_status: ActivationStatus
    suspension_reasons: list[str] | None
