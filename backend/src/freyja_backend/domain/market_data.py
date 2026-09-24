"""Provider-agnostic market-data contracts (ADR 0002).

The vocabulary every consumer of candles speaks, whichever provider produced
them: canonical instruments and timeframes in, closed candles plus explicit
quality and provenance out. Nothing here knows any provider's wire format,
naming or client library — adapters live in `infrastructure/` and translate
at the boundary.

Rules the contract enforces:

* A candle covers the half-open interval ``[open_time, close_time)``, and
  every timestamp is timezone-aware UTC.
* Money-like values (prices, volume) are `Decimal`, never `float`.
* Only *closed* candles are ever delivered as candles. An in-progress candle
  is dropped and reported, never returned.
* A result is never silently "fine": it carries a `DataQuality` and the list
  of `QualityIssue`s that explain it. Anything that is not `OK` must be shown
  as degraded by whoever renders it, and old data must never pass as current.
"""

import enum
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Protocol

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class MarketDataError(Exception):
    """Base class for contract violations raised by this package."""


class MarketDataRequestError(MarketDataError, ValueError):
    """The *caller* asked for something outside the contract (unsupported
    instrument, non-positive limit, naive datetime...). This is a programming
    error, not a provider degradation, so it is raised instead of being
    reported as quality."""


class UnsupportedInstrumentError(MarketDataRequestError):
    """The instrument is not in the adapter's allowlist."""


class InvalidMarketDataError(MarketDataError):
    """Data that violates the contract's invariants (broken OHLC, misaligned
    or conflicting candles). Adapters turn it into an UNAVAILABLE result."""


class Timeframe(enum.StrEnum):
    """Canonical timeframes of catalog v1 (`freyja2_timeframes.code`)."""

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"

    @property
    def duration(self) -> timedelta:
        return timedelta(seconds=_TIMEFRAME_SECONDS[self])

    def floor(self, moment: datetime) -> datetime:
        """Start of the timeframe bucket containing `moment` (UTC epoch grid)."""
        _require_utc(moment, "moment")
        step = _TIMEFRAME_SECONDS[self]
        seconds = int(moment.timestamp())
        return datetime.fromtimestamp(seconds - seconds % step, UTC)


_TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
}


@dataclass(frozen=True, slots=True)
class InstrumentRef:
    """Canonical instrument by its natural key, as in the catalog."""

    market: str
    product: str
    symbol: str


class DataQuality(enum.StrEnum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class QualityIssueCode(enum.StrEnum):
    # Informational: the result is still complete and trustworthy.
    OPEN_CANDLE_EXCLUDED = "OPEN_CANDLE_EXCLUDED"
    # Degrading: the candles returned are real, but the series has a defect.
    DUPLICATE_DROPPED = "DUPLICATE_DROPPED"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    GAP = "GAP"
    INCOMPLETE_RANGE = "INCOMPLETE_RANGE"
    STALE = "STALE"
    INSTRUMENT_NOT_TRADING = "INSTRUMENT_NOT_TRADING"
    # The provider now reports different values for a candle Freyja already
    # stored. The stored candle is kept as is; this makes the disagreement visible.
    REVISED_CANDLE = "REVISED_CANDLE"
    # Set when reading stored data: the source's latest sync attempt failed, so
    # newer candles than the ones shown may exist upstream.
    PROVIDER_FAILING = "PROVIDER_FAILING"
    # Failures: nothing trustworthy was obtained, so no candle is returned.
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
    # Set when reading stored data: nothing has been stored for the series yet.
    NO_DATA = "NO_DATA"


INFORMATIONAL_ISSUES: frozenset[QualityIssueCode] = frozenset(
    {QualityIssueCode.OPEN_CANDLE_EXCLUDED}
)
FAILURE_ISSUES: frozenset[QualityIssueCode] = frozenset(
    {
        QualityIssueCode.RATE_LIMITED,
        QualityIssueCode.TIMEOUT,
        QualityIssueCode.PROVIDER_ERROR,
        QualityIssueCode.INVALID_RESPONSE,
        QualityIssueCode.SYMBOL_MISMATCH,
        QualityIssueCode.NO_DATA,
    }
)


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: QualityIssueCode
    detail: str


def quality_from_issues(issues: Sequence[QualityIssue]) -> DataQuality:
    """The single place that turns issues into a quality level."""
    codes = {issue.code for issue in issues}
    if codes & FAILURE_ISSUES:
        return DataQuality.UNAVAILABLE
    if codes - INFORMATIONAL_ISSUES:
        return DataQuality.DEGRADED
    return DataQuality.OK


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where and when a result came from. `source` matches the future
    `freyja2_data_sources.code`; `received_at` is when the data was obtained,
    so a consumer can always tell how old it is."""

    source: str
    endpoint: str
    provider_symbol: str
    requested_at: datetime
    received_at: datetime
    attempts: int


@dataclass(frozen=True, slots=True)
class Candle:
    """One *closed* candle covering ``[open_time, close_time)``."""

    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        _require_utc(self.open_time, "open_time")
        _require_utc(self.close_time, "close_time")
        if self.close_time <= self.open_time:
            raise InvalidMarketDataError("close_time must be after open_time")
        prices = (self.open, self.high, self.low, self.close)
        if not all(price.is_finite() and price > 0 for price in prices):
            raise InvalidMarketDataError("prices must be finite and positive")
        if not (self.volume.is_finite() and self.volume >= 0):
            raise InvalidMarketDataError("volume must be finite and non-negative")
        if self.high < max(self.open, self.close, self.low) or self.low > min(
            self.open, self.close, self.high
        ):
            raise InvalidMarketDataError("inconsistent OHLC: high/low do not bound open/close")


@dataclass(frozen=True, slots=True)
class CandleBatch:
    """Closed candles for one instrument and timeframe, oldest first.

    `candles` is empty whenever `quality` is UNAVAILABLE. Consumers must treat
    anything other than OK as degraded and read `issues` for the reason.
    """

    instrument: InstrumentRef
    timeframe: Timeframe
    candles: tuple[Candle, ...]
    quality: DataQuality
    issues: tuple[QualityIssue, ...]
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class InstrumentMetadata:
    instrument: InstrumentRef
    provider_symbol: str
    base_asset: str
    quote_asset: str
    trading: bool


@dataclass(frozen=True, slots=True)
class MetadataResult:
    """`metadata` is None whenever `quality` is UNAVAILABLE."""

    metadata: InstrumentMetadata | None
    quality: DataQuality
    issues: tuple[QualityIssue, ...]
    provenance: Provenance


class CandleProvider(Protocol):
    """Port implemented by every market-data adapter."""

    def get_closed_candles(
        self,
        instrument: InstrumentRef,
        timeframe: Timeframe,
        *,
        limit: int = ...,
        start: datetime | None = ...,
        end: datetime | None = ...,
    ) -> CandleBatch: ...

    def get_instrument_metadata(self, instrument: InstrumentRef) -> MetadataResult: ...


def _require_utc(moment: datetime, name: str) -> None:
    if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
        raise InvalidMarketDataError(f"{name} must be timezone-aware UTC")


DEFAULT_PUBLICATION_GRACE = timedelta(seconds=10)


@dataclass(frozen=True, slots=True)
class CandleGap:
    """`missing` consecutive candles are absent right after the candle that
    opened at `after`."""

    after: datetime
    missing: int


@dataclass(frozen=True, slots=True)
class CandleAssessment:
    candles: tuple[Candle, ...]
    issues: tuple[QualityIssue, ...]
    gaps: tuple[CandleGap, ...] = ()


def newest_expected_open(
    timeframe: Timeframe,
    now: datetime,
    publication_grace: timedelta = DEFAULT_PUBLICATION_GRACE,
) -> datetime:
    """Open time of the newest candle that must already be available at `now`:
    the last bucket that closed more than `publication_grace` ago."""
    return timeframe.floor(now - publication_grace) - timeframe.duration


def assess_candles(
    candles: Sequence[Candle],
    *,
    timeframe: Timeframe,
    now: datetime,
    start: datetime | None = None,
    end: datetime | None = None,
    publication_grace: timedelta = DEFAULT_PUBLICATION_GRACE,
) -> CandleAssessment:
    """Turn provider candles into a trustworthy closed series plus issues.

    Deterministic and free of I/O: the same input and `now` always give the
    same output. Raises `InvalidMarketDataError` when candles contradict each
    other or the timeframe grid (the caller reports that as UNAVAILABLE).

    With neither `start` nor `end` the request is "the most recent candles", so the newest
    closed candle must not be older than the last bucket that closed more than
    `publication_grace` ago — otherwise the series is STALE. With `start`/`end`
    the request is a historical window ``[start, end)`` and completeness is
    judged against it instead.
    """
    _require_utc(now, "now")
    duration = timeframe.duration
    issues: list[QualityIssue] = []

    for candle in candles:
        if candle.close_time - candle.open_time != duration:
            raise InvalidMarketDataError(
                f"candle at {candle.open_time.isoformat()} does not span one {timeframe.value}"
            )
        if timeframe.floor(candle.open_time) != candle.open_time:
            raise InvalidMarketDataError(
                f"candle at {candle.open_time.isoformat()} is off the {timeframe.value} UTC grid"
            )

    closed = [candle for candle in candles if candle.close_time <= now]
    open_count = len(candles) - len(closed)
    if open_count:
        issues.append(
            QualityIssue(
                QualityIssueCode.OPEN_CANDLE_EXCLUDED,
                f"{open_count} candle(s) still in progress were excluded",
            )
        )

    if _was_really_unordered(closed):
        issues.append(
            QualityIssue(QualityIssueCode.OUT_OF_ORDER, "candles were not ascending in time")
        )
    ordered = sorted(closed, key=lambda candle: candle.open_time)

    unique: list[Candle] = []
    for candle in ordered:
        if unique and unique[-1].open_time == candle.open_time:
            if unique[-1] != candle:
                raise InvalidMarketDataError(
                    f"conflicting duplicates at {candle.open_time.isoformat()}"
                )
            issues.append(
                QualityIssue(
                    QualityIssueCode.DUPLICATE_DROPPED,
                    f"duplicate candle at {candle.open_time.isoformat()} dropped",
                )
            )
            continue
        unique.append(candle)
    gaps: list[CandleGap] = []
    for previous, current in pairwise(unique):
        missing = int((current.open_time - previous.open_time) / duration) - 1
        if missing > 0:
            gaps.append(CandleGap(after=previous.open_time, missing=missing))
            issues.append(
                QualityIssue(
                    QualityIssueCode.GAP,
                    f"{missing} candle(s) missing after {previous.open_time.isoformat()}",
                )
            )

    if start is None and end is None:
        newest_expected = newest_expected_open(timeframe, now, publication_grace)
        if not unique or unique[-1].open_time < newest_expected:
            newest = unique[-1].open_time.isoformat() if unique else "none"
            issues.append(
                QualityIssue(
                    QualityIssueCode.STALE,
                    f"newest closed candle is {newest}; expected at least "
                    f"{newest_expected.isoformat()}",
                )
            )
    if start is not None or end is not None:
        issues.extend(_range_issues(unique, timeframe, now, start, end, publication_grace))

    return CandleAssessment(candles=tuple(unique), issues=tuple(issues), gaps=tuple(gaps))


def _was_really_unordered(closed: Sequence[Candle]) -> bool:
    """True when candles go backwards in time (duplicates alone do not)."""
    return any(a.open_time > b.open_time for a, b in pairwise(closed))


def _range_issues(
    candles: Sequence[Candle],
    timeframe: Timeframe,
    now: datetime,
    start: datetime | None,
    end: datetime | None,
    publication_grace: timedelta,
) -> list[QualityIssue]:
    duration = timeframe.duration
    if start is None:
        # Only an upper bound was given: nothing defines where the window opens.
        return []
    first_expected = timeframe.floor(start)
    if first_expected < start:
        first_expected += duration
    last_closed_open = newest_expected_open(timeframe, now, publication_grace)
    window_last_open = timeframe.floor(end - timedelta(microseconds=1)) if end is not None else None
    last_expected = (
        last_closed_open if window_last_open is None else min(window_last_open, last_closed_open)
    )
    if last_expected < first_expected:
        return []  # the window contains no closed candle yet, so nothing is owed
    if (
        not candles
        or candles[0].open_time > first_expected
        or candles[-1].open_time < last_expected
    ):
        got = (
            f"{candles[0].open_time.isoformat()}..{candles[-1].open_time.isoformat()}"
            if candles
            else "none"
        )
        return [
            QualityIssue(
                QualityIssueCode.INCOMPLETE_RANGE,
                f"expected candles {first_expected.isoformat()}..{last_expected.isoformat()}, "
                f"got {got}",
            )
        ]
    return []
