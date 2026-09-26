"""Diamond detector (POINT3-EXPANSION-001, third part).

Contract in section 10 of ``docs/domain/detectores-de-expansion.md``. A diamond is two connected
phases: the price first **expands** (higher highs, lower lows) and then **contracts** (lower highs,
higher lows), and the widest point is the transition. Its six swings, in order:

* starting with a high: high 1, low 1, **high 2 (top vertex)**, **low 2 (bottom vertex)**,
  high 3, low 3;
* starting with a low: low 1, high 1, **low 2 (bottom vertex)**, **high 2 (top vertex)**,
  low 3, high 3.

The two vertices are consecutive swings: a choice of ``diamond-params-v1``, not a law of the figure
(a diamond whose highs turn and whose lows turn at different swings is left out). Each phase is a
two-boundary channel (`pattern_channel`): the expansion runs from the first swing to the later
vertex, the contraction from the earlier vertex to the last swing, and they share the vertices.

The geometry is **frozen** when the diamond is completed: for each first anchor the diamond is the
shortest valid window, and what comes later (a wick beyond a boundary, a swing beyond a vertex, one
more contact) is evidence, never a new anchor and never a boundary that moves. The price leaves a
diamond through the two boundaries of the contraction; the first **close** beyond either one is the
breakout, recorded with its real direction, whatever the context before was.

What Freyja **knew** is kept apart from what **happened**: a breakout is ``LIVE`` only if its candle
opened when Freyja already knew the diamond (`known_at`); one that opened after the diamond existed
in the market but before Freyja had the data is ``AFTER_MARKET_FORMATION``, and one that opened
before it existed is ``RETROSPECTIVE``. Only ``LIVE`` can be the basis of anything operable.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from freyja_backend.domain.chart_pattern import (
    BoundaryRole,
    PatternEvaluation,
    PatternEvidence,
    PatternType,
    evidence,
)
from freyja_backend.domain.market_data import Candle
from freyja_backend.domain.market_structure import Pivot, PivotKind, PivotParams
from freyja_backend.domain.pattern_channel import (
    Channel,
    boundaries_of,
    falling,
    first_breakout,
    fit_channel,
    rising,
    strictly_higher,
    strictly_lower,
)
from freyja_backend.domain.pattern_detection import (
    ContinuationParams,
    DetectionContext,
    DetectorResult,
    DiamondParams,
    Judgement,
    PatternCandidate,
    PatternDetector,
    Side,
    anchor_of,
    breakout_evidence,
    index_by_open_time,
    judge,
    prior_trend_state,
    reference_range,
)

_MIN_SWINGS = 6
_SIX = Decimal("0.000001")

LIVE = "LIVE"
AFTER_MARKET_FORMATION = "AFTER_MARKET_FORMATION"
RETROSPECTIVE = "RETROSPECTIVE"


@dataclass(frozen=True, slots=True)
class DiamondShape:
    """A diamond as measured: its two phases, the vertices they share, what it was judged by."""

    window: tuple[Pivot, ...]
    expansion: Channel
    contraction: Channel
    top: Pivot
    bottom: Pivot
    widest_width: Decimal
    reference: Decimal


def provenance_of(opened: datetime, formed_at: datetime, known_at: datetime | None) -> str:
    """Whether a candle that opened at `opened` could have been the one that revealed the exit of
    a diamond, from what Freyja knew when it opened. Without `known_at` (no arrival times) it can
    never be said to be live."""
    if known_at is not None and opened >= known_at:
        return LIVE
    if opened >= formed_at:
        return AFTER_MARKET_FORMATION
    return RETROSPECTIVE


def phase_accepts(fit: Channel, params: ContinuationParams, *, expanding: bool) -> bool:
    """Whether a channel is one phase of a diamond. The expansion: the upper boundary rises and
    the lower one falls (each at least `slope_min` of the phase's height) through strictly higher
    highs and strictly lower lows. The contraction: the same the other way round."""
    if expanding:
        return (
            rising(fit.upper_rise, fit.height, params)
            and falling(fit.lower_rise, fit.height, params)
            and strictly_higher(fit.highs)
            and strictly_lower(fit.lows)
        )
    return (
        falling(fit.upper_rise, fit.height, params)
        and rising(fit.lower_rise, fit.height, params)
        and strictly_lower(fit.highs)
        and strictly_higher(fit.lows)
    )


class DiamondDetector(PatternDetector):
    pattern_type = PatternType.DIAMOND
    version = "diamond-detector-v1"

    def parameter_version(self, context: DetectionContext) -> str:
        return context.diamond.version

    def pivot_params(self, context: DetectionContext) -> PivotParams:
        return context.diamond.pivot_params

    def min_history(self, context: DetectionContext) -> int:
        return context.diamond.min_history

    def detect(self, context: DetectionContext, candles: Sequence[Candle]) -> DetectorResult:
        """With arrival times, only the candles Freyja had received by `observed_at` are read: a
        candle that arrives late leaves a hole (the data is not fit) until it does."""
        received = context.received_at
        if received is not None:
            candles = [
                c
                for c in candles
                if (arrived := received.get(c.open_time)) is not None
                and arrived <= context.observed_at
            ]
        return super().detect(context, candles)

    def find(
        self, context: DetectionContext, closed: Sequence[Candle], swings: Sequence[Pivot]
    ) -> list[PatternCandidate]:
        params = context.diamond
        channel_params = params.channel_params()
        index = index_by_open_time(closed)
        found: list[PatternCandidate] = []
        covered_until = -1  # position of the last swing of the longest diamond found so far
        for start in range(len(swings) - _MIN_SWINGS + 1):
            shape = self._shape(params, channel_params, closed, index, swings, start)
            if shape is None:
                continue
            end = start + len(shape.window) - 1
            if end <= covered_until:
                continue  # a piece of a diamond that began earlier: the same figure, not another
            covered_until = end
            candidate = self._figure(context, closed, swings, shape)
            if candidate is not None:
                found.append(candidate)
        return found

    def _shape(
        self,
        params: DiamondParams,
        channel_params: ContinuationParams,
        closed: Sequence[Candle],
        index: dict[datetime, int],
        swings: Sequence[Pivot],
        start: int,
    ) -> DiamondShape | None:
        """The shortest valid diamond that begins at swing `start`, if any. The vertices are the
        swings `t` and `t + 1`; the expansion is everything up to the later one, the contraction the
        two swings after the vertices."""
        for transition in range(start + 2, len(swings) - 3):
            window = tuple(swings[start : transition + 4])
            expansion = self._phase(
                channel_params, closed, index, swings[start : transition + 2], expanding=True
            )
            if expansion is None:
                continue
            contraction = self._phase(
                channel_params, closed, index, swings[transition : transition + 4], expanding=False
            )
            if contraction is None:
                continue
            first, second = swings[transition], swings[transition + 1]
            top, bottom = (first, second) if first.kind is PivotKind.HIGH else (second, first)
            widest = top.price - bottom.price
            reference = reference_range(
                closed, index[window[0].open_time], params.range_window_candles
            )
            if reference <= 0 or widest < params.min_height_fraction * reference:
                continue
            return DiamondShape(window, expansion, contraction, top, bottom, widest, reference)
        return None

    @staticmethod
    def _phase(
        params: ContinuationParams,
        closed: Sequence[Candle],
        index: dict[datetime, int],
        window: Sequence[Pivot],
        *,
        expanding: bool,
    ) -> Channel | None:
        """One phase as a channel, if its slopes and its order of contacts are its direction's."""
        fit = fit_channel(params, closed, index, window, check_height=False)
        if fit is None or not phase_accepts(fit, params, expanding=expanding):
            return None
        return fit

    def _figure(
        self,
        context: DetectionContext,
        closed: Sequence[Candle],
        swings: Sequence[Pivot],
        shape: DiamondShape,
    ) -> PatternCandidate | None:
        params = context.diamond
        exit_ = shape.contraction
        last = len(closed) - 1
        upward = judge(
            closed,
            side=Side.BOTTOM,
            params=params,
            start_index=shape.expansion.first_index,
            exceed_from=None,
            breakout_from=exit_.last_index + 1,
            complete=True,
            forming=False,
            neckline_at=lambda candle: exit_.upper(candle.close_time),
            height=exit_.height,
            expires_after=exit_.expires_after,
            boundary_role=BoundaryRole.UPPER,
        )
        downward = judge(
            closed,
            side=Side.TOP,
            params=params,
            start_index=shape.expansion.first_index,
            exceed_from=None,
            breakout_from=exit_.last_index + 1,
            complete=True,
            forming=False,
            neckline_at=lambda candle: exit_.lower(candle.close_time),
            height=exit_.height,
            expires_after=exit_.expires_after,
            boundary_role=BoundaryRole.LOWER,
        )
        if upward is None or downward is None:
            return None
        judgement = first_breakout(upward, downward)

        anchors = []
        upper_count = lower_count = 0
        for pivot in shape.window:
            if pivot.kind is PivotKind.HIGH:
                upper_count += 1
                anchors.append(anchor_of(pivot, f"UPPER_{upper_count}"))
            else:
                lower_count += 1
                anchors.append(anchor_of(pivot, f"LOWER_{lower_count}"))
        items: list[PatternEvidence | None] = [
            self._phases(context, closed, shape),
            self._timing(context, closed, shape, judgement),
            _prior_trend(context, closed, shape.window[0]),
            *breakout_evidence(judgement, closed),
            self._wicks(closed, swings, shape, judgement),
            self._additional_contacts(params, closed, swings, shape),
        ]
        return self.candidate(
            context,
            PatternEvaluation(
                evaluated_at=context.observed_at,
                as_of=closed[-1].close_time,
                candle_count=last - shape.expansion.first_index + 1,
                state=judgement.state,
                anchors=tuple(anchors),
                boundaries=(*boundaries_of(shape.expansion), *boundaries_of(shape.contraction)),
                breakout=judgement.breakout,
                invalidation_reasons=judgement.invalidation_reasons,
                evidence=tuple(item for item in items if item is not None),
            ),
        )

    def _phases(
        self, context: DetectionContext, closed: Sequence[Candle], shape: DiamondShape
    ) -> PatternEvidence:
        params = context.diamond
        expansion, contraction = shape.expansion, shape.contraction
        broadening = (
            len(expansion.window) >= 5
            and fit_channel(
                params.channel_params(),
                closed,
                index_by_open_time(closed),
                expansion.window,
                check_height=True,
            )
            is not None
        )
        return evidence(
            "DIAMOND_PHASES",
            "the two phases, the vertices where they meet and the measures each rule reads",
            bottom_vertex_price=shape.bottom.price,
            bottom_vertex_time=shape.bottom.open_time.isoformat(),
            contraction_candles=contraction.last_index - contraction.first_index,
            contraction_height=contraction.height,
            contraction_lower_rise=contraction.lower_rise,
            contraction_swings=len(contraction.window),
            contraction_upper_rise=contraction.upper_rise,
            expansion_candles=expansion.last_index - expansion.first_index,
            expansion_height=expansion.height,
            expansion_lower_rise=expansion.lower_rise,
            expansion_phase_is_broadening=broadening,
            expansion_swings=len(expansion.window),
            expansion_upper_rise=expansion.upper_rise,
            reference_range=shape.reference,
            top_vertex_price=shape.top.price,
            top_vertex_time=shape.top.open_time.isoformat(),
            widest_width=shape.widest_width,
        )

    def _timing(
        self,
        context: DetectionContext,
        closed: Sequence[Candle],
        shape: DiamondShape,
        judgement: Judgement,
    ) -> PatternEvidence:
        """What happened (market times), when Freyja got it (arrival times) and when Freyja could
        first know the diamond, kept apart; and, with a breakout, where it stands (`provenance`)."""
        received = context.received_at
        formed_at = max(p.confirmed_at for p in shape.window if p.confirmed_at is not None)
        known_at = _known_at(closed, received, shape, formed_at)
        facts: dict[str, str | bool] = {
            "apex_passed": shape.contraction.expires_after is not None,
            "market_formed_at": formed_at.isoformat(),
            "receipts_available": received is not None,
        }
        if known_at is not None:
            facts["known_at"] = known_at.isoformat()
        first = judgement.first_beyond_index
        if first is not None:
            candle = closed[first]
            facts["breakout_open_time"] = candle.open_time.isoformat()
            facts["breakout_close_time"] = candle.close_time.isoformat()
            facts["provenance"] = provenance_of(candle.open_time, formed_at, known_at)
            arrival = None if received is None else received.get(candle.open_time)
            if arrival is not None:
                facts["breakout_received_at"] = arrival.isoformat()
            breakout = judgement.breakout
            if breakout is not None and breakout.confirmed:
                facts["confirmation_close_time"] = breakout.candle_close_time.isoformat()
                confirming = None if received is None else received.get(breakout.candle_open_time)
                if confirming is not None:
                    facts["confirmation_received_at"] = confirming.isoformat()
        return evidence(
            "DIAMOND_TIMING",
            "market time, arrival time and the moment the diamond was known, kept apart",
            **facts,
        )

    def _wicks(
        self,
        closed: Sequence[Candle],
        swings: Sequence[Pivot],
        shape: DiamondShape,
        judgement: Judgement,
    ) -> PatternEvidence | None:
        """Facts after the diamond was formed that are not a breakout: a wick beyond an exit
        boundary with the close back inside, and a swing beyond a vertex. Evidence only."""
        exit_ = shape.contraction
        first = judgement.first_beyond_index
        stop = len(closed) - 1 if first is None else first - 1
        if exit_.expires_after is not None:
            stop = min(stop, exit_.expires_after)
        count = 0
        first_time: datetime | None = None
        last_time: datetime | None = None
        deepest = Decimal(0)
        side = ""
        for k in range(exit_.last_index + 1, stop + 1):
            candle = closed[k]
            above = candle.high - exit_.upper(candle.close_time)
            below = exit_.lower(candle.close_time) - candle.low
            depth = max(above, below)
            if depth <= 0:
                continue
            count += 1
            first_time = first_time or candle.open_time
            last_time = candle.open_time
            if depth > deepest:
                deepest = depth
                side = "UPPER" if above >= below else "LOWER"
        last_anchor = shape.window[-1].open_time
        beyond = [
            p
            for p in swings
            if p.open_time > last_anchor
            and (
                (p.kind is PivotKind.HIGH and p.price > shape.top.price)
                or (p.kind is PivotKind.LOW and p.price < shape.bottom.price)
            )
        ]
        if not count and not beyond:
            return None
        facts: dict[str, int | str | Decimal] = {
            "beyond_vertex_swings": len(beyond),
            "wick_candles": count,
        }
        if count and first_time is not None and last_time is not None:
            facts["deepest_side"] = side
            facts["deepest_wick_fraction"] = (deepest / exit_.height).quantize(_SIX)
            facts["first_wick_open_time"] = first_time.isoformat()
            facts["last_wick_open_time"] = last_time.isoformat()
        return evidence(
            "WICK_PENETRATIONS",
            "wicks beyond an exit boundary with the close back inside, and swings beyond a vertex: "
            "facts only, no breakout and no change to the recorded geometry",
            **facts,
        )

    def _additional_contacts(
        self,
        params: DiamondParams,
        closed: Sequence[Candle],
        swings: Sequence[Pivot],
        shape: DiamondShape,
    ) -> PatternEvidence | None:
        """Swings after the diamond was formed that go on contracting and touch an exit boundary
        (within the contact tolerance of the contraction's height), with every close since the last
        anchor still inside. Evidence only: they are not anchors and no boundary moves."""
        exit_ = shape.contraction
        index = index_by_open_time(closed)
        last_anchor = shape.window[-1]
        after = index[last_anchor.open_time] + 1
        tolerance = params.contact_tolerance * exit_.height
        previous_high = exit_.highs[-1].price
        previous_low = exit_.lows[-1].price
        count = 0
        latest: Pivot | None = None
        for pivot in swings:
            at = index.get(pivot.open_time)
            if pivot.open_time <= last_anchor.open_time or at is None:
                continue
            if any(
                candle.close > exit_.upper(candle.close_time)
                or candle.close < exit_.lower(candle.close_time)
                for candle in closed[after : at + 1]
            ):
                continue
            if pivot.kind is PivotKind.HIGH:
                touches = abs(pivot.price - exit_.upper(pivot.open_time)) <= tolerance
                follows = pivot.price < previous_high
            else:
                touches = abs(pivot.price - exit_.lower(pivot.open_time)) <= tolerance
                follows = pivot.price > previous_low
            if not (touches and follows):
                continue
            count += 1
            latest = pivot
            if pivot.kind is PivotKind.HIGH:
                previous_high = pivot.price
            else:
                previous_low = pivot.price
        if latest is None:
            return None
        return evidence(
            "ADDITIONAL_CONTACTS",
            "swings that went on contracting and touched an exit boundary after the diamond was "
            "formed: evidence only, not anchors, and the boundaries do not move",
            additional_contacts=count,
            latest_contact_price=latest.price,
            latest_contact_side="UPPER" if latest.kind is PivotKind.HIGH else "LOWER",
            latest_contact_time=latest.open_time.isoformat(),
        )


def _known_at(
    closed: Sequence[Candle],
    received: Mapping[datetime, datetime] | None,
    shape: DiamondShape,
    formed_at: datetime,
) -> datetime | None:
    """The last arrival among the candles the figure depends on: from the one of its first anchor to
    the one that confirms its last pivot (the closes between contacts decide it is valid too)."""
    if received is None:
        return None
    first = next(k for k, c in enumerate(closed) if c.open_time == shape.window[0].open_time)
    confirming = next((k for k, c in enumerate(closed) if c.close_time == formed_at), None)
    if confirming is None:
        return None
    arrivals = [received.get(c.open_time) for c in closed[first : confirming + 1]]
    if any(arrival is None for arrival in arrivals):
        return None
    return max(arrival for arrival in arrivals if arrival is not None)


def _prior_trend(
    context: DetectionContext, closed: Sequence[Candle], first: Pivot
) -> PatternEvidence:
    state = prior_trend_state(
        context,
        closed,
        first,
        pivot_params=context.diamond.pivot_params,
        min_history=context.diamond.min_history,
    )
    return evidence("PRIOR_TREND", f"trend before the figure: {state.value}", state=state.value)
