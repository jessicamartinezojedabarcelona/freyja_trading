"""Rising and falling wedge detectors (POINT3-EXPANSION-001, first part).

Rules in ``docs/domain/detectores-de-expansion.md``. A wedge is the two-boundary channel of the
triangles and the rectangle (`pattern_channel`) whose boundaries **slope the same way and close
in**:

* rising wedge: both boundaries rise, the lower one faster, so the height shrinks;
* falling wedge: both boundaries fall, the upper one faster.

What sets it apart from the rest of the family is only the slopes and the convergence: a triangle
has a flat boundary, a symmetrical triangle boundaries that slope opposite ways, a rectangle
none, and a parallel channel that slopes the same way does not close in (a flag, if it follows a
mast, or nothing at all).

The tradition attaches a bias to each (rising: bearish, falling: bullish) but the detector does
**not** use it: like the triangles it watches both boundaries, and the first close beyond either one
is the breakout, recorded with its real direction. Whether the wedge reverses or continues what
came before is not a property of the figure: the trend before it is kept as context and the
breakout says the rest.
"""

from freyja_backend.domain.chart_pattern import PatternType
from freyja_backend.domain.pattern_channel import (
    Channel,
    ChannelDetector,
    falling,
    rising,
)
from freyja_backend.domain.pattern_detection import ContinuationParams


def closing_in(fit: Channel, params: ContinuationParams) -> bool:
    """The height at the last contact is at most `1 - wedge_convergence_min` of the height at the
    first one. Inclusive: exactly that much is enough."""
    return fit.gap_at_end <= (1 - params.wedge_convergence_min) * fit.height


class RisingWedgeDetector(ChannelDetector):
    pattern_type = PatternType.RISING_WEDGE
    version = "rising-wedge-detector-v1"

    def accepts(self, fit: Channel, params: ContinuationParams) -> bool:
        return (
            rising(fit.upper_rise, fit.height, params)
            and rising(fit.lower_rise, fit.height, params)
            and closing_in(fit, params)
        )


class FallingWedgeDetector(ChannelDetector):
    pattern_type = PatternType.FALLING_WEDGE
    version = "falling-wedge-detector-v1"

    def accepts(self, fit: Channel, params: ContinuationParams) -> bool:
        return (
            falling(fit.upper_rise, fit.height, params)
            and falling(fit.lower_rise, fit.height, params)
            and closing_in(fit, params)
        )
