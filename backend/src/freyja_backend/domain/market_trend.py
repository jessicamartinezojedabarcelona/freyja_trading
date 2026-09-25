"""Structural trend classifier (POINT2-TREND-001).

The contract lives in ``docs/domain/tendencia-estructural.md`` (and, above it,
``docs/domain/contexto-y-tendencia.md``); this is its reference implementation. Pure and
free of I/O: the same candles, the same ``observed_at`` and the same parameters always give
the same classification, and nothing reads the clock.

It classifies one timeframe at a time from the *confirmed swing points* of
``market_structure`` (never from indicators), after the observable context of
``market_context`` has said whether the data is fit to classify. It produces a *state of the
market*, not a signal: no direction to act on, no order, no alert, and nothing here knows a
broker, an executor or a notification channel.

Fail-closed: whenever the data is not sufficient, or there are not enough confirmed swings,
the answer is ``INSUFFICIENT_DATA`` with the reasons. No directional state is ever a default.
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import pairwise

from freyja_backend.domain.market_calendar import MarketSchedule
from freyja_backend.domain.market_context import (
    MissingDataReason,
    build_observable_context,
)
from freyja_backend.domain.market_data import (
    DEFAULT_PUBLICATION_GRACE,
    Candle,
    InstrumentRef,
    Timeframe,
    _require_utc,
    assess_candles,
)
from freyja_backend.domain.market_structure import (
    DEFAULT_PIVOT_PARAMS,
    MIN_HISTORY_CANDLES,
    STRUCTURE_ALGORITHM_VERSION,
    Pivot,
    PivotKind,
    PivotParams,
    detect_pivots,
    swing_points,
)

# Bump on ANY change to how the state is derived from the swings, so a stored classification
# can always be traced to the exact definition that produced it.
TREND_DEFINITION_VERSION = "trend-v1"


class InvalidTrendRequestError(ValueError):
    """The request itself is wrong (not the data): a configuration error to fix."""


class TrendState(enum.StrEnum):
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"
    # Not a fourth kind of market: the absence of a classification.
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class InsufficientDataReason(enum.StrEnum):
    # The observable context found the data unfit (same reasons, same names).
    SOURCE_NOT_AUTHORIZED = "SOURCE_NOT_AUTHORIZED"
    SCHEDULE_UNKNOWN = "SCHEDULE_UNKNOWN"
    NO_DATA = "NO_DATA"
    INVALID_CANDLES = "INVALID_CANDLES"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    STALE_DATA = "STALE_DATA"
    GAPS_IN_WINDOW = "GAPS_IN_WINDOW"
    DEGRADED_DATA = "DEGRADED_DATA"
    # Judged here: the data is fine but has too few confirmed swing points to read a structure.
    INSUFFICIENT_SWINGS = "INSUFFICIENT_SWINGS"


class EvidenceCode(enum.StrEnum):
    HIGHER_HIGHS = "HIGHER_HIGHS"
    HIGHER_LOWS = "HIGHER_LOWS"
    LOWER_HIGHS = "LOWER_HIGHS"
    LOWER_LOWS = "LOWER_LOWS"
    LEVEL_HIGHS = "LEVEL_HIGHS"
    LEVEL_LOWS = "LEVEL_LOWS"
    # The structure has a conflict that fits no directional sequence and no range.
    MIXED_STRUCTURE = "MIXED_STRUCTURE"
    # A close went beyond the last swing that the trend depends on.
    STRUCTURE_BROKEN = "STRUCTURE_BROKEN"
    # A close went beyond a limit of the range.
    RANGE_BROKEN = "RANGE_BROKEN"
    # The swing prices of one side, listed when they explain a conflict.
    SWING_LEVELS = "SWING_LEVELS"
    SWING_COUNT = "SWING_COUNT"


@dataclass(frozen=True, slots=True)
class TrendParams:
    """How the swings are read.

    `window_swings`: the most recent confirmed swing points that are read; even, so highs and
    lows are counted equally. 4 means the last two highs and the last two lows: one step on
    each side, the classic higher-highs-and-higher-lows reading. 6 (three of each) was
    measured on real candles and left 92-98 % of instants as TRANSITION, so it says nothing.

    `significance`: a fraction of the height of the swing range (highest high minus lowest
    low). A step between two swings of the same side is a real rise or fall only if it is
    larger than that fraction of the height; two swings closer than it are *level*. One
    number for both, so a sequence can never be directional and level at once.
    """

    window_swings: int = 4
    significance: Decimal = Decimal("0.15")

    def __post_init__(self) -> None:
        if isinstance(self.window_swings, bool) or not isinstance(self.window_swings, int):
            raise ValueError("window_swings must be an integer")
        if self.window_swings < 4 or self.window_swings % 2:
            raise ValueError("window_swings must be an even number, at least 4")
        if not isinstance(self.significance, Decimal) or not (
            Decimal(0) < self.significance < Decimal(1)
        ):
            raise ValueError("significance must be a Decimal strictly between 0 and 1")


DEFAULT_TREND_PARAMS = TrendParams()


@dataclass(frozen=True, slots=True)
class TrendEvidence:
    """One fact that supports the state, readable by a person and stable for a machine."""

    code: EvidenceCode
    detail: str


@dataclass(frozen=True, slots=True)
class TrendClassification:
    state: TrendState
    instrument_id: str
    data_source: str
    timeframe: Timeframe
    observed_at: datetime
    # Close of the newest closed candle that was read; None if there was none.
    as_of: datetime | None
    definition_version: str
    structure_version: str
    params: TrendParams
    pivot_params: PivotParams
    # Closed candles in the window that was read.
    window_candles: int
    # The confirmed swing points the state rests on, oldest first (empty when the data was
    # unfit before any swing was looked for).
    confirmed_swings: tuple[Pivot, ...]
    evidence: tuple[TrendEvidence, ...]
    # Why there is no classification; empty exactly when `state` is not INSUFFICIENT_DATA.
    insufficient_data_reasons: tuple[InsufficientDataReason, ...]

    @property
    def is_sufficient(self) -> bool:
        return self.state is not TrendState.INSUFFICIENT_DATA


@dataclass(frozen=True, slots=True)
class TrendTimeframes:
    """The pair of timeframes of a strategy: configuration owned by that strategy and
    versioned with it. There is no universal signal/context map anywhere in Freyja."""

    signal: Timeframe
    context: Timeframe
    config_version: str

    def __post_init__(self) -> None:
        if not self.config_version.strip():
            raise InvalidTrendRequestError("the timeframe pair must carry its config version")
        if self.context.duration < self.signal.duration:
            raise InvalidTrendRequestError("context timeframe must not be finer than the signal's")


@dataclass(frozen=True, slots=True)
class TrendPair:
    """Both timeframes, classified independently. There is deliberately no combined label:
    the two answers are never merged into one."""

    timeframes: TrendTimeframes
    signal: TrendClassification
    context: TrendClassification


def classify_trend(
    *,
    instrument_id: str,
    instrument: InstrumentRef,
    schedule: MarketSchedule,
    timeframe: Timeframe,
    observed_at: datetime,
    data_source: str,
    authorized_sources: frozenset[str],
    candles: Sequence[Candle],
    pivot_params: PivotParams = DEFAULT_PIVOT_PARAMS,
    params: TrendParams = DEFAULT_TREND_PARAMS,
    min_history: int = MIN_HISTORY_CANDLES,
    publication_grace: timedelta = DEFAULT_PUBLICATION_GRACE,
) -> TrendClassification:
    """The structural trend of one timeframe's series at `observed_at`.

    `candles` are the stored candles of that series and source; any candle not closed at
    `observed_at` is ignored, so the answer can never depend on the future. Bad data never
    raises: it yields `INSUFFICIENT_DATA` with its reasons. Only a wrong request (naive
    `observed_at`, impossible parameters) raises.
    """
    _require_utc(observed_at, "observed_at")

    def result(
        state: TrendState,
        *,
        as_of: datetime | None,
        window: int = 0,
        swings: tuple[Pivot, ...] = (),
        evidence: tuple[TrendEvidence, ...] = (),
        reasons: tuple[InsufficientDataReason, ...] = (),
    ) -> TrendClassification:
        return TrendClassification(
            state=state,
            instrument_id=instrument_id,
            data_source=data_source,
            timeframe=timeframe,
            observed_at=observed_at,
            as_of=as_of,
            definition_version=TREND_DEFINITION_VERSION,
            structure_version=STRUCTURE_ALGORITHM_VERSION,
            params=params,
            pivot_params=pivot_params,
            window_candles=window,
            confirmed_swings=swings,
            evidence=evidence,
            insufficient_data_reasons=reasons,
        )

    # The series is classified on its own: it is both the signal and the context of itself.
    observable = build_observable_context(
        instrument_id=instrument_id,
        instrument=instrument,
        schedule=schedule,
        signal_timeframe=timeframe,
        context_timeframe=timeframe,
        observed_at=observed_at,
        data_source=data_source,
        authorized_sources=authorized_sources,
        candles=candles,
        min_history=min_history,
        publication_grace=publication_grace,
    )
    if not observable.is_sufficient:
        return result(
            TrendState.INSUFFICIENT_DATA,
            as_of=observable.last_closed_candle_at,
            window=observable.window_candles,
            reasons=tuple(
                sorted(_reason_from_context(reason) for reason in observable.missing_data_reasons)
            ),
        )

    closed = assess_candles(
        candles, timeframe=timeframe, now=observed_at, publication_grace=publication_grace
    ).candles
    window = tuple(closed[-min_history:])
    swings = swing_points(
        detect_pivots(
            window, timeframe=timeframe, observed_at=observed_at, params=pivot_params
        ).confirmed
    )
    if len(swings) < params.window_swings:
        found = (
            f"{len(swings)} confirmed swing point(s) in the last {len(window)} candles; "
            f"{params.window_swings} are needed"
        )
        return result(
            TrendState.INSUFFICIENT_DATA,
            as_of=window[-1].close_time,
            window=len(window),
            swings=swings,
            evidence=(TrendEvidence(EvidenceCode.SWING_COUNT, found),),
            reasons=(InsufficientDataReason.INSUFFICIENT_SWINGS,),
        )

    used = swings[-params.window_swings :]
    state, evidence = _read_structure(used, window, params)
    return result(
        state,
        as_of=window[-1].close_time,
        window=len(window),
        swings=used,
        evidence=evidence,
    )


def classify_trend_pair(
    *,
    timeframes: TrendTimeframes,
    signal_candles: Sequence[Candle],
    context_candles: Sequence[Candle],
    instrument_id: str,
    instrument: InstrumentRef,
    schedule: MarketSchedule,
    observed_at: datetime,
    data_source: str,
    authorized_sources: frozenset[str],
    pivot_params: PivotParams = DEFAULT_PIVOT_PARAMS,
    params: TrendParams = DEFAULT_TREND_PARAMS,
    min_history: int = MIN_HISTORY_CANDLES,
    publication_grace: timedelta = DEFAULT_PUBLICATION_GRACE,
) -> TrendPair:
    """Classify the signal and the context timeframes of a strategy, each on its own candles.

    Neither answer reads the other's candles, and they are returned side by side, never
    combined. Both use the same source: a context is never mixed with another source.
    """

    def one(timeframe: Timeframe, candles: Sequence[Candle]) -> TrendClassification:
        return classify_trend(
            instrument_id=instrument_id,
            instrument=instrument,
            schedule=schedule,
            timeframe=timeframe,
            observed_at=observed_at,
            data_source=data_source,
            authorized_sources=authorized_sources,
            candles=candles,
            pivot_params=pivot_params,
            params=params,
            min_history=min_history,
            publication_grace=publication_grace,
        )

    return TrendPair(
        timeframes=timeframes,
        signal=one(timeframes.signal, signal_candles),
        context=one(timeframes.context, context_candles),
    )


# -- reading the structure ------------------------------------------------------------------


def _reason_from_context(reason: MissingDataReason) -> InsufficientDataReason:
    return InsufficientDataReason(reason.value)


def _read_structure(
    swings: Sequence[Pivot], window: Sequence[Candle], params: TrendParams
) -> tuple[TrendState, tuple[TrendEvidence, ...]]:
    """State and evidence from the most recent alternating swing points."""
    highs = [s for s in swings if s.kind is PivotKind.HIGH]
    lows = [s for s in swings if s.kind is PivotKind.LOW]
    height = max(s.price for s in highs) - min(s.price for s in lows)
    if height <= 0:
        return TrendState.TRANSITION, (
            TrendEvidence(EvidenceCode.MIXED_STRUCTURE, "the swing range has no height"),
        )
    band = height * params.significance

    if _steps(highs, band) is _Steps.RISING and _steps(lows, band) is _Steps.RISING:
        evidence = (
            TrendEvidence(EvidenceCode.HIGHER_HIGHS, _levels("highs", highs)),
            TrendEvidence(EvidenceCode.HIGHER_LOWS, _levels("lows", lows)),
        )
        last_low = lows[-1]
        broken = _first_close_beyond(window, after=last_low.open_time, below=last_low.price)
        if broken is not None:
            return TrendState.TRANSITION, (
                *evidence,
                _broken(EvidenceCode.STRUCTURE_BROKEN, broken, "below", last_low),
            )
        return TrendState.UPTREND, evidence

    if _steps(highs, band) is _Steps.FALLING and _steps(lows, band) is _Steps.FALLING:
        evidence = (
            TrendEvidence(EvidenceCode.LOWER_HIGHS, _levels("highs", highs)),
            TrendEvidence(EvidenceCode.LOWER_LOWS, _levels("lows", lows)),
        )
        last_high = highs[-1]
        broken = _first_close_beyond(window, after=last_high.open_time, above=last_high.price)
        if broken is not None:
            return TrendState.TRANSITION, (
                *evidence,
                _broken(EvidenceCode.STRUCTURE_BROKEN, broken, "above", last_high),
            )
        return TrendState.DOWNTREND, evidence

    if _steps(highs, band) is _Steps.LEVEL and _steps(lows, band) is _Steps.LEVEL:
        upper = max(s.price for s in highs)
        lower = min(s.price for s in lows)
        evidence = (
            TrendEvidence(EvidenceCode.LEVEL_HIGHS, _levels("highs", highs)),
            TrendEvidence(EvidenceCode.LEVEL_LOWS, _levels("lows", lows)),
        )
        first = swings[0].open_time
        above = _first_close_beyond(window, after=first, above=upper)
        below = _first_close_beyond(window, after=first, below=lower)
        if above is not None:
            return TrendState.TRANSITION, (
                *evidence,
                TrendEvidence(
                    EvidenceCode.RANGE_BROKEN,
                    f"a candle closed at {above.close} above the upper limit {upper}",
                ),
            )
        if below is not None:
            return TrendState.TRANSITION, (
                *evidence,
                TrendEvidence(
                    EvidenceCode.RANGE_BROKEN,
                    f"a candle closed at {below.close} below the lower limit {lower}",
                ),
            )
        return TrendState.RANGE, evidence

    return TrendState.TRANSITION, (
        TrendEvidence(
            EvidenceCode.MIXED_STRUCTURE,
            f"highs are {_steps(highs, band).value.lower()} and lows are "
            f"{_steps(lows, band).value.lower()}: neither a trend nor a range",
        ),
        TrendEvidence(EvidenceCode.SWING_LEVELS, _levels("highs", highs)),
        TrendEvidence(EvidenceCode.SWING_LEVELS, _levels("lows", lows)),
    )


class _Steps(enum.Enum):
    RISING = "RISING"
    FALLING = "FALLING"
    LEVEL = "LEVEL"
    # Anything else: some steps rise, some fall, or a step is too small to count either way.
    IRREGULAR = "IRREGULAR"


def _steps(side: Sequence[Pivot], band: Decimal) -> _Steps:
    """How one side (the highs, or the lows) moves from swing to swing.

    A step is real only if larger than `band`. RISING/FALLING need every step to be. LEVEL
    needs the whole side to stay within `band`. By construction the three cannot overlap
    (two real steps in one direction are already wider than `band`).
    """
    if len(side) < 2:
        # One point has no step to read; treating it as "rising" by default would be a guess.
        raise ValueError("a side needs at least two swings to be read")
    prices = [s.price for s in side]
    diffs = [b - a for a, b in pairwise(prices)]
    if all(d > band for d in diffs):
        return _Steps.RISING
    if all(-d > band for d in diffs):
        return _Steps.FALLING
    if max(prices) - min(prices) <= band:
        return _Steps.LEVEL
    return _Steps.IRREGULAR


def _first_close_beyond(
    window: Sequence[Candle],
    *,
    after: datetime,
    above: Decimal | None = None,
    below: Decimal | None = None,
) -> Candle | None:
    """The first closed candle after `after` that closes strictly beyond a price."""
    for candle in window:
        if candle.open_time <= after:
            continue
        if above is not None and candle.close > above:
            return candle
        if below is not None and candle.close < below:
            return candle
    return None


def _broken(code: EvidenceCode, candle: Candle, side: str, swing: Pivot) -> TrendEvidence:
    return TrendEvidence(
        code,
        f"a candle closed at {candle.close} {side} the last swing {swing.kind.value.lower()} "
        f"{swing.price} of {_at(swing.open_time)}",
    )


def _levels(label: str, side: Sequence[Pivot]) -> str:
    return f"{label}: " + " -> ".join(f"{s.price}@{_at(s.open_time)}" for s in side)


def _at(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%MZ")
