import uuid

from pydantic import BaseModel

# Read-only external contract for the canonical catalog (POINT1-DB-001).
# Every field here is copied verbatim from a persisted column — never
# recomputed, concatenated, or coerced. In particular, Instrument never gains
# a `shape` field: freyja2_instruments deliberately has no structure_type
# column (see db/models/catalog.py), and this DTO mirrors that choice rather
# than inventing one at the API boundary.


class MarketRef(BaseModel):
    id: uuid.UUID
    code: str
    display_name: str


class ProductTypeRef(BaseModel):
    id: uuid.UUID
    code: str
    display_name: str


class AssetRef(BaseModel):
    id: uuid.UUID
    code: str
    display_name: str


class TimeframeRef(BaseModel):
    id: uuid.UUID
    code: str
    display_name: str
    duration_seconds: int


class InstrumentOut(BaseModel):
    instrument_id: uuid.UUID
    market: MarketRef
    product_type: ProductTypeRef
    canonical_symbol: str
    base_asset: AssetRef | None
    quote_asset: AssetRef | None
    underlying_asset: AssetRef | None
    underlying_instrument_id: uuid.UUID | None
    is_active: bool
    timeframes: list[TimeframeRef]
