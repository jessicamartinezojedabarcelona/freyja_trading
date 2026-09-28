"""Single-candle pattern detectors (POINT4-SINGLE-001).

The contract lives in ``docs/domain/detectores-de-una-vela.md`` (and, above it,
``docs/domain/patrones-de-vela.md`` and ``docs/domain/instancia-de-patron-de-vela.md``). Unlike
the chart-figure detectors (``pattern_detection.py``, pivots confirmed over many candles), a
single-candle detector judges **one closed candle**: its geometry is fully known the instant it
closes, and the trend right before it is a pure function of still older candles, so it never needs
a second evaluation. There is no boundary, no breakout, no incremental state.

Every check here is a pure function of closed candles: the same candles always give the same
answer, and candles that close later (or the one in progress) are never read.

Thresholds are provisional and versioned (``single-candle-params-v1``): reasoned from published
technical-analysis definitions, not validated (PARAMS-VALIDATION-001).
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol

from freyja_backend.domain.candlestick_pattern import (
    CandleAnchor,
    CandlePatternEvaluation,
    CandlePatternInstance,
    CandlePatternState,
    CandlePatternType,
    start_candle_pattern_instance,
)
from freyja_backend.domain.chart_pattern import PatternEvidence, evidence
from freyja_backend.domain.market_calendar import MarketSchedule
from freyja_backend.domain.market_context import MissingDataReason
from freyja_backend.domain.market_data import (
    DEFAULT_PUBLICATION_GRACE,
    Candle,
    InstrumentRef,
    InvalidMarketDataError,
    Timeframe,
    _require_utc,
    assess_candles,
)
from freyja_backend.domain.market_structure import (
    DEFAULT_PIVOT_PARAMS,
    MIN_HISTORY_CANDLES,
    PivotParams,
)
from freyja_backend.domain.market_trend import (
    DEFAULT_TREND_PARAMS,
    TrendParams,
    TrendState,
    classify_trend,
)
from freyja_backend.domain.pattern_detection import InvalidDetectionRequestError

# Bump on ANY change to a threshold or to how they are read.
SINGLE_CANDLE_PARAMETER_VERSION = "single-candle-params-v1"
# One detector, one version, for all nine patterns: they share geometry, parameters and the same
# context rule in full (docs/domain/detectores-de-una-vela.md, section 6, decision 5).
SINGLE_CANDLE_DETECTOR_VERSION = "single-candle-detector-v1"

_T = CandlePatternType


@dataclass(frozen=True, slots=True)
class SingleCandleParams:
    """Every threshold a single-candle detector reads, and the version of the set (part of every
    instance's identity). Relative to each candle's own range, so the same values read the same
    on any instrument and timeframe. Provisional and unvalidated: see PARAMS-VALIDATION-001."""

    version: str = SINGLE_CANDLE_PARAMETER_VERSION
    doji_max_body_ratio: Decimal = Decimal("0.10")
    short_wick_max_ratio: Decimal = Decimal("0.10")
    long_wick_min_ratio: Decimal = Decimal("0.60")
    small_body_max_ratio: Decimal = Decimal("0.30")
    pin_bar_max_body_ratio: Decimal = Decimal("0.25")
    pin_bar_min_wick_ratio: Decimal = Decimal("0.66")
    pivot_params: PivotParams = DEFAULT_PIVOT_PARAMS
    trend_params: TrendParams = DEFAULT_TREND_PARAMS
    min_history: int = MIN_HISTORY_CANDLES

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise InvalidDetectionRequestError("the parameters must carry their version")
        for name in (
            "doji_max_body_ratio",
            "short_wick_max_ratio",
            "long_wick_min_ratio",
            "small_body_max_ratio",
            "pin_bar_max_body_ratio",
            "pin_bar_min_wick_ratio",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not (Decimal(0) < value < Decimal(1)):
                raise InvalidDetectionRequestError(f"{name} must be a Decimal between 0 and 1")
        if (
            isinstance(self.min_history, bool)
            or not isinstance(self.min_history, int)
            or (self.min_history < 1)
        ):
            raise InvalidDetectionRequestError("min_history must be an integer of at least 1")
        if self.short_wick_max_ratio >= self.long_wick_min_ratio:
            raise InvalidDetectionRequestError(
                "the short wick ceiling must be below the long wick floor"
            )


DEFAULT_SINGLE_CANDLE_PARAMS = SingleCandleParams()


@dataclass(frozen=True, slots=True)
class SingleCandleContext:
    """What a single-candle detector needs to know about the series it reads, at one instant.

    Deliberately its own type, not `pattern_detection.DetectionContext` (POINT3's chart-figure
    context, docs/domain/detectores-de-una-vela.md section 7): reusing it would mean extending a
    POINT3 file from a POINT4 task. The two share the same shape by design, so wiring this into a
    future integration is mechanical, not a redesign.
    """

    instrument_id: str
    instrument: InstrumentRef
    schedule: MarketSchedule
    data_source: str
    authorized_sources: frozenset[str]
    timeframe: Timeframe
    observed_at: datetime
    params: SingleCandleParams = DEFAULT_SINGLE_CANDLE_PARAMS
    publication_grace: timedelta = DEFAULT_PUBLICATION_GRACE

    def at(self, observed_at: datetime) -> "SingleCandleContext":
        return replace(self, observed_at=observed_at)


class SharedGeometry(enum.StrEnum):
    """A geometry two catalogue patterns share, distinguished only by which trend preceded it
    (docs/domain/detectores-de-una-vela.md, section 4)."""

    HAMMER_OR_HANGING_MAN = "HAMMER_OR_HANGING_MAN"
    INVERTED_HAMMER_OR_SHOOTING_STAR = "INVERTED_HAMMER_OR_SHOOTING_STAR"


@dataclass(frozen=True, slots=True)
class AmbiguousGeometry:
    """A candle whose geometry matches a shared-geometry family, observed at an instant whose
    prior trend does not resolve which of its two names applies (RANGE, TRANSITION, or the trend
    classifier itself lacking enough data).

    Deliberately not a `CandlePatternInstance`: it carries no `pattern_type` and no
    `CandlePatternState`, because assigning either — even unconfirmed — would be exactly the
    invented interpretation `patrones-de-vela.md` (section 6) and `instancia-de-patron-de-vela.md`
    (section 7) refuse to make without context. It holds the geometric fact only — which candle,
    which shared family, what trend was actually observed, and which detector and parameter
    version read it — so the observation stays reproducible and auditable without ever being
    mistaken for a confirmed pattern, counted as evidence of one, or read as a signal: nothing in
    this module, and nothing that only reads `CandlePatternInstance` values (a future hypothesis
    aggregator included), can consume it as if it were.
    """

    geometry: SharedGeometry
    instrument_id: str
    data_source: str
    timeframe: Timeframe
    anchor: CandleAnchor
    observed_at: datetime
    observed_trend: TrendState
    detector_version: str
    parameter_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.geometry, SharedGeometry):
            raise InvalidDetectionRequestError(
                "geometry must be one of the shared-geometry families"
            )
        for name in ("instrument_id", "data_source", "detector_version", "parameter_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDetectionRequestError(f"{name} must be declared")


@dataclass(frozen=True, slots=True)
class SingleCandleResult:
    """What the single-candle detectors saw at one instant. If the data was not fit to judge,
    there are no instances and the reasons say why: nothing is guessed from unfit data."""

    instances: tuple[CandlePatternInstance, ...]
    # Shared-geometry candles whose context did not resolve a name (section above).
    ambiguous_geometries: tuple[AmbiguousGeometry, ...]
    unfit_reasons: tuple[MissingDataReason, ...]
    # Close of the newest closed candle read; None if there was none.
    as_of: datetime | None


# -- geometry: pure functions of one candle's proportions --------------------------------------


def _ratios(anchor: CandleAnchor) -> tuple[Decimal, Decimal, Decimal]:
    """(body, upper wick, lower wick), each as a fraction of the candle's range. Never called on
    a zero-range candle: the caller filters those out first."""
    span = anchor.range
    return (anchor.body / span, anchor.upper_wick / span, anchor.lower_wick / span)


def _is_doji(anchor: CandleAnchor, p: SingleCandleParams) -> bool:
    body, _upper, _lower = _ratios(anchor)
    return body <= p.doji_max_body_ratio


def _is_dragonfly_doji(anchor: CandleAnchor, p: SingleCandleParams) -> bool:
    body, upper, lower = _ratios(anchor)
    return (
        body <= p.doji_max_body_ratio
        and upper <= p.short_wick_max_ratio
        and lower >= (p.long_wick_min_ratio)
    )


def _is_gravestone_doji(anchor: CandleAnchor, p: SingleCandleParams) -> bool:
    body, upper, lower = _ratios(anchor)
    return (
        body <= p.doji_max_body_ratio
        and lower <= p.short_wick_max_ratio
        and upper >= (p.long_wick_min_ratio)
    )


def _is_hammer_shape(anchor: CandleAnchor, p: SingleCandleParams) -> bool:
    body, upper, lower = _ratios(anchor)
    return (
        body <= p.small_body_max_ratio
        and upper <= p.short_wick_max_ratio
        and lower >= (p.long_wick_min_ratio)
    )


def _is_inverted_hammer_shape(anchor: CandleAnchor, p: SingleCandleParams) -> bool:
    body, upper, lower = _ratios(anchor)
    return (
        body <= p.small_body_max_ratio
        and lower <= p.short_wick_max_ratio
        and upper >= (p.long_wick_min_ratio)
    )


def _is_bullish_pin_bar(anchor: CandleAnchor, p: SingleCandleParams) -> bool:
    body, _upper, lower = _ratios(anchor)
    return body <= p.pin_bar_max_body_ratio and lower >= p.pin_bar_min_wick_ratio


def _is_bearish_pin_bar(anchor: CandleAnchor, p: SingleCandleParams) -> bool:
    body, upper, _lower = _ratios(anchor)
    return body <= p.pin_bar_max_body_ratio and upper >= p.pin_bar_min_wick_ratio


class _GeometryCheck(Protocol):
    def __call__(self, anchor: CandleAnchor, p: SingleCandleParams) -> bool: ...


# A single geometry that only ever means one thing once its context is checked.
_SINGLE_NAME: tuple[tuple[_GeometryCheck, CandlePatternType], ...] = (
    (_is_dragonfly_doji, _T.DRAGONFLY_DOJI),
    (_is_gravestone_doji, _T.GRAVESTONE_DOJI),
    (_is_bullish_pin_bar, _T.BULLISH_PIN_BAR),
    (_is_bearish_pin_bar, _T.BEARISH_PIN_BAR),
)

# The same geometry, two mutually exclusive names depending on which trend preceded it. Neither
# name is declared when the context does not resolve which one applies (section 4 of the doc);
# the geometry itself is still reported, as an `AmbiguousGeometry`, never as either name.
_SHARED_GEOMETRY: tuple[
    tuple[_GeometryCheck, CandlePatternType, CandlePatternType, SharedGeometry], ...
] = (
    (_is_hammer_shape, _T.HAMMER, _T.HANGING_MAN, SharedGeometry.HAMMER_OR_HANGING_MAN),
    (
        _is_inverted_hammer_shape,
        _T.INVERTED_HAMMER,
        _T.SHOOTING_STAR,
        SharedGeometry.INVERTED_HAMMER_OR_SHOOTING_STAR,
    ),
)

_REQUIRED_TREND: dict[CandlePatternType, TrendState] = {
    _T.DRAGONFLY_DOJI: TrendState.DOWNTREND,
    _T.GRAVESTONE_DOJI: TrendState.UPTREND,
    _T.BULLISH_PIN_BAR: TrendState.DOWNTREND,
    _T.BEARISH_PIN_BAR: TrendState.UPTREND,
}


# -- context: the trend right before the candle -------------------------------------------------


def _prior_trend(
    context: SingleCandleContext,
    before: Sequence[Candle],
    at: datetime,
    cache: dict[datetime, TrendState],
) -> TrendState:
    """The trend the POINT2 classifier would give right before a candle opening at `at`, from the
    candles strictly before it.

    `cache` is local to one `detect_single_candle_patterns` call (built there, passed down: never
    stored on `context`). Within a single call, `before` for a given `at` is always the same
    sequence, so keying by `at` alone is safe there. It is deliberately *not* kept across calls
    that reuse the same context (`.at()`): a candle that later arrives, or an earlier one that
    gets corrected, changes what `before` should be for the same `at` without necessarily
    changing its length — a cache keyed by `(at, len(before))` was tried and still returned a
    stale classification when a candle was corrected in place (same count, same instant,
    different content); reproduced against two real series (a downtrend and an uptrend, same
    length, same final instant) before removing the cross-call cache entirely (see the contract
    doc)."""
    cached = cache.get(at)
    if cached is not None:
        return cached
    params = context.params
    state = classify_trend(
        instrument_id=context.instrument_id,
        instrument=context.instrument,
        schedule=context.schedule,
        timeframe=context.timeframe,
        observed_at=at,
        data_source=context.data_source,
        authorized_sources=context.authorized_sources,
        candles=before,
        pivot_params=params.pivot_params,
        params=params.trend_params,
        min_history=params.min_history,
        publication_grace=context.publication_grace,
    ).state
    cache[at] = state
    return state


def _context_evidence(required: TrendState | None, observed: TrendState) -> PatternEvidence:
    required_value = required.value if required is not None else "NONE"
    compatible = required is None or observed is required
    return evidence(
        "CONTEXT",
        f"trend before the candle: {observed.value}; needed {required_value}",
        state=observed.value,
        required=required_value,
        compatible=compatible,
    )


# -- building instances ---------------------------------------------------------------------


def _confirmed(
    anchor: CandleAnchor, at: datetime, required: TrendState | None, observed: TrendState
) -> CandlePatternEvaluation:
    return CandlePatternEvaluation(
        at,
        at,
        CandlePatternState.CONFIRMED,
        (anchor,),
        evidence=(_context_evidence(required, observed),),
    )


def _morphologically_valid(anchor: CandleAnchor, at: datetime) -> CandlePatternEvaluation:
    return CandlePatternEvaluation(at, at, CandlePatternState.MORPHOLOGICALLY_VALID, (anchor,))


def _instance(
    context: SingleCandleContext,
    pattern_type: CandlePatternType,
    evaluation: CandlePatternEvaluation,
) -> CandlePatternInstance:
    return start_candle_pattern_instance(
        pattern_type=pattern_type,
        instrument_id=context.instrument_id,
        data_source=context.data_source,
        timeframe=context.timeframe,
        detector_version=SINGLE_CANDLE_DETECTOR_VERSION,
        parameter_version=context.params.version,
        first_evaluation=evaluation,
    )


def _ambiguous(
    context: SingleCandleContext,
    geometry: SharedGeometry,
    anchor: CandleAnchor,
    at: datetime,
    observed: TrendState,
) -> AmbiguousGeometry:
    return AmbiguousGeometry(
        geometry=geometry,
        instrument_id=context.instrument_id,
        data_source=context.data_source,
        timeframe=context.timeframe,
        anchor=anchor,
        observed_at=at,
        observed_trend=observed,
        detector_version=SINGLE_CANDLE_DETECTOR_VERSION,
        parameter_version=context.params.version,
    )


def _instances_for_candle(
    context: SingleCandleContext,
    before: Sequence[Candle],
    candle: Candle,
    cache: dict[datetime, TrendState],
) -> tuple[list[CandlePatternInstance], list[AmbiguousGeometry]]:
    anchor = CandleAnchor.from_candle(candle, "FIRST")
    if anchor.range <= 0:
        return [], []
    params = context.params
    at = candle.close_time
    found: list[CandlePatternInstance] = []
    ambiguous: list[AmbiguousGeometry] = []

    if _is_doji(anchor, params):
        observed = _prior_trend(context, before, candle.open_time, cache)
        found.append(_instance(context, _T.DOJI, _confirmed(anchor, at, None, observed)))

    for check, pattern_type in _SINGLE_NAME:
        if not check(anchor, params):
            continue
        observed = _prior_trend(context, before, candle.open_time, cache)
        required = _REQUIRED_TREND[pattern_type]
        evaluation = (
            _confirmed(anchor, at, required, observed)
            if observed is required
            else _morphologically_valid(anchor, at)
        )
        found.append(_instance(context, pattern_type, evaluation))

    for check, down_type, up_type, geometry in _SHARED_GEOMETRY:
        if not check(anchor, params):
            continue
        observed = _prior_trend(context, before, candle.open_time, cache)
        if observed is TrendState.DOWNTREND:
            found.append(
                _instance(
                    context, down_type, _confirmed(anchor, at, TrendState.DOWNTREND, observed)
                )
            )
        elif observed is TrendState.UPTREND:
            found.append(
                _instance(context, up_type, _confirmed(anchor, at, TrendState.UPTREND, observed))
            )
        else:
            # RANGE / TRANSITION / INSUFFICIENT_DATA: neither name is declared, but the geometric
            # observation itself is not discarded (see `AmbiguousGeometry`).
            ambiguous.append(_ambiguous(context, geometry, anchor, at, observed))

    return found, ambiguous


def detect_single_candle_patterns(
    context: SingleCandleContext, candles: Sequence[Candle]
) -> SingleCandleResult:
    """The single-candle patterns visible at `context.observed_at`, from the candles closed by
    then. Candles that close later, and the one in progress, are ignored. Bad data never raises:
    it yields no instances and the reasons. Only a wrong request raises.

    A pure function of the whole closed series every time it is called (no incremental state): a
    candle's own result never changes once computed, so calling this again with more candles only
    ever adds instances (or ambiguous-geometry observations), never revises one already found
    (docs/domain/detectores-de-una-vela.md, section 6).

    The prior-trend cache lives only for the duration of this call (built here, never stored on
    `context`): sharing it across separate calls proved unsafe even when keyed by
    `(instant, candles read)`, because a candle corrected in place — same count, same instant,
    different content — still returned the earlier, wrong classification (see the contract doc).
    """
    _require_utc(context.observed_at, "observed_at")  # a wrong request, not bad data
    try:
        closed = assess_candles(
            candles,
            timeframe=context.timeframe,
            now=context.observed_at,
            publication_grace=context.publication_grace,
        ).candles
    except InvalidMarketDataError:
        return SingleCandleResult((), (), (MissingDataReason.INVALID_CANDLES,), None)
    as_of = closed[-1].close_time if closed else None
    if context.data_source not in context.authorized_sources:
        return SingleCandleResult((), (), (MissingDataReason.SOURCE_NOT_AUTHORIZED,), as_of)
    instances: list[CandlePatternInstance] = []
    ambiguous: list[AmbiguousGeometry] = []
    trend_cache: dict[datetime, TrendState] = {}
    for index, candle in enumerate(closed):
        found, amb = _instances_for_candle(context, closed[:index], candle, trend_cache)
        instances.extend(found)
        ambiguous.extend(amb)
    return SingleCandleResult(tuple(instances), tuple(ambiguous), (), as_of)
