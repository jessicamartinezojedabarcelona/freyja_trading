"""Triple top and triple bottom detectors (POINT3-REVERSAL-001).

Rules in ``docs/domain/detectores-de-reversion.md``, section "Triple techo y triple suelo". The two
detectors mirror each other through `Side`; they share nothing with the double or head-and-
shoulders detectors, because "three comparable extremes" is not "two comparable extremes plus
one": the third must agree with both, and the support is the lower of two troughs.

A triple top is five swing points in a row, **peak, trough, peak, trough, peak**, where the three
peaks are comparable to their mean and the two troughs comparable to each other (all within
`level_tolerance` of the figure's height, peak level to trough level). The **neckline** is the
level of the lower trough. It is *forming* once the first two peaks and both troughs are confirmed
and the price is back at the peaks' level; *valid* once the third peak is confirmed.
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
    prior_trend_evidence,
    reference_range,
)


class _TripleDetector(PatternDetector):
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
        first, first_trough, second, second_trough = window[:4]
        third = window[4] if len(window) > 4 else None
        first_index = index[first.open_time]
        reference = reference_range(closed, first_index, params.range_window_candles)
        if reference <= 0:
            return None

        peaks = [first, second] if third is None else [first, second, third]
        troughs = [first_trough, second_trough]
        mean_peak = sum((signed(p.price) for p in peaks), start=Decimal(0)) / len(peaks)
        mean_trough = sum((signed(t.price) for t in troughs), start=Decimal(0)) / len(troughs)
        height = mean_peak - mean_trough
        if height <= 0 or height < params.min_height_fraction * reference:
            return None

        tolerance = params.level_tolerance * height
        peak_gaps = [abs(signed(p.price) - mean_peak) for p in peaks]
        trough_gap = abs(signed(first_trough.price) - signed(second_trough.price))
        if any(gap > tolerance for gap in peak_gaps[:2]) or trough_gap > tolerance:
            return None  # two peaks and two troughs that do not agree: not this figure
        complete = third is not None and peak_gaps[2] <= tolerance

        anchors = [
            anchor_of(first, "EXTREME_1"),
            anchor_of(first_trough, "INTERMEDIATE_1"),
            anchor_of(second, "EXTREME_2"),
            anchor_of(second_trough, "INTERMEDIATE_2"),
        ]
        if third is not None:
            anchors.append(anchor_of(third, "EXTREME_3"))

        lower = min(troughs, key=lambda t: signed(t.price))
        neckline_level = lower.price
        second_trough_index = index[second_trough.open_time]
        third_index = None if third is None else index[third.open_time]

        judgement: Judgement | None
        if third is not None and not complete:
            higher = signed(third.price) > max(signed(first.price), signed(second.price))
            reason = (
                InvalidationReason.ANCHOR_EXCEEDED if higher else InvalidationReason.GEOMETRY_BROKEN
            )
            judgement = Judgement(PatternState.INVALIDATED, invalidation_reasons=(reason,))
        else:
            # See the double top: a fall before the third extreme is confirmed is judged as the
            # breakout it is once that extreme is, never as an invalidation.
            extreme_price = max(peaks, key=lambda p: signed(p.price)).price
            forming = third is None and any(
                signed(side.extreme_of(c)) >= mean_peak - tolerance
                for c in closed[second_trough_index + 1 :]
            )
            judgement = judge(
                closed,
                side=side,
                params=params,
                start_index=first_index,
                exceed_from=index[first_trough.open_time] + 1,
                breakout_from=(third_index + 1)
                if complete and third_index is not None
                else last + 1,
                complete=complete,
                forming=forming,
                neckline_at=lambda _candle: neckline_level,
                height=height,
                extreme_price=extreme_price,
                exceed_margin=params.exceed_margin,
            )
        if judgement is None:
            return None

        boundaries: tuple[Boundary, ...] = ()
        if complete:
            boundaries = (
                Boundary(
                    BoundaryRole.NECKLINE,
                    (
                        BoundaryPoint(first_trough.open_time, neckline_level),
                        BoundaryPoint(anchors[-1].open_time, neckline_level),
                    ),
                    (first_trough.open_time, second_trough.open_time),
                ),
            )
        facts: dict[str, Decimal] = {
            "height": height,
            "level_tolerance": params.level_tolerance,
            "reference_range": reference,
            "trough_gap": trough_gap,
            "largest_peak_gap": max(peak_gaps),
        }
        items = (
            evidence(
                "EXTREME_LEVELS",
                "the three extremes and two troughs and the height they are judged against",
                **facts,
            ),
            prior_trend_evidence(context, closed, side, first),
            *breakout_evidence(judgement, closed),
        )
        return self.candidate(
            context,
            PatternEvaluation(
                evaluated_at=context.observed_at,
                as_of=closed[-1].close_time,
                candle_count=last - first_index + 1,
                state=judgement.state,
                anchors=tuple(anchors),
                boundaries=boundaries,
                breakout=judgement.breakout,
                invalidation_reasons=judgement.invalidation_reasons,
                evidence=items,
            ),
        )


class TripleTopDetector(_TripleDetector):
    pattern_type = PatternType.TRIPLE_TOP
    version = "triple-top-detector-v1"
    side = Side.TOP


class TripleBottomDetector(_TripleDetector):
    pattern_type = PatternType.TRIPLE_BOTTOM
    version = "triple-bottom-detector-v1"
    side = Side.BOTTOM
