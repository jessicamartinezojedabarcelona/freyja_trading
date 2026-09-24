import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from freyja_backend.db.models.market_data import Candle as CandleRow
from freyja_backend.db.models.market_data import MarketDataSyncState
from freyja_backend.domain.market_data import (
    Candle,
    DataQuality,
    QualityIssue,
    QualityIssueCode,
    Timeframe,
    assess_candles,
    newest_expected_open,
    quality_from_issues,
)
from freyja_backend.dto.market_data import (
    CandleOut,
    CandleSeriesOut,
    FreshnessOut,
    FreshnessStatus,
    GapOut,
    ProviderStatusOut,
    QualityIssueOut,
)
from freyja_backend.repositories import market_data_repository
from freyja_backend.repositories.market_data_repository import SeriesKey

# Reading stored candles (MARKET-DATA-PERSISTENCE-001, ADR 0003). Nothing here
# fetches from a provider: it only reports what is stored, how current it is,
# where it has holes, and how the last sync went. Gaps and freshness are computed
# at read time, with the same deterministic function the ingest side uses, so a
# stale label can never outlive the data it described.

DEFAULT_TIMEFRAME_CODE = "1m"  # Freyja's standard candle period; the user may pick another.
MAX_LIMIT = 1000


class MarketDataNotFoundError(Exception):
    """The instrument, source or their mapping does not exist."""


class MarketDataInvalidQueryError(Exception):
    """The request is well-formed but asks for something the contract does not allow."""


def _utc(moment: datetime, name: str) -> datetime:
    if moment.tzinfo is None:
        raise MarketDataInvalidQueryError(
            f"{name} debe incluir zona horaria (por ejemplo 2026-09-24T12:00:00Z)."
        )
    return moment.astimezone(UTC)


def _resolve(
    session: Session, *, instrument_id: uuid.UUID, data_source_code: str, timeframe_code: str
) -> tuple[SeriesKey, Timeframe]:
    instrument = market_data_repository.get_instrument_by_id(session, instrument_id)
    if instrument is None or not instrument.is_active:
        raise MarketDataNotFoundError("Instrumento no encontrado.")
    source = market_data_repository.get_data_source(session, data_source_code)
    if source is None or not source.is_active:
        raise MarketDataNotFoundError("Fuente de datos no encontrada.")
    if (
        market_data_repository.get_analysis_mapping(session, source.id, instrument.instrument_id)
        is None
    ):
        raise MarketDataNotFoundError("Esta fuente no publica datos para este instrumento.")

    catalog_timeframe = market_data_repository.get_timeframe(session, timeframe_code)
    if catalog_timeframe is None or not catalog_timeframe.is_active:
        raise MarketDataInvalidQueryError("Temporalidad no válida.")
    if not market_data_repository.has_active_instrument_timeframe(
        session, instrument.instrument_id, catalog_timeframe.id
    ):
        raise MarketDataInvalidQueryError("Temporalidad no habilitada para este instrumento.")
    try:
        timeframe = Timeframe(timeframe_code)
    except ValueError:
        raise MarketDataInvalidQueryError(
            "Temporalidad sin datos de mercado disponibles."
        ) from None
    key = SeriesKey(
        data_source_id=source.id,
        instrument_id=instrument.instrument_id,
        timeframe_id=catalog_timeframe.id,
    )
    return key, timeframe


def _to_domain(row: CandleRow) -> Candle:
    return Candle(
        open_time=row.open_time.astimezone(UTC),
        close_time=row.close_time.astimezone(UTC),
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume,
    )


def _candle_out(row: CandleRow) -> CandleOut:
    return CandleOut(
        open_time=row.open_time.astimezone(UTC),
        close_time=row.close_time.astimezone(UTC),
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume,
        quality=row.quality,
        received_at=row.received_at.astimezone(UTC),
    )


def get_candle_series(
    session: Session,
    *,
    instrument_id: uuid.UUID,
    data_source_code: str,
    timeframe_code: str = DEFAULT_TIMEFRAME_CODE,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 500,
    now: datetime,
) -> CandleSeriesOut:
    """Stored closed candles for one series, with freshness, gaps and provider state.

    * Neither `start` nor `end`: the newest `limit` candles.
    * `start` (optionally `end`): reading forward from `start` (up to, excluding,
      `end`); if more follow, `has_more` and `next_start` say where to continue.
    * Only `end`: the newest `limit` candles that opened before `end`.
    """
    if not 1 <= limit <= MAX_LIMIT:
        raise MarketDataInvalidQueryError(f"limit debe estar entre 1 y {MAX_LIMIT}.")
    start_utc = _utc(start, "start") if start is not None else None
    end_utc = _utc(end, "end") if end is not None else None
    if start_utc is not None and end_utc is not None and start_utc >= end_utc:
        raise MarketDataInvalidQueryError("start debe ser anterior a end.")

    key, timeframe = _resolve(
        session,
        instrument_id=instrument_id,
        data_source_code=data_source_code,
        timeframe_code=timeframe_code,
    )

    has_more = False
    next_start: datetime | None = None
    if start_utc is not None:
        rows = market_data_repository.list_candles_from(
            session, key, start=start_utc, end=end_utc, limit=limit + 1
        )
        if len(rows) > limit:
            has_more = True
            next_start = rows[limit].open_time.astimezone(UTC)
            rows = rows[:limit]
    else:
        rows = market_data_repository.list_latest_candles(session, key, before=end_utc, limit=limit)

    latest = market_data_repository.get_latest_candle(session, key)
    state = market_data_repository.get_sync_state(session, key)
    freshness = _freshness(latest, timeframe, now)

    issues: list[QualityIssue] = []
    gaps: list[GapOut] = []
    if latest is None:
        issues.append(
            QualityIssue(
                QualityIssueCode.NO_DATA, "Todavía no hay velas guardadas para esta serie."
            )
        )
    else:
        # When more candles follow, judge only what was returned: the window
        # continues on the next page, so it is not "incomplete".
        judged_end = rows[-1].close_time.astimezone(UTC) if has_more else end_utc
        assessment = assess_candles(
            [_to_domain(row) for row in rows],
            timeframe=timeframe,
            now=now,
            start=start_utc,
            end=judged_end,
        )
        issues.extend(assessment.issues)
        gaps = [GapOut(after_open_time=gap.after, missing=gap.missing) for gap in assessment.gaps]
    if state is not None and state.last_status is DataQuality.UNAVAILABLE:
        issues.append(
            QualityIssue(
                QualityIssueCode.PROVIDER_FAILING,
                "El último intento de sincronizar esta serie falló; puede haber velas más "
                "recientes que las mostradas.",
            )
        )

    return CandleSeriesOut(
        instrument_id=instrument_id,
        data_source_code=data_source_code,
        timeframe_code=timeframe_code,
        candles=[_candle_out(row) for row in rows],
        quality=quality_from_issues(issues),
        issues=[QualityIssueOut(code=issue.code, detail=issue.detail) for issue in issues],
        gaps=gaps,
        freshness=freshness,
        provider=_provider_status(state),
        has_more=has_more,
        next_start=next_start,
    )


def _freshness(latest: CandleRow | None, timeframe: Timeframe, now: datetime) -> FreshnessOut:
    if latest is None:
        return FreshnessOut(
            status=FreshnessStatus.NO_DATA,
            checked_at=now,
            latest_open_time=None,
            latest_close_time=None,
            latest_received_at=None,
        )
    latest_open = latest.open_time.astimezone(UTC)
    fresh = latest_open >= newest_expected_open(timeframe, now)
    return FreshnessOut(
        status=FreshnessStatus.FRESH if fresh else FreshnessStatus.STALE,
        checked_at=now,
        latest_open_time=latest_open,
        latest_close_time=latest.close_time.astimezone(UTC),
        latest_received_at=latest.received_at.astimezone(UTC),
    )


def _provider_status(state: MarketDataSyncState | None) -> ProviderStatusOut | None:
    if state is None:
        return None
    return ProviderStatusOut(
        last_attempt_at=state.last_attempt_at.astimezone(UTC),
        last_success_at=(
            state.last_success_at.astimezone(UTC) if state.last_success_at is not None else None
        ),
        last_status=state.last_status,
        last_issue_codes=list(state.last_issue_codes),
        last_detail=state.last_detail,
        consecutive_failures=state.consecutive_failures,
    )
