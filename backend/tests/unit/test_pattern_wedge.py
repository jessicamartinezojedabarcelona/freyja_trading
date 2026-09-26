"""POINT3-EXPANSION-001 (first part): the rising and falling wedge detectors.

Series are built leg by leg (ten candles per leg, prices in exact tenths), so every contact, line
and breakout can be read off the numbers and the expected story written from the rules in
``docs/domain/detectores-de-expansion.md``, never from the code under test. A swing "at 132" has
its high at 132.5 and a swing "at 116" its low at 115.5.
"""

import ast
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from freyja_backend.domain import pattern_wedge
from freyja_backend.domain.chart_pattern import (
    BoundaryPoint,
    BoundaryRole,
    BreakoutDirection,
    InvalidationReason,
    PatternBias,
    PatternRole,
    PatternState,
    PatternType,
)
from freyja_backend.domain.market_context import MissingDataReason
from freyja_backend.domain.market_structure import Pivot, PivotKind, PivotStatus
from freyja_backend.domain.pattern_channel import (
    AscendingTriangleDetector,
    Channel,
    DescendingTriangleDetector,
    RectangleDetector,
    SymmetricalTriangleDetector,
)
from freyja_backend.domain.pattern_detection import (
    DEFAULT_CONTINUATION_PARAMS,
    ContinuationParams,
    InvalidDetectionRequestError,
)
from freyja_backend.domain.pattern_flag import (
    BearFlagDetector,
    BearPennantDetector,
    BullFlagDetector,
    BullPennantDetector,
)
from freyja_backend.domain.pattern_wedge import FallingWedgeDetector, RisingWedgeDetector
from tests.unit.test_market_trend import T0, TF, UP, candle_at, random_walk, zigzag
from tests.unit.test_pattern_channel import (
    context_for,
    facts_of,
    figure_of,
    history,
    labels,
    mirror,
    states,
    the_figure,
    wild_future,
)

S = PatternState
D = Decimal
REPO = Path(__file__).resolve().parents[3]

DETECTORS = [RisingWedgeDetector(), FallingWedgeDetector()]

# The price climbs to 130 and falls back to 116, then bounces between two lines that both rise and
# close in: highs at 132, 134 and 135 and lows at 121 and 126 (the first swings, 130 and 116, are
# before the figure). Then it goes on either way.
RISING = [*UP, 116, 132, 121, 134, 126, 135]


# -- the two figures, told from their rules ------------------------------------------------------


def test_a_rising_wedge_is_valid_and_goes_the_way_the_price_breaks() -> None:
    down = the_figure(RisingWedgeDetector(), [*RISING, 112])

    assert down.pattern_type is PatternType.RISING_WEDGE
    assert down.traditional_bias is PatternBias.BEARISH
    assert {PatternRole.REVERSAL, PatternRole.CONTINUATION, PatternRole.COMPRESSION} <= (
        down.traditional_roles
    )
    assert states(down)[0] is S.GEOMETRICALLY_VALID and S.FORMING not in states(down)
    assert states(down)[-1] is S.CONFIRMED_DOWN
    assert labels(down) == ["UPPER_1", "LOWER_1", "UPPER_2", "LOWER_2", "UPPER_3"]
    upper, lower = down.latest.boundaries
    assert upper.points[0].price < upper.points[-1].price  # the ceiling rises...
    assert lower.points[0].price < lower.points[-1].price  # ...and so does the floor
    breakout = down.latest.breakout
    assert breakout is not None and breakout.confirmed
    assert breakout.direction is BreakoutDirection.DOWN and breakout.boundary is BoundaryRole.LOWER
    assert down.detector_version == "rising-wedge-detector-v1"
    assert down.parameter_version == "continuation-params-v1"
    channel = facts_of(down, "CHANNEL")
    assert channel["upper_rise"] == D(3) and channel["lower_rise"] == D(10)  # the floor is steeper
    assert channel["height"] == D("14.5") and channel["gap_at_end"] == D("7.5")


def test_the_bias_of_a_wedge_is_not_its_breakout() -> None:
    """A rising wedge is traditionally bearish, and here it breaks out upwards: the breakout is
    recorded as it happened and nothing forces it into the tradition. The same the other way."""
    up = the_figure(RisingWedgeDetector(), [*RISING, 142])
    assert (
        up.traditional_bias is PatternBias.BEARISH
    )  # what the tradition expects: a fact of the type
    assert states(up)[-1] is S.CONFIRMED_UP
    assert up.latest.breakout is not None
    assert up.latest.breakout.direction is BreakoutDirection.UP
    assert up.latest.breakout.boundary is BoundaryRole.UPPER
    falling_up = the_figure(FallingWedgeDetector(), mirror([*RISING, 112]))
    assert falling_up.traditional_bias is PatternBias.BULLISH
    assert states(falling_up)[-1] is S.CONFIRMED_UP  # the tradition and the breakout agree here
    falling_down = the_figure(FallingWedgeDetector(), mirror([*RISING, 142]))
    assert states(falling_down)[-1] is S.CONFIRMED_DOWN  # and here they do not
    assert falling_down.traditional_bias is PatternBias.BULLISH


def test_a_falling_wedge_is_the_same_story_upside_down() -> None:
    figure = the_figure(FallingWedgeDetector(), mirror([*RISING, 112]))

    assert figure.pattern_type is PatternType.FALLING_WEDGE
    assert labels(figure) == ["LOWER_1", "UPPER_1", "LOWER_2", "UPPER_2", "LOWER_3"]
    upper, lower = figure.latest.boundaries
    assert upper.points[0].price > upper.points[-1].price  # the ceiling falls...
    assert lower.points[0].price > lower.points[-1].price  # ...and so does the floor
    channel = facts_of(figure, "CHANNEL")
    assert channel["upper_rise"] == D(-10) and channel["lower_rise"] == D(
        -3
    )  # the ceiling is steeper
    assert states(figure)[-1] is S.CONFIRMED_UP


def test_the_trend_before_a_wedge_is_context_only() -> None:
    """The trend that came before is recorded, and remembering it never changes an answer: the
    figure is the same whether that trend is known beforehand or worked out at each instant."""
    candles = zigzag([*RISING, 112])
    detector = RisingWedgeDetector()
    figure = figure_of(history(detector, candles))
    assert set(facts_of(figure, "PRIOR_TREND")) == {"state"}
    shared = context_for(candles)
    warmed = [
        detector.detect(
            shared.at(c.close_time), [k for k in candles if k.close_time <= c.close_time]
        )
        for c in candles[110:]
    ]
    cold = [
        detector.detect(
            context_for(candles).at(c.close_time),
            [k for k in candles if k.close_time <= c.close_time],
        )
        for c in candles[110:]
    ]
    assert warmed == cold


def test_the_evidence_of_a_wedge_explains_its_lines_and_its_breakout() -> None:
    figure = the_figure(RisingWedgeDetector(), [*RISING, 112])
    codes = {item.code for item in figure.latest.evidence}
    assert {"CHANNEL", "PRIOR_TREND", "BREAKOUT_SCAN", "BREAKOUT_VOLUME"} <= codes
    assert facts_of(figure, "CHANNEL")["upper_contacts"] == 3


# -- what is a wedge and what is not -------------------------------------------------------------

PARALLEL_UP = [*UP, 116, 134, 120, 138, 124, 142]  # both boundaries rise, by the same amount
TRIANGLES: dict[str, tuple[Any, list[int | str]]] = {
    "ascending": (AscendingTriangleDetector(), [*UP, 118, 130, 122, 130, 126, 130, 136]),
    "symmetrical": (SymmetricalTriangleDetector(), [*UP, 116, 128, 118, 126, 120, 130]),
    "rectangle": (RectangleDetector(), [*UP, 118, 130, 118, 130, 118, 130, 137]),
}


def test_parallel_boundaries_that_slope_the_same_way_are_a_channel_not_a_wedge() -> None:
    candles = zigzag(PARALLEL_UP)
    for detector in DETECTORS:
        assert history(detector, candles) == (), detector.version
    for detector in DETECTORS:
        assert history(detector, zigzag(mirror(PARALLEL_UP))) == (), detector.version


def test_a_wedge_is_not_any_other_figure_of_the_family() -> None:
    wedge = zigzag([*RISING, 112])
    others = [
        AscendingTriangleDetector(),
        DescendingTriangleDetector(),
        SymmetricalTriangleDetector(),
        RectangleDetector(),
        BullFlagDetector(),
        BearFlagDetector(),
        BullPennantDetector(),
        BearPennantDetector(),
    ]
    for detector in others:
        assert history(detector, wedge) == (), detector.version
        assert history(detector, zigzag(mirror([*RISING, 112]))) == (), detector.version


@pytest.mark.parametrize("name", list(TRIANGLES))
def test_the_triangles_and_the_rectangle_are_not_wedges(name: str) -> None:
    detector, extremes = TRIANGLES[name]
    assert history(detector, zigzag(extremes))  # it is that figure...
    for wedge in DETECTORS:
        assert history(wedge, zigzag(extremes)) == (), (name, wedge.version)  # ...and not a wedge


def test_a_rising_wedge_is_not_found_in_a_falling_one_and_the_other_way_round() -> None:
    assert history(FallingWedgeDetector(), zigzag([*RISING, 112])) == ()
    assert history(RisingWedgeDetector(), zigzag(mirror([*RISING, 112]))) == ()


# -- breakouts, failure and the end of the figure ------------------------------------------------


def test_a_breakout_that_closes_back_inside_fails_and_stays_failed() -> None:
    # Up through the ceiling by less than the margin, back inside, then down through the floor: the
    # first attempt is the one on record and it failed; what came after does not undo it.
    figure = the_figure(RisingWedgeDetector(), [*RISING, 138, 125, 118], tail_to=117)
    assert states(figure)[-1] is S.FAILED_BREAKOUT and figure.is_terminal
    assert figure.latest.breakout is not None
    assert figure.latest.breakout.direction is BreakoutDirection.UP
    assert not figure.latest.breakout.confirmed


def line_at(points: Sequence[BoundaryPoint], at: datetime) -> Decimal:
    """The straight line through the first and the last point of a boundary, at a moment."""
    first, last = points[0], points[-1]
    slope = (last.price - first.price) / D((last.time - first.time).total_seconds())
    return Decimal(first.price + slope * D((at - first.time).total_seconds()))


def test_an_unresolved_wedge_ends_at_its_apex_if_the_price_never_left() -> None:
    """The price walks between the two lines, midway, until they meet and past it. It never makes a
    swing and never closes beyond a line, so nothing changes the figure but time: it ran its
    course."""
    base = zigzag(RISING, tail=0)
    # The lines of the figure once all its contacts are known (the last one is only confirmed
    # after some candles), read off the same series with a way out.
    upper, lower = the_figure(RisingWedgeDetector(), [*RISING, 112]).latest.boundaries
    tail = []
    for n in range(1, 60):
        opened = base[-1].open_time + TF.duration * n
        closing = opened + TF.duration  # the lines are read at the close of each candle
        mid = (line_at(upper.points, closing) + line_at(lower.points, closing)) / 2
        tail.append(candle_at(opened, mid, TF.duration))
    figure = figure_of(history(RisingWedgeDetector(), [*base, *tail]))
    assert figure.state is S.INVALIDATED
    assert figure.latest.invalidation_reasons == (InvalidationReason.TOO_LONG,)
    assert figure.latest.breakout is None


def test_a_wedge_needs_its_contacts_its_time_and_its_size() -> None:
    candles = zigzag([*RISING, 112])
    assert history(RisingWedgeDetector(), candles, min_channel_candles=999) == ()
    assert history(RisingWedgeDetector(), candles, min_height_fraction=D("0.99")) == ()
    assert history(RisingWedgeDetector(), zigzag([*UP, 116, 132, 121])) == ()  # a floor with one


# -- the thresholds, exactly at their value and at both neighbours -------------------------------


def channel(*, height: str, gap_at_end: str, upper_rise: str, lower_rise: str) -> Channel:
    pivot = Pivot(PivotKind.HIGH, PivotStatus.CONFIRMED, T0, D(100), T0 + TF.duration)
    return Channel(
        window=(pivot,) * 4,
        upper=lambda _at: D(0),
        lower=lambda _at: D(0),
        highs=(pivot, pivot),
        lows=(pivot, pivot),
        height=D(height),
        gap_at_end=D(gap_at_end),
        upper_rise=D(upper_rise),
        lower_rise=D(lower_rise),
        reference=D(50),
        first_index=0,
        last_index=30,
        expires_after=None,
    )


@pytest.mark.parametrize(
    ("gap", "expected"),
    # A height of 20 must end at most 0.70 of itself: 14 or less.
    [("13.99", True), ("14", True), ("14.01", False), ("20", False)],
)
@pytest.mark.parametrize("rising_wedge", [True, False])
def test_a_wedge_must_close_in_by_at_least_thirty_percent(
    gap: str, expected: bool, rising_wedge: bool
) -> None:
    upper, lower = ("5", "9") if rising_wedge else ("-9", "-5")
    detector = RisingWedgeDetector() if rising_wedge else FallingWedgeDetector()
    fit = channel(height="20", gap_at_end=gap, upper_rise=upper, lower_rise=lower)
    assert detector.accepts(fit, DEFAULT_CONTINUATION_PARAMS) is expected


@pytest.mark.parametrize(
    ("upper", "lower", "expected"),
    # Both must rise by at least 0.15 of the height (20): 3. Flat, falling or short is not a wedge.
    [
        ("3", "6", True),  # exactly the minimum on the ceiling
        ("2.99", "6", False),
        ("3", "3", True),  # (not converging by slope alone: the gap decides, here it is given)
        ("3", "2.99", False),
        ("-3", "6", False),  # opposite ways: a symmetrical triangle
        ("0", "6", False),  # a flat ceiling: an ascending triangle
        ("6", "0", False),
    ],
)
def test_both_boundaries_must_rise_by_the_minimum_for_a_rising_wedge(
    upper: str, lower: str, expected: bool
) -> None:
    fit = channel(height="20", gap_at_end="10", upper_rise=upper, lower_rise=lower)
    assert RisingWedgeDetector().accepts(fit, DEFAULT_CONTINUATION_PARAMS) is expected
    mirrored = channel(
        height="20", gap_at_end="10", upper_rise=str(-D(lower)), lower_rise=str(-D(upper))
    )
    assert FallingWedgeDetector().accepts(mirrored, DEFAULT_CONTINUATION_PARAMS) is expected


@pytest.mark.parametrize(
    "bad",
    [
        {"wedge_convergence_min": D(0)},
        {"wedge_convergence_min": D(1)},
        {"wedge_convergence_min": 0.3},
        {"wedge_convergence_min": D("0.2")},  # parallel up to what already counts as converging
        {"parallel_tolerance": D("0.3")},
    ],
)
def test_parameters_that_make_no_sense_are_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(InvalidDetectionRequestError):
        ContinuationParams(**bad)


# -- units, no look-ahead, determinism -----------------------------------------------------------


def test_each_detector_is_its_own_unit_with_its_own_version() -> None:
    assert {d.version for d in DETECTORS} == {
        "rising-wedge-detector-v1",
        "falling-wedge-detector-v1",
    }
    assert {d.pattern_type for d in DETECTORS} == {
        PatternType.RISING_WEDGE,
        PatternType.FALLING_WEDGE,
    }


def test_data_that_is_not_fit_judges_no_figure_and_says_why() -> None:
    candles = zigzag([*RISING, 112])
    detector = RisingWedgeDetector()
    holed = [c for i, c in enumerate(candles) if i != 100]
    result = detector.detect(context_for(candles), holed)
    assert result.candidates == () and MissingDataReason.GAPS_IN_WINDOW in result.unfit_reasons
    few = candles[:40]
    assert detector.detect(context_for(few), few).unfit_reasons == (
        MissingDataReason.INSUFFICIENT_HISTORY,
    )


@pytest.mark.parametrize("name", ["rising", "falling"])
def test_a_figure_at_any_instant_depends_only_on_what_was_closed_by_then(name: str) -> None:
    extremes = [*RISING, 112] if name == "rising" else mirror([*RISING, 112])
    detector = RisingWedgeDetector() if name == "rising" else FallingWedgeDetector()
    candles = zigzag(extremes)
    seen_something = False
    for index in range(len(candles) - 1):
        at = candles[index].close_time
        upto = [c for c in candles if c.close_time <= at]
        context = context_for(candles).at(at)
        past = detector.detect(context, upto)
        assert detector.detect(context, candles) == past, f"{name} at {at}"
        assert detector.detect(context, wild_future(candles, at)) == past, f"{name} at {at}"
        seen_something = seen_something or bool(past.candidates)
    assert seen_something  # not vacuous


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_random_walks_never_leak_the_future_into_any_wedge_detector(seed: int) -> None:
    candles = random_walk(seed, 260)
    for index in range(110, 259, 6):
        at = candles[index].close_time
        upto = [c for c in candles if c.close_time <= at]
        context = context_for(candles).at(at)
        for detector in DETECTORS:
            past = detector.detect(context, upto)
            assert detector.detect(context, candles) == past, (seed, index, detector.version)


def test_the_same_candles_always_give_the_same_history() -> None:
    candles = zigzag([*RISING, 112])
    assert history(RisingWedgeDetector(), candles) == history(RisingWedgeDetector(), candles)


def test_the_documented_wedge_parameter_is_the_default_one() -> None:
    params = DEFAULT_CONTINUATION_PARAMS
    for name in ("detectores-de-expansion.md", "detectores-de-continuacion.md"):
        text = (REPO / "docs" / "domain" / name).read_text(encoding="utf-8")
        assert (
            f"| `wedge_convergence_min` | {str(params.wedge_convergence_min).replace('.', ',')} |"
            in text
        )


def test_the_wedges_only_read_the_domain_never_a_candlestick_pattern_or_an_indicator() -> None:
    allowed = {"abc", "collections.abc", "dataclasses", "datetime", "decimal", "typing"}
    tree = ast.parse(Path(str(pattern_wedge.__file__)).read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    foreign = {
        m for m in imported if m not in allowed and not m.startswith("freyja_backend.domain.")
    }
    assert not foreign, foreign
    forbidden = {"indicators", "candlestick", "market_indicators", "pattern_double"}
    assert not any(any(word in m for word in forbidden) for m in imported)
