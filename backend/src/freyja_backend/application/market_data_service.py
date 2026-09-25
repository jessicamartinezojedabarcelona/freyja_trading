from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from freyja_backend.domain.market_data import (
    INFORMATIONAL_ISSUES,
    CandleProvider,
    Clock,
    DataQuality,
    InstrumentRef,
    MarketDataRequestError,
    QualityIssue,
    QualityIssueCode,
    Timeframe,
    quality_from_issues,
    utc_now,
)
from freyja_backend.repositories import market_data_repository
from freyja_backend.repositories.market_data_repository import SeriesKey

# Sync and backfill of market data into PostgreSQL (MARKET-DATA-PERSISTENCE-001,
# ADR 0003). Both are idempotent: running the same window twice stores each
# candle once and leaves what was stored untouched.
#
# `sync_candles` never commits: the caller owns the transaction. `backfill_candles`
# commits after each page so a long, interrupted backfill keeps its progress and
# can simply be run again.

DEFAULT_PAGE_LIMIT = 1000
MAX_BACKFILL_CANDLES = 10_000
_MAX_DETAIL_LENGTH = 300


class MarketDataConfigurationError(Exception):
    """The requested source, instrument, timeframe or mapping is not set up in
    the catalog, so nothing was fetched."""


class MarketDataIntegrityError(Exception):
    """The provider's answer does not match what was asked or what the catalog
    maps (wrong source, symbol, instrument or timeframe). Nothing is stored."""


@dataclass(frozen=True, slots=True)
class SyncResult:
    source_code: str
    instrument: InstrumentRef
    timeframe: Timeframe
    quality: DataQuality
    issues: tuple[QualityIssue, ...]
    inserted: int
    unchanged: int
    revised: tuple[datetime, ...]
    received_at: datetime


@dataclass(frozen=True, slots=True)
class BackfillResult:
    pages: int
    inserted: int
    unchanged: int
    revised: int
    quality: DataQuality
    completed: bool
    """True only when every page up to the requested end was fetched."""


def _resolve_series(
    session: Session, *, source_code: str, instrument: InstrumentRef, timeframe: Timeframe
) -> tuple[SeriesKey, str]:
    source = market_data_repository.get_data_source(session, source_code)
    if source is None or not source.is_active:
        raise MarketDataConfigurationError(f"data source {source_code!r} is not active")
    catalog_instrument = market_data_repository.get_instrument(
        session,
        market_code=instrument.market,
        product_code=instrument.product,
        symbol=instrument.symbol,
    )
    if catalog_instrument is None or not catalog_instrument.is_active:
        raise MarketDataConfigurationError(
            f"instrument {instrument.market}/{instrument.product} {instrument.symbol} "
            "is not active in the catalog"
        )
    catalog_timeframe = market_data_repository.get_timeframe(session, timeframe.value)
    if catalog_timeframe is None or not catalog_timeframe.is_active:
        raise MarketDataConfigurationError(f"timeframe {timeframe.value!r} is not active")
    if not market_data_repository.has_active_instrument_timeframe(
        session, catalog_instrument.instrument_id, catalog_timeframe.id
    ):
        raise MarketDataConfigurationError(
            f"timeframe {timeframe.value!r} is not enabled for {instrument.symbol}"
        )
    mapping = market_data_repository.get_analysis_mapping(
        session, source.id, catalog_instrument.instrument_id
    )
    if mapping is None:
        raise MarketDataConfigurationError(
            f"{source_code} has no active analysis mapping for {instrument.symbol}"
        )
    key = SeriesKey(
        data_source_id=source.id,
        instrument_id=catalog_instrument.instrument_id,
        timeframe_id=catalog_timeframe.id,
    )
    return key, mapping.provider_symbol


def latest_open_time(
    session: Session, *, source_code: str, instrument: InstrumentRef, timeframe: Timeframe
) -> datetime | None:
    """Open time of the newest stored candle of a series, or None if it has none.

    Raises `MarketDataConfigurationError` when the series is not set up in the catalog,
    exactly as `sync_candles` would, so a caller can tell "empty" from "not configured".
    """
    key, _ = _resolve_series(
        session, source_code=source_code, instrument=instrument, timeframe=timeframe
    )
    latest = market_data_repository.get_latest_candle(session, key)
    return None if latest is None else latest.open_time.astimezone(UTC)


def sync_candles(
    session: Session,
    provider: CandleProvider,
    *,
    source_code: str,
    instrument: InstrumentRef,
    timeframe: Timeframe,
    limit: int = 500,
    start: datetime | None = None,
    end: datetime | None = None,
) -> SyncResult:
    """Fetch one batch from `provider` and store its closed candles.

    A failed fetch stores nothing but is still recorded, so the API can show
    the provider as failing instead of silently serving old data.
    """
    key, mapped_symbol = _resolve_series(
        session, source_code=source_code, instrument=instrument, timeframe=timeframe
    )
    batch = provider.get_closed_candles(instrument, timeframe, limit=limit, start=start, end=end)
    provenance = batch.provenance
    if (
        provenance.source != source_code
        or batch.instrument != instrument
        or batch.timeframe != timeframe
        or provenance.provider_symbol != mapped_symbol
    ):
        raise MarketDataIntegrityError(
            f"provider answered {provenance.source}/{provenance.provider_symbol} for "
            f"{batch.instrument.symbol} {batch.timeframe.value}, expected "
            f"{source_code}/{mapped_symbol} for {instrument.symbol} {timeframe.value}"
        )

    issues = list(batch.issues)
    outcome = market_data_repository.insert_candles(
        session,
        key,
        batch.candles,
        quality=batch.quality,
        received_at=provenance.received_at,
    )
    if outcome.revised:
        issues.append(
            QualityIssue(
                QualityIssueCode.REVISED_CANDLE,
                f"{len(outcome.revised)} stored candle(s) differ from the provider's values; "
                f"first at {outcome.revised[0].isoformat()}",
            )
        )
    quality = quality_from_issues(issues)

    notable = [issue for issue in issues if issue.code not in INFORMATIONAL_ISSUES]
    market_data_repository.record_sync_attempt(
        session,
        key,
        attempted_at=provenance.received_at,
        status=quality,
        issue_codes=sorted({issue.code.value for issue in issues}),
        detail=notable[0].detail[:_MAX_DETAIL_LENGTH] if notable else None,
    )
    return SyncResult(
        source_code=source_code,
        instrument=instrument,
        timeframe=timeframe,
        quality=quality,
        issues=tuple(issues),
        inserted=outcome.inserted,
        unchanged=outcome.unchanged,
        revised=outcome.revised,
        received_at=provenance.received_at,
    )


def backfill_candles(
    session: Session,
    provider: CandleProvider,
    *,
    source_code: str,
    instrument: InstrumentRef,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    page_limit: int | None = None,
    max_candles: int = MAX_BACKFILL_CANDLES,
    clock: Clock = utc_now,
) -> BackfillResult:
    """Fill ``[start, end)`` page by page, oldest first.

    Bounded: a window that would need more than `max_candles` candles is
    refused up front. Repeatable: pages already stored are `unchanged`. Stops
    at the first page the provider fails to deliver, reporting
    `completed=False`, so a later run resumes from the same window.
    """
    for name, moment in (("start", start), ("end", end)):
        if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
            raise MarketDataRequestError(f"{name} must be timezone-aware UTC")
    if page_limit is None:
        page_limit = provider.limits.max_candles_per_request
    duration = timeframe.duration
    first = timeframe.floor(start)
    if first < start:
        first += duration
    # Only closed candles can be backfilled, so the window stops at the last boundary.
    last = min(timeframe.floor(end), timeframe.floor(clock()))
    if last <= first:
        return BackfillResult(0, 0, 0, 0, DataQuality.OK, completed=True)
    expected = int((last - first) / duration)
    if expected > max_candles:
        raise MarketDataRequestError(
            f"backfill of {expected} candles exceeds the limit of {max_candles}; "
            "use a shorter window"
        )

    cursor = first
    pages = inserted = unchanged = revised = 0
    worst = DataQuality.OK
    while cursor < last:
        page_end = min(last, cursor + duration * page_limit)
        result = sync_candles(
            session,
            provider,
            source_code=source_code,
            instrument=instrument,
            timeframe=timeframe,
            limit=page_limit,
            start=cursor,
            end=page_end,
        )
        session.commit()
        pages += 1
        inserted += result.inserted
        unchanged += result.unchanged
        revised += len(result.revised)
        worst = _worse(worst, result.quality)
        if result.quality is DataQuality.UNAVAILABLE:
            return BackfillResult(pages, inserted, unchanged, revised, worst, completed=False)
        cursor = page_end
    return BackfillResult(pages, inserted, unchanged, revised, worst, completed=True)


_SEVERITY = {DataQuality.OK: 0, DataQuality.DEGRADED: 1, DataQuality.UNAVAILABLE: 2}


def _worse(current: DataQuality, other: DataQuality) -> DataQuality:
    return other if _SEVERITY[other] > _SEVERITY[current] else current
