"""Observable market context (POINT2-CONTEXT-001).

Everything that can be known about a series *before* classifying its trend, at one
instant: which candle is the last closed one, how fresh and complete the data is,
whether the market is open and in which session. It says nothing about direction and
decides no signal.

Pure and stateless. Every call answers from the candles it receives; there is no cache
and no "last valid context" to fall back on. Bad or missing data never raises: it
produces a context that is insufficient, with the reasons spelled out.
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise

from freyja_backend.domain.market_calendar import (
    FOREX_CALENDAR_VERSION,
    MarketSchedule,
    MarketSession,
    forex_session_at,
    is_expected_open,
    is_forex_open,
    last_forex_close,
)
from freyja_backend.domain.market_data import (
    DEFAULT_PUBLICATION_GRACE,
    Candle,
    DataQuality,
    InstrumentRef,
    InvalidMarketDataError,
    QualityIssue,
    QualityIssueCode,
    Timeframe,
    _require_utc,
    assess_candles,
    newest_expected_open,
    quality_from_issues,
)
from freyja_backend.domain.market_structure import MIN_HISTORY_CANDLES

# Bump on ANY change to what the context contains or how it is derived.
CONTEXT_VERSION = "context-v1"

# Issues this module judges itself, with the market calendar in hand, instead of
# taking the calendar-blind verdict of `assess_candles` (a Forex weekend is not a gap).
_CALENDAR_BLIND = frozenset(
    {QualityIssueCode.GAP, QualityIssueCode.STALE, QualityIssueCode.INCOMPLETE_RANGE}
)


class InvalidContextRequestError(ValueError):
    """The request itself is wrong (not the data): a configuration error to fix."""


class DataFreshness(enum.StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    NO_DATA = "NO_DATA"
    # Freshness cannot be judged: the schedule is unknown or the source is not allowed.
    UNKNOWN = "UNKNOWN"


class MissingDataReason(enum.StrEnum):
    SOURCE_NOT_AUTHORIZED = "SOURCE_NOT_AUTHORIZED"
    SCHEDULE_UNKNOWN = "SCHEDULE_UNKNOWN"
    NO_DATA = "NO_DATA"
    INVALID_CANDLES = "INVALID_CANDLES"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    STALE_DATA = "STALE_DATA"
    GAPS_IN_WINDOW = "GAPS_IN_WINDOW"
    DEGRADED_DATA = "DEGRADED_DATA"


@dataclass(frozen=True, slots=True)
class ObservableContext:
    observed_at: datetime
    instrument_id: str
    product_type: str
    signal_timeframe: Timeframe
    context_timeframe: Timeframe
    # Close of the newest closed candle of the context series; None if there is none.
    last_closed_candle_at: datetime | None
    data_source: str
    data_freshness: DataFreshness
    # None when the schedule is unknown.
    market_open: bool | None
    # Only Forex has named sessions. None means "not applicable", never a borrowed one.
    market_session: MarketSession | None
    timezone: str
    data_quality_status: DataQuality
    missing_data_reasons: tuple[MissingDataReason, ...]
    # Always recorded, in UTC: the only calendar facts crypto has.
    weekday_utc: int
    hour_utc: int
    # How many closed candles were evaluated, and the version of what evaluated them.
    window_candles: int
    calendar_version: str | None
    context_version: str

    @property
    def is_sufficient(self) -> bool:
        return not self.missing_data_reasons


def build_observable_context(
    *,
    instrument_id: str,
    instrument: InstrumentRef,
    schedule: MarketSchedule,
    signal_timeframe: Timeframe,
    context_timeframe: Timeframe,
    observed_at: datetime,
    data_source: str,
    authorized_sources: frozenset[str],
    candles: Sequence[Candle],
    min_history: int = MIN_HISTORY_CANDLES,
    publication_grace: timedelta = DEFAULT_PUBLICATION_GRACE,
) -> ObservableContext:
    """The observable context of the `context_timeframe` series at `observed_at`.

    `candles` are the stored candles of that series and source; any candle not closed
    at `observed_at` is ignored. `context_timeframe` may equal `signal_timeframe` but
    not be finer than it. Raises `InvalidContextRequestError` for a wrong request and never
    for bad data, which yields an insufficient context instead.
    """
    _require_utc(observed_at, "observed_at")
    if context_timeframe.duration < signal_timeframe.duration:
        raise InvalidContextRequestError(
            "context_timeframe must not be finer than signal_timeframe"
        )
    if min_history < 1:
        raise InvalidContextRequestError("min_history must be at least 1")

    market_open = is_expected_open(schedule, observed_at)
    market_session = (
        forex_session_at(observed_at) if schedule is MarketSchedule.FOREX_WEEKLY else None
    )
    reasons: set[MissingDataReason] = set()

    def build(
        *,
        freshness: DataFreshness,
        quality: DataQuality,
        last_closed: datetime | None = None,
        window: int = 0,
    ) -> ObservableContext:
        return ObservableContext(
            observed_at=observed_at,
            instrument_id=instrument_id,
            product_type=instrument.product,
            signal_timeframe=signal_timeframe,
            context_timeframe=context_timeframe,
            last_closed_candle_at=last_closed,
            data_source=data_source,
            data_freshness=freshness,
            market_open=market_open,
            market_session=market_session,
            timezone="UTC",
            data_quality_status=quality,
            missing_data_reasons=tuple(sorted(reasons)),
            weekday_utc=observed_at.astimezone(UTC).weekday(),
            hour_utc=observed_at.astimezone(UTC).hour,
            window_candles=window,
            calendar_version=(
                FOREX_CALENDAR_VERSION if schedule is MarketSchedule.FOREX_WEEKLY else None
            ),
            context_version=CONTEXT_VERSION,
        )

    if data_source not in authorized_sources:
        # Not even looked at: candles from a source we may not use are not evidence.
        reasons.add(MissingDataReason.SOURCE_NOT_AUTHORIZED)
        return build(freshness=DataFreshness.UNKNOWN, quality=DataQuality.UNAVAILABLE)
    if schedule is MarketSchedule.BROKER_DEFINED:
        reasons.add(MissingDataReason.SCHEDULE_UNKNOWN)
        return build(freshness=DataFreshness.UNKNOWN, quality=DataQuality.UNAVAILABLE)

    try:
        assessment = assess_candles(
            candles,
            timeframe=context_timeframe,
            now=observed_at,
            publication_grace=publication_grace,
        )
    except InvalidMarketDataError:
        reasons.add(MissingDataReason.INVALID_CANDLES)
        return build(freshness=DataFreshness.UNKNOWN, quality=DataQuality.UNAVAILABLE)

    closed = assessment.candles
    if not closed:
        reasons.add(MissingDataReason.NO_DATA)
        return build(freshness=DataFreshness.NO_DATA, quality=DataQuality.UNAVAILABLE)

    issues = [i for i in assessment.issues if i.code not in _CALENDAR_BLIND]
    window = closed[-min_history:]
    if len(closed) < min_history:
        reasons.add(MissingDataReason.INSUFFICIENT_HISTORY)

    gap_issues = _gaps_in_window(window, context_timeframe, schedule)
    if gap_issues:
        reasons.add(MissingDataReason.GAPS_IN_WINDOW)
        issues.extend(gap_issues)

    fresh = _is_fresh(closed[-1], context_timeframe, schedule, observed_at, publication_grace)
    if not fresh:
        reasons.add(MissingDataReason.STALE_DATA)
        issues.append(QualityIssue(QualityIssueCode.STALE, "newest closed candle is too old"))

    if any(
        i.code not in (_CALENDAR_BLIND | {QualityIssueCode.OPEN_CANDLE_EXCLUDED}) for i in issues
    ):
        reasons.add(MissingDataReason.DEGRADED_DATA)

    return build(
        freshness=DataFreshness.FRESH if fresh else DataFreshness.STALE,
        quality=quality_from_issues(issues),
        last_closed=closed[-1].close_time,
        window=len(window),
    )


def _gaps_in_window(
    window: Sequence[Candle], timeframe: Timeframe, schedule: MarketSchedule
) -> list[QualityIssue]:
    """Missing candles between consecutive candles, ignoring those the market was closed for."""
    step = timeframe.duration
    issues: list[QualityIssue] = []
    for previous, current in pairwise(window):
        missing_opens = []
        moment = previous.open_time + step
        while moment < current.open_time:
            if is_expected_open(schedule, moment):
                missing_opens.append(moment)
            moment += step
        if missing_opens:
            issues.append(
                QualityIssue(
                    QualityIssueCode.GAP,
                    f"{len(missing_opens)} candle(s) missing after "
                    f"{previous.open_time.isoformat()}",
                )
            )
    return issues


def _is_fresh(
    newest: Candle,
    timeframe: Timeframe,
    schedule: MarketSchedule,
    observed_at: datetime,
    grace: timedelta,
) -> bool:
    """Fresh when the newest candle is the one that had to exist. While a weekly market
    is closed, that is judged at its last close, not at the (idle) present."""
    reference = observed_at
    if schedule is MarketSchedule.FOREX_WEEKLY and not is_forex_open(observed_at):
        reference = last_forex_close(observed_at) + grace
    return newest.open_time >= newest_expected_open(timeframe, reference, grace)
