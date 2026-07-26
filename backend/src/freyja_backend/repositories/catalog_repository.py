import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session, aliased

from freyja_backend.db.models.catalog import (
    Asset,
    Instrument,
    InstrumentTimeframe,
    ProductType,
    Timeframe,
    UnderlyingMarket,
)

# Read-only queries for the canonical catalog (POINT1-DB-001). Every function
# issues a fixed, small number of round trips regardless of how many rows are
# returned: one query for the joined identity row(s), plus at most one batch
# query (WHERE ... IN (:ids)) for the one-to-many timeframe associations —
# never one query per instrument.

_BaseAsset = aliased(Asset)
_QuoteAsset = aliased(Asset)
_UnderlyingAsset = aliased(Asset)


@dataclass(frozen=True)
class InstrumentRow:
    instrument: Instrument
    market: UnderlyingMarket
    product_type: ProductType
    base_asset: Asset | None
    quote_asset: Asset | None
    underlying_asset: Asset | None


_InstrumentSelectRow = tuple[
    Instrument, UnderlyingMarket, ProductType, Asset | None, Asset | None, Asset | None
]


def _instrument_select() -> Select[_InstrumentSelectRow]:
    # sqlalchemy's own overloads type a plain select(...) column as non-optional
    # regardless of the outerjoin applied below (it has no way to see the join
    # type at the type-checker level) — the ignore reflects that library typing
    # gap, not an actual runtime risk: an outer join genuinely yields NULL here.
    return (
        select(  # type: ignore[return-value]
            Instrument, UnderlyingMarket, ProductType, _BaseAsset, _QuoteAsset, _UnderlyingAsset
        )
        .join(UnderlyingMarket, UnderlyingMarket.id == Instrument.underlying_market_id)
        .join(ProductType, ProductType.id == Instrument.product_type_id)
        .outerjoin(_BaseAsset, _BaseAsset.id == Instrument.base_asset_id)
        .outerjoin(_QuoteAsset, _QuoteAsset.id == Instrument.quote_asset_id)
        .outerjoin(_UnderlyingAsset, _UnderlyingAsset.id == Instrument.underlying_asset_id)
    )


def load_timeframes_for_instruments(
    session: Session, instrument_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[Timeframe]]:
    if not instrument_ids:
        return {}
    stmt = (
        select(InstrumentTimeframe.instrument_id, Timeframe)
        .join(Timeframe, Timeframe.id == InstrumentTimeframe.timeframe_id)
        .where(
            InstrumentTimeframe.instrument_id.in_(instrument_ids),
            InstrumentTimeframe.is_active.is_(True),
        )
        .order_by(Timeframe.duration_seconds, Timeframe.id)
    )
    result: dict[uuid.UUID, list[Timeframe]] = {}
    for instrument_id, timeframe in session.execute(stmt).all():
        result.setdefault(instrument_id, []).append(timeframe)
    return result


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
) -> tuple[list[InstrumentRow], int]:
    stmt = _instrument_select()

    conditions = []
    if market_code is not None:
        conditions.append(UnderlyingMarket.code == market_code)
    if product_type_code is not None:
        conditions.append(ProductType.code == product_type_code)
    if symbol is not None:
        conditions.append(Instrument.canonical_symbol == symbol)
    if is_active is not None:
        conditions.append(Instrument.is_active == is_active)
    if timeframe_code is not None:
        conditions.append(
            Instrument.instrument_id.in_(
                select(InstrumentTimeframe.instrument_id)
                .join(Timeframe, Timeframe.id == InstrumentTimeframe.timeframe_id)
                .where(
                    InstrumentTimeframe.is_active.is_(True),
                    Timeframe.code == timeframe_code,
                )
            )
        )
    if conditions:
        stmt = stmt.where(and_(*conditions))

    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    stmt = (
        stmt.order_by(
            UnderlyingMarket.code,
            ProductType.code,
            Instrument.canonical_symbol,
            Instrument.instrument_id,
        )
        .limit(limit)
        .offset(offset)
    )

    rows = [
        InstrumentRow(
            instrument=instrument,
            market=market,
            product_type=product_type,
            base_asset=base_asset,
            quote_asset=quote_asset,
            underlying_asset=underlying_asset,
        )
        for instrument, market, product_type, base_asset, quote_asset, underlying_asset in (
            session.execute(stmt).all()
        )
    ]
    return rows, total


def get_instrument(session: Session, instrument_id: uuid.UUID) -> InstrumentRow | None:
    stmt = _instrument_select().where(Instrument.instrument_id == instrument_id)
    row = session.execute(stmt).first()
    if row is None:
        return None
    instrument, market, product_type, base_asset, quote_asset, underlying_asset = row
    return InstrumentRow(
        instrument=instrument,
        market=market,
        product_type=product_type,
        base_asset=base_asset,
        quote_asset=quote_asset,
        underlying_asset=underlying_asset,
    )
