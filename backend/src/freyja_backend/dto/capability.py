import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from freyja_backend.db.models.capability import CapabilityStatus
from freyja_backend.dto.catalog import TimeframeRef

# Read-only external contract for technical capability (POINT1-CAPABILITY-001).
# The 5 CapabilityStatus values are always passed through verbatim — never
# coerced into a boolean, never reinterpreted.


class InstrumentRef(BaseModel):
    instrument_id: uuid.UUID
    canonical_symbol: str


class CapabilityProviderRef(BaseModel):
    kind: Literal["venue", "data_source"]
    id: uuid.UUID
    code: str
    display_name: str


class TechnicalCapabilityOut(BaseModel):
    id: uuid.UUID
    instrument: InstrumentRef
    timeframe: TimeframeRef
    provider: CapabilityProviderRef
    market_data_status: CapabilityStatus
    signal_detection_status: CapabilityStatus
    backtest_status: CapabilityStatus
    demo_execution_status: CapabilityStatus
    real_execution_status: CapabilityStatus
    settlement_status: CapabilityStatus
    reason_unavailable: str | None
    effective_from: datetime
    effective_to: datetime | None
