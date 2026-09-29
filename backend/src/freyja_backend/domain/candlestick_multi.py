"""Two- and three-candle pattern detectors (POINT4-MULTI-001).

The contract lives in ``docs/domain/detectores-de-dos-y-tres-velas.md`` (and, above it,
``docs/domain/patrones-de-vela.md`` and ``docs/domain/instancia-de-patron-de-vela.md``). Same
architecture as ``candlestick_single.py``: each pattern is resolved completely the instant its
last candle closes, from the candles closed by then and the trend right before the pattern's
first candle (a pure function of still older candles, so no incremental state is needed).

Two families, two independent versions (contract, "Versionado"). ``THREE_INSIDE_UP``/``DOWN``
reuse the harami geometry checks (``is_bullish_harami``/``is_bearish_harami``) but never
``MultiCandleParams``'s own version: ``ThreeCandleParams.harami_params()`` stamps its own version
onto the borrowed thresholds first, the same trick ``DiamondParams.channel_params()`` uses in
``pattern_detection.py``. A change to one family's thresholds or detector logic never shifts the
other family's instance identities.

Thresholds are provisional and versioned (``multi-candle-params-v1``, ``three-candle-params-v2``):
reasoned from published technical-analysis definitions, not validated (PARAMS-VALIDATION-001).

The gap policy for ``MORNING_STAR``/``EVENING_STAR`` (contract section 2) is decided by market:
``_gap_policy_for_market`` gives CRYPTO ``GAP_NOT_APPLICABLE`` and FOREX/METALS ``GAP_OPTIONAL``,
applied whenever ``ThreeCandleParams.gap_policy`` is left unset (``None``); an explicit value on
the params always overrides the market default.
"""

import enum
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
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

# Bump on ANY change to a two-candle threshold or to how they are read. Governs ONLY the eight
# two-candle patterns' identity: see the module docstring for why this never mixes with the
# three-candle family's own version.
MULTI_CANDLE_PARAMETER_VERSION = "multi-candle-params-v1"
# One detector, one version, for the eight two-candle patterns: they share parameters and the
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


# Bump on ANY change to a three-candle threshold, to a structural rule, or to how they are read.
# Its own version, decoupled from `MultiCandleParams`'s: see the module docstring.
# v2 (POINT4-TEST-001 follow-up, 2026-09-29): the gap policy for MORNING_STAR/EVENING_STAR is
# now decided by market (`_gap_policy_for_market`) when `gap_policy` is left unset, instead of
# always defaulting to GAP_NOT_APPLICABLE regardless of instrument — see `ThreeCandleParams`.
THREE_CANDLE_PARAMETER_VERSION = "three-candle-params-v2"
# One detector, one version, for the six three-candle patterns.
THREE_CANDLE_DETECTOR_VERSION = "three-candle-detector-v1"


class GapPolicy(enum.StrEnum):
    """`patrones-de-vela.md`, section 2. Applies only to the gap between candle 1 and candle 2 of
    `MORNING_STAR`/`EVENING_STAR`."""

    GAP_REQUIRED = "GAP_REQUIRED"
    GAP_OPTIONAL = "GAP_OPTIONAL"
    GAP_NOT_APPLICABLE = "GAP_NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class ThreeCandleParams:
    """Every threshold a three-candle detector reads, and the version of the set (part of every
    instance's identity). Its own values, own version: `harami_params()` is the only bridge to
    the two-candle delivery's harami check (`is_bullish_harami`/`is_bearish_harami`), and it
    stamps this version onto what it borrows, so a change here never silently changes
    `BULLISH_HARAMI`/`BEARISH_HARAMI`'s own identity, and a change to `MultiCandleParams` never
    silently changes `THREE_INSIDE_UP`/`DOWN`'s. Provisional and unvalidated: see
    PARAMS-VALIDATION-001."""

    version: str = THREE_CANDLE_PARAMETER_VERSION
    # THREE_INSIDE_UP/DOWN's own copy of the harami thresholds (contract section 7): read from
    # here, never from `MultiCandleParams`, so the two families version independently.
    harami_outer_min_body_ratio: Decimal = Decimal("0.50")
    harami_inner_max_body_ratio: Decimal = Decimal("0.50")
    # MORNING_STAR/EVENING_STAR: candle 2's body is "small" (or a doji) at most this fraction of
    # its own range.
    min_body_ratio: Decimal = Decimal("0.30")
    # MORNING_STAR/EVENING_STAR, with GAP_REQUIRED: the gap between candle 1 and candle 2's
    # bodies is at least this fraction of candle 1's body.
    gap_min_fraction: Decimal = Decimal("0.10")
    # None means "let the market decide" (`_gap_policy_for_market`, keyed on
    # `MultiCandleContext.instrument.market` — patrones-de-vela.md section 2, POINT4-TEST-001
    # follow-up): CRYPTO x SPOT trades in continuous session, no real gaps, so it gets
    # GAP_NOT_APPLICABLE; FOREX and METALS can gap, but essentially only at their weekly reopen,
    # never candle-to-candle within a session at Freyja's intraday timeframes, so they get
    # GAP_OPTIONAL rather than GAP_REQUIRED (demanding one would make MORNING_STAR/EVENING_STAR
    # nearly undetectable there — the same "invalidaría el patrón por construcción" problem the
    # contract warns against). An explicit value here always wins over the market default.
    gap_policy: GapPolicy | None = None
    # THREE_WHITE_SOLDIERS/THREE_BLACK_CROWS: the wick on the side against the trend of each
    # candle is at most this fraction of its own range ("mechas superiores pequeñas").
    three_soldiers_upper_wick_max_ratio: Decimal = Decimal("0.20")
    pivot_params: PivotParams = DEFAULT_PIVOT_PARAMS
    trend_params: TrendParams = DEFAULT_TREND_PARAMS
    min_history: int = MIN_HISTORY_CANDLES

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise InvalidDetectionRequestError("the parameters must carry their version")
        for name in (
            "harami_outer_min_body_ratio",
            "harami_inner_max_body_ratio",
            "min_body_ratio",
            "gap_min_fraction",
            "three_soldiers_upper_wick_max_ratio",
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

    def harami_params(self) -> "MultiCandleParams":
        """THREE_INSIDE_UP/DOWN's own harami thresholds, in the shape `is_bullish_harami`/
        `is_bearish_harami` read, stamped with this version (same trick as
        `DiamondParams.channel_params()` in `pattern_detection.py`): reusing the check never ties
        this family's identity to `multi-candle-params-v1`."""
        return MultiCandleParams(
            version=self.version,
            harami_outer_min_body_ratio=self.harami_outer_min_body_ratio,
            harami_inner_max_body_ratio=self.harami_inner_max_body_ratio,
            pivot_params=self.pivot_params,
            trend_params=self.trend_params,
            min_history=self.min_history,
        )


DEFAULT_THREE_CANDLE_PARAMS = ThreeCandleParams()


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
    triple: ThreeCandleParams = DEFAULT_THREE_CANDLE_PARAMS
    publication_grace: timedelta = DEFAULT_PUBLICATION_GRACE

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


# -- geometry: pure functions of three candles' proportions --------------------------------------

# Markets whose real product/instrument still doesn't rule out a weekly-reopen gap, so requiring
# one on every candle would make the pattern nearly undetectable at intraday timeframes — the
# market default is GAP_OPTIONAL for these (and for any market not listed, conservatively: never
# assume a gap is either impossible or guaranteed). Only CRYPTO gets GAP_NOT_APPLICABLE, since it
# is the only market Freyja's catalog has today that genuinely never gaps.
_NO_GAP_MARKET = "CRYPTO"


def _gap_policy_for_market(market: str) -> GapPolicy:
    """patrones-de-vela.md section 2: which gap policy applies to which market, decided here
    (product decision, 2026-09-29) — FOREX and METALS (XAU/USD, an OTC-like market: treated the
    same as FOREX unless the contract says otherwise) both get GAP_OPTIONAL, CRYPTO gets
    GAP_NOT_APPLICABLE. Only used when `ThreeCandleParams.gap_policy` is left unset (`None`); an
    explicit value always overrides this. Provider-agnostic on purpose: this layer never names
    which data source publishes a market's candles."""
    if market == _NO_GAP_MARKET:
        return GapPolicy.GAP_NOT_APPLICABLE
    return GapPolicy.GAP_OPTIONAL


def _star_gap(
    c1: CandleAnchor, c2: CandleAnchor, p: ThreeCandleParams, *, down: bool
) -> tuple[bool, PatternEvidence | None]:
    """Whether the gap requirement between candle 1 and candle 2 is met, and the `GAP` evidence
    to attach. `GAP_NOT_APPLICABLE` measures nothing and always passes (contract section 6).
    `p.gap_policy` must already be resolved (never `None`) — callers go through
    `_resolved_triple_params` first."""
    policy = p.gap_policy
    assert policy is not None, "gap_policy must be resolved before _star_gap is called"
    if policy is GapPolicy.GAP_NOT_APPLICABLE:
        return True, None
    if down:
        gap = min(c1.open, c1.close) - max(c2.open, c2.close)
    else:
        gap = min(c2.open, c2.close) - max(c1.open, c1.close)
    required = p.gap_min_fraction * c1.body if policy is GapPolicy.GAP_REQUIRED else Decimal(0)
    met = gap >= required
    ok = met if policy is GapPolicy.GAP_REQUIRED else True
    return ok, _gap_evidence(policy, gap, required, met)


def _morning_or_evening_star(
    c1: CandleAnchor, c2: CandleAnchor, c3: CandleAnchor, p: ThreeCandleParams
) -> tuple[CandlePatternType, PatternEvidence | None] | None:
    """`MORNING_STAR` if candle 1 is wide-bodied bearish, candle 2 small-bodied (or a doji),
    candle 3 bullish closing at or beyond the midpoint of candle 1's body; `EVENING_STAR` the
    mirror. `None` if neither. The gap, when the policy asks for one, is part of the geometry
    itself (contract section 5): failing it under `GAP_REQUIRED` means the shape does not exist
    at all, not that it exists unconfirmed."""
    if c2.body / c2.range > p.min_body_ratio:
        return None
    midpoint = (c1.open + c1.close) / 2
    outer_ok = c1.body / c1.range >= p.harami_outer_min_body_ratio
    if c1.is_bearish and outer_ok and c3.is_bullish and c3.close >= midpoint:
        ok, gap_ev = _star_gap(c1, c2, p, down=True)
        if ok:
            return _T.MORNING_STAR, gap_ev
    if c1.is_bullish and outer_ok and c3.is_bearish and c3.close <= midpoint:
        ok, gap_ev = _star_gap(c1, c2, p, down=False)
        if ok:
            return _T.EVENING_STAR, gap_ev
    return None


def _is_three_white_soldiers(
    c1: CandleAnchor, c2: CandleAnchor, c3: CandleAnchor, p: ThreeCandleParams
) -> bool:
    if not (c1.is_bullish and c2.is_bullish and c3.is_bullish):
        return False
    if not (c2.close > c1.close and c3.close > c2.close):
        return False
    if not (c1.open < c2.open < c1.close):
        return False
    if not (c2.open < c3.open < c2.close):
        return False
    return all(
        c.upper_wick / c.range <= p.three_soldiers_upper_wick_max_ratio for c in (c1, c2, c3)
    )


def _is_three_black_crows(
    c1: CandleAnchor, c2: CandleAnchor, c3: CandleAnchor, p: ThreeCandleParams
) -> bool:
    if not (c1.is_bearish and c2.is_bearish and c3.is_bearish):
        return False
    if not (c2.close < c1.close and c3.close < c2.close):
        return False
    if not (c1.close < c2.open < c1.open):
        return False
    if not (c2.close < c3.open < c2.open):
        return False
    return all(
        c.lower_wick / c.range <= p.three_soldiers_upper_wick_max_ratio for c in (c1, c2, c3)
    )


_REQUIRED_TREND_TRIPLE: dict[CandlePatternType, TrendState | None] = {
    _T.MORNING_STAR: TrendState.DOWNTREND,
    _T.EVENING_STAR: TrendState.UPTREND,
    # Traditionally significant after a decline/consolidation, but not a strict requirement
    # (patrones-de-vela.md, section 5.3): the instance always confirms once the geometry holds.
    _T.THREE_WHITE_SOLDIERS: None,
    _T.THREE_BLACK_CROWS: None,
    _T.THREE_INSIDE_UP: TrendState.DOWNTREND,
    _T.THREE_INSIDE_DOWN: TrendState.UPTREND,
}


# -- context: the trend right before the pattern's first candle ---------------------------------


def _prior_trend(
    context: MultiCandleContext,
    before: Sequence[Candle],
    at: datetime,
    cache: dict[datetime, TrendState],
) -> TrendState:
    """The trend the POINT2 classifier would give right before the pattern's first candle: a pure
    function of still older candles, same principle as `detectores-de-una-vela.md`.

    `cache` is local to one `detect_multi_candle_patterns` call (built there, passed down: never
    stored on `context`). Within a single call, `before` for a given `at` is always the same
    sequence, so keying by `at` alone is safe there. It is deliberately *not* kept across calls
    that reuse the same context (`.at()`): a first attempt keyed a context-level cache by
    `(at, len(before))` to survive a late-arriving candle, but a candle corrected in place — same
    count, same instant, different content — still returned a stale classification; reproduced
    against two real series (a downtrend and an uptrend, same length, same final instant) before
    removing the cross-call cache entirely (see the contract doc)."""
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
        f"trend before the pattern: {observed.value}; needed {required_value}",
        state=observed.value,
        required=required_value,
        compatible=compatible,
    )


def _gap_evidence(policy: GapPolicy, gap: Decimal, required: Decimal, met: bool) -> PatternEvidence:
    return evidence(
        "GAP",
        f"gap policy {policy.value}: measured {gap} against candle 1's body, needed {required}",
        policy=policy.value,
        gap=gap,
        required=required,
        met=met,
    )


# -- building instances ---------------------------------------------------------------------


def _confirmed(
    anchors: tuple[CandleAnchor, ...],
    at: datetime,
    required: TrendState | None,
    observed: TrendState,
    extra_evidence: tuple[PatternEvidence, ...] = (),
) -> CandlePatternEvaluation:
    return CandlePatternEvaluation(
        at,
        at,
        CandlePatternState.CONFIRMED,
        anchors,
        evidence=(_context_evidence(required, observed), *extra_evidence),
    )


def _morphologically_valid(
    anchors: tuple[CandleAnchor, ...], at: datetime
) -> CandlePatternEvaluation:
    return CandlePatternEvaluation(at, at, CandlePatternState.MORPHOLOGICALLY_VALID, anchors)


def _instance(
    context: MultiCandleContext,
    pattern_type: CandlePatternType,
    evaluation: CandlePatternEvaluation,
    *,
    detector_version: str,
    parameter_version: str,
) -> CandlePatternInstance:
    return start_candle_pattern_instance(
        pattern_type=pattern_type,
        instrument_id=context.instrument_id,
        data_source=context.data_source,
        timeframe=context.timeframe,
        detector_version=detector_version,
        parameter_version=parameter_version,
        first_evaluation=evaluation,
    )


def _instances_for_pair(
    context: MultiCandleContext,
    before: Sequence[Candle],
    first: Candle,
    second: Candle,
    cache: dict[datetime, TrendState],
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
        observed = _prior_trend(context, before, first.open_time, cache)
        required = _REQUIRED_TREND[pattern_type]
        evaluation = (
            _confirmed((c1, c2), at, required, observed)
            if observed is required
            else _morphologically_valid((c1, c2), at)
        )
        found.append(
            _instance(
                context,
                pattern_type,
                evaluation,
                detector_version=MULTI_CANDLE_DETECTOR_VERSION,
                parameter_version=params.version,
            )
        )

    return found


def _resolved_triple_params(context: MultiCandleContext) -> ThreeCandleParams:
    """`context.triple` with `gap_policy` filled in from the instrument's market when the caller
    left it unset (`None`) — an explicit value on `context.triple` always wins."""
    triple = context.triple
    if triple.gap_policy is None:
        triple = replace(triple, gap_policy=_gap_policy_for_market(context.instrument.market))
    return triple


def _instances_for_triple(
    context: MultiCandleContext,
    before: Sequence[Candle],
    first: Candle,
    second: Candle,
    third: Candle,
    cache: dict[datetime, TrendState],
) -> list[CandlePatternInstance]:
    c1 = CandleAnchor.from_candle(first, "FIRST")
    c2 = CandleAnchor.from_candle(second, "SECOND")
    c3 = CandleAnchor.from_candle(third, "THIRD")
    if c1.range <= 0 or c2.range <= 0 or c3.range <= 0:
        return []
    triple = _resolved_triple_params(context)
    at = third.close_time
    found: list[CandlePatternInstance] = []

    def build(pattern_type: CandlePatternType, extra: tuple[PatternEvidence, ...] = ()) -> None:
        required = _REQUIRED_TREND_TRIPLE[pattern_type]
        if required is None:
            observed = _prior_trend(context, before, first.open_time, cache)
            evaluation = _confirmed((c1, c2, c3), at, None, observed, extra)
        else:
            observed = _prior_trend(context, before, first.open_time, cache)
            evaluation = (
                _confirmed((c1, c2, c3), at, required, observed, extra)
                if observed is required
                else _morphologically_valid((c1, c2, c3), at)
            )
        found.append(
            _instance(
                context,
                pattern_type,
                evaluation,
                detector_version=THREE_CANDLE_DETECTOR_VERSION,
                parameter_version=triple.version,
            )
        )

    star = _morning_or_evening_star(c1, c2, c3, triple)
    if star is not None:
        pattern_type, gap_ev = star
        build(pattern_type, (gap_ev,) if gap_ev is not None else ())

    if _is_three_white_soldiers(c1, c2, c3, triple):
        build(_T.THREE_WHITE_SOLDIERS)
    if _is_three_black_crows(c1, c2, c3, triple):
        build(_T.THREE_BLACK_CROWS)

    harami_params = triple.harami_params()
    if is_bullish_harami(c1, c2, harami_params) and c3.close > c1.high:
        build(_T.THREE_INSIDE_UP)
    if is_bearish_harami(c1, c2, harami_params) and c3.close < c1.low:
        build(_T.THREE_INSIDE_DOWN)

    return found


def detect_multi_candle_patterns(
    context: MultiCandleContext, candles: Sequence[Candle]
) -> MultiCandleResult:
    """The two- and three-candle patterns visible at `context.observed_at`, from the candles
    closed by then. Candles that close later, and the one in progress, are ignored. Bad data
    never raises: it yields no instances and the reasons. Only a wrong request raises.

    A pure function of the whole closed series every time it is called (no incremental state),
    same principle as `detect_single_candle_patterns`.

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
        return MultiCandleResult((), (MissingDataReason.INVALID_CANDLES,), None)
    as_of = closed[-1].close_time if closed else None
    if context.data_source not in context.authorized_sources:
        return MultiCandleResult((), (MissingDataReason.SOURCE_NOT_AUTHORIZED,), as_of)
    instances: list[CandlePatternInstance] = []
    trend_cache: dict[datetime, TrendState] = {}
    for index in range(2, len(closed)):
        before = closed[: index - 2]
        instances.extend(
            _instances_for_triple(
                context, before, closed[index - 2], closed[index - 1], closed[index], trend_cache
            )
        )
    for index in range(1, len(closed)):
        before = closed[: index - 1]
        instances.extend(
            _instances_for_pair(context, before, closed[index - 1], closed[index], trend_cache)
        )
    return MultiCandleResult(tuple(instances), (), as_of)
