"""Broadening formation detector (POINT3-EXPANSION-001, second part).

Rules in ``docs/domain/detectores-de-expansion.md``. A broadening formation is the two-boundary
channel of the triangles (`pattern_channel`) turned inside out: the price swings between two
boundaries that **move apart**, the upper one rising through ever higher highs and the lower one
falling through ever lower lows. It needs five swings (three of one kind and two of the other), not
the four of the rest of the family.

Because the upper boundary rises and the lower one falls, they diverge by construction: no
separate convergence rule is needed, and there is no apex, so the figure never expires for that
reason. What sets it apart from every other figure of the family is the pair of slopes: a
symmetrical triangle is its mirror (upper falls, lower rises), a wedge slopes both ways the same
way, and the rest have a flat boundary.

The tradition gives it no bias (context dependent) and neither does the detector: both boundaries
are watched and the first close beyond either one is the breakout, recorded with its real
direction. The trend before it is kept as context.
"""

from freyja_backend.domain.chart_pattern import PatternType
from freyja_backend.domain.pattern_channel import (
    Channel,
    ChannelDetector,
    falling,
    rising,
    strictly_higher,
    strictly_lower,
)
from freyja_backend.domain.pattern_detection import ContinuationParams


class BroadeningFormationDetector(ChannelDetector):
    pattern_type = PatternType.BROADENING_FORMATION
    version = "broadening-formation-detector-v1"
    min_swings = 5

    def accepts(self, fit: Channel, params: ContinuationParams) -> bool:
        return (
            rising(fit.upper_rise, fit.height, params)
            and falling(fit.lower_rise, fit.height, params)
            and strictly_higher(fit.highs)
            and strictly_lower(fit.lows)
        )
