"""Two-candle pattern detectors (POINT4-MULTI-001, first delivery).

The contract lives in ``docs/domain/detectores-de-dos-y-tres-velas.md`` (and, above it,
``docs/domain/patrones-de-vela.md`` and ``docs/domain/instancia-de-patron-de-vela.md``). Same
architecture as ``candlestick_single.py``: each pattern is resolved completely the instant its
last candle closes, from the candles closed by then and the trend right before the first candle
of the pair (a pure function of still older candles, so no incremental state is needed).

Three-candle patterns (``MORNING_STAR``, ``EVENING_STAR``, ``THREE_WHITE_SOLDIERS``,
``THREE_BLACK_CROWS``, ``THREE_INSIDE_UP``, ``THREE_INSIDE_DOWN``) are a second delivery of the
same task: ``THREE_INSIDE_UP``/``DOWN`` reuse the harami geometry checks defined here (see the
contract, section 7), so this module comes first.

Thresholds are provisional and versioned (``multi-candle-params-v1``): reasoned from published
technical-analysis definitions, not validated (PARAMS-VALIDATION-001).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import Decimal

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

# Bump on ANY change to a threshold or to how they are read. Shared across the whole task (both
# deliveries): new fields the three-candle patterns need are added to `MultiCandleParams` with
# defaults, never by bumping this for the two-candle thresholds already here.
MULTI_CANDLE_PARAMETER_VERSION = "multi-candle-params-v1"
# One detector, one version, for the whole task: the fourteen patterns share parameters and the
# same context rule in full (same reasoning as single-candle-detector-v1).
MULTI_CANDLE_DETECTOR_VERSION = "multi-candle-detector-v1"

_T = CandlePatternType


@dataclass(frozen=True, slots=True)
class MultiCandleParams:
    """Every threshold a two- or three-candle detector reads, and the version of the set (part of
    every instance's identity). Relative to each candle's own range or body, so the same values
    read the same on any instrument and timeframe. Provisional and unvalidated: see
    PARAMS-VALIDATION-001."""

    version: str = MULTI_CANDLE_PARAMETER_VERSION
    # The harami's first candle is "wide-bodied": its body is at least this fraction of its range.
    harami_outer_min_body_ratio: Decimal = Decimal("0.50")
    # The harami's second candle is "small-bodied": its body is at most this fraction of the
    # first candle's body.
    harami_inner_max_body_ratio: Decimal = Decimal("0.50")
    # Two lows (or highs) are "practically equal" within this fraction of the mean of the two
    # candles' ranges.
    tweezer_tolerance: Decimal = Decimal("0.10")
    pivot_params: PivotParams = DEFAULT_PIVOT_PARAMS
    trend_params: TrendParams = DEFAULT_TREND_PARAMS
    min_history: int = MIN_HISTORY_CANDLES

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise InvalidDetectionRequestError("the parameters must carry their version")
        for name in (
            "harami_outer_min_body_ratio",
            "harami_inner_max_body_ratio",
            "tweezer_tolerance",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not (Decimal(0) < value < Decimal(1)):
                raise InvalidDetectionRequestError(f"{name} must be a Decimal between 0 and 1")
        if (
            isinstance(self.min_history, bool)
            or not isinstance(self.min_history, int)
            or self.min_history < 1
        ):
            raise InvalidDetectionRequestError("min_history must be an integer of at least 1")


DEFAULT_MULTI_CANDLE_PARAMS = MultiCandleParams()


@dataclass(frozen=True, slots=True)
class MultiCandleContext:
    """What a two- or three-candle detector needs to know about the series it reads, at one
    instant. Its own type, not `SingleCandleContext` or `DetectionContext`: POINT4-MULTI-001 is
    its own task, with its own parameters, even though the shape mirrors both on purpose."""

    instrument_id: str
    instrument: InstrumentRef
    schedule: MarketSchedule
    data_source: str
    authorized_sources: frozenset[str]
    timeframe: Timeframe
    observed_at: datetime
    params: MultiCandleParams = DEFAULT_MULTI_CANDLE_PARAMS
    publication_grace: timedelta = DEFAULT_PUBLICATION_GRACE
    # Memory of prior-trend classifications, keyed by the pattern's first candle's open_time.
    _prior_trends: dict[datetime, TrendState] = field(
        default_factory=dict, compare=False, repr=False
    )

    def at(self, observed_at: datetime) -> "MultiCandleContext":
        return replace(self, observed_at=observed_at)


@dataclass(frozen=True, slots=True)
class MultiCandleResult:
    """What the two-/three-candle detectors saw at one instant. If the data was not fit to judge,
    there are no instances and the reasons say why: nothing is guessed from unfit data."""

    instances: tuple[CandlePatternInstance, ...]
    unfit_reasons: tuple[MissingDataReason, ...]
    # Close of the newest closed candle read; None if there was none.
    as_of: datetime | None


# -- geometry: pure functions of two candles' proportions ---------------------------------------


_PairGeometryCheck = Callable[[CandleAnchor, CandleAnchor, MultiCandleParams], bool]


def _is_bullish_engulfing(c1: CandleAnchor, c2: CandleAnchor, _p: MultiCandleParams) -> bool:
    return c1.is_bearish and c2.is_bullish and c2.open <= c1.close and c2.close >= c1.open


def _is_bearish_engulfing(c1: CandleAnchor, c2: CandleAnchor, _p: MultiCandleParams) -> bool:
    return c1.is_bullish and c2.is_bearish and c2.open >= c1.close and c2.close <= c1.open


def is_bullish_harami(c1: CandleAnchor, c2: CandleAnchor, p: MultiCandleParams) -> bool:
    """Public: reused as-is by the THREE_INSIDE_UP detector (contract section 7)."""
    if not (c1.is_bearish and c2.is_bullish) or c1.range <= 0 or c1.body <= 0:
        return False
    if c1.body / c1.range < p.harami_outer_min_body_ratio:
        return False
    if c2.body > p.harami_inner_max_body_ratio * c1.body:
        return False
    return c1.close < c2.open and c2.close < c1.open


def is_bearish_harami(c1: CandleAnchor, c2: CandleAnchor, p: MultiCandleParams) -> bool:
    """Public: reused as-is by the THREE_INSIDE_DOWN detector (contract section 7)."""
    if not (c1.is_bullish and c2.is_bearish) or c1.range <= 0 or c1.body <= 0:
        return False
    if c1.body / c1.range < p.harami_outer_min_body_ratio:
        return False
    if c2.body > p.harami_inner_max_body_ratio * c1.body:
        return False
    return c1.open < c2.close and c2.open < c1.close


def _is_tweezer_bottom(c1: CandleAnchor, c2: CandleAnchor, p: MultiCandleParams) -> bool:
    reference = (c1.range + c2.range) / 2
    if reference <= 0:
        return False
    return abs(c1.low - c2.low) <= p.tweezer_tolerance * reference


def _is_tweezer_top(c1: CandleAnchor, c2: CandleAnchor, p: MultiCandleParams) -> bool:
    reference = (c1.range + c2.range) / 2
    if reference <= 0:
        return False
    return abs(c1.high - c2.high) <= p.tweezer_tolerance * reference


def _is_piercing_pattern(c1: CandleAnchor, c2: CandleAnchor, _p: MultiCandleParams) -> bool:
    if not (c1.is_bearish and c2.is_bullish) or c1.body <= 0 or c2.open > c1.close:
        return False
    midpoint = (c1.open + c1.close) / 2
    return midpoint < c2.close < c1.open


def _is_dark_cloud_cover(c1: CandleAnchor, c2: CandleAnchor, _p: MultiCandleParams) -> bool:
    if not (c1.is_bullish and c2.is_bearish) or c1.body <= 0 or c2.open < c1.close:
        return False
    midpoint = (c1.open + c1.close) / 2
    return c1.open < c2.close < midpoint


_PAIR_CHECKS: tuple[tuple[_PairGeometryCheck, CandlePatternType], ...] = (
    (_is_bullish_engulfing, _T.BULLISH_ENGULFING),
    (_is_bearish_engulfing, _T.BEARISH_ENGULFING),
    (is_bullish_harami, _T.BULLISH_HARAMI),
    (is_bearish_harami, _T.BEARISH_HARAMI),
    (_is_tweezer_bottom, _T.TWEEZER_BOTTOM),
    (_is_tweezer_top, _T.TWEEZER_TOP),
    (_is_piercing_pattern, _T.PIERCING_PATTERN),
    (_is_dark_cloud_cover, _T.DARK_CLOUD_COVER),
)

_REQUIRED_TREND: dict[CandlePatternType, TrendState] = {
    _T.BULLISH_ENGULFING: TrendState.DOWNTREND,
    _T.BEARISH_ENGULFING: TrendState.UPTREND,
    _T.BULLISH_HARAMI: TrendState.DOWNTREND,
    _T.BEARISH_HARAMI: TrendState.UPTREND,
    _T.TWEEZER_BOTTOM: TrendState.DOWNTREND,
    _T.TWEEZER_TOP: TrendState.UPTREND,
    _T.PIERCING_PATTERN: TrendState.DOWNTREND,
    _T.DARK_CLOUD_COVER: TrendState.UPTREND,
}


# -- context: the trend right before the pattern's first candle ---------------------------------


def _prior_trend(context: MultiCandleContext, before: Sequence[Candle], at: datetime) -> TrendState:
    """The trend the POINT2 classifier would give right before the pattern's first candle: a pure
    function of still older candles, same principle as `detectores-de-una-vela.md`."""
    cached = context._prior_trends.get(at)
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
    context._prior_trends[at] = state
    return state


def _context_evidence(required: TrendState, observed: TrendState) -> PatternEvidence:
    compatible = observed is required
    return evidence(
        "CONTEXT",
        f"trend before the pattern: {observed.value}; needed {required.value}",
        state=observed.value,
        required=required.value,
        compatible=compatible,
    )


# -- building instances ---------------------------------------------------------------------


def _confirmed(
    anchors: tuple[CandleAnchor, ...], at: datetime, required: TrendState, observed: TrendState
) -> CandlePatternEvaluation:
    return CandlePatternEvaluation(
        at,
        at,
        CandlePatternState.CONFIRMED,
        anchors,
        evidence=(_context_evidence(required, observed),),
    )


def _morphologically_valid(
    anchors: tuple[CandleAnchor, ...], at: datetime
) -> CandlePatternEvaluation:
    return CandlePatternEvaluation(at, at, CandlePatternState.MORPHOLOGICALLY_VALID, anchors)


def _instance(
    context: MultiCandleContext,
    pattern_type: CandlePatternType,
    evaluation: CandlePatternEvaluation,
) -> CandlePatternInstance:
    return start_candle_pattern_instance(
        pattern_type=pattern_type,
        instrument_id=context.instrument_id,
        data_source=context.data_source,
        timeframe=context.timeframe,
        detector_version=MULTI_CANDLE_DETECTOR_VERSION,
        parameter_version=context.params.version,
        first_evaluation=evaluation,
    )


def _instances_for_pair(
    context: MultiCandleContext, before: Sequence[Candle], first: Candle, second: Candle
) -> list[CandlePatternInstance]:
    c1 = CandleAnchor.from_candle(first, "FIRST")
    c2 = CandleAnchor.from_candle(second, "SECOND")
    if c1.range <= 0 or c2.range <= 0:
        return []
    params = context.params
    at = second.close_time
    found: list[CandlePatternInstance] = []

    for check, pattern_type in _PAIR_CHECKS:
        if not check(c1, c2, params):
            continue
        observed = _prior_trend(context, before, first.open_time)
        required = _REQUIRED_TREND[pattern_type]
        evaluation = (
            _confirmed((c1, c2), at, required, observed)
            if observed is required
            else _morphologically_valid((c1, c2), at)
        )
        found.append(_instance(context, pattern_type, evaluation))

    return found


def detect_multi_candle_patterns(
    context: MultiCandleContext, candles: Sequence[Candle]
) -> MultiCandleResult:
    """The two-candle patterns visible at `context.observed_at`, from the candles closed by then.
    Candles that close later, and the one in progress, are ignored. Bad data never raises: it
    yields no instances and the reasons. Only a wrong request raises.

    A pure function of the whole closed series every time it is called (no incremental state),
    same principle as `detect_single_candle_patterns`.
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
        return MultiCandleResult((), (MissingDataReason.INVALID_CANDLES,), None)
    as_of = closed[-1].close_time if closed else None
    if context.data_source not in context.authorized_sources:
        return MultiCandleResult((), (MissingDataReason.SOURCE_NOT_AUTHORIZED,), as_of)
    instances: list[CandlePatternInstance] = []
    for index in range(1, len(closed)):
        before = closed[: index - 1]
        instances.extend(_instances_for_pair(context, before, closed[index - 1], closed[index]))
    return MultiCandleResult(tuple(instances), (), as_of)
