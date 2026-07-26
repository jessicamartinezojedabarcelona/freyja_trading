import uuid

from pydantic import BaseModel

from freyja_backend.db.models.provider import (
    DataSourceInstrumentPurpose,
    DataSourceType,
    VenueType,
)

# Read-only external contract for provider mappings (POINT1-PROVIDER-001).
# provider_symbol is always kept in its own field, never merged with or
# substituted for canonical_symbol.


class VenueOut(BaseModel):
    id: uuid.UUID
    code: str
    display_name: str
    venue_type: VenueType
    is_active: bool


class DataSourceOut(BaseModel):
    id: uuid.UUID
    code: str
    display_name: str
    source_type: DataSourceType
    is_active: bool


class VenueInstrumentOut(BaseModel):
    id: uuid.UUID
    venue: VenueOut
    provider_symbol: str
    provider_contract_id: str | None
    is_active: bool


class DataSourceInstrumentOut(BaseModel):
    id: uuid.UUID
    data_source: DataSourceOut
    provider_symbol: str
    purpose: DataSourceInstrumentPurpose
    is_active: bool


class InstrumentMappingsOut(BaseModel):
    instrument_id: uuid.UUID
    venue_instruments: list[VenueInstrumentOut]
    data_source_instruments: list[DataSourceInstrumentOut]
