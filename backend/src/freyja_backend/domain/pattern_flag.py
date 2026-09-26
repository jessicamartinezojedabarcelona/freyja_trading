"""Flag and pennant detectors (POINT3-CONTINUATION-001).

Rules in ``docs/domain/detectores-de-continuacion.md``. A flag or a pennant is a **mast** (a sharp,
short move) followed by a short consolidation inside two boundaries that the price then leaves in
the direction of the mast:

* flag: the boundaries stay roughly parallel and drift a little against the mast (or none);
* pennant: the boundaries converge, a small triangle.

Both raise the hypothesis that the mast continues, and no more than that: like the triangles they
watch **both** boundaries, and the first close beyond either one is the breakout. One through the
boundary the mast points at is what the tradition expects; one through the other boundary is a
breakout against that expectation, recorded as such (the direction of the mast is kept in the
evidence), never forced into a continuation. Bull and bear figures are mirrors (`Thrust`); flag and
pennant differ only in the shape of the consolidation.

The consolidation is the same two-line channel the triangles use (`pattern_channel`), starting at
the end of the mast, which is its first contact; the mast start is the figure's first anchor and the
identity of the instance. Nothing is claimed before the fourth contact of the consolidation.
The size of the figure is judged against the mast, not against the recent range: the mast is
what has to stand out.
"""

import enum
from collections.abc import Callable, Sequence
from datetime import datetime
from decimal import Decimal

from freyja_backend.domain.chart_pattern import (
    AnchorPivot,
    BoundaryRole,
    BreakoutDirection,
    PatternEvaluation,
    PatternEvidence,
    PatternType,
    evidence,
)
from freyja_backend.domain.market_data import Candle
from freyja_backend.domain.market_structure import Pivot, PivotKind
from freyja_backend.domain.market_trend import TrendState
from freyja_backend.domain.pattern_channel import (
    Channel,
    ContinuationDetector,
    boundaries_of,
    channel_evidence,
    first_breakout,
    grow_channel,
)
from freyja_backend.domain.pattern_detection import (
    ContinuationParams,
    DetectionContext,
    Judgement,
    PatternCandidate,
    Side,
    anchor_of,
    breakout_evidence,
    index_by_open_time,
    judge,
    prior_trend_state,
    reference_range,
)

_SIX = Decimal("0.000001")
_MIN_FLAG_SWINGS = 4  # two highs and two lows in the consolidation, the mast end being the first


class Thrust(enum.StrEnum):
    """Which way the mast points. Mirror figures share nothing but this."""

    BULL = "BULL"  # a mast up: it starts at a low, ends at a high, and the price goes on up
    BEAR = "BEAR"

    @property
    def sign(self) -> int:
        return 1 if self is Thrust.BULL else -1

    @property
    def end_kind(self) -> PivotKind:
        return PivotKind.HIGH if self is Thrust.BULL else PivotKind.LOW

    @property
    def direction(self) -> BreakoutDirection:
        """The way the mast points: the breakout the tradition expects."""
        return BreakoutDirection.UP if self is Thrust.BULL else BreakoutDirection.DOWN

    @property
    def required_prior_trend(self) -> TrendState:
        return TrendState.UPTREND if self is Thrust.BULL else TrendState.DOWNTREND


class MastDetector(ContinuationDetector):
    """One detector = one figure. Subclasses say which way the mast points and whether the
    consolidation is parallel (a flag) or converging (a pennant)."""

    thrust: Thrust
    converging: bool

    def find(
        self, context: DetectionContext, closed: Sequence[Candle], swings: Sequence[Pivot]
    ) -> list[PatternCandidate]:
        index = index_by_open_time(closed)
        found: list[PatternCandidate] = []
        for position in range(len(swings) - _MIN_FLAG_SWINGS):
            candidate = self._figure(context, closed, index, swings, position)
            if candidate is not None:
                found.append(candidate)
        return found

    def accepts(
        self, fit: Channel, mast_end: Pivot, mast: Decimal, params: ContinuationParams
    ) -> bool:
        """Whether a consolidation of this size is a flag (or a pennant) after this mast."""
        sign = self.thrust.sign
        if fit.last_index - fit.first_index > params.max_flag_candles:
            return False
        if fit.height > params.flag_max_height_fraction * mast:
            return False
        if retracement(self.thrust, fit, mast_end) > params.max_retrace * mast:
            return False
        # It may not go on with the mast (that is a channel, not a pause); how far it may go against
        # the mast is what `max_retrace` already limits, through the contacts.
        if sign * (fit.upper_rise + fit.lower_rise) / 2 > params.flat_tolerance * mast:
            return False
        if self.converging:
            # A falling ceiling and a rising floor: two boundaries that both slope the same way,
            # even if they close in, are a wedge, not a pennant.
            if not fit.upper_rise < 0 < fit.lower_rise:
                return False
            return fit.gap_at_end <= (1 - params.pennant_convergence_min) * fit.height
        return abs(fit.gap_at_end - fit.height) <= params.parallel_tolerance * fit.height

    def _figure(
        self,
        context: DetectionContext,
        closed: Sequence[Candle],
        index: dict[datetime, int],
        swings: Sequence[Pivot],
        position: int,
    ) -> PatternCandidate | None:
        params, thrust = context.continuation, self.thrust
        start, end = swings[position], swings[position + 1]
        if end.kind is not thrust.end_kind:  # swings alternate: the start is the other kind
            return None
        mast = thrust.sign * (end.price - start.price)
        start_index, end_index = index[start.open_time], index[end.open_time]
        if end_index - start_index > params.mast_max_candles:
            return None
        # A mast that points the wrong way is negative, so it is never tall enough.
        reference = reference_range(closed, start_index, params.range_window_candles)
        if reference <= 0 or mast < params.mast_min_height_fraction * reference:
            return None
        channel = grow_channel(
            params,
            closed,
            index,
            swings,
            position + 1,
            accepted=lambda fit: self.accepts(fit, end, mast, params),
            min_candles=params.min_flag_candles,
            check_height=False,
        )
        if channel is None:
            return None

        judgement = self._judged(params, closed, channel)
        if judgement is None:
            return None
        last = len(closed) - 1
        items = (
            flagpole_evidence(
                thrust, channel, end, mast, reference, closed[start_index : end_index + 1]
            ),
            volume_evidence(closed, start_index, end_index, channel),
            channel_evidence(channel, params),
            self._prior_trend(context, closed, start),
            *breakout_evidence(judgement, closed),
        )
        return self.candidate(
            context,
            PatternEvaluation(
                evaluated_at=context.observed_at,
                as_of=closed[-1].close_time,
                candle_count=last - start_index + 1,
                state=judgement.state,
                anchors=(anchor_of(start, "MAST_START"), *self._flag_anchors(channel)),
                boundaries=boundaries_of(channel),
                breakout=judgement.breakout,
                invalidation_reasons=judgement.invalidation_reasons,
                evidence=items,
            ),
        )

    def _judged(
        self, params: ContinuationParams, closed: Sequence[Candle], channel: Channel
    ) -> Judgement | None:
        """Where the figure stands: the first close beyond either boundary is the breakout, in the
        direction of the mast or against it, and what came first wins, as in every channel."""

        def watch(
            side: Side, line: Callable[[datetime], Decimal], role: BoundaryRole
        ) -> Judgement | None:
            return judge(
                closed,
                side=side,
                params=params,
                start_index=channel.first_index,
                exceed_from=None,
                breakout_from=channel.last_index + 1,
                complete=True,
                forming=False,
                neckline_at=lambda candle: line(candle.close_time),
                height=channel.height,
                expires_after=channel.expires_after,
                boundary_role=role,
            )

        upward = watch(Side.BOTTOM, channel.upper, BoundaryRole.UPPER)
        downward = watch(Side.TOP, channel.lower, BoundaryRole.LOWER)
        if upward is None or downward is None:
            return None
        return first_breakout(upward, downward)

    def _flag_anchors(self, channel: Channel) -> tuple[AnchorPivot, ...]:
        """The consolidation's swings. The first one is the end of the mast, which is also the
        first contact of one boundary; the rest are numbered per boundary after it."""
        counts = {PivotKind.HIGH: 0, PivotKind.LOW: 0}
        anchors = []
        for number, pivot in enumerate(channel.window):
            counts[pivot.kind] += 1
            if number == 0:
                anchors.append(anchor_of(pivot, "MAST_END"))
                continue
            side = "UPPER" if pivot.kind is PivotKind.HIGH else "LOWER"
            anchors.append(anchor_of(pivot, f"{side}_{counts[pivot.kind]}"))
        return tuple(anchors)

    def _prior_trend(
        self, context: DetectionContext, closed: Sequence[Candle], start: Pivot
    ) -> PatternEvidence:
        """The trend before the mast began. A mast that came out of a trend the other way (a sharp
        recovery inside a downtrend, say) is still observed, with this recorded."""
        state = prior_trend_state(
            context,
            closed,
            start,
            pivot_params=context.continuation.pivot_params,
            min_history=context.continuation.min_history,
        )
        required = self.thrust.required_prior_trend
        return evidence(
            "PRIOR_TREND",
            f"trend before the mast: {state.value}; needed {required.value}",
            state=state.value,
            required=required.value,
            compatible=state is required,
        )


def retracement(thrust: Thrust, fit: Channel, mast_end: Pivot) -> Decimal:
    """How far the consolidation gave back the mast: the distance from the end of the mast to the
    contact that went furthest against it, in price (positive when it retraced)."""
    counter = fit.lows if thrust is Thrust.BULL else fit.highs
    return max(thrust.sign * (mast_end.price - pivot.price) for pivot in counter)


def flagpole_evidence(
    thrust: Thrust,
    channel: Channel,
    mast_end: Pivot,
    mast: Decimal,
    reference: Decimal,
    mast_candles: Sequence[Candle],
) -> PatternEvidence:
    drift = thrust.sign * (channel.upper_rise + channel.lower_rise) / 2
    return evidence(
        "FLAGPOLE",
        "the mast, how much of it the consolidation gave back, how tall that is and how it drifts",
        mast_direction=thrust.direction.value,
        mast_height=mast,
        mast_candles=len(mast_candles) - 1,
        mast_share_of_reference=(mast / reference).quantize(_SIX),
        reference_range=reference,
        flag_height_share=(channel.height / mast).quantize(_SIX),
        retracement_share=(retracement(thrust, channel, mast_end) / mast).quantize(_SIX),
        drift_share=(drift / mast).quantize(_SIX),
        flag_candles=channel.last_index - channel.first_index,
    )


def volume_evidence(
    closed: Sequence[Candle], start_index: int, end_index: int, channel: Channel
) -> PatternEvidence:
    """The volume of the mast and of the pause, side by side, so that whoever uses the figure can
    see whether activity fell during the pause as the classical description expects. (The
    breakout's own volume is `BREAKOUT_VOLUME`.) Informational only: it decides nothing."""
    mast = closed[start_index : end_index + 1]
    pause = closed[end_index + 1 : channel.last_index + 1]
    facts: dict[str, Decimal] = {
        "mast_mean_volume": sum((c.volume for c in mast), start=Decimal(0)) / len(mast),
        "pause_mean_volume": sum((c.volume for c in pause), start=Decimal(0)) / len(pause),
    }
    if facts["mast_mean_volume"] > 0:
        facts["pause_to_mast"] = (facts["pause_mean_volume"] / facts["mast_mean_volume"]).quantize(
            _SIX
        )
    return evidence(
        "FLAG_VOLUME",
        "mean volume of the mast and of the pause, before any breakout",
        **facts,
    )


class BullFlagDetector(MastDetector):
    pattern_type = PatternType.BULL_FLAG
    version = "bull-flag-detector-v1"
    thrust = Thrust.BULL
    converging = False


class BearFlagDetector(MastDetector):
    pattern_type = PatternType.BEAR_FLAG
    version = "bear-flag-detector-v1"
    thrust = Thrust.BEAR
    converging = False


class BullPennantDetector(MastDetector):
    pattern_type = PatternType.BULL_PENNANT
    version = "bull-pennant-detector-v1"
    thrust = Thrust.BULL
    converging = True


class BearPennantDetector(MastDetector):
    pattern_type = PatternType.BEAR_PENNANT
    version = "bear-pennant-detector-v1"
    thrust = Thrust.BEAR
    converging = True
