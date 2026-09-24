import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from freyja_backend.db.models.catalog import (
    Instrument,
    InstrumentTimeframe,
    ProductType,
    Timeframe,
    UnderlyingMarket,
)
from freyja_backend.db.models.market_data import Candle, MarketDataSyncState
from freyja_backend.db.models.provider import (
    DataSource,
    DataSourceInstrument,
    DataSourceInstrumentPurpose,
)
from freyja_backend.domain.market_data import Candle as CandleValue
from freyja_backend.domain.market_data import DataQuality

# Queries for market-data persistence (MARKET-DATA-PERSISTENCE-001). Candles
# are only ever inserted, never updated: the database itself rejects UPDATE
# (migration 0013), so this module has no update path for them at all.


@dataclass(frozen=True, slots=True)
class SeriesKey:
    """Identifies one stored series: a source's candles for one instrument and
    timeframe. Every query below is scoped to exactly one, so a read can never
    mix instruments, timeframes or providers."""

    data_source_id: uuid.UUID
    instrument_id: uuid.UUID
    timeframe_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class InsertOutcome:
    inserted: int
    unchanged: int
    # Open times whose stored values differ from what the provider now reports.
    revised: tuple[datetime, ...]


def get_data_source(session: Session, code: str) -> DataSource | None:
    return session.execute(select(DataSource).where(DataSource.code == code)).scalar_one_or_none()


def get_instrument(
    session: Session, *, market_code: str, product_code: str, symbol: str
) -> Instrument | None:
    return session.execute(
        select(Instrument)
        .join(UnderlyingMarket, UnderlyingMarket.id == Instrument.underlying_market_id)
        .join(ProductType, ProductType.id == Instrument.product_type_id)
        .where(
            UnderlyingMarket.code == market_code,
            ProductType.code == product_code,
            Instrument.canonical_symbol == symbol,
        )
    ).scalar_one_or_none()


def get_timeframe(session: Session, code: str) -> Timeframe | None:
    return session.execute(select(Timeframe).where(Timeframe.code == code)).scalar_one_or_none()


def has_active_instrument_timeframe(
    session: Session, instrument_id: uuid.UUID, timeframe_id: uuid.UUID
) -> bool:
    return (
        session.execute(
            select(InstrumentTimeframe.instrument_id).where(
                InstrumentTimeframe.instrument_id == instrument_id,
                InstrumentTimeframe.timeframe_id == timeframe_id,
                InstrumentTimeframe.is_active.is_(True),
            )
        ).first()
        is not None
    )


def get_analysis_mapping(
    session: Session, data_source_id: uuid.UUID, instrument_id: uuid.UUID
) -> DataSourceInstrument | None:
    return session.execute(
        select(DataSourceInstrument).where(
            DataSourceInstrument.data_source_id == data_source_id,
            DataSourceInstrument.instrument_id == instrument_id,
            DataSourceInstrument.purpose == DataSourceInstrumentPurpose.ANALYSIS,
            DataSourceInstrument.is_active.is_(True),
        )
    ).scalar_one_or_none()


def insert_candles(
    session: Session,
    key: SeriesKey,
    candles: Sequence[CandleValue],
    *,
    quality: DataQuality,
    received_at: datetime,
) -> InsertOutcome:
    """Store `candles` idempotently and report what happened to each.

    New candles are inserted. A candle that already exists is left exactly as
    it is: if the provider's values match it counts as `unchanged`, if they
    differ it is reported in `revised` — never overwritten.
    """
    if not candles:
        return InsertOutcome(inserted=0, unchanged=0, revised=())

    rows = [
        {
            "data_source_id": key.data_source_id,
            "instrument_id": key.instrument_id,
            "timeframe_id": key.timeframe_id,
            "open_time": candle.open_time,
            "close_time": candle.close_time,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "quality": quality,
            "received_at": received_at,
        }
        for candle in candles
    ]
    inserted_times = set(
        session.execute(
            pg_insert(Candle)
            .values(rows)
            .on_conflict_do_nothing(
                index_elements=["data_source_id", "instrument_id", "timeframe_id", "open_time"]
            )
            .returning(Candle.open_time)
        ).scalars()
    )

    already_there = [candle for candle in candles if candle.open_time not in inserted_times]
    stored = {
        row.open_time: row
        for row in session.execute(
            select(Candle).where(
                Candle.data_source_id == key.data_source_id,
                Candle.instrument_id == key.instrument_id,
                Candle.timeframe_id == key.timeframe_id,
                Candle.open_time.in_([candle.open_time for candle in already_there]),
            )
        ).scalars()
    }
    revised: list[datetime] = []
    unchanged = 0
    for candle in already_there:
        existing = stored[candle.open_time]
        same = (
            existing.close_time == candle.close_time
            and existing.open == candle.open
            and existing.high == candle.high
            and existing.low == candle.low
            and existing.close == candle.close
            and existing.volume == candle.volume
        )
        if same:
            unchanged += 1
        else:
            revised.append(candle.open_time)
    return InsertOutcome(inserted=len(inserted_times), unchanged=unchanged, revised=tuple(revised))


def record_sync_attempt(
    session: Session,
    key: SeriesKey,
    *,
    attempted_at: datetime,
    status: DataQuality,
    issue_codes: Sequence[str],
    detail: str | None,
) -> None:
    """Record the outcome of a sync attempt. A failed attempt bumps
    `consecutive_failures` and keeps the previous `last_success_at`; a
    successful one (data delivered, even if degraded) resets the counter."""
    succeeded = status is not DataQuality.UNAVAILABLE
    insert = pg_insert(MarketDataSyncState).values(
        data_source_id=key.data_source_id,
        instrument_id=key.instrument_id,
        timeframe_id=key.timeframe_id,
        last_attempt_at=attempted_at,
        last_success_at=attempted_at if succeeded else None,
        last_status=status,
        last_issue_codes=list(issue_codes),
        last_detail=detail,
        consecutive_failures=0 if succeeded else 1,
    )
    table = MarketDataSyncState.__table__
    changes: dict[str, object] = {
        "last_attempt_at": attempted_at,
        "last_status": status,
        "last_issue_codes": list(issue_codes),
        "last_detail": detail,
        "consecutive_failures": 0 if succeeded else table.c.consecutive_failures + 1,
    }
    if succeeded:
        changes["last_success_at"] = attempted_at
    session.execute(
        insert.on_conflict_do_update(
            index_elements=["data_source_id", "instrument_id", "timeframe_id"], set_=changes
        )
    )


def _series_filter(key: SeriesKey) -> tuple[ColumnElement[bool], ...]:
    return (
        Candle.data_source_id == key.data_source_id,
        Candle.instrument_id == key.instrument_id,
        Candle.timeframe_id == key.timeframe_id,
    )


def get_instrument_by_id(session: Session, instrument_id: uuid.UUID) -> Instrument | None:
    return session.get(Instrument, instrument_id)


def list_latest_candles(
    session: Session, key: SeriesKey, *, before: datetime | None, limit: int
) -> list[Candle]:
    """The newest `limit` candles (opened before `before`, if given), oldest first."""
    query = select(Candle).where(*_series_filter(key))
    if before is not None:
        query = query.where(Candle.open_time < before)
    rows = session.execute(query.order_by(Candle.open_time.desc()).limit(limit)).scalars()
    return list(reversed(list(rows)))


def list_candles_from(
    session: Session, key: SeriesKey, *, start: datetime, end: datetime | None, limit: int
) -> list[Candle]:
    """Up to `limit` candles opened at or after `start` (and before `end`), oldest first."""
    query = select(Candle).where(*_series_filter(key), Candle.open_time >= start)
    if end is not None:
        query = query.where(Candle.open_time < end)
    return list(session.execute(query.order_by(Candle.open_time).limit(limit)).scalars())


def get_latest_candle(session: Session, key: SeriesKey) -> Candle | None:
    return session.execute(
        select(Candle).where(*_series_filter(key)).order_by(Candle.open_time.desc()).limit(1)
    ).scalar_one_or_none()


def get_sync_state(session: Session, key: SeriesKey) -> MarketDataSyncState | None:
    return session.get(
        MarketDataSyncState, (key.data_source_id, key.instrument_id, key.timeframe_id)
    )
