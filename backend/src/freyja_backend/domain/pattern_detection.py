"""Shared machinery of the reversal pattern detectors (POINT3-REVERSAL-001).

The contract lives in ``docs/domain/detectores-de-reversion.md`` (and, above it,
``docs/domain/figuras-chartistas.md`` and ``docs/domain/instancia-de-figura.md``). Each detector
is its own unit with its own rules and its own version (double top, triple bottom, head and
shoulders...). What they share here is *plumbing*, never geometry: how a detector is fed, how a
breakout after a neckline is judged, how instances are carried from one instant to the next.

Every detector is a **pure function of what was knowable at one instant**: given the candles
closed at ``observed_at`` it returns what it sees, and the same candles always give the same
answer. It reads nothing else: no clock, no database, no indicator, no candlestick pattern. It
never says what to do about a figure: a breakout can complete a figure, it never authorises a
trade, and a figure whose prior trend is not the one it needs is still *observed* (with the fact
recorded) but cannot back a signal.

Thresholds are provisional and versioned (``reversal-params-v1``): they are reasoned, not
validated (PARAMS-VALIDATION-001).
"""

import abc
import enum
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import Decimal

from freyja_backend.domain.chart_pattern import (
    AnchorPivot,
    Boundary,
    BoundaryPoint,
    BoundaryRole,
    Breakout,
    BreakoutDirection,
    InvalidationReason,
    InvalidPatternError,
    PatternEvaluation,
    PatternEvidence,
    PatternInstance,
    PatternState,
    PatternType,
    derive_pattern_instance_id,
    evidence,
    start_pattern_instance,
)
from freyja_backend.domain.market_calendar import MarketSchedule
from freyja_backend.domain.market_context import MissingDataReason, build_observable_context
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
    Pivot,
    PivotKind,
    PivotParams,
    detect_pivots,
    swing_points,
)
from freyja_backend.domain.market_trend import TrendState, classify_trend

# Bump on ANY change to a threshold or to how the parameters are read.
REVERSAL_PARAMETER_VERSION = "reversal-params-v1"

# Prices are stored with 12 decimals (NUMERIC(38,12)): a computed level is never finer than that.
_PRICE_STEP = Decimal("0.000000000001")


class InvalidDetectionRequestError(ValueError):
    """The request itself is wrong (not the data): a configuration error to fix."""


class Side(enum.StrEnum):
    """Which end of a trend a reversal figure sits at. Mirror figures share nothing but this."""

    TOP = "TOP"  # peaks: reverses an uptrend, resolves downwards
    BOTTOM = "BOTTOM"  # troughs: reverses a downtrend, resolves upwards

    @property
    def extreme_kind(self) -> PivotKind:
        return PivotKind.HIGH if self is Side.TOP else PivotKind.LOW

    @property
    def opposite_kind(self) -> PivotKind:
        return PivotKind.LOW if self is Side.TOP else PivotKind.HIGH

    @property
    def breakout_direction(self) -> BreakoutDirection:
        return BreakoutDirection.DOWN if self is Side.TOP else BreakoutDirection.UP

    @property
    def confirmed_state(self) -> PatternState:
        return PatternState.CONFIRMED_DOWN if self is Side.TOP else PatternState.CONFIRMED_UP

    @property
    def required_prior_trend(self) -> TrendState:
        return TrendState.UPTREND if self is Side.TOP else TrendState.DOWNTREND

    def signed(self, price: Decimal) -> Decimal:
        """The price as seen by a TOP figure: for a BOTTOM figure the axis is turned over, so the
        same comparisons read the same way."""
        return price if self is Side.TOP else -price

    def extreme_of(self, candle: Candle) -> Decimal:
        """The price of a candle that reaches furthest into the figure's extreme."""
        return candle.high if self is Side.TOP else candle.low


@dataclass(frozen=True, slots=True)
class ReversalParams:
    """Thresholds of the reversal detectors. Relative, so the same values read the same on any
    instrument and timeframe. Provisional: see PARAMS-VALIDATION-001."""

    version: str = REVERSAL_PARAMETER_VERSION
    pivot_params: PivotParams = DEFAULT_PIVOT_PARAMS
    # Two extremes are "comparable" when they differ by at most this fraction of the figure's
    # height (peak to trough), so the test does not depend on the price level.
    level_tolerance: Decimal = Decimal("0.15")
    # A figure must be at least this fraction of the price range of the `range_window_candles`
    # candles that end at its first pivot: smaller wiggles are noise, not a figure.
    min_height_fraction: Decimal = Decimal("0.25")
    range_window_candles: int = 100
    # A close beyond the neckline by at least this fraction of the height confirms the breakout;
    # a smaller one leaves it pending.
    breakout_margin: Decimal = Decimal("0.10")
    # A close back on the inner side of the neckline within this many candles of the first
    # close beyond it makes the breakout fail.
    failure_window_candles: int = 10
    # An unresolved figure older than this many candles (from its first pivot) is stale.
    max_age_candles: int = 150
    # Before any breakout, a close beyond the extreme by more than this fraction of the height
    # is the price going the other way: the figure is over.
    exceed_margin: Decimal = Decimal("0.15")
    # Candles the data must have (and be free of gaps over) for the figure to be judged at all.
    min_history: int = MIN_HISTORY_CANDLES
    # Head and shoulders only. The head must stand out from the higher shoulder by at least this
    # fraction of the height, or it is not a head.
    head_prominence: Decimal = Decimal("0.10")
    # Head and shoulders only. The two shoulders are comparable within this fraction of the
    # height (looser than the extremes of a double top: shoulders are rarely level).
    shoulder_tolerance: Decimal = Decimal("0.30")
    # Rounding tops and bottoms only. The closes of the whole arc must follow a parabola with at
    # least this coefficient of determination (R squared), open downwards for a top.
    arc_fit_min: Decimal = Decimal("0.85")
    # Rounding only. At least this share of the arc's closes must be within the top quarter of its
    # height: a dome dwells near its top (a parabola: half of its width), a pointed peak does not
    # (a tent: a quarter), and R squared alone cannot tell them apart.
    min_top_dwell: Decimal = Decimal("0.40")
    # Rounding only. The apex lies in the middle part of the arc: between this fraction and its
    # complement of the way from the left end to the right end.
    apex_position_band: Decimal = Decimal("0.25")
    # Rounding only. An arc spans at least / at most this many candles (left end to right end).
    min_arc_candles: int = 30
    max_arc_candles: int = 150

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise InvalidDetectionRequestError("the parameters must carry their version")
        for name in (
            "level_tolerance",
            "min_height_fraction",
            "breakout_margin",
            "exceed_margin",
            "head_prominence",
            "shoulder_tolerance",
            "arc_fit_min",
            "min_top_dwell",
            "apex_position_band",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not (Decimal(0) < value < Decimal(1)):
                raise InvalidDetectionRequestError(f"{name} must be a Decimal between 0 and 1")
        for name in (
            "range_window_candles",
            "failure_window_candles",
            "max_age_candles",
            "min_history",
            "min_arc_candles",
            "max_arc_candles",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise InvalidDetectionRequestError(f"{name} must be an integer of at least 1")
        if self.min_arc_candles > self.max_arc_candles:
            raise InvalidDetectionRequestError("an arc cannot be required longer than it may be")


DEFAULT_REVERSAL_PARAMS = ReversalParams()


@dataclass(frozen=True, slots=True)
class DetectionContext:
    """What a detector needs to know about the series it reads, at one instant."""

    instrument_id: str
    instrument: InstrumentRef
    schedule: MarketSchedule
    data_source: str
    authorized_sources: frozenset[str]
    timeframe: Timeframe
    observed_at: datetime
    params: ReversalParams = DEFAULT_REVERSAL_PARAMS
    publication_grace: timedelta = DEFAULT_PUBLICATION_GRACE
    # Memory of prior-trend classifications, keyed by (side, first pivot). It only saves work:
    # each entry is a pure function of the candles before that pivot, so it never changes an answer.
    _prior_trends: dict[tuple[Side, datetime], TrendState] = field(
        default_factory=dict, compare=False, repr=False
    )

    def at(self, observed_at: datetime) -> "DetectionContext":
        return replace(self, observed_at=observed_at)


@dataclass(frozen=True, slots=True)
class PatternCandidate:
    """A figure a detector sees at one instant, ready to become or continue an instance."""

    pattern_type: PatternType
    detector_version: str
    parameter_version: str
    instrument_id: str
    data_source: str
    timeframe: Timeframe
    evaluation: PatternEvaluation

    @property
    def pattern_instance_id(self) -> uuid.UUID:
        first = self.evaluation.anchors[0]
        return derive_pattern_instance_id(
            pattern_type=self.pattern_type,
            instrument_id=self.instrument_id,
            data_source=self.data_source,
            timeframe=self.timeframe,
            started_at=first.open_time,
            first_anchor_kind=first.kind,
            detector_version=self.detector_version,
            parameter_version=self.parameter_version,
        )


@dataclass(frozen=True, slots=True)
class DetectorResult:
    """What one detector saw at one instant. If the data was not fit to judge, there are no
    candidates and the reasons say why: a figure is never guessed from unfit data."""

    candidates: tuple[PatternCandidate, ...]
    unfit_reasons: tuple[MissingDataReason, ...]
    # Close of the newest closed candle read; None if there was none.
    as_of: datetime | None


class PatternDetector(abc.ABC):
    """One detector = one figure = one version. Subclasses hold only that figure's rules."""

    pattern_type: PatternType
    version: str
    side: Side

    def detect(self, context: DetectionContext, candles: Sequence[Candle]) -> DetectorResult:
        """The figures of this kind visible at `context.observed_at`, from the candles closed by
        then. Candles that close later, and the one in progress, are ignored. Bad data never
        raises: it yields no candidates and the reasons. Only a wrong request raises."""
        params = context.params
        _require_utc(context.observed_at, "observed_at")  # a wrong request, not bad data
        try:
            closed = assess_candles(
                candles,
                timeframe=context.timeframe,
                now=context.observed_at,
                publication_grace=context.publication_grace,
            ).candles
        except InvalidMarketDataError:
            return DetectorResult((), (MissingDataReason.INVALID_CANDLES,), None)
        observable = build_observable_context(
            instrument_id=context.instrument_id,
            instrument=context.instrument,
            schedule=context.schedule,
            signal_timeframe=context.timeframe,
            context_timeframe=context.timeframe,
            observed_at=context.observed_at,
            data_source=context.data_source,
            authorized_sources=context.authorized_sources,
            candles=candles,
            min_history=params.min_history,
            publication_grace=context.publication_grace,
        )
        as_of = closed[-1].close_time if closed else None
        if not observable.is_sufficient:
            return DetectorResult((), observable.missing_data_reasons, as_of)
        swings = swing_points(
            detect_pivots(
                closed,
                timeframe=context.timeframe,
                observed_at=context.observed_at,
                params=params.pivot_params,
            ).confirmed
        )
        found = self.find(context, tuple(closed), swings)
        return DetectorResult(tuple(found), (), as_of)

    @abc.abstractmethod
    def find(
        self, context: DetectionContext, closed: Sequence[Candle], swings: Sequence[Pivot]
    ) -> list[PatternCandidate]:
        """This figure's own geometry over the swing points and candles closed by the instant."""

    def candidate(
        self, context: DetectionContext, evaluation: PatternEvaluation
    ) -> PatternCandidate:
        return PatternCandidate(
            self.pattern_type,
            self.version,
            context.params.version,
            context.instrument_id,
            context.data_source,
            context.timeframe,
            evaluation,
        )


# -- helpers the detectors share ------------------------------------------------------------


def index_by_open_time(closed: Sequence[Candle]) -> dict[datetime, int]:
    return {candle.open_time: index for index, candle in enumerate(closed)}


def reference_range(closed: Sequence[Candle], end_index: int, window: int) -> Decimal:
    """Price range of the `window` candles ending at `end_index`: known when the figure starts
    and never changed by what comes after, so its size is judged against a fixed yardstick."""
    lo = max(0, end_index - window + 1)
    span = closed[lo : end_index + 1]
    return max(c.high for c in span) - min(c.low for c in span)


def anchor_of(pivot: Pivot, label: str) -> AnchorPivot:
    return AnchorPivot.from_pivot(pivot, label)


def line_through(
    first_time: datetime, first_price: Decimal, second_time: datetime, second_price: Decimal
) -> Callable[[datetime], Decimal]:
    """The straight line through two points, as a function of time: `price(t)` is the line's price
    at instant `t`, also before the first point and after the second. `Decimal` arithmetic, never a
    float, multiplying before dividing and rounded to the 12 decimals prices are stored with; a
    line needs two different instants."""
    span = Decimal((second_time - first_time).total_seconds())
    if span <= 0:
        raise InvalidDetectionRequestError("a line is drawn through two different instants")
    rise = second_price - first_price

    def price(at: datetime) -> Decimal:
        elapsed = Decimal((at - first_time).total_seconds())
        return (first_price + rise * elapsed / span).quantize(_PRICE_STEP)

    return price


def prior_trend_evidence(
    context: DetectionContext, closed: Sequence[Candle], side: Side, first: Pivot
) -> PatternEvidence:
    """The trend right before the figure began, by the POINT2 classifier, at the instant of its
    first pivot. A figure whose prior trend is not the one it reverses is **observed**, with this
    fact recorded, but cannot back a signal: it is never dropped here and never assumed."""
    key = (side, first.open_time)
    state = context._prior_trends.get(key)
    if state is None:
        state = classify_trend(
            instrument_id=context.instrument_id,
            instrument=context.instrument,
            schedule=context.schedule,
            timeframe=context.timeframe,
            observed_at=first.open_time,
            data_source=context.data_source,
            authorized_sources=context.authorized_sources,
            candles=closed,
            pivot_params=context.params.pivot_params,
            min_history=context.params.min_history,
            publication_grace=context.publication_grace,
        ).state
        context._prior_trends[key] = state
    compatible = state is side.required_prior_trend
    return evidence(
        "PRIOR_TREND",
        f"trend before the figure: {state.value}; needed {side.required_prior_trend.value}",
        state=state.value,
        required=side.required_prior_trend.value,
        compatible=compatible,
    )


@dataclass(frozen=True, slots=True)
class Judgement:
    state: PatternState
    breakout: Breakout | None = None
    invalidation_reasons: tuple[InvalidationReason, ...] = ()
    # Candles (indices) of the first close beyond the neckline, and of its confirmation or
    # failure, kept as evidence of how the breakout unfolded.
    first_beyond_index: int | None = None
    resolved_index: int | None = None


def judge(
    closed: Sequence[Candle],
    *,
    side: Side,
    params: ReversalParams,
    start_index: int,
    exceed_from: int,
    breakout_from: int,
    complete: bool,
    forming: bool,
    neckline_at: Callable[[Candle], Decimal],
    height: Decimal,
    extreme_price: Decimal,
    boundary_role: BoundaryRole = BoundaryRole.NECKLINE,
) -> Judgement | None:
    """Where a figure stands, from the candles closed by the instant. None: it is not one (yet).

    `start_index` is the candle of the first pivot; the price is checked for going the wrong way
    from `exceed_from`; the neckline is watched from `breakout_from`. All of it reads only closes:
    a wick through a level is not a breakout. Order matters: what happened first wins (a figure
    already broken out of is not later "invalidated" by what the price does afterwards).
    """
    last = len(closed) - 1
    signed = side.signed
    margin = params.breakout_margin * height

    limit = signed(extreme_price) + params.exceed_margin * height
    exceed = next(
        (k for k in range(exceed_from, last + 1) if signed(closed[k].close) > limit), None
    )

    def depth(candle: Candle) -> Decimal:
        """How far the close is beyond the neckline (negative: still inside)."""
        return signed(neckline_at(candle)) - signed(candle.close)

    def beyond(candle: Candle) -> bool:
        return depth(candle) > 0  # strictly: a close on the level is not through it

    def confirms(candle: Candle) -> bool:
        return depth(candle) >= margin  # at least the margin, as the contract says

    first = None
    if complete:
        first = next((k for k in range(breakout_from, last + 1) if beyond(closed[k])), None)

    stale = (last - start_index) > params.max_age_candles

    if exceed is not None and (first is None or exceed < first):
        return Judgement(
            PatternState.INVALIDATED,
            invalidation_reasons=(InvalidationReason.CLOSED_THROUGH_AGAINST_BIAS,),
        )
    if first is not None:
        confirmed = first if confirms(closed[first]) else None
        failed = None
        for k in range(first + 1, last + 1):
            if (k - first) <= params.failure_window_candles and not beyond(closed[k]):
                failed = k
                break
            if confirmed is None and confirms(closed[k]):
                confirmed = k
        if failed is not None:
            was_confirmed = confirmed is not None and confirmed < failed
            shown = confirmed if was_confirmed and confirmed is not None else first
            return Judgement(
                PatternState.FAILED_BREAKOUT,
                _breakout(closed[shown], side, was_confirmed, boundary_role),
                first_beyond_index=first,
                resolved_index=failed,
            )
        if confirmed is not None:
            return Judgement(
                side.confirmed_state,
                _breakout(closed[confirmed], side, True, boundary_role),
                first_beyond_index=first,
                resolved_index=confirmed,
            )
        if stale:
            return Judgement(
                PatternState.INVALIDATED, invalidation_reasons=(InvalidationReason.TOO_LONG,)
            )
        return Judgement(
            PatternState.BREAKOUT_PENDING_CONFIRMATION,
            _breakout(closed[first], side, False, boundary_role),
            first_beyond_index=first,
        )
    if stale:
        return Judgement(
            PatternState.INVALIDATED, invalidation_reasons=(InvalidationReason.TOO_LONG,)
        )
    if complete:
        return Judgement(PatternState.GEOMETRICALLY_VALID)
    if forming:
        return Judgement(PatternState.FORMING)
    return None


def _breakout(candle: Candle, side: Side, confirmed: bool, role: BoundaryRole) -> Breakout:
    return Breakout(
        direction=side.breakout_direction,
        boundary=role,
        candle_open_time=candle.open_time,
        candle_close_time=candle.close_time,
        close_price=candle.close,
        confirmed=confirmed,
    )


def breakout_evidence(
    judgement: Judgement, closed: Sequence[Candle]
) -> tuple[PatternEvidence, ...]:
    if judgement.first_beyond_index is None:
        return ()
    last = len(closed) - 1
    facts: dict[str, int | bool] = {
        "candles_since_first_close_beyond": last - judgement.first_beyond_index,
        "resolved": judgement.resolved_index is not None,
    }
    if judgement.resolved_index is not None:
        facts["candles_to_resolution"] = judgement.resolved_index - judgement.first_beyond_index
    return (
        evidence(
            "BREAKOUT_SCAN",
            "how the price behaved after its first close beyond the neckline",
            **facts,
        ),
    )


def horizontal_neckline(level: Decimal, from_time: datetime, to_time: datetime) -> Boundary | None:
    if to_time <= from_time:
        return None
    return Boundary(
        BoundaryRole.NECKLINE,
        (BoundaryPoint(from_time, level), BoundaryPoint(to_time, level)),
        (from_time,),
    )


# -- carrying instances from one instant to the next --------------------------------------------


def _same_content(before: PatternEvaluation, after: PatternEvaluation) -> bool:
    return (
        before.state is after.state
        and before.anchors == after.anchors
        and before.breakout == after.breakout
        and before.invalidation_reasons == after.invalidation_reasons
        and before.insufficient_data_reasons == after.insufficient_data_reasons
    )


def _closing_evaluation(
    instance: PatternInstance,
    *,
    observed_at: datetime,
    as_of: datetime | None,
    state: PatternState,
    invalidation_reasons: tuple[InvalidationReason, ...] = (),
    insufficient_data_reasons: tuple[MissingDataReason, ...] = (),
) -> PatternEvaluation:
    latest = instance.latest
    return PatternEvaluation(
        evaluated_at=observed_at,
        as_of=as_of if as_of is not None else latest.as_of,
        candle_count=latest.candle_count,
        state=state,
        anchors=latest.anchors,
        boundaries=latest.boundaries,
        breakout=None,
        invalidation_reasons=invalidation_reasons,
        insufficient_data_reasons=insufficient_data_reasons,
        evidence=latest.evidence,
    )


def update_instances(
    previous: Sequence[PatternInstance],
    result: DetectorResult,
    *,
    observed_at: datetime,
) -> tuple[PatternInstance, ...]:
    """The instances after one more instant: what was already known, carried forward.

    A new figure starts an instance (unless it is already invalidated, which was never a figure);
    a known one advances when something about it changed; one whose anchors are no longer the
    ones it was built on is invalidated (`SUPERSEDED`), never rewritten; one the detector no
    longer sees is invalidated (`GEOMETRY_BROKEN`) unless its breakout was already confirmed; and
    when the data is unfit every figure still open is marked `INSUFFICIENT_DATA`. A finished
    figure is never touched again.
    """
    instances: dict[uuid.UUID, PatternInstance] = {
        instance.pattern_instance_id: instance for instance in previous
    }
    seen: set[uuid.UUID] = set()

    for candidate in result.candidates:
        identity = candidate.pattern_instance_id
        seen.add(identity)
        known = instances.get(identity)
        evaluation = candidate.evaluation
        if known is None:
            if evaluation.state is PatternState.INVALIDATED:
                continue
            instances[identity] = start_pattern_instance(
                pattern_type=candidate.pattern_type,
                instrument_id=candidate.instrument_id,
                data_source=candidate.data_source,
                timeframe=candidate.timeframe,
                detector_version=candidate.detector_version,
                parameter_version=candidate.parameter_version,
                first_evaluation=evaluation,
            )
        elif known.is_terminal or _same_content(known.latest, evaluation):
            continue
        else:
            try:
                instances[identity] = known.advance(evaluation)
            except InvalidPatternError:
                instances[identity] = known.advance(
                    _closing_evaluation(
                        known,
                        observed_at=observed_at,
                        as_of=result.as_of,
                        state=PatternState.INVALIDATED,
                        invalidation_reasons=(InvalidationReason.SUPERSEDED,),
                    )
                )

    for identity, known in list(instances.items()):
        if identity in seen or known.is_terminal:
            continue
        if result.unfit_reasons:
            if known.state is PatternState.INSUFFICIENT_DATA and (
                known.latest.insufficient_data_reasons == result.unfit_reasons
            ):
                continue
            instances[identity] = known.advance(
                _closing_evaluation(
                    known,
                    observed_at=observed_at,
                    as_of=result.as_of,
                    state=PatternState.INSUFFICIENT_DATA,
                    insufficient_data_reasons=result.unfit_reasons,
                )
            )
        elif known.state in (PatternState.CONFIRMED_UP, PatternState.CONFIRMED_DOWN):
            continue  # a confirmed figure stays as it was confirmed
        else:
            instances[identity] = known.advance(
                _closing_evaluation(
                    known,
                    observed_at=observed_at,
                    as_of=result.as_of,
                    state=PatternState.INVALIDATED,
                    invalidation_reasons=(InvalidationReason.GEOMETRY_BROKEN,),
                )
            )
    return tuple(
        sorted(instances.values(), key=lambda i: (i.started_at, str(i.pattern_instance_id)))
    )


def replay_detector(
    detector: PatternDetector,
    context: DetectionContext,
    candles: Sequence[Candle],
    *,
    from_index: int | None = None,
) -> tuple[PatternInstance, ...]:
    """The instances a detector would have built by watching the series close candle by candle,
    up to `context.observed_at`. At each instant it sees only the candles closed by then, so
    the result at the end is what a live detector would hold, and it is reproducible."""
    ordered = sorted(
        (c for c in candles if c.close_time <= context.observed_at), key=lambda c: c.open_time
    )
    start = max(0, context.params.min_history - 1) if from_index is None else from_index
    instances: tuple[PatternInstance, ...] = ()
    for index in range(start, len(ordered)):
        instant = ordered[index].close_time
        at = context.at(instant)
        result = detector.detect(at, ordered[: index + 1])
        instances = update_instances(instances, result, observed_at=instant)
    return instances
