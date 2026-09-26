"""POINT3-EXPANSION-001 (second part): the broadening formation detector.

Series are built leg by leg (ten candles per leg, prices in exact tenths), so every contact, line
and breakout can be read off the numbers and the expected story written from the rules in
``docs/domain/detectores-de-expansion.md``, never from the code under test. A swing "at 137" has
its high at 137.5 and a swing "at 106" its low at 105.5.
"""

import ast
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from freyja_backend.domain import pattern_broadening
from freyja_backend.domain.chart_pattern import (
    BoundaryRole,
    BreakoutDirection,
    PatternBias,
    PatternRole,
    PatternState,
    PatternType,
)
from freyja_backend.domain.market_context import MissingDataReason
from freyja_backend.domain.market_structure import Pivot, PivotKind, PivotStatus
from freyja_backend.domain.pattern_broadening import BroadeningFormationDetector
from freyja_backend.domain.pattern_channel import (
    AscendingTriangleDetector,
    Channel,
    DescendingTriangleDetector,
    RectangleDetector,
    SymmetricalTriangleDetector,
)
from freyja_backend.domain.pattern_detection import DEFAULT_CONTINUATION_PARAMS
from freyja_backend.domain.pattern_flag import (
    BearFlagDetector,
    BearPennantDetector,
    BullFlagDetector,
    BullPennantDetector,
)
from freyja_backend.domain.pattern_wedge import FallingWedgeDetector, RisingWedgeDetector
from tests.unit.test_market_trend import T0, UP, random_walk, zigzag
from tests.unit.test_pattern_channel import (
    SYMMETRICAL,
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
from tests.unit.test_pattern_wedge import RISING

S = PatternState
D = Decimal

DETECTOR = BroadeningFormationDetector()

# The price climbs to 130, then swings between two lines that move apart: highs at 130, 133 and 137
# (each higher) and lows at 116 and 106 (each lower). Five swings: the smallest figure. Then it
# goes on either way.
BROADENING = [*UP, 116, 133, 106, 137]


# -- the figure, told from its rules -------------------------------------------------------------


def test_a_broadening_formation_is_valid_and_goes_the_way_the_price_breaks() -> None:
    down = the_figure(DETECTOR, [*BROADENING, 88], tail_to=85)

    assert down.pattern_type is PatternType.BROADENING_FORMATION
    assert down.traditional_bias is PatternBias.CONTEXT_DEPENDENT
    assert {PatternRole.REVERSAL, PatternRole.EXPANSION} <= down.traditional_roles
    assert states(down)[0] is S.GEOMETRICALLY_VALID and S.FORMING not in states(down)
    assert states(down)[-1] is S.CONFIRMED_DOWN
    assert labels(down) == ["UPPER_1", "LOWER_1", "UPPER_2", "LOWER_2", "UPPER_3"]
    upper, lower = down.latest.boundaries
    assert (upper.role, lower.role) == (BoundaryRole.UPPER, BoundaryRole.LOWER)
    assert [p.price for p in upper.points] == [D("130.5"), D("137.5")]  # the ceiling rises...
    assert [p.price for p in lower.points] == [D("115.5"), D("105.5")]  # ...and the floor falls
    assert len(upper.contacts) == 3 and len(lower.contacts) == 2
    breakout = down.latest.breakout
    assert breakout is not None and breakout.confirmed
    assert breakout.direction is BreakoutDirection.DOWN and breakout.boundary is BoundaryRole.LOWER
    assert down.detector_version == "broadening-formation-detector-v1"
    assert down.parameter_version == "continuation-params-v1"
    channel = facts_of(down, "CHANNEL")
    assert channel["upper_rise"] == D(7) and channel["lower_rise"] == D(-20)
    # The lines move apart: what the figure is, and no convergence rule to state it.
    assert channel["height"] == D(10) and channel["gap_at_end"] == D(37)


def test_a_broadening_formation_can_break_upwards_and_the_tradition_says_nothing() -> None:
    up = the_figure(DETECTOR, [*BROADENING, 128, 150], tail_to=152)
    assert up.traditional_bias is PatternBias.CONTEXT_DEPENDENT  # no direction is expected
    assert states(up)[-1] is S.CONFIRMED_UP
    assert up.latest.breakout is not None
    assert up.latest.breakout.direction is BreakoutDirection.UP
    assert up.latest.breakout.boundary is BoundaryRole.UPPER
    assert labels(up) == ["UPPER_1", "LOWER_1", "UPPER_2", "LOWER_2", "UPPER_3"]


def test_a_broadening_formation_upside_down_is_the_same_figure() -> None:
    """The figure is symmetric: turned over, it is still one, with the lows first."""
    figure = the_figure(DETECTOR, mirror(BROADENING))
    assert labels(figure) == ["LOWER_1", "UPPER_1", "LOWER_2", "UPPER_2", "LOWER_3"]
    upper, lower = figure.latest.boundaries
    assert [p.price for p in upper.points] == [D("184.5"), D("194.5")]  # 2 highs, rising
    assert [p.price for p in lower.points] == [D("169.5"), D("162.5")]  # 3 lows, falling
    channel = facts_of(figure, "CHANNEL")
    assert channel["upper_rise"] == D(20) and channel["lower_rise"] == D(-7)
    assert channel["upper_contacts"] == 2 and channel["lower_contacts"] == 3


def test_a_breakout_that_closes_back_inside_fails() -> None:
    figure = the_figure(DETECTOR, [*BROADENING, 128, 142], tail_to=125)
    assert states(figure)[-1] is S.FAILED_BREAKOUT and figure.is_terminal
    assert figure.latest.breakout is not None
    assert figure.latest.breakout.direction is BreakoutDirection.UP
    assert not figure.latest.breakout.confirmed


def test_a_wick_through_a_boundary_is_not_a_breakout() -> None:
    figure = the_figure(DETECTOR, [*BROADENING, 128, 139], tail_to=125)
    assert states(figure)[-1] is S.GEOMETRICALLY_VALID
    assert figure.latest.breakout is None


def test_the_evidence_of_a_broadening_formation_explains_its_lines_and_its_context() -> None:
    figure = the_figure(DETECTOR, [*BROADENING, 88], tail_to=85)
    codes = {item.code for item in figure.latest.evidence}
    assert {"CHANNEL", "PRIOR_TREND", "BREAKOUT_SCAN", "BREAKOUT_VOLUME"} <= codes
    assert facts_of(figure, "CHANNEL")["upper_contacts"] == 3
    assert set(facts_of(figure, "PRIOR_TREND")) == {"state"}


def test_a_figure_that_keeps_making_new_extremes_is_followed_by_the_next_one() -> None:
    """A broadening formation goes on making higher highs. For the figure that ended before it, a
    new high beyond its upper line is a breakout (and here it fails: the price is back inside); the
    figure that includes it is another one, one swing later. Both are on the record."""
    figures = history(DETECTOR, zigzag([*UP, 116, 133, 106, 137, 98, 142]))
    assert len(figures) == 2
    first, second = sorted(figures, key=lambda i: i.latest.anchors[0].open_time)
    assert states(first)[-1] is S.FAILED_BREAKOUT
    assert first.latest.breakout is not None
    assert first.latest.breakout.direction is BreakoutDirection.UP
    assert states(second)[-1] is S.GEOMETRICALLY_VALID
    assert second.latest.anchors[0].open_time == first.latest.anchors[2].open_time  # one swing on


# -- what is a broadening formation and what is not ----------------------------------------------

OTHERS: dict[str, tuple[Any, list[int | str]]] = {
    "symmetrical": (SymmetricalTriangleDetector(), [*SYMMETRICAL, 130]),
    "rising wedge": (RisingWedgeDetector(), [*RISING, 112]),
    "falling wedge": (FallingWedgeDetector(), mirror([*RISING, 112])),
    "rectangle": (RectangleDetector(), [*UP, 118, 130, 118, 130, 118, 130, 137]),
    "ascending": (AscendingTriangleDetector(), [*UP, 118, 130, 122, 130, 126, 130, 136]),
}


@pytest.mark.parametrize("name", list(OTHERS))
def test_the_other_figures_of_the_family_are_not_broadening_formations(name: str) -> None:
    detector, extremes = OTHERS[name]
    assert history(detector, zigzag(extremes))  # it is that figure...
    assert history(DETECTOR, zigzag(extremes)) == ()  # ...and not this one


def test_a_broadening_formation_is_none_of_the_other_figures() -> None:
    candles = zigzag([*BROADENING, 88], tail_to=85)
    others = [
        RectangleDetector(),
        AscendingTriangleDetector(),
        DescendingTriangleDetector(),
        SymmetricalTriangleDetector(),
        RisingWedgeDetector(),
        FallingWedgeDetector(),
        BullFlagDetector(),
        BearFlagDetector(),
        BullPennantDetector(),
        BearPennantDetector(),
    ]
    for detector in others:
        assert history(detector, candles) == (), detector.version
        assert history(detector, zigzag(mirror([*BROADENING, 88]), tail_to=215)) == (), (
            detector.version
        )


def test_it_needs_five_swings_and_the_rest_of_the_family_four() -> None:
    four = [*UP, 116, 133, 106]  # two highs, two lows, moving apart: a figure of four swings
    assert history(DETECTOR, zigzag(four)) == ()
    assert history(DETECTOR, zigzag(BROADENING))  # the fifth swing is the figure


# -- the slopes and the order of the contacts, exactly at their values ---------------------------


def pivot(kind: PivotKind, price: str, minutes: int) -> Pivot:
    return Pivot(
        kind,
        PivotStatus.CONFIRMED,
        T0 + timedelta(minutes=minutes),
        D(price),
        T0 + timedelta(days=1),
    )


def channel(
    *,
    upper_rise: str,
    lower_rise: str,
    highs: Sequence[str] = ("100", "110", "120"),
    lows: Sequence[str] = ("90", "80"),
    height: str = "20",
) -> Channel:
    upper = tuple(pivot(PivotKind.HIGH, p, 10 * i) for i, p in enumerate(highs))
    lower = tuple(pivot(PivotKind.LOW, p, 10 * i + 5) for i, p in enumerate(lows))
    return Channel(
        window=(*upper, *lower),
        upper=lambda _at: D(0),
        lower=lambda _at: D(0),
        highs=upper,
        lows=lower,
        height=D(height),
        gap_at_end=D(height) + D(upper_rise) - D(lower_rise),
        upper_rise=D(upper_rise),
        lower_rise=D(lower_rise),
        reference=D(50),
        first_index=0,
        last_index=30,
        expires_after=None,
    )


@pytest.mark.parametrize(
    ("upper", "lower", "expected"),
    # Each boundary moves at least 0.15 of the height (20), that is 3: ceiling up, floor down.
    [
        ("3", "-3", True),  # exactly the minimum on both
        ("2.99", "-3", False),
        ("3", "-2.99", False),
        ("50", "-50", True),
        ("0", "-6", False),  # a flat ceiling: a descending triangle turned over
        ("6", "0", False),  # a flat floor: an ascending triangle
        ("-3", "3", False),  # converging: a symmetrical triangle
        ("6", "6", False),  # both rising: a wedge or a channel
        ("-6", "-6", False),
    ],
)
def test_the_ceiling_must_rise_and_the_floor_fall_by_the_minimum(
    upper: str, lower: str, expected: bool
) -> None:
    fit = channel(upper_rise=upper, lower_rise=lower)
    assert DETECTOR.accepts(fit, DEFAULT_CONTINUATION_PARAMS) is expected


@pytest.mark.parametrize(
    ("highs", "lows", "expected"),
    [
        (("100", "110", "120"), ("90", "80"), True),
        (("100", "100", "120"), ("90", "80"), False),  # a high that is not higher
        (("100", "99", "120"), ("90", "80"), False),  # a high that is lower
        (("100", "110", "120"), ("90", "90"), False),  # a low that is not lower
        (("100", "110", "120"), ("90", "91"), False),  # a low that is higher
        (("100", "120"), ("90", "80", "70"), True),  # three lows and two highs
        (("100", "120"), ("90", "70", "70"), False),
    ],
)
def test_every_contact_is_higher_than_the_one_before_on_the_ceiling_and_lower_on_the_floor(
    highs: tuple[str, ...], lows: tuple[str, ...], expected: bool
) -> None:
    fit = channel(upper_rise="10", lower_rise="-10", highs=highs, lows=lows)
    assert DETECTOR.accepts(fit, DEFAULT_CONTINUATION_PARAMS) is expected


# -- units, no look-ahead, determinism -----------------------------------------------------------


def test_the_detector_is_its_own_unit_with_its_own_version() -> None:
    assert DETECTOR.version == "broadening-formation-detector-v1"
    assert DETECTOR.pattern_type is PatternType.BROADENING_FORMATION
    assert DETECTOR.min_swings == 5
    assert RisingWedgeDetector().min_swings == 4  # the rest of the family is unchanged


def test_data_that_is_not_fit_judges_no_figure_and_says_why() -> None:
    candles = zigzag([*BROADENING, 88], tail_to=85)
    holed = [c for i, c in enumerate(candles) if i != 100]
    result = DETECTOR.detect(context_for(candles), holed)
    assert result.candidates == () and MissingDataReason.GAPS_IN_WINDOW in result.unfit_reasons
    few = candles[:40]
    assert DETECTOR.detect(context_for(few), few).unfit_reasons == (
        MissingDataReason.INSUFFICIENT_HISTORY,
    )


@pytest.mark.parametrize("upside_down", [False, True])
def test_a_figure_at_any_instant_depends_only_on_what_was_closed_by_then(
    upside_down: bool,
) -> None:
    extremes = [*BROADENING, 128, 150]
    candles = zigzag(mirror(extremes) if upside_down else extremes, tail_to=152)
    seen_something = False
    for index in range(len(candles) - 1):
        at = candles[index].close_time
        upto = [c for c in candles if c.close_time <= at]
        context = context_for(candles).at(at)
        past = DETECTOR.detect(context, upto)
        assert DETECTOR.detect(context, candles) == past, f"at {at}"
        assert DETECTOR.detect(context, wild_future(candles, at)) == past, f"at {at}"
        seen_something = seen_something or bool(past.candidates)
    assert seen_something  # not vacuous


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_random_walks_never_leak_the_future_into_the_detector(seed: int) -> None:
    candles = random_walk(seed, 260)
    for index in range(110, 259, 6):
        at = candles[index].close_time
        upto = [c for c in candles if c.close_time <= at]
        context = context_for(candles).at(at)
        assert DETECTOR.detect(context, candles) == DETECTOR.detect(context, upto), (seed, index)


def test_the_same_candles_always_give_the_same_history() -> None:
    candles = zigzag([*BROADENING, 88], tail_to=85)
    assert history(DETECTOR, candles) == history(DETECTOR, candles)
    assert figure_of(history(DETECTOR, candles)).latest.anchors


def test_the_detector_only_reads_the_domain_never_a_candlestick_pattern_or_an_indicator() -> None:
    allowed = {
        "abc",
        "collections.abc",
        "dataclasses",
        "datetime",
        "decimal",
        "itertools",
        "typing",
    }
    tree = ast.parse(Path(str(pattern_broadening.__file__)).read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    foreign = {
        m for m in imported if m not in allowed and not m.startswith("freyja_backend.domain.")
    }
    assert not foreign, foreign
    forbidden = {"indicators", "candlestick", "market_indicators", "pattern_double"}
    assert not any(any(word in m for word in forbidden) for m in imported)
