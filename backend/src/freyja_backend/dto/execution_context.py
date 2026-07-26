import uuid
from datetime import datetime

from pydantic import BaseModel

from freyja_backend.db.models.capability import (
    ActivationStatus,
    CredentialsStatus,
    ExecutionEnvironment,
    OwnerAuthorizationStatus,
    RegulatoryEligibilityStatus,
    RegulatoryRuleEffect,
    VenuePermissionStatus,
)
from freyja_backend.dto.catalog import ProductTypeRef
from freyja_backend.dto.provider import VenueOut

# Read-only external contract for ExecutionContext (POINT1-CAPABILITY-001).
# Never includes credentials, tokens, or secret material — only the opaque
# account_key and status enums, passed through verbatim (never coerced into a
# single can_trade boolean).


class RegulatoryRuleEvidenceOut(BaseModel):
    id: uuid.UUID
    jurisdiction: str
    client_classification: str | None
    effect: RegulatoryRuleEffect
    source_citation: str
    verified_at: datetime
    effective_from: datetime
    effective_to: datetime | None


class ExecutionContextOut(BaseModel):
    id: uuid.UUID
    account_key: str
    venue: VenueOut
    product_type: ProductTypeRef
    execution_environment: ExecutionEnvironment
    jurisdiction: str
    client_classification: str
    credentials_status: CredentialsStatus
    venue_permission_status: VenuePermissionStatus
    regulatory_eligibility_status: RegulatoryEligibilityStatus
    owner_authorization_status: OwnerAuthorizationStatus
    activation_status: ActivationStatus
    suspension_reasons: list[str] | None
    regulatory_rules: list[RegulatoryRuleEvidenceOut]
