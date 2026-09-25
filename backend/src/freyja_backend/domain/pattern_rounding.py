"""Rounding top and rounding bottom detectors (POINT3-REVERSAL-001).

Rules in ``docs/domain/detectores-de-reversion.md``, section "Techo y suelo redondeados". The two
detectors mirror each other through `Side`. They share nothing with the doubles, triples or
head and shoulders, because a rounding top has **no sharp pivots to compare**: it is a curve.
What can be checked, exactly, is that the closes follow one.

A rounding top has three anchors: the **left end** (a confirmed swing low where the arc begins),
the **apex** (the confirmed swing high on top) and the **right end** (the first closed candle after
the apex whose close is back at the level of the left end). It is not a pivot, on purpose: a
dome that falls straight through its base never leaves a confirmed low there, and waiting for one
would hide the very breakout the figure is about. The **base** is the horizontal level of the left
end: the right end is where the price is back at it, and a breakout is a close below it. (A line
through the two ends would slope up to wherever the descent was first caught, and the arc's own
last candles, still on their way down to the base, would already count as a break.) The arc must

* span between `min_arc_candles` and `max_arc_candles` candles;
* have its apex in the middle part of the arc (`apex_position_band`);
* have closes that follow a parabola open downwards (upwards for a bottom) with a coefficient of
  determination of at least `arc_fit_min`, fitted by least squares in exact rational arithmetic;
* dwell near the top: at least `min_top_dwell` of its closes in the top quarter of its height.
  A pointed peak also fits a parabola well, and is not rounded.

It is *forming* once the left end and the apex are confirmed, the left half of the arc already
follows a parabola, and the price is on its way down; *valid* once the right end exists.
"""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from functools import lru_cache

from freyja_backend.domain.chart_pattern import (
    AnchorPivot,
    Boundary,
    BoundaryPoint,
    BoundaryRole,
    PatternEvaluation,
    PatternType,
    evidence,
)
from freyja_backend.domain.market_data import Candle
from freyja_backend.domain.market_structure import Pivot
from freyja_backend.domain.pattern_detection import (
    DetectionContext,
    Judgement,
    PatternCandidate,
    PatternDetector,
    Side,
    anchor_of,
    breakout_evidence,
    index_by_open_time,
    judge,
    prior_trend_evidence,
    reference_range,
)

_SIX = Decimal("0.000001")


def _det3(m: Sequence[Sequence[Fraction]]) -> Fraction:
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def quadratic_fit(ys: Sequence[Fraction]) -> tuple[Fraction, Fraction] | None:
    """Least-squares parabola `y = c + b*x + q*x^2` through `ys` at x = 0, 1, 2..., exactly.

    Returns `(q, r_squared)`: the curvature (negative: open downwards) and the share of the
    variance of `ys` the parabola explains. `None` when there is nothing to fit (fewer than three
    points, or all `ys` equal). Rational arithmetic: no float is ever involved."""
    n = len(ys)
    if n < 3:
        return None
    zero = Fraction(0)
    sums = [sum((Fraction(x) ** power for x in range(n)), start=zero) for power in range(5)]
    moments = [
        sum((Fraction(x) ** power * y for x, y in enumerate(ys)), start=zero) for power in range(3)
    ]
    matrix = [[sums[i + j] for j in range(3)] for i in range(3)]
    det = _det3(matrix)
    if det == 0:
        return None

    def solved(column: int) -> Fraction:
        replaced = [
            [moments[i] if j == column else matrix[i][j] for j in range(3)] for i in range(3)
        ]
        return _det3(replaced) / det

    c, b, q = solved(0), solved(1), solved(2)
    mean = moments[0] / n
    total = sum(((y - mean) ** 2 for y in ys), start=zero)
    if total == 0:
        return None
    residual = sum(((y - (c + b * x + q * x * x)) ** 2 for x, y in enumerate(ys)), start=zero)
    return q, 1 - residual / total


@lru_cache(maxsize=1024)
def _fit_of(closes: tuple[Decimal, ...]) -> tuple[Fraction, Fraction] | None:
    """`quadratic_fit` of a window of closes. The same window comes back at every later instant
    (a pure function of the candles), so its exact fit is worked out once."""
    return quadratic_fit([Fraction(close) for close in closes])


def _decimal(value: Fraction) -> Decimal:
    return (Decimal(value.numerator) / Decimal(value.denominator)).quantize(_SIX)


class _RoundingDetector(PatternDetector):
    def find(
        self, context: DetectionContext, closed: Sequence[Candle], swings: Sequence[Pivot]
    ) -> list[PatternCandidate]:
        index = index_by_open_time(closed)
        found: list[PatternCandidate] = []
        for position, apex in enumerate(swings):
            if apex.kind is not self.side.extreme_kind:
                continue
            candidate = self._figure(context, closed, index, swings, position)
            if candidate is not None:
                found.append(candidate)
        return found

    def _figure(
        self,
        context: DetectionContext,
        closed: Sequence[Candle],
        index: dict[datetime, int],
        swings: Sequence[Pivot],
        position: int,
    ) -> PatternCandidate | None:
        params, side = context.params, self.side
        signed = side.signed
        last = len(closed) - 1
        apex = swings[position]
        apex_index = index[apex.open_time]

        # The left end: the oldest swing before the apex, within reach, from which the climb to
        # the apex already follows a parabola. It depends only on what lies to the left of the
        # apex, so it does not change when the right side appears (the identity stays put).
        left: Pivot | None = None
        estimate = Decimal(0)
        reference = Decimal(0)
        for earlier in swings[:position]:
            if earlier.kind is side.extreme_kind:
                continue
            earlier_index = index[earlier.open_time]
            if apex_index - earlier_index > params.max_arc_candles:
                continue
            if apex_index - earlier_index < params.min_arc_candles // 2:
                continue
            rise = signed(apex.price) - signed(earlier.price)
            span_range = reference_range(closed, earlier_index, params.range_window_candles)
            if span_range <= 0 or rise <= 0 or rise < params.min_height_fraction * span_range:
                continue
            climbing = closed[earlier_index : apex_index + 1]
            climb = _fit_of(tuple(signed(c.close) for c in climbing))
            if climb is None or climb[0] >= 0 or climb[1] < Fraction(params.arc_fit_min):
                continue
            # A straight climb is a parabola of no curvature and fits perfectly: what makes it a
            # dome is that the price lingers near the top of the climb, as a parabola does.
            near_top = signed(apex.price) - rise / 4
            lingering = Fraction(
                sum(1 for c in climbing if signed(c.close) >= near_top), len(climbing)
            )
            if lingering < Fraction(params.min_top_dwell):
                continue
            left, estimate, reference = earlier, rise, span_range
            break
        if left is None:
            return None
        left_index = index[left.open_time]
        base_level = signed(left.price) + params.level_tolerance * estimate

        # The right end: the first candle after the apex that closes back at the base level,
        # unless the price first makes a higher extreme (this is not the top) or the arc would be
        # wider than allowed.
        right_index: int | None = None
        for k in range(apex_index + 1, min(last, left_index + params.max_arc_candles) + 1):
            candle = closed[k]
            if signed(side.extreme_of(candle)) > signed(apex.price):
                return None
            if signed(candle.close) <= base_level:
                right_index = k
                break
        if right_index is None and last - left_index >= params.max_arc_candles:
            return None

        complete = right_index is not None
        if right_index is not None:
            right_candle = closed[right_index]
            if signed(right_candle.close) < signed(left.price) - params.level_tolerance * estimate:
                return None  # it fell through the base instead of returning to it
            right_price = right_candle.low if side is Side.TOP else right_candle.high
            right = AnchorPivot(
                side.opposite_kind,
                right_candle.open_time,
                right_price,
                right_candle.close_time,
                "RIGHT_END",
            )
            height = estimate
            span = right_index - left_index + 1
            arc = closed[left_index : right_index + 1]
            if span < params.min_arc_candles:
                return None  # (the right end is searched within `max_arc_candles`: no upper check)
            apex_fraction = Fraction(apex_index - left_index, right_index - left_index)
            band = Fraction(params.apex_position_band)
            if not (band <= apex_fraction <= 1 - band):
                return None
        else:
            if apex_index - left_index < params.min_arc_candles // 2:
                return None
            height = estimate
            span = last - left_index + 1
            arc = closed[left_index : apex_index + 1]
            apex_fraction = Fraction(apex_index - left_index, last - left_index)

        fit = _fit_of(tuple(signed(c.close) for c in arc))
        if fit is None:
            return None
        curvature, r_squared = fit
        if r_squared < Fraction(params.arc_fit_min):
            return None  # (an arc that fits well with the apex in the middle is open downwards)
        top_level = signed(apex.price) - height / 4
        dwell = Fraction(sum(1 for c in arc if signed(c.close) >= top_level), len(arc))
        if complete and dwell < Fraction(params.min_top_dwell):
            return None

        anchors = [anchor_of(left, "LEFT_END"), anchor_of(apex, "APEX")]
        boundaries: tuple[Boundary, ...] = ()
        if complete:
            anchors.append(right)
            boundaries = (
                Boundary(
                    BoundaryRole.BASE,
                    (
                        BoundaryPoint(left.open_time, left.price),
                        BoundaryPoint(right.open_time, left.price),
                    ),
                    (left.open_time, right.open_time),
                ),
                Boundary(
                    BoundaryRole.ARC,
                    (
                        BoundaryPoint(left.open_time, left.price),
                        BoundaryPoint(apex.open_time, apex.price),
                        BoundaryPoint(right.open_time, right.price),
                    ),
                    (apex.open_time,),
                ),
            )

        # Age counts from the last anchor: an arc is long by nature.
        anchored_at = right_index if right_index is not None else apex_index
        judgement: Judgement | None = judge(
            closed,
            side=side,
            params=params,
            start_index=anchored_at,
            exceed_from=apex_index + 1,
            breakout_from=(right_index + 1) if right_index is not None else last + 1,
            complete=complete,
            forming=not complete,
            neckline_at=lambda _candle: left.price,
            height=height,
            extreme_price=apex.price,
            boundary_role=BoundaryRole.BASE,
        )
        if judgement is None:
            return None

        facts: dict[str, Decimal | int] = {
            "fit_r_squared": _decimal(r_squared),
            "curvature": _decimal(curvature),
            "apex_position": _decimal(apex_fraction),
            "top_dwell": _decimal(dwell),
            "arc_candles": span,
            "height": height,
            "reference_range": reference,
        }
        items = (
            evidence(
                "ROUNDING_ARC",
                "how well the closes follow a parabola, where its apex is and how it dwells on top",
                **facts,
            ),
            prior_trend_evidence(context, closed, side, left),
            *breakout_evidence(judgement, closed),
        )
        return self.candidate(
            context,
            PatternEvaluation(
                evaluated_at=context.observed_at,
                as_of=closed[-1].close_time,
                candle_count=last - left_index + 1,
                state=judgement.state,
                anchors=tuple(anchors),
                boundaries=boundaries,
                breakout=judgement.breakout,
                invalidation_reasons=judgement.invalidation_reasons,
                evidence=items,
            ),
        )


class RoundingTopDetector(_RoundingDetector):
    pattern_type = PatternType.ROUNDING_TOP
    version = "rounding-top-detector-v1"
    side = Side.TOP


class RoundingBottomDetector(_RoundingDetector):
    pattern_type = PatternType.ROUNDING_BOTTOM
    version = "rounding-bottom-detector-v1"
    side = Side.BOTTOM
