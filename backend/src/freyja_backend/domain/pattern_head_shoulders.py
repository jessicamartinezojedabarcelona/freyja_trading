"""Head and shoulders (top) and inverse head and shoulders (bottom) detectors
(POINT3-REVERSAL-001).

Rules in ``docs/domain/detectores-de-reversion.md``, section "Hombro-cabeza-hombro". The two
detectors are mirrors of each other through `Side`. They share nothing with the doubles and
triples: this figure has a **head** that must stand out, two **shoulders** that are only roughly
level, and a **neckline that may slope**, so a close that would break a horizontal level can sit
above the line that actually matters.

A head and shoulders top is five swing points in a row, **shoulder, trough, head, trough,
shoulder**, where the head is the furthest extreme by at least `head_prominence` of the figure's
height, the two shoulders are comparable within `shoulder_tolerance` of it, and the figure is tall
enough to matter (`min_height_fraction` of the range where it began). The height is the vertical
distance from the head to the **neckline**, the straight line through the two troughs, read at
the head's time. It is *forming* once the first shoulder, both troughs and the head are confirmed
and the price is back at the first shoulder's level; *valid* once the right shoulder is confirmed.
"""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from freyja_backend.domain.chart_pattern import (
    Boundary,
    BoundaryPoint,
    BoundaryRole,
    InvalidationReason,
    PatternEvaluation,
    PatternState,
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
    line_through,
    prior_trend_evidence,
    reference_range,
)


class _HeadAndShouldersDetector(PatternDetector):
    def find(
        self, context: DetectionContext, closed: Sequence[Candle], swings: Sequence[Pivot]
    ) -> list[PatternCandidate]:
        side = self.side
        index = index_by_open_time(closed)
        found: list[PatternCandidate] = []
        kinds = (side.extreme_kind, side.opposite_kind) * 2
        for position in range(len(swings) - 3):
            window = swings[position : position + 5]
            if any(swing.kind is not kind for swing, kind in zip(window, kinds, strict=False)):
                continue
            candidate = self._figure(context, closed, index, window)
            if candidate is not None:
                found.append(candidate)
        return found

    def _figure(
        self,
        context: DetectionContext,
        closed: Sequence[Candle],
        index: dict[datetime, int],
        window: Sequence[Pivot],
    ) -> PatternCandidate | None:
        params, side = context.params, self.side
        signed = side.signed
        last = len(closed) - 1
        left, left_trough, head, right_trough = window[:4]
        right = window[4] if len(window) > 4 else None
        left_index, head_index = index[left.open_time], index[head.open_time]

        reference = reference_range(closed, left_index, params.range_window_candles)
        if reference <= 0:
            return None

        neckline = line_through(
            left_trough.open_time, left_trough.price, right_trough.open_time, right_trough.price
        )
        height = signed(head.price) - signed(neckline(head.open_time))
        if height <= 0 or height < params.min_height_fraction * reference:
            return None
        higher_shoulder = (
            signed(left.price) if right is None else max(signed(left.price), signed(right.price))
        )
        prominence = signed(head.price) - higher_shoulder
        right_below_head = right is None or signed(right.price) < signed(head.price)
        if right_below_head and prominence < params.head_prominence * height:
            return None  # no head: the middle extreme does not stand out from the shoulders

        anchors = [
            anchor_of(left, "LEFT_SHOULDER"),
            anchor_of(left_trough, "LEFT_TROUGH"),
            anchor_of(head, "HEAD"),
            anchor_of(right_trough, "RIGHT_TROUGH"),
        ]
        facts: dict[str, Decimal] = {
            "height": height,
            "head_prominence": prominence,
            "head_prominence_required": params.head_prominence * height,
            "shoulder_tolerance": params.shoulder_tolerance,
            "reference_range": reference,
            "neckline_rise_per_hour": (
                (right_trough.price - left_trough.price)
                * 3600
                / Decimal((right_trough.open_time - left_trough.open_time).total_seconds())
            ).quantize(Decimal("0.000001")),
        }

        right_index = None
        complete = False
        judgement: Judgement | None
        if right is not None:
            anchors.append(anchor_of(right, "RIGHT_SHOULDER"))
            right_index = index[right.open_time]
            shoulder_gap = abs(signed(left.price) - signed(right.price))
            facts["shoulder_gap"] = shoulder_gap
            complete = shoulder_gap <= params.shoulder_tolerance * height and (
                signed(right.price) < signed(head.price)
            )

        if right is not None and not complete:
            higher = signed(right.price) >= signed(head.price)
            reason = (
                InvalidationReason.ANCHOR_EXCEEDED if higher else InvalidationReason.GEOMETRY_BROKEN
            )
            judgement = Judgement(PatternState.INVALIDATED, invalidation_reasons=(reason,))
        else:
            right_trough_index = index[right_trough.open_time]
            forming = right is None and any(
                signed(side.extreme_of(c))
                >= signed(left.price) - params.shoulder_tolerance * height
                for c in closed[right_trough_index + 1 :]
            )
            judgement = judge(
                closed,
                side=side,
                params=params,
                start_index=left_index,
                exceed_from=head_index + 1,
                breakout_from=(right_index + 1)
                if complete and right_index is not None
                else last + 1,
                complete=complete,
                forming=forming,
                neckline_at=lambda candle: neckline(candle.close_time),
                height=height,
                extreme_price=head.price,
            )
        if judgement is None:
            return None

        boundaries: tuple[Boundary, ...] = ()
        if complete:
            boundaries = (
                Boundary(
                    BoundaryRole.NECKLINE,
                    (
                        BoundaryPoint(left_trough.open_time, left_trough.price),
                        BoundaryPoint(right_trough.open_time, right_trough.price),
                    ),
                    (left_trough.open_time, right_trough.open_time),
                ),
            )
        items = (
            evidence(
                "HEAD_AND_SHOULDERS",
                "the head, the shoulders and the height above the neckline they are judged against",
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


class HeadAndShouldersTopDetector(_HeadAndShouldersDetector):
    pattern_type = PatternType.HEAD_AND_SHOULDERS_TOP
    version = "head-and-shoulders-top-detector-v1"
    side = Side.TOP


class HeadAndShouldersBottomDetector(_HeadAndShouldersDetector):
    pattern_type = PatternType.HEAD_AND_SHOULDERS_BOTTOM
    version = "head-and-shoulders-bottom-detector-v1"
    side = Side.BOTTOM
