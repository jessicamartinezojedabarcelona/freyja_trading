"""Double top and double bottom detectors (POINT3-REVERSAL-001).

Rules in ``docs/domain/detectores-de-reversion.md``, section "Doble techo y doble suelo". The two
detectors are mirrors of each other and share this one geometry through `Side`; they share
nothing with the triple or head-and-shoulders detectors, which have their own rules.

A double top is three swing points in a row, **peak, trough, peak** (a double bottom: trough,
peak, trough), where the two peaks are *comparable* (within `level_tolerance` of the figure's
height) and the figure is tall enough to matter (`min_height_fraction` of the price range where it
began). The **neckline** is the level of the trough. The figure is *forming* while only the first
peak and the trough are confirmed and the price has climbed back to the peak's level; *valid*
once the second peak is confirmed; and it is judged on the closes after that (`judge`).
"""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from freyja_backend.domain.chart_pattern import (
    Boundary,
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
    horizontal_neckline,
    index_by_open_time,
    judge,
    prior_trend_evidence,
    reference_range,
)


class _DoubleDetector(PatternDetector):
    def find(
        self, context: DetectionContext, closed: Sequence[Candle], swings: Sequence[Pivot]
    ) -> list[PatternCandidate]:
        side = self.side
        index = index_by_open_time(closed)
        found: list[PatternCandidate] = []
        for position in range(len(swings) - 1):
            first, trough = swings[position], swings[position + 1]
            if first.kind is not side.extreme_kind or trough.kind is not side.opposite_kind:
                continue
            second = swings[position + 2] if position + 2 < len(swings) else None
            candidate = self._figure(context, closed, index, first, trough, second)
            if candidate is not None:
                found.append(candidate)
        return found

    def _figure(
        self,
        context: DetectionContext,
        closed: Sequence[Candle],
        index: dict[datetime, int],
        first: Pivot,
        trough: Pivot,
        second: Pivot | None,
    ) -> PatternCandidate | None:
        params, side = context.params, self.side
        signed = side.signed
        last = len(closed) - 1
        first_index, trough_index = index[first.open_time], index[trough.open_time]

        reference = reference_range(closed, first_index, params.range_window_candles)
        if reference <= 0:
            return None
        peaks = (first.price,) if second is None else (first.price, second.price)
        mean_peak = sum((signed(price) for price in peaks), start=Decimal(0)) / len(peaks)
        height = mean_peak - signed(trough.price)
        if height <= 0 or height < params.min_height_fraction * reference:
            return None

        anchors = [anchor_of(first, "FIRST_EXTREME"), anchor_of(trough, "INTERMEDIATE")]
        facts: dict[str, object] = {
            "height": height,
            "level_tolerance": params.level_tolerance,
            "reference_range": reference,
        }
        neckline_level = trough.price
        second_index = None if second is None else index[second.open_time]
        if second is not None:
            anchors.append(anchor_of(second, "SECOND_EXTREME"))
            gap = abs(signed(second.price) - signed(first.price))
            facts["extreme_gap"] = gap

        complete = second is not None and gap <= params.level_tolerance * height
        judgement: Judgement | None
        if second is not None and not complete:
            higher = signed(second.price) > signed(first.price)
            reason = (
                InvalidationReason.ANCHOR_EXCEEDED if higher else InvalidationReason.GEOMETRY_BROKEN
            )
            judgement = Judgement(PatternState.INVALIDATED, invalidation_reasons=(reason,))
        else:
            # A close below the neckline before the second extreme is confirmed is not an
            # invalidation: a pivot is confirmed k candles late, so a fall right after the peak
            # looks exactly like that. Once the extreme is confirmed the breakout is judged from
            # the candle after it, and that fall is the breakout.
            extreme_price = (
                first.price
                if second is None or signed(first.price) >= signed(second.price)
                else second.price
            )
            forming = second is None and any(
                signed(side.extreme_of(c)) >= signed(first.price) - params.level_tolerance * height
                for c in closed[trough_index + 1 :]
            )
            judgement = judge(
                closed,
                side=side,
                params=params,
                start_index=first_index,
                exceed_from=trough_index + 1,
                breakout_from=(second_index + 1)
                if complete and second_index is not None
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
            line = horizontal_neckline(neckline_level, trough.open_time, anchors[-1].open_time)
            boundaries = () if line is None else (line,)

        items = (
            evidence(
                "EXTREME_LEVELS",
                "the two extremes and the height they are judged against",
                **facts,  # type: ignore[arg-type]
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


class DoubleTopDetector(_DoubleDetector):
    pattern_type = PatternType.DOUBLE_TOP
    version = "double-top-detector-v1"
    side = Side.TOP


class DoubleBottomDetector(_DoubleDetector):
    pattern_type = PatternType.DOUBLE_BOTTOM
    version = "double-bottom-detector-v1"
    side = Side.BOTTOM
