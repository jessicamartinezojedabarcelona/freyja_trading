"""POINT3-REVERSAL-001: the rounding top and rounding bottom detectors.

A rounding top is a curve, so the series here are **built as curves**: closes that follow an exact
parabola (or a tent, or two humps) between a base and an apex. The parabolic fit is checked
against a second, independent least-squares solver, and the expected stories are written from the
rules in ``docs/domain/detectores-de-reversion.md``, section 8.
"""

from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest

from freyja_backend.domain.chart_pattern import (
    BoundaryRole,
    BreakoutDirection,
    PatternBias,
    PatternInstance,
    PatternState,
    PatternType,
    pattern_instance_from_document,
)
from freyja_backend.domain.market_data import Candle
from freyja_backend.domain.pattern_detection import (
    InvalidDetectionRequestError,
    ReversalParams,
    replay_detector,
)
from freyja_backend.domain.pattern_rounding import (
    RoundingBottomDetector,
    RoundingTopDetector,
    quadratic_fit,
)
from tests.unit.test_market_trend import STEP, UP, candle_at, zigzag
from tests.unit.test_pattern_detection import (
    context_for,
    facts_of,
    mirror,
    prior_compatible,
    states,
    the_one,
)

S = PatternState
CENTS = Decimal("0.01")


# -- the parabolic fit, exactly -----------------------------------------------------------------


def independent_fit(ys: list[Fraction]) -> tuple[Fraction, Fraction]:
    """Least squares by Gauss-Jordan elimination on the normal equations: another algorithm
    than the one under test (which uses Cramer's rule), so agreeing is evidence, not tautology."""
    zero = Fraction(0)
    n = len(ys)
    rows = [
        [sum((Fraction(x) ** (i + j) for x in range(n)), start=zero) for j in range(3)]
        + [sum((Fraction(x) ** i * y for x, y in enumerate(ys)), start=zero)]
        for i in range(3)
    ]
    for col in range(3):
        pivot = next(r for r in range(col, 3) if rows[r][col] != 0)
        rows[col], rows[pivot] = rows[pivot], rows[col]
        rows[col] = [v / rows[col][col] for v in rows[col]]
        for r in range(3):
            if r != col:
                factor = rows[r][col]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[col], strict=True)]
    c, b, q = rows[0][3], rows[1][3], rows[2][3]
    mean = sum(ys, start=zero) / n
    total = sum(((y - mean) ** 2 for y in ys), start=zero)
    residual = sum(((y - (c + b * x + q * x * x)) ** 2 for x, y in enumerate(ys)), start=zero)
    return q, 1 - residual / total


def fractions(*values: str | int) -> list[Fraction]:
    return [Fraction(str(v)) for v in values]


def test_a_perfect_parabola_is_fitted_exactly() -> None:
    # y = 3 + 2x - x^2 for x = 0..6
    ys = [Fraction(3 + 2 * x - x * x) for x in range(7)]
    assert quadratic_fit(ys) == (Fraction(-1), Fraction(1))
    assert quadratic_fit([Fraction(x * x) for x in range(5)]) == (Fraction(1), Fraction(1))


def test_a_straight_line_has_no_curvature_and_a_perfect_fit() -> None:
    assert quadratic_fit([Fraction(2 * x + 1) for x in range(8)]) == (Fraction(0), Fraction(1))


@pytest.mark.parametrize(
    "ys",
    [
        fractions(0, 2, 1, 3, 1, 4),
        fractions("1.5", "2.25", 2, "3.125", 5, 4, "0.5"),
        fractions(10, 12, 15, 14, 11, 9, 4),
        fractions(5, 5, 6, 5, 5, 7, 5, 5),
    ],
)
def test_the_fit_agrees_with_an_independent_solver_on_data_that_is_not_a_parabola(
    ys: list[Fraction],
) -> None:
    fitted = quadratic_fit(ys)
    assert fitted is not None
    assert fitted == independent_fit(ys)
    assert 0 <= fitted[1] < 1  # imperfect: some of the variance is left over


def test_there_is_nothing_to_fit_in_fewer_than_three_points_or_in_a_flat_series() -> None:
    assert quadratic_fit(fractions(1, 2)) is None
    assert quadratic_fit(fractions(4, 4, 4, 4, 4)) is None


def test_the_fit_is_exact_rational_arithmetic_never_a_float() -> None:
    q, r_squared = quadratic_fit(fractions("0.1", "0.2", "0.4", "0.7", "1.1")) or (0, 0)
    assert isinstance(q, Fraction) and isinstance(r_squared, Fraction)
    assert q == Fraction(1, 20)  # the second difference of tenths, exactly (0.1 would not be)


# -- building curves as candles -----------------------------------------------------------------


def dome_mids(
    n: int, base: int, height: int, *, shape: str = "round", peak: int | None = None
) -> list[Decimal]:
    """`n` closes between two base levels: 'round' (a parabola) or 'tent' (straight up, straight
    down). `peak` puts the apex off-centre (the two sides are then parabolas of different width)."""
    centre = Decimal(peak) if peak is not None else Decimal(n + 1) / 2
    out: list[Decimal] = []
    for x in range(1, n + 1):
        side_width = centre if Decimal(x) <= centre else Decimal(n + 1) - centre
        d = abs(Decimal(x) - centre) / side_width
        value = 1 - d * d if shape == "round" else 1 - d
        out.append(Decimal(base) + Decimal(height) * max(value, Decimal(0)))
    return out


def curve(
    *,
    n: int = 60,
    height: int = 17,
    shape: str = "round",
    peak: int | None = None,
    after: tuple[int, ...] = (116, 112, 108, 104, 104, 104),
    upside_down: bool = False,
) -> list[Candle]:
    """An uptrend that ends in a low at 118, then a curve of `n` candles back to 118, then
    `after`. `upside_down` turns it all over (p becomes 300 - p): a downtrend and a bowl."""
    prefix = zigzag(mirror([*UP, 118]) if upside_down else [*UP, 118], tail=0)
    mids = [*dome_mids(n, 118, height, shape=shape, peak=peak), Decimal(118), *map(Decimal, after)]
    if upside_down:
        mids = [Decimal(300) - mid for mid in mids]
    out = list(prefix)
    for k, mid in enumerate(mids, start=1):
        out.append(candle_at(prefix[-1].open_time + STEP * k, mid.quantize(CENTS), STEP))
    return out


def run(detector: Any, candles: list[Candle], **params: Any) -> tuple[PatternInstance, ...]:
    return replay_detector(detector, context_for(candles, **params), candles)


def complete_at_the_end(detector: Any, candles: list[Candle], **params: Any) -> list[Any]:
    """What the detector says about the whole series at its last instant, alone: the candidates
    that already have a right end. Unlike the history, it cannot be hidden by a figure that was
    invalidated earlier, while it was still forming."""
    result = detector.detect(context_for(candles, **params), candles)
    return [c for c in result.candidates if len(c.evaluation.anchors) == 3]


def completed(instances: tuple[PatternInstance, ...]) -> list[PatternInstance]:
    """The figures that got to have a right end: a dome that formed and then stopped being one
    is a (finished) instance too, but never a complete arc."""
    return [i for i in instances if any(len(e.anchors) == 3 for e in i.evaluations)]


# -- the rounding top, told from its rules ------------------------------------------------------


def test_a_rounding_top_forms_becomes_valid_and_is_broken_out_of() -> None:
    figure = the_one(run(RoundingTopDetector(), curve()), compatible=True)

    assert figure.pattern_type is PatternType.ROUNDING_TOP
    assert states(figure) == [
        S.FORMING,
        S.GEOMETRICALLY_VALID,
        S.BREAKOUT_PENDING_CONFIRMATION,
        S.CONFIRMED_DOWN,
    ]
    left, apex, right = figure.latest.anchors
    assert [a.label for a in figure.latest.anchors] == ["LEFT_END", "APEX", "RIGHT_END"]
    assert (left.kind.value, apex.kind.value, right.kind.value) == ("LOW", "HIGH", "LOW")
    assert apex.price > left.price and apex.price > right.price
    # The two ends are at the base: the arc leaves it and comes back to it.
    assert abs(right.price - left.price) < (apex.price - left.price) * Decimal("0.3")
    assert [a.label for a in figure.evaluations[0].anchors] == ["LEFT_END", "APEX"]  # forming
    assert figure.traditional_bias is PatternBias.BEARISH
    assert figure.detector_version == "rounding-top-detector-v1"


def test_the_right_end_is_a_closed_candle_known_when_it_closes_and_not_before() -> None:
    candles = curve()
    figure = the_one(run(RoundingTopDetector(), candles), compatible=True)
    right = figure.latest.anchors[-1]

    closing = next(c for c in candles if c.open_time == right.open_time)
    assert right.confirmed_at == closing.close_time  # no confirmation lag: a candle, not a pivot
    assert right.price == closing.low
    valid_at = next(e.evaluated_at for e in figure.evaluations if e.state is S.GEOMETRICALLY_VALID)
    assert valid_at == closing.close_time  # it becomes a figure the moment that candle closes
    before = [e for e in figure.evaluations if e.evaluated_at < closing.close_time]
    assert all(len(e.anchors) == 2 for e in before)


def test_the_base_and_the_arc_are_recorded_and_the_breakout_goes_through_the_base() -> None:
    figure = the_one(run(RoundingTopDetector(), curve()), compatible=True)
    roles = {b.role for b in figure.latest.boundaries}
    assert roles == {BoundaryRole.BASE, BoundaryRole.ARC}
    base = next(b for b in figure.latest.boundaries if b.role is BoundaryRole.BASE)
    left, apex, right = figure.latest.anchors
    assert [p.price for p in base.points] == [left.price, left.price]  # level of the left end
    assert base.contacts == (left.open_time, right.open_time)
    arc = next(b for b in figure.latest.boundaries if b.role is BoundaryRole.ARC)
    assert [p.price for p in arc.points] == [left.price, apex.price, right.price]
    assert arc.contacts == (apex.open_time,)
    breakout = figure.latest.breakout
    assert breakout is not None and breakout.confirmed
    assert breakout.boundary is BoundaryRole.BASE and breakout.direction is BreakoutDirection.DOWN


def test_the_result_explains_how_round_it_is() -> None:
    figure = the_one(run(RoundingTopDetector(), curve()), compatible=True)
    arc = facts_of(figure, "ROUNDING_ARC")
    assert arc["fit_r_squared"] >= Decimal("0.999")
    assert arc["curvature"] < 0
    assert Decimal("0.25") <= arc["apex_position"] <= Decimal("0.75")
    assert arc["top_dwell"] >= Decimal("0.40")
    assert 30 <= arc["arc_candles"] <= 150
    assert arc["height"] > 0
    assert facts_of(figure, "PRIOR_TREND") == {
        "compatible": True,
        "required": "UPTREND",
        "state": "UPTREND",
    }


def test_a_rounding_bottom_is_the_same_story_upside_down() -> None:
    figure = the_one(run(RoundingBottomDetector(), curve(upside_down=True)), compatible=True)

    assert figure.pattern_type is PatternType.ROUNDING_BOTTOM
    assert states(figure)[0] is S.FORMING and states(figure)[-1] is S.CONFIRMED_UP
    left, apex, right = figure.latest.anchors
    assert (left.kind.value, apex.kind.value, right.kind.value) == ("HIGH", "LOW", "HIGH")
    assert apex.price < left.price and apex.price < right.price  # the bowl's bottom
    assert facts_of(figure, "ROUNDING_ARC")["curvature"] < 0  # open downwards, in the turned axis
    assert facts_of(figure, "PRIOR_TREND")["state"] == "DOWNTREND"
    assert figure.traditional_bias is PatternBias.BULLISH


def test_a_top_finds_no_bottom_and_a_bottom_no_top() -> None:
    assert not completed(run(RoundingBottomDetector(), curve()))
    assert not completed(run(RoundingTopDetector(), curve(upside_down=True)))


# -- what is not a rounding top -----------------------------------------------------------------


def test_a_pointed_peak_fits_a_parabola_well_and_is_still_not_rounded() -> None:
    """A tent (straight up, straight down) is fitted almost perfectly by a parabola, which is why
    the fit alone cannot say 'rounded': the price must linger near the top, and a tent does not."""
    tent = curve(shape="tent")
    closes = [Fraction(c.close) for c in tent[121:182]]
    fitted = quadratic_fit(closes)
    assert fitted is not None and fitted[1] > Fraction(9, 10)  # it does fit a parabola well
    assert not completed(run(RoundingTopDetector(), tent))  # ... and it is refused all the same


def test_an_arc_that_is_too_short_is_a_spike_not_a_dome() -> None:
    short = curve(n=20, height=17)
    assert not completed(run(RoundingTopDetector(), short))
    allowed = run(RoundingTopDetector(), short, min_arc_candles=10)
    assert the_one(allowed).state in (
        S.GEOMETRICALLY_VALID,
        S.CONFIRMED_DOWN,
        S.BREAKOUT_PENDING_CONFIRMATION,
    )


def test_an_arc_that_is_too_long_is_a_trend_not_a_dome() -> None:
    detector = RoundingTopDetector()
    assert not completed(run(detector, curve(n=90), max_arc_candles=60))
    assert not complete_at_the_end(detector, curve(n=90), max_arc_candles=60)
    assert completed(run(detector, curve(n=90)))  # within the default 150
    assert complete_at_the_end(detector, curve(n=90))


def test_an_apex_far_off_centre_is_not_a_rounded_top() -> None:
    """Only the position of the apex differs between the two runs: the fit is relaxed in both so
    that the rule under test is the one that decides."""
    lopsided = curve(n=80, peak=12)  # the top is a seventh of the way along
    loose = {"min_arc_candles": 10, "arc_fit_min": Decimal("0.5")}
    assert not completed(run(RoundingTopDetector(), lopsided, **loose))
    relaxed = run(RoundingTopDetector(), lopsided, apex_position_band=Decimal("0.1"), **loose)
    assert completed(relaxed)
    arc = facts_of(the_one(completed(relaxed)), "ROUNDING_ARC")
    assert arc["apex_position"] < Decimal("0.25")  # it really is off-centre


def test_a_curve_that_is_not_smooth_is_refused_by_the_fit() -> None:
    strict = run(RoundingTopDetector(), curve(), arc_fit_min=Decimal("0.99999"))
    assert the_one(strict, compatible=True).state is S.CONFIRMED_DOWN  # an exact parabola passes
    ragged = curve()
    for k in range(125, 185, 3):  # knock every third close far off the curve
        ragged[k] = candle_at(
            ragged[k].open_time, ragged[k].close - Decimal(6) * (1 if k % 2 else -1), STEP
        )
    assert not [
        i for i in run(RoundingTopDetector(), ragged) if i.state in (S.GEOMETRICALLY_VALID,)
    ]


def piecewise(mids: list[Decimal], base: Decimal = Decimal(118)) -> list[Candle]:
    prefix = zigzag([*UP, int(base)], tail=0)
    out = list(prefix)
    for k, mid in enumerate(mids, start=1):
        out.append(candle_at(prefix[-1].open_time + STEP * k, mid.quantize(CENTS), STEP))
    return out


def test_a_price_that_falls_through_the_base_did_not_return_to_it() -> None:
    """The climb is a dome, but the descent goes straight through the base: there is no return to
    it, so there is no right end and no figure (a fall is not a rounded top)."""
    candles = piecewise([*dome_mids(60, 118, 17)[:40], Decimal(100), Decimal(90), Decimal(90)])
    assert not completed(run(RoundingTopDetector(), candles))


def test_a_higher_extreme_before_the_price_returns_to_the_base_means_this_is_not_the_top() -> None:
    """Up to 130, a dip to 126, up again to 138, and only then back to the base: 130 is not the
    top of this arc, so it never becomes a valid one."""
    up_a = [Decimal(118) + Decimal(12) * (1 - ((Decimal(20) - x) / 20) ** 2) for x in range(1, 21)]
    dip = [Decimal(130) - Decimal(4) * Decimal(k) / 5 for k in range(1, 6)]
    up_b = [Decimal(126) + Decimal(12) * (1 - ((Decimal(20) - x) / 20) ** 2) for x in range(1, 21)]
    down = [Decimal(138) - Decimal(20) * (Decimal(k) / 12) ** 2 for k in range(1, 13)]
    candles = piecewise([*up_a, *dip, *up_b, *down, Decimal(118), Decimal(114), Decimal(110)])
    found = run(RoundingTopDetector(), candles)
    at_first_top = [
        i for i in found if abs(i.latest.anchors[1].price - Decimal("130.5")) < Decimal(1)
    ]
    assert all(i.state is S.INVALIDATED for i in at_first_top)  # if it ever formed, it ended


def test_the_figure_forms_only_when_the_climb_already_curves_like_a_dome() -> None:
    candles = curve()
    detector = RoundingTopDetector()
    figure = the_one(run(detector, candles), compatible=True)
    apex = figure.latest.anchors[1]
    at = candles[[c.open_time for c in candles].index(apex.open_time) + 12].close_time
    upto = [c for c in candles if c.close_time <= at]
    result = detector.detect(context_for(candles).at(at), upto)
    (forming,) = [
        c for c in result.candidates if c.evaluation.anchors[0] == figure.latest.anchors[0]
    ]
    assert forming.evaluation.state is S.FORMING and len(forming.evaluation.anchors) == 2
    assert forming.evaluation.boundaries == () and forming.evaluation.breakout is None


def test_without_an_uptrend_before_it_the_dome_is_seen_but_flagged() -> None:
    """A dome that starts after a fall: seen, the fact recorded, never dropped or assumed."""
    prefix = zigzag([300 - int(p) for p in UP], tail=0)  # a downtrend that ends in a low at 170
    base = int(prefix[-1].close)
    mids = [*dome_mids(60, base, 17), Decimal(base), Decimal(base - 4), Decimal(base - 8)]
    candles = list(prefix)
    for k, mid in enumerate(mids, start=1):
        candles.append(candle_at(prefix[-1].open_time + STEP * k, mid.quantize(CENTS), STEP))
    found = run(RoundingTopDetector(), candles)
    assert [i for i in found if len(i.latest.anchors) == 3]
    assert all(not prior_compatible(i) for i in found)
    assert all(facts_of(i, "PRIOR_TREND")["state"] != "UPTREND" for i in found)


# -- each rule on its own: shapes that pass everything but one ------------------------------
#
# The climb of a dome is a half parabola that ends at the apex; the descent is another that starts
# there. Built separately, either half can be made to fail while the other is perfect, so that the
# rule under test is the only one that can refuse the figure. Each test also shows the same data
# accepted once that one rule is relaxed: it is the rule that decides, not something else.


def rising(n: int, base: int, height: int) -> list[Decimal]:
    """A half parabola from the base up to the apex, `n` candles, curving over at the top."""
    return [
        Decimal(base) + Decimal(height) * (1 - ((Decimal(n) - x) / n) ** 2) for x in range(1, n + 1)
    ]


def falling(n: int, base: int, height: int) -> list[Decimal]:
    """A half parabola from the apex down to the base, `n` candles."""
    return [Decimal(base) + Decimal(height) * (1 - (Decimal(x) / n) ** 2) for x in range(1, n + 1)]


def straight_down(n: int, base: int, height: int) -> list[Decimal]:
    return [Decimal(base) + Decimal(height) * (1 - Decimal(x) / n) for x in range(1, n + 1)]


def jagged(mids: list[Decimal], amplitude: int) -> list[Decimal]:
    """Every third close knocked off its curve, up and down in turn."""
    return [
        mid + Decimal(amplitude) * (1 if (k // 3) % 2 else -1) if k % 3 == 0 else mid
        for k, mid in enumerate(mids)
    ]


TAIL = [Decimal(116), Decimal(112), Decimal(108), Decimal(104)]


def test_a_straight_descent_fits_a_parabola_well_but_not_as_well_as_a_strict_fit_asks() -> None:
    """The same arc, curved up and straight down, is accepted by the default fit (0.85) and
    refused by a strict one (0.99): it is the threshold on the whole arc that decides. Its dwell
    is relaxed in both runs, because that is another rule (tested below)."""
    mids = [*rising(30, 118, 17), *straight_down(30, 118, 17), Decimal(118), *TAIL]
    candles = piecewise(mids)
    lenient = {"min_top_dwell": Decimal("0.2")}
    assert completed(run(RoundingTopDetector(), candles, **lenient))
    assert not completed(
        run(RoundingTopDetector(), candles, arc_fit_min=Decimal("0.99"), **lenient)
    )


def test_a_dome_with_a_straight_descent_does_not_dwell_enough_on_top() -> None:
    """Curved on the way up and straight on the way down: the whole arc fits a parabola well, and
    only a third of its closes are near the top, where a real dome has about half."""
    mids = [*rising(30, 118, 17), *straight_down(30, 118, 17), Decimal(118), *TAIL]
    candles = piecewise(mids)
    assert not completed(run(RoundingTopDetector(), candles))
    assert completed(run(RoundingTopDetector(), candles, min_top_dwell=Decimal("0.2")))


def test_a_straight_climb_is_not_the_beginning_of_a_dome_at_any_instant() -> None:
    """The climb is the one thing known while the dome is still forming: if it is straight, the
    figure is not forming at all (a straight line fits a parabola perfectly and dwells nowhere)."""
    tent = curve(shape="tent")
    detector = RoundingTopDetector()
    for k in range(125, len(tent) - 1):
        at = tent[k].close_time
        upto = [c for c in tent if c.close_time <= at]
        assert detector.detect(context_for(tent).at(at), upto).candidates == (), at
    relaxed = ReversalParams(min_top_dwell=Decimal("0.2"))
    assert any(
        detector.detect(
            context_for(tent, min_top_dwell=relaxed.min_top_dwell).at(tent[k].close_time),
            [c for c in tent if c.close_time <= tent[k].close_time],
        ).candidates
        for k in range(125, len(tent) - 1)
    )


def cubic_rising(n: int, base: int, height: int) -> list[Decimal]:
    """A climb that eases off like a cube rather than a square: a parabola fits it very well, but
    not perfectly."""
    return [
        Decimal(base) + Decimal(height) * (1 - ((Decimal(n) - x) / n) ** 3) for x in range(1, n + 1)
    ]


def test_a_climb_that_only_roughly_fits_a_parabola_is_not_a_dome_forming_under_a_strict_fit() -> (
    None
):
    """The same climb forms a dome under the default fit and not under a very strict one: while
    the dome is still forming, the fit on the left half is the rule in play."""
    candles = piecewise([*cubic_rising(30, 118, 17), *falling(30, 118, 17), Decimal(118), *TAIL])
    detector = RoundingTopDetector()

    def forming(**params: Any) -> bool:
        return any(
            detector.detect(
                context_for(candles, **params).at(candles[k].close_time),
                [c for c in candles if c.close_time <= candles[k].close_time],
            ).candidates
            for k in range(125, len(candles) - 1)
        )

    assert forming()
    assert not forming(arc_fit_min=Decimal("0.999"))


def test_a_smooth_arc_narrower_than_the_minimum_is_a_spike() -> None:
    """15 candles up and 10 down, each side a clean half parabola: the fit, the dwell and the
    position of the apex are all fine, and at 25 candles it is simply too narrow."""
    narrow = piecewise([*rising(15, 118, 17), *falling(10, 118, 17), Decimal(118), *TAIL])
    assert not complete_at_the_end(RoundingTopDetector(), narrow)
    assert complete_at_the_end(RoundingTopDetector(), narrow, min_arc_candles=20)


def test_a_climb_shorter_than_half_the_minimum_is_too_abrupt_to_be_the_start_of_a_dome() -> None:
    """12 candles up and 22 down: 34 in all, so the minimum width of the whole arc is met, and
    the apex is a third of the way along. It is the climb, shorter than half the minimum (15),
    that is too abrupt."""
    abrupt = piecewise([*rising(12, 118, 17), *falling(22, 118, 17), Decimal(118), *TAIL])
    assert not complete_at_the_end(RoundingTopDetector(), abrupt)
    assert complete_at_the_end(RoundingTopDetector(), abrupt, min_arc_candles=20)


def test_a_climb_too_small_to_matter_is_not_a_dome_forming() -> None:
    tiny = piecewise([*rising(30, 118, 3), *falling(30, 118, 3), Decimal(118), *TAIL])
    detector = RoundingTopDetector()
    assert not [
        i for i in run(detector, tiny) if i.latest.anchors[1].price - i.latest.anchors[0].price > 0
    ]
    relaxed = run(detector, tiny, min_height_fraction=Decimal("0.05"))
    assert relaxed


def test_a_gap_through_the_base_is_not_a_return_to_it() -> None:
    """A long, clean dome whose last candle before the base is a plunge far below it: there is
    no return to the base, only a fall through it. One outlier barely dents a long arc's fit, so
    it is the check on the return that refuses it."""
    long_dome = dome_mids(140, 118, 17)
    candles = piecewise([*long_dome[:131], Decimal(100), Decimal(96), Decimal(92)])
    detector = RoundingTopDetector()
    assert not completed(run(detector, candles))
    assert not complete_at_the_end(detector, candles)
    # The very same dome, with the descent left to reach the base on its own, is a figure.
    assert complete_at_the_end(detector, piecewise([*long_dome, Decimal(118), *TAIL]))


def test_the_apex_is_the_highest_point_of_the_arc_it_belongs_to() -> None:
    """A slight bump to the right of the top rises above it, before the price is back at the
    base. The figure's apex is then the bump, never the lower point to its left."""
    mids = dome_mids(60, 118, 17)
    mids[34] = mids[34] + Decimal("1.5")  # a bump on the way down, higher than the top
    candles = piecewise([*mids, Decimal(118), *TAIL])
    done = completed(run(RoundingTopDetector(), candles))
    highest = max(c.high for c in candles[120:])
    assert all(i.latest.anchors[1].price == highest for i in done)


def test_a_higher_extreme_after_the_apex_and_before_the_base_takes_the_apex_away() -> None:
    """Up to 135, a real dip to 126 (a confirmed low, so the two highs do not merge), up again to
    140 and only then down to the base. Whatever the detector calls a complete arc here, its apex
    is the highest point: 135 is not the top of an arc that goes on to 140."""
    ramp_down = [Decimal(135) - Decimal(9) * Decimal(k) / 8 for k in range(1, 9)]
    ramp_up = [Decimal(126) + Decimal(14) * Decimal(k) / 8 for k in range(1, 9)]
    candles = piecewise(
        [*rising(30, 118, 17), *ramp_down, *ramp_up, *falling(30, 118, 22), Decimal(118), *TAIL]
    )
    highest = max(c.high for c in candles[121:])
    detector = RoundingTopDetector()
    for candidate in complete_at_the_end(detector, candles):
        assert candidate.evaluation.anchors[1].price == highest
    for figure in completed(run(detector, candles)):
        assert figure.latest.anchors[1].price == highest


def test_a_bump_above_the_apex_that_is_not_yet_a_pivot_already_takes_the_apex_away() -> None:
    """A single candle above the top, on the way down. It needs three candles after it to be a
    pivot, and until then the top it overtook must not be offered as the apex of the arc."""
    mids = dome_mids(60, 118, 17)
    mids[34] = mids[34] + Decimal("1.5")
    candles = piecewise([*mids, Decimal(118), *TAIL])
    detector = RoundingTopDetector()
    bump = max(range(121, len(candles)), key=lambda k: candles[k].high)
    old_apex = max(c.high for c in candles[121:bump])
    for k in (bump + 1, bump + 2):  # before it has the three candles that make it a pivot
        at = candles[k].close_time
        upto = [c for c in candles if c.close_time <= at]
        result = detector.detect(context_for(candles).at(at), upto)
        assert not [c for c in result.candidates if c.evaluation.anchors[1].price == old_apex], (
            f"the old top was offered as the apex at {at}"
        )


def test_a_long_arc_that_has_just_completed_is_not_stale_for_its_length() -> None:
    """Age counts from the last anchor: the arc took 140 candles and the price has held above
    its base for 25 more, which is nothing for a figure that has only just completed."""
    hold = [Decimal(122)] * 25
    candles = piecewise([*dome_mids(140, 118, 17), Decimal(118), *hold])
    figure = the_one(completed(run(RoundingTopDetector(), candles)), compatible=True)
    assert figure.state is S.GEOMETRICALLY_VALID
    assert not any(e.invalidation_reasons for e in figure.evaluations)


# -- no look-ahead, and the instance is a proper one --------------------------------------------


def wild(candles: list[Candle], after: datetime) -> list[Candle]:
    return [
        c if c.close_time <= after else candle_at(c.open_time, Decimal(1 + i % 2) * 5000, STEP)
        for i, c in enumerate(candles)
    ]


@pytest.mark.parametrize(
    ("detector", "upside_down"), [(RoundingTopDetector(), False), (RoundingBottomDetector(), True)]
)
def test_a_rounding_figure_at_any_instant_depends_only_on_what_was_closed_by_then(
    detector: Any, upside_down: bool
) -> None:
    candles = curve(upside_down=upside_down)
    seen = False
    for index in range(len(candles) - 1):
        at = candles[index].close_time
        upto = [c for c in candles if c.close_time <= at]
        context = context_for(candles).at(at)
        past = detector.detect(context, upto)
        assert detector.detect(context, candles) == past, f"at {at}"
        assert detector.detect(context, wild(candles, at)) == past, f"at {at}"
        seen = seen or bool(past.candidates)
    assert seen


def test_the_history_is_the_same_whatever_comes_later() -> None:
    candles = curve()
    detector = RoundingTopDetector()
    for cut in (len(candles) - 30, len(candles) - 8):
        at = candles[cut].close_time
        upto = [c for c in candles if c.close_time <= at]
        assert replay_detector(detector, context_for(candles).at(at), candles) == replay_detector(
            detector, context_for(upto).at(at), upto
        )


def test_an_instance_of_it_survives_the_document_round_trip() -> None:
    figure = the_one(run(RoundingTopDetector(), curve()), compatible=True)
    assert pattern_instance_from_document(figure.document()) == figure


def test_an_arc_cannot_be_required_longer_than_it_may_be() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="longer than it may be"):
        ReversalParams(min_arc_candles=100, max_arc_candles=50)
    for bad in (
        {"arc_fit_min": Decimal(0)},
        {"min_top_dwell": Decimal(1)},
        {"apex_position_band": Decimal("1.5")},
        {"min_arc_candles": 0},
        {"max_arc_candles": True},
    ):
        with pytest.raises(InvalidDetectionRequestError):
            ReversalParams(**bad)
