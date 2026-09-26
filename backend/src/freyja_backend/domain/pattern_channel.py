"""Triangle and rectangle detectors (POINT3-CONTINUATION-001).

Rules in ``docs/domain/detectores-de-continuacion.md``. These four figures are the same kind of
thing seen from different slopes: the price bounces between an **upper** and a **lower** boundary,
each a straight line through swing highs (or swing lows) that touch it, and what tells the figures
apart is only where each line goes:

* rectangle: both boundaries flat;
* ascending triangle: a flat upper boundary and a rising lower one;
* descending triangle: a flat lower boundary and a falling upper one;
* symmetrical triangle: a falling upper boundary and a rising lower one.

Unlike a reversal figure, the price may leave a channel in **either** direction: the detector
watches both boundaries and the first close beyond either one is the breakout. It does not
anticipate one: the figure's traditional bias is recorded by the catalogue, the direction that
actually happened is recorded by the breakout, and the trend before the figure is kept as context
(``PRIOR_TREND``) without deciding anything.

A channel is a run of consecutive swing points that holds at least two highs and two lows, grown
one swing at a time for as long as it stays a valid figure of its kind; the growth stops at the
first swing that does not fit (usually because the price has left the channel), and what was
found stays as it was. Nothing is claimed before the fourth contact: there is no *forming* state.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from freyja_backend.domain.chart_pattern import (
    Boundary,
    BoundaryPoint,
    BoundaryRole,
    PatternEvaluation,
    PatternEvidence,
    PatternType,
    evidence,
)
from freyja_backend.domain.market_data import Candle
from freyja_backend.domain.market_structure import Pivot, PivotKind, PivotParams
from freyja_backend.domain.pattern_detection import (
    ContinuationParams,
    DetectionContext,
    Judgement,
    PatternCandidate,
    PatternDetector,
    Side,
    anchor_of,
    breakout_evidence,
    index_by_open_time,
    judge,
    line_through,
    prior_trend_state,
    reference_range,
)

_MIN_SWINGS = 4  # two highs and two lows


@dataclass(frozen=True, slots=True)
class Channel:
    """A run of swings and the two straight lines that bound it."""

    window: tuple[Pivot, ...]
    upper: Callable[[datetime], Decimal]
    lower: Callable[[datetime], Decimal]
    highs: tuple[Pivot, ...]
    lows: tuple[Pivot, ...]
    # Vertical distance between the lines at the first contact: the figure's height, the yardstick
    # for every tolerance and margin (fixed once the figure has begun).
    height: Decimal
    gap_at_end: Decimal
    upper_rise: Decimal
    lower_rise: Decimal
    reference: Decimal
    first_index: int
    last_index: int
    # Last candle in which a first breakout can still happen: converging lines meet at an apex,
    # and past it the "upper" line lies below the "lower" one. None while the apex is still ahead.
    expires_after: int | None


def flat(rise: Decimal, height: Decimal, params: ContinuationParams) -> bool:
    return abs(rise) <= params.flat_tolerance * height


def rising(rise: Decimal, height: Decimal, params: ContinuationParams) -> bool:
    return rise >= params.slope_min * height


def falling(rise: Decimal, height: Decimal, params: ContinuationParams) -> bool:
    return rise <= -params.slope_min * height


def fit_channel(
    params: ContinuationParams,
    closed: Sequence[Candle],
    index: dict[datetime, int],
    window: Sequence[Pivot],
    *,
    min_candles: int | None = None,
    check_height: bool = True,
) -> Channel | None:
    """The two lines through the highs and through the lows of `window`, if what lies between them
    is a channel: the lines through the first and the last contact of each side, the contacts in
    between within `contact_tolerance` of their line, and every close from the first contact to the
    last one **inside** both lines. (A close beyond a line is a breakout: the figure stops growing
    there, so a breakout is always found after its last contact and never inside it.)

    It says nothing about the slopes: which figure this is, is up to the detector. `min_candles`
    replaces the minimum span, and `check_height=False` skips the comparison with the recent range,
    for figures (flags) whose size is judged against something else."""
    highs = tuple(p for p in window if p.kind is PivotKind.HIGH)
    lows = tuple(p for p in window if p.kind is PivotKind.LOW)
    if len(highs) < 2 or len(lows) < 2:
        return None
    upper = line_through(highs[0].open_time, highs[0].price, highs[-1].open_time, highs[-1].price)
    lower = line_through(lows[0].open_time, lows[0].price, lows[-1].open_time, lows[-1].price)
    start, end = window[0].open_time, window[-1].open_time
    height = upper(start) - lower(start)
    gap_at_end = upper(end) - lower(end)
    if height <= 0 or gap_at_end <= 0:
        return None
    first_index, last_index = index[start], index[end]
    minimum = params.min_channel_candles if min_candles is None else min_candles
    if last_index - first_index < minimum:
        return None
    reference = reference_range(closed, first_index, params.range_window_candles)
    if reference <= 0 or (check_height and height < params.min_height_fraction * reference):
        return None
    tolerance = params.contact_tolerance * height
    if any(abs(p.price - upper(p.open_time)) > tolerance for p in highs[1:-1]):
        return None
    if any(abs(p.price - lower(p.open_time)) > tolerance for p in lows[1:-1]):
        return None
    for candle in closed[first_index : last_index + 1]:
        if candle.close > upper(candle.close_time) or candle.close < lower(candle.close_time):
            return None
    return Channel(
        tuple(window),
        upper,
        lower,
        highs,
        lows,
        height,
        gap_at_end,
        upper(end) - upper(start),
        lower(end) - lower(start),
        reference,
        first_index,
        last_index,
        _expires_after(closed, last_index, end, height, gap_at_end, end - start),
    )


def _expires_after(
    closed: Sequence[Candle],
    last_index: int,
    end: datetime,
    height: Decimal,
    gap_at_end: Decimal,
    span: timedelta,
) -> int | None:
    """Index of the last candle that closes before the lines meet, or None if none has yet
    closed at or after that moment (or the lines do not converge). Exact, `Decimal` seconds."""
    if gap_at_end >= height:
        return None
    to_apex = Decimal(span.total_seconds()) * gap_at_end / (height - gap_at_end)
    for k in range(last_index + 1, len(closed)):
        if Decimal((closed[k].close_time - end).total_seconds()) >= to_apex:
            return k - 1
    return None


def left_the_lines(channel: Channel, closed: Sequence[Candle], until: int) -> bool:
    """A close after the channel's last contact, up to candle `until`, beyond one of its lines."""
    return any(
        candle.close > channel.upper(candle.close_time)
        or candle.close < channel.lower(candle.close_time)
        for candle in closed[channel.last_index + 1 : until + 1]
    )


def grow_channel(
    params: ContinuationParams,
    closed: Sequence[Candle],
    index: dict[datetime, int],
    swings: Sequence[Pivot],
    position: int,
    *,
    accepted: Callable[[Channel], bool],
    min_candles: int | None = None,
    check_height: bool = True,
    min_swings: int = _MIN_SWINGS,
) -> Channel | None:
    """The longest run of swings from `position` that is a figure of its kind (`accepted`) at every
    size from `min_swings` (the fourth swing, by default) on. The first size that fails ends the
    growth.

    Growing moves the two lines (they run through the first and the last contact), so it may
    only happen while the price has stayed inside the lines the figure had before: a close
    beyond them is a breakout, already part of the story, and a new last contact must never
    make it look as if it had not been one."""
    channel: Channel | None = None
    size = min_swings
    while position + size <= len(swings):
        fit = fit_channel(
            params,
            closed,
            index,
            swings[position : position + size],
            min_candles=min_candles,
            check_height=check_height,
        )
        if fit is None or not accepted(fit):
            break
        if channel is not None and left_the_lines(channel, closed, fit.last_index):
            break
        channel = fit
        size += 1
    return channel


class ContinuationDetector(PatternDetector):
    """What every continuation detector shares: it reads the continuation parameters, their
    version is part of each figure's identity, and so are the pivot parameters and the history it
    asks of the series."""

    def parameter_version(self, context: DetectionContext) -> str:
        return context.continuation.version

    def pivot_params(self, context: DetectionContext) -> PivotParams:
        return context.continuation.pivot_params

    def min_history(self, context: DetectionContext) -> int:
        return context.continuation.min_history


class ChannelDetector(ContinuationDetector):
    """One detector = one figure of the two-boundary family. Subclasses say which slopes they
    accept and nothing else."""

    # Swings the figure needs before it exists: two highs and two lows, unless the figure says more.
    min_swings: int = _MIN_SWINGS

    def accepts(self, fit: Channel, params: ContinuationParams) -> bool:
        """Whether this channel, measured, is a figure of this kind."""
        raise NotImplementedError

    def find(
        self, context: DetectionContext, closed: Sequence[Candle], swings: Sequence[Pivot]
    ) -> list[PatternCandidate]:
        index = index_by_open_time(closed)
        found: list[PatternCandidate] = []
        covered_until = -1  # position of the last swing of the longest figure found so far
        for position in range(len(swings) - self.min_swings + 1):
            channel = self._grown(context.continuation, closed, index, swings, position)
            if channel is None:
                continue
            end = position + len(channel.window) - 1
            if end <= covered_until:
                continue  # a piece of a figure that began earlier: the same figure, not another
            covered_until = end
            candidate = self._figure(context, closed, channel)
            if candidate is not None:
                found.append(candidate)
        return found

    def _grown(
        self,
        params: ContinuationParams,
        closed: Sequence[Candle],
        index: dict[datetime, int],
        swings: Sequence[Pivot],
        position: int,
    ) -> Channel | None:
        return grow_channel(
            params,
            closed,
            index,
            swings,
            position,
            accepted=lambda fit: self.accepts(fit, params),
            min_swings=self.min_swings,
        )

    def _figure(
        self, context: DetectionContext, closed: Sequence[Candle], channel: Channel
    ) -> PatternCandidate | None:
        params = context.continuation
        last = len(closed) - 1
        upward = judge(
            closed,
            side=Side.BOTTOM,
            params=params,
            start_index=channel.first_index,
            exceed_from=None,
            breakout_from=channel.last_index + 1,
            complete=True,
            forming=False,
            neckline_at=lambda candle: channel.upper(candle.close_time),
            height=channel.height,
            expires_after=channel.expires_after,
            boundary_role=BoundaryRole.UPPER,
        )
        downward = judge(
            closed,
            side=Side.TOP,
            params=params,
            start_index=channel.first_index,
            exceed_from=None,
            breakout_from=channel.last_index + 1,
            complete=True,
            forming=False,
            neckline_at=lambda candle: channel.lower(candle.close_time),
            height=channel.height,
            expires_after=channel.expires_after,
            boundary_role=BoundaryRole.LOWER,
        )
        if upward is None or downward is None:
            return None
        judgement = first_breakout(upward, downward)

        anchors = []
        upper_count = lower_count = 0
        for pivot in channel.window:
            if pivot.kind is PivotKind.HIGH:
                upper_count += 1
                anchors.append(anchor_of(pivot, f"UPPER_{upper_count}"))
            else:
                lower_count += 1
                anchors.append(anchor_of(pivot, f"LOWER_{lower_count}"))
        items = (
            channel_evidence(channel, params),
            prior_trend_context(context, closed, channel.window[0]),
            *breakout_evidence(judgement, closed),
        )
        return self.candidate(
            context,
            PatternEvaluation(
                evaluated_at=context.observed_at,
                as_of=closed[-1].close_time,
                candle_count=last - channel.first_index + 1,
                state=judgement.state,
                anchors=tuple(anchors),
                boundaries=boundaries_of(channel),
                breakout=judgement.breakout,
                invalidation_reasons=judgement.invalidation_reasons,
                evidence=items,
            ),
        )


def boundaries_of(channel: Channel) -> tuple[Boundary, Boundary]:
    """The two lines of a channel as the model records them, with the anchors that touch each."""
    return (
        Boundary(
            BoundaryRole.UPPER,
            (
                BoundaryPoint(channel.highs[0].open_time, channel.highs[0].price),
                BoundaryPoint(channel.highs[-1].open_time, channel.highs[-1].price),
            ),
            tuple(p.open_time for p in channel.highs),
        ),
        Boundary(
            BoundaryRole.LOWER,
            (
                BoundaryPoint(channel.lows[0].open_time, channel.lows[0].price),
                BoundaryPoint(channel.lows[-1].open_time, channel.lows[-1].price),
            ),
            tuple(p.open_time for p in channel.lows),
        ),
    )


def first_breakout(upward: Judgement, downward: Judgement) -> Judgement:
    """Of the two boundaries, the one the price went through first decides the figure (what
    happened first wins, and a breakout that failed is not undone by what comes after). With no
    breakout at all the two judgements say the same (the figure is intact or has run its course),
    and either will do."""
    up, down = upward.first_beyond_index, downward.first_beyond_index
    if up is not None and (down is None or up < down):
        return upward
    if down is not None:
        return downward
    return upward


def channel_evidence(channel: Channel, params: ContinuationParams) -> PatternEvidence:
    return evidence(
        "CHANNEL",
        "the two boundaries, how far each one moves and how tall the figure is between them",
        height=channel.height,
        gap_at_end=channel.gap_at_end,
        upper_rise=channel.upper_rise,
        lower_rise=channel.lower_rise,
        upper_contacts=len(channel.highs),
        lower_contacts=len(channel.lows),
        span_candles=channel.last_index - channel.first_index,
        reference_range=channel.reference,
        contact_tolerance=params.contact_tolerance,
        flat_tolerance=params.flat_tolerance,
        slope_min=params.slope_min,
    )


def prior_trend_context(
    context: DetectionContext, closed: Sequence[Candle], first: Pivot
) -> PatternEvidence:
    """The trend before the figure began, as context only: whether it continues that trend or
    reverses it depends on which way the figure breaks, and that is for the breakout to say."""
    state = prior_trend_state(
        context,
        closed,
        first,
        pivot_params=context.continuation.pivot_params,
        min_history=context.continuation.min_history,
    )
    return evidence(
        "PRIOR_TREND",
        f"trend before the figure: {state.value}",
        state=state.value,
    )


class RectangleDetector(ChannelDetector):
    pattern_type = PatternType.RECTANGLE
    version = "rectangle-detector-v1"

    def accepts(self, fit: Channel, params: ContinuationParams) -> bool:
        return flat(fit.upper_rise, fit.height, params) and flat(fit.lower_rise, fit.height, params)


class AscendingTriangleDetector(ChannelDetector):
    pattern_type = PatternType.ASCENDING_TRIANGLE
    version = "ascending-triangle-detector-v1"

    def accepts(self, fit: Channel, params: ContinuationParams) -> bool:
        return flat(fit.upper_rise, fit.height, params) and rising(
            fit.lower_rise, fit.height, params
        )


class DescendingTriangleDetector(ChannelDetector):
    pattern_type = PatternType.DESCENDING_TRIANGLE
    version = "descending-triangle-detector-v1"

    def accepts(self, fit: Channel, params: ContinuationParams) -> bool:
        return falling(fit.upper_rise, fit.height, params) and flat(
            fit.lower_rise, fit.height, params
        )


class SymmetricalTriangleDetector(ChannelDetector):
    pattern_type = PatternType.SYMMETRICAL_TRIANGLE
    version = "symmetrical-triangle-detector-v1"

    def accepts(self, fit: Channel, params: ContinuationParams) -> bool:
        return falling(fit.upper_rise, fit.height, params) and rising(
            fit.lower_rise, fit.height, params
        )
