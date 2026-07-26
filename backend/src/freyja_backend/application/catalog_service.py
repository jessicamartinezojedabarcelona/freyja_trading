import uuid

from sqlalchemy.orm import Session

from freyja_backend.db.models.catalog import Asset, Timeframe
from freyja_backend.dto.catalog import (
    AssetRef,
    InstrumentOut,
    MarketRef,
    ProductTypeRef,
    TimeframeRef,
)
from freyja_backend.dto.pagination import Page
from freyja_backend.repositories import catalog_repository
from freyja_backend.repositories.catalog_repository import InstrumentRow


def _asset_ref(asset: Asset | None) -> AssetRef | None:
    if asset is None:
        return None
    return AssetRef(id=asset.id, code=asset.code, display_name=asset.display_name)


def _timeframe_ref(timeframe: Timeframe) -> TimeframeRef:
    return TimeframeRef(
        id=timeframe.id,
        code=timeframe.code,
        display_name=timeframe.display_name,
        duration_seconds=timeframe.duration_seconds,
    )


def _instrument_out(
    row: InstrumentRow, timeframes_by_instrument: dict[uuid.UUID, list[Timeframe]]
) -> InstrumentOut:
    timeframes = timeframes_by_instrument.get(row.instrument.instrument_id, [])
    return InstrumentOut(
        instrument_id=row.instrument.instrument_id,
        market=MarketRef(
            id=row.market.id, code=row.market.code, display_name=row.market.display_name
        ),
        product_type=ProductTypeRef(
            id=row.product_type.id,
            code=row.product_type.code,
            display_name=row.product_type.display_name,
        ),
        canonical_symbol=row.instrument.canonical_symbol,
        base_asset=_asset_ref(row.base_asset),
        quote_asset=_asset_ref(row.quote_asset),
        underlying_asset=_asset_ref(row.underlying_asset),
        underlying_instrument_id=row.instrument.underlying_instrument_id,
        is_active=row.instrument.is_active,
        timeframes=[_timeframe_ref(tf) for tf in timeframes],
    )


def list_instruments(
    session: Session,
    *,
    market_code: str | None = None,
    product_type_code: str | None = None,
    symbol: str | None = None,
    timeframe_code: str | None = None,
    is_active: bool | None = None,
    limit: int,
    offset: int,
) -> Page[InstrumentOut]:
    rows, total = catalog_repository.list_instruments(
        session,
        market_code=market_code,
        product_type_code=product_type_code,
        symbol=symbol,
        timeframe_code=timeframe_code,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    instrument_ids = [row.instrument.instrument_id for row in rows]
    timeframes_by_instrument = catalog_repository.load_timeframes_for_instruments(
        session, instrument_ids
    )
    items = [_instrument_out(row, timeframes_by_instrument) for row in rows]
    return Page(items=items, total=total, limit=limit, offset=offset)


def get_instrument(session: Session, instrument_id: uuid.UUID) -> InstrumentOut | None:
    row = catalog_repository.get_instrument(session, instrument_id)
    if row is None:
        return None
    timeframes_by_instrument = catalog_repository.load_timeframes_for_instruments(
        session, [row.instrument.instrument_id]
    )
    return _instrument_out(row, timeframes_by_instrument)
