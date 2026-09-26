"""POINT3-EXPANSION-001 (third part): the diamond detector.

The expected story of every case is written from the contract in section 10 of
``docs/domain/detectores-de-expansion.md``, never from the code under test. Series are built leg by
leg (ten candles per leg unless said, prices in exact tenths): a swing "at 142" has its high at
142.5 and a swing "at 104" its low at 103.5.

    BASE = [*UP, 118, 142, 104, 133, 113]

is a diamond that begins at the high of 130.5 that ends `UP`: expansion high 130.5, low 117.5, then
the vertices high 142.5 and low 103.5, then contraction high 133.5 and low 112.5. Its exit lines are
the two of the contraction: the upper one from 142.5 to 133.5, the lower one from 103.5 to 112.5.
"""

import ast
import dataclasses
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from freyja_backend.domain import pattern_diamond
from freyja_backend.domain.chart_pattern import (
    BoundaryRole,
    BreakoutDirection,
    InvalidationReason,
    PatternBias,
    PatternInstance,
    PatternRole,
    PatternState,
    PatternType,
)
from freyja_backend.domain.market_context import MissingDataReason
from freyja_backend.domain.market_data import Candle
from freyja_backend.domain.pattern_broadening import BroadeningFormationDetector
from freyja_backend.domain.pattern_channel import (
    AscendingTriangleDetector,
    Channel,
    SymmetricalTriangleDetector,
)
from freyja_backend.domain.pattern_detection import (
    DEFAULT_DIAMOND_PARAMS,
    DetectionContext,
    DiamondParams,
    InvalidDetectionRequestError,
    PatternCandidate,
    replay_detector,
)
from freyja_backend.domain.pattern_diamond import (
    AFTER_MARKET_FORMATION,
    LIVE,
    RETROSPECTIVE,
    DiamondDetector,
    phase_accepts,
    provenance_of,
)
from freyja_backend.domain.pattern_wedge import FallingWedgeDetector, RisingWedgeDetector
from tests.unit.test_market_trend import DOWN, T0, TF, UP, candle_at, random_walk, zigzag
from tests.unit.test_pattern_broadening import BROADENING, channel
from tests.unit.test_pattern_channel import (
    context_for,
    labels,
    mirror,
    states,
    wild_future,
)
from tests.unit.test_pattern_wedge import RISING, line_at

S = PatternState
D = Decimal
STEP = TF.duration
DETECTOR = DiamondDetector()

BASE = [*UP, 118, 142, 104, 133, 113]
# A tiny diamond whose numbers make every threshold exact: widest width 7.0 (= 0.25 of the reference
# range, 28.0), expansion height 2, contraction height 8, every boundary moving 3 in 30 candles.
TINY = [*UP, 128, 132, 126, 130, 128]
# Two phases of 75 candles each (legs of 25): the exit lines meet only after 250 candles.
LONG = [*UP, 118, 142, 104, 137, 109]
# Seven swings: the expansion has five, so it is a broadening formation on its own.
BASE5 = [*UP, 112, 140, 96, 150, 105, 141]


def diamond_context(
    candles: Sequence[Candle],
    receipts: Mapping[datetime, datetime] | None = None,
    **diamond: Any,
) -> DetectionContext:
    context = context_for(candles)
    if diamond:
        context = dataclasses.replace(context, diamond=DiamondParams(**diamond))
    return dataclasses.replace(context, received_at=receipts)


def at_close(candles: Sequence[Candle]) -> dict[datetime, datetime]:
    """Every candle received the moment it closed: no delay anywhere."""
    return {c.open_time: c.close_time for c in candles}


def now(
    candles: Sequence[Candle],
    receipts: Mapping[datetime, datetime] | None = None,
    **diamond: Any,
) -> list[PatternCandidate]:
    """What the detector sees at the last instant."""
    context = diamond_context(candles, receipts, **diamond)
    return list(DETECTOR.detect(context, candles).candidates)


def diamond_now(
    candles: Sequence[Candle],
    receipts: Mapping[datetime, datetime] | None = None,
    **diamond: Any,
) -> PatternCandidate:
    found = now(candles, receipts, **diamond)
    assert found, "no diamond was found"
    return max(found, key=lambda c: len(c.evaluation.anchors))


def history(
    candles: Sequence[Candle],
    receipts: Mapping[datetime, datetime] | None = None,
    **diamond: Any,
) -> tuple[PatternInstance, ...]:
    return replay_detector(DETECTOR, diamond_context(candles, receipts, **diamond), candles)


def the_instance(
    extremes: Sequence[int | str],
    receipts: Mapping[datetime, datetime] | None = None,
    **series: Any,
) -> PatternInstance:
    candles = zigzag(extremes, **series)
    found = history(candles, at_close(candles) if receipts is None else receipts)
    assert found, "no diamond was found"
    return max(found, key=lambda i: len(i.latest.anchors))


def fact(item: PatternCandidate | PatternInstance, code: str) -> dict[str, Any]:
    evaluation = item.evaluation if isinstance(item, PatternCandidate) else item.latest
    return dict(next(e for e in evaluation.evidence if e.code == code).facts)


def has(item: PatternCandidate | PatternInstance, code: str) -> bool:
    evaluation = item.evaluation if isinstance(item, PatternCandidate) else item.latest
    return any(e.code == code for e in evaluation.evidence)


def iso(moment: datetime) -> str:
    return moment.isoformat()


# -- the figure, told from its rules -----------------------------------------------------------


def test_a_diamond_after_a_rise_is_formed_and_valid_and_says_what_it_measured() -> None:
    figure = the_instance(BASE)

    assert figure.pattern_type is PatternType.DIAMOND
    assert figure.traditional_bias is PatternBias.CONTEXT_DEPENDENT
    assert {PatternRole.REVERSAL, PatternRole.EXPANSION, PatternRole.COMPRESSION} <= (
        figure.traditional_roles
    )
    assert states(figure)[0] is S.GEOMETRICALLY_VALID and S.FORMING not in states(figure)
    assert labels(figure) == ["UPPER_1", "LOWER_1", "UPPER_2", "LOWER_2", "UPPER_3", "LOWER_3"]
    assert [a.price for a in figure.latest.anchors] == [
        D("130.5"),
        D("117.5"),
        D("142.5"),
        D("103.5"),
        D("133.5"),
        D("112.5"),
    ]
    assert figure.detector_version == "diamond-detector-v1"
    assert figure.parameter_version == "diamond-params-v1"

    # Four boundaries: the two of the expansion and then the two of the contraction.
    boundaries = figure.latest.boundaries
    assert [b.role for b in boundaries] == [
        BoundaryRole.UPPER,
        BoundaryRole.LOWER,
        BoundaryRole.UPPER,
        BoundaryRole.LOWER,
    ]
    assert [[p.price for p in b.points] for b in boundaries] == [
        [D("130.5"), D("142.5")],
        [D("117.5"), D("103.5")],
        [D("142.5"), D("133.5")],
        [D("103.5"), D("112.5")],
    ]

    phases = fact(figure, "DIAMOND_PHASES")
    assert phases["top_vertex_price"] == D("142.5") and phases["bottom_vertex_price"] == D("103.5")
    assert phases["widest_width"] == D(39)  # 142.5 - 103.5, the widest of the two vertices
    assert phases["expansion_height"] == D(6) and phases["contraction_height"] == D("43.5")
    assert phases["expansion_upper_rise"] == D(18) and phases["expansion_lower_rise"] == D(-21)
    assert phases["contraction_upper_rise"] == D("-13.5")
    assert phases["contraction_lower_rise"] == D("13.5")
    assert phases["expansion_swings"] == 4 and phases["contraction_swings"] == 4
    assert phases["reference_range"] == D("28.0")
    assert phases["expansion_phase_is_broadening"] is False  # four swings are not a megaphone
    assert fact(figure, "PRIOR_TREND") == {"state": "UPTREND"}


def test_a_diamond_that_begins_with_a_low_is_the_same_figure_after_a_fall() -> None:
    """The other order of the six swings: low, high, bottom vertex, top vertex, low, high."""
    figure = the_instance(mirror(BASE))

    assert labels(figure) == ["LOWER_1", "UPPER_1", "LOWER_2", "UPPER_2", "LOWER_3", "UPPER_3"]
    phases = fact(figure, "DIAMOND_PHASES")
    assert phases["widest_width"] == D(39)
    assert phases["bottom_vertex_time"] < phases["top_vertex_time"]  # the low vertex comes first
    assert fact(figure, "PRIOR_TREND") == {"state": "DOWNTREND"}
    assert states(figure)[0] is S.GEOMETRICALLY_VALID


def test_the_expansion_phase_says_when_it_is_already_a_broadening_formation() -> None:
    """A tramo expansivo can be the evidence of a later diamond without rewriting its own record."""
    candles = zigzag(BASE5)
    figure = diamond_now(candles)
    phases = fact(figure, "DIAMOND_PHASES")
    assert phases["expansion_swings"] == 5 and phases["expansion_phase_is_broadening"] is True
    assert labels_of(figure) == [
        "UPPER_1",
        "LOWER_1",
        "UPPER_2",
        "LOWER_2",
        "UPPER_3",
        "LOWER_3",
        "UPPER_4",
    ]

    # The broadening formation that existed before the diamond was complete is the same record with
    # or without the rest of the diamond: what came later never rewrites it.
    broadening = BroadeningFormationDetector()
    context = context_for(candles)
    cut = (
        datetime.fromisoformat(phases["top_vertex_time"]) + STEP * 4
    )  # the top vertex is confirmed here
    known = [c for c in candles if c.close_time <= cut]
    early = replay_detector(broadening, context.at(cut), known)
    late = replay_detector(broadening, context, candles)
    assert early
    for before in early:
        after = next(i for i in late if i.pattern_instance_id == before.pattern_instance_id)
        assert [e for e in after.evaluations if e.evaluated_at <= cut] == list(before.evaluations)
    assert diamond_first_evaluation(candles) > cut  # the diamond is known only later


def labels_of(item: PatternCandidate) -> list[str]:
    return [a.label for a in item.evaluation.anchors]


def diamond_first_evaluation(candles: Sequence[Candle]) -> datetime:
    found = history(candles, at_close(candles))
    return min(i.evaluations[0].evaluated_at for i in found)


# -- what is a diamond and what is not ---------------------------------------------------------


def none_in(extremes: Sequence[int | str], **series: Any) -> bool:
    return not now(zigzag(extremes, **series))


def test_an_expansion_that_never_contracts_is_not_a_diamond() -> None:
    assert none_in(BROADENING)
    assert none_in([*UP, 118, 142, 104])  # the swings of the expansion alone
    assert none_in([*UP, 118, 142, 104, 133])  # one contraction swing is not a contraction


def test_a_contraction_that_never_expanded_is_not_a_diamond() -> None:
    """Highs falling and lows rising from the very first swing: a symmetrical triangle, with no
    expansion before it."""
    contraction = [130, 100, 128, 102, 126, 104, 124, 106, 122, 108, 120, 110, 118]
    assert none_in(contraction)
    candles = zigzag(contraction)
    triangle = SymmetricalTriangleDetector()
    assert triangle.detect(context_for(candles), candles).candidates  # it is a triangle...


def test_wedges_and_triangles_are_not_diamonds_and_a_diamond_is_not_a_wedge_or_a_megaphone() -> (
    None
):
    assert none_in([*RISING, 112])
    assert none_in(mirror([*RISING, 112]))
    assert none_in([*UP, 118, 130, 122, 130, 126, 130, 136])  # ascending triangle
    candles = zigzag([*BASE, 140], tail_to=142)
    others = [
        RisingWedgeDetector(),
        FallingWedgeDetector(),
        AscendingTriangleDetector(),
        BroadeningFormationDetector(),
    ]
    for detector in others:
        assert not detector.detect(context_for(candles), candles).candidates, detector.version
    # Its contraction, on the other hand, is a symmetrical triangle (both are on the record).
    triangle = SymmetricalTriangleDetector()
    assert triangle.detect(context_for(candles), candles).candidates


def test_the_two_vertices_must_be_consecutive_swings_in_diamond_params_v1() -> None:
    """The look-alike of the contract (10.2): the highs turn at 140 and the lows only at 100, three
    swings later. It has one expansion and one contraction on each side and still is not a diamond
    of this version: there is no single transition."""
    offset = [*UP, 118, 140, 110, 136, 100, 132, 108]
    assert none_in(offset)
    # The same idea with the turns together (a diamond): it is found.
    assert now(zigzag([*UP, 118, 142, 104, 133, 113]))


@pytest.mark.parametrize(
    "extremes",
    [
        [*UP, 118, 142, 104, 142, 113],  # the third high equals the top vertex
        [*UP, 118, 142, 104, 133, 104],  # the third low equals the bottom vertex
        [*UP, 118, 130, 104, 120, 113],  # the second high equals the first
    ],
)
def test_the_comparisons_are_strict(extremes: list[int | str]) -> None:
    assert none_in(extremes)


def test_a_new_extreme_that_undoes_the_contraction_before_the_figure_is_valid() -> None:
    """After the lower high the price goes above the top vertex instead of making a higher low:
    there never is a contraction, so there is no diamond, then or later."""
    assert none_in([*UP, 118, 142, 104, 133, 146])
    assert none_in([*UP, 118, 142, 104, 133, 146, 120, 138])


def test_a_diamond_appears_at_the_instant_its_last_pivot_is_confirmed_and_not_before() -> None:
    candles = zigzag(BASE)
    formed = datetime.fromisoformat(
        fact(diamond_now(candles), "DIAMOND_TIMING")["market_formed_at"]
    )
    context = diamond_context(candles)
    before = DETECTOR.detect(
        context.at(formed - STEP), [c for c in candles if c.close_time < formed]
    )
    exact = DETECTOR.detect(context.at(formed), [c for c in candles if c.close_time <= formed])
    assert not before.candidates
    assert exact.candidates and exact.candidates[0].evaluation.state is S.GEOMETRICALLY_VALID


# -- breakouts: both sides, the real direction, pending and failed -----------------------------

UP_OUT: tuple[list[int | str], dict[str, Any]] = ([*BASE, 140], {"tail_to": 142})
DOWN_OUT: tuple[list[int | str], dict[str, Any]] = ([*BASE, 120, 90], {"tail_to": 88})


@pytest.mark.parametrize(
    ("way_out", "upside_down", "direction", "boundary", "trend"),
    [
        (UP_OUT, False, BreakoutDirection.UP, BoundaryRole.UPPER, "UPTREND"),
        (DOWN_OUT, False, BreakoutDirection.DOWN, BoundaryRole.LOWER, "UPTREND"),
        (UP_OUT, True, BreakoutDirection.DOWN, BoundaryRole.LOWER, "DOWNTREND"),
        (DOWN_OUT, True, BreakoutDirection.UP, BoundaryRole.UPPER, "DOWNTREND"),
    ],
)
def test_the_diamond_goes_the_way_the_price_breaks_whatever_came_before(
    way_out: tuple[list[int | str], dict[str, Any]],
    upside_down: bool,
    direction: BreakoutDirection,
    boundary: BoundaryRole,
    trend: str,
) -> None:
    extremes, series = way_out
    if upside_down:
        extremes, series = mirror(extremes), {"tail_to": 300 - series["tail_to"]}
    figure = the_instance(extremes, **series)
    assert figure.pattern_type is PatternType.DIAMOND  # never renamed by what happens next
    assert figure.traditional_bias is PatternBias.CONTEXT_DEPENDENT
    assert fact(figure, "PRIOR_TREND") == {"state": trend}  # context, only recorded
    wanted = S.CONFIRMED_UP if direction is BreakoutDirection.UP else S.CONFIRMED_DOWN
    assert states(figure)[-1] is wanted
    assert figure.latest.breakout is not None and figure.latest.breakout.confirmed
    assert figure.latest.breakout.direction is direction
    assert figure.latest.breakout.boundary is boundary


def test_a_close_beyond_the_line_short_of_the_margin_is_pending_and_can_fail() -> None:
    pending = the_instance([*BASE, 126], tail_to=126)
    assert states(pending)[-1] is S.BREAKOUT_PENDING_CONFIRMATION
    assert pending.latest.breakout is not None and not pending.latest.breakout.confirmed
    failed = the_instance([*BASE, 126, 116], tail_to=116)
    assert states(failed)[-1] is S.FAILED_BREAKOUT and failed.is_terminal
    assert failed.latest.breakout is not None
    assert failed.latest.breakout.direction is BreakoutDirection.UP


# -- thresholds, exactly at their value and at both neighbours ---------------------------------


def tiny_found(extremes: Sequence[int | str] = TINY, **diamond: Any) -> bool:
    return bool(now(zigzag(extremes), **diamond))


def test_the_tiny_diamond_measures_what_the_thresholds_below_are_built_on() -> None:
    figure = diamond_now(zigzag(TINY))
    phases = fact(figure, "DIAMOND_PHASES")
    assert phases["widest_width"] == D(7) and phases["reference_range"] == D("28.0")
    assert phases["expansion_height"] == D(2) and phases["contraction_height"] == D(8)
    assert phases["expansion_upper_rise"] == D(3) and phases["contraction_lower_rise"] == D(3)
    # The margin is a tenth of the contraction's height (0.8), not of the widest width (0.7).


@pytest.mark.parametrize(
    ("top", "expected"),
    # widest width = top vertex - 125.5: 6.9, 7.0 and 7.1 against 0.25 x 28.0 = 7.0.
    [("131.9", False), ("132", True), ("132.1", True)],
)
def test_the_widest_width_must_reach_the_minimum_fraction_of_the_reference_range(
    top: str, expected: bool
) -> None:
    assert tiny_found([*UP, 128, top, 126, 130, 128]) is expected


@pytest.mark.parametrize(
    ("slope_min", "expected"),
    # Every boundary moves 3 and the contraction is 8 tall: 0.375 x 8 = 3, exactly.
    [("0.374", True), ("0.375", True), ("0.376", False)],
)
def test_every_boundary_must_move_the_minimum_fraction_of_its_phase_height(
    slope_min: str, expected: bool
) -> None:
    assert tiny_found(slope_min=D(slope_min)) is expected


@pytest.mark.parametrize(("minimum", "expected"), [(29, True), (30, True), (31, False)])
def test_each_phase_spans_at_least_the_minimum_number_of_candles(
    minimum: int, expected: bool
) -> None:
    assert tiny_found(min_channel_candles=minimum) is expected


def line_closes(figure: PatternCandidate, candle_open: datetime, beyond: str) -> Decimal:
    """The close that is `beyond` outside the upper exit line at the close of the candle."""
    upper = figure.evaluation.boundaries[2]
    return line_at(upper.points, candle_open + STEP) + D(beyond)


def one_more_candle(candles: list[Candle], close: Decimal) -> list[Candle]:
    return [*candles, candle_at(candles[-1].open_time + STEP, close, STEP)]


@pytest.mark.parametrize(
    ("beyond", "state"),
    # The margin is 0.10 x the contraction's height (8) = 0.8. A tenth of the widest width (0.7)
    # would confirm the middle case: it must not.
    [
        ("0", S.GEOMETRICALLY_VALID),  # on the line is not beyond
        ("0.75", S.BREAKOUT_PENDING_CONFIRMATION),
        ("0.79", S.BREAKOUT_PENDING_CONFIRMATION),
        ("0.8", S.CONFIRMED_UP),
        ("0.81", S.CONFIRMED_UP),
    ],
)
def test_the_margin_is_a_tenth_of_the_contraction_height_and_not_of_the_widest_width(
    beyond: str, state: PatternState
) -> None:
    base = zigzag(TINY)
    figure = diamond_now(base)
    candles = one_more_candle(base, line_closes(figure, base[-1].open_time + STEP, beyond))
    assert diamond_now(candles).evaluation.state is state


def test_the_parameters_that_make_no_sense_are_refused() -> None:
    for bad in (
        {"min_height_fraction": D(0)},
        {"contact_tolerance": D(1)},
        {"slope_min": 0.15},
        {"breakout_margin": D("-0.1")},
        {"range_window_candles": 0},
        {"min_channel_candles": True},
        {"failure_window_candles": 0},
        {"diamond_max_age_candles": 0},
        {"min_history": 1.5},
        {"version": " "},
    ):
        with pytest.raises(InvalidDetectionRequestError):
            DiamondParams(**bad)


def test_the_set_has_its_own_identity_and_every_number_the_detector_reads() -> None:
    params = DEFAULT_DIAMOND_PARAMS
    assert params.version == "diamond-params-v1"
    assert (params.min_height_fraction, params.range_window_candles) == (D("0.25"), 100)
    assert (params.contact_tolerance, params.slope_min) == (D("0.15"), D("0.15"))
    assert (params.min_channel_candles, params.breakout_margin) == (15, D("0.10"))
    assert (params.failure_window_candles, params.diamond_max_age_candles) == (10, 200)


def test_a_change_in_the_continuation_parameters_does_not_change_a_diamond() -> None:
    candles = zigzag(BASE)
    plain = diamond_now(candles).evaluation
    changed = dataclasses.replace(
        context_for(candles, min_channel_candles=999, slope_min=D("0.9"), flat_tolerance=D("0.5"))
    )
    assert DETECTOR.detect(changed, candles).candidates[0].evaluation.anchors == plain.anchors
    assert diamond_now(candles, contact_tolerance=D("0.01")).evaluation.anchors == plain.anchors


# -- what Freyja knew and when: market time, arrival time and provenance -----------------------


def receipts_with(
    candles: Sequence[Candle], late: Mapping[datetime, datetime]
) -> dict[datetime, datetime]:
    """Every candle received at its close, except those given: `late` maps the open time of a candle
    to the instant it was really received."""
    return {**at_close(candles), **late}


def confirming_candle(candles: Sequence[Candle], formed_at: datetime) -> Candle:
    return next(c for c in candles if c.close_time == formed_at)


def dependency(candles: Sequence[Candle], timing: Mapping[str, Any]) -> Candle:
    """A candle the figure depends on, well before the one that confirms its last swing."""
    formed = datetime.fromisoformat(timing["market_formed_at"])
    return next(c for c in candles if c.close_time == formed - STEP * 15)


def test_a_breakout_of_a_diamond_already_known_when_the_candle_opened_is_live() -> None:
    candles = zigzag(UP_OUT[0], **UP_OUT[1])
    figure = diamond_now(candles, at_close(candles))
    timing = fact(figure, "DIAMOND_TIMING")
    assert timing["receipts_available"] is True
    assert timing["known_at"] == timing["market_formed_at"]  # nothing arrived late
    assert timing["breakout_open_time"] >= timing["known_at"]
    assert timing["provenance"] == LIVE
    assert timing["breakout_received_at"] == timing["breakout_close_time"]


def test_a_breakout_before_the_diamond_existed_is_retrospective_even_if_it_arrives_late() -> None:
    """The price leaves at once: the breakout candle closes before the last swing is confirmed.
    Freyja can describe what happened but could not have detected at that candle the breakout of
    a diamond that did not exist yet, whenever the candle arrived."""
    candles = zigzag([*BASE, 200], tail_to=202)
    probe = fact(diamond_now(candles, at_close(candles)), "DIAMOND_TIMING")
    breakout_open = datetime.fromisoformat(probe["breakout_open_time"])
    formed = datetime.fromisoformat(probe["market_formed_at"])
    assert breakout_open < formed  # it opened before the diamond existed
    late = {breakout_open: formed + STEP * 5}  # and it arrived well after
    figure = diamond_now(candles, receipts_with(candles, late))
    timing = fact(figure, "DIAMOND_TIMING")
    assert timing["provenance"] == RETROSPECTIVE
    assert timing["breakout_received_at"] >= timing["known_at"]  # it is one of the candles it needs
    assert timing["breakout_close_time"] < timing["known_at"]  # the market closed it earlier still
    assert figure.evaluation.state is S.CONFIRMED_UP  # described, with its real direction


def test_the_diamond_is_born_with_the_breakout_it_already_had() -> None:
    candles = zigzag([*BASE, 200], tail_to=202)
    born = history(candles, at_close(candles))[0]
    first = born.evaluations[0]
    assert first.state is S.CONFIRMED_UP and first.breakout is not None  # never a simulated birth
    assert S.GEOMETRICALLY_VALID not in states(born)


def test_a_candle_that_opened_after_the_market_formed_the_diamond_but_before_freyja_knew_it() -> (
    None
):
    candles = zigzag(UP_OUT[0], **UP_OUT[1])
    probe = fact(diamond_now(candles, at_close(candles)), "DIAMOND_TIMING")
    formed = datetime.fromisoformat(probe["market_formed_at"])
    opened = datetime.fromisoformat(probe["breakout_open_time"])
    assert formed <= opened
    arrival = (
        opened + STEP
    )  # the confirming candle only reached Freyja after the breakout candle opened
    receipts = receipts_with(candles, {confirming_candle(candles, formed).open_time: arrival})
    timing = fact(diamond_now(candles, receipts), "DIAMOND_TIMING")
    assert timing["known_at"] == iso(arrival)
    assert timing["provenance"] == AFTER_MARKET_FORMATION  # exists in the market, not yet known


def test_the_limit_is_inclusive_a_candle_that_opens_exactly_when_it_is_known_is_live() -> None:
    candles = zigzag(UP_OUT[0], **UP_OUT[1])
    probe = fact(diamond_now(candles, at_close(candles)), "DIAMOND_TIMING")
    formed = datetime.fromisoformat(probe["market_formed_at"])
    opened = datetime.fromisoformat(probe["breakout_open_time"])
    confirming = confirming_candle(candles, formed)
    on = fact(
        diamond_now(candles, receipts_with(candles, {confirming.open_time: opened})),
        "DIAMOND_TIMING",
    )
    just_after = fact(
        diamond_now(
            candles,
            receipts_with(candles, {confirming.open_time: opened + timedelta(seconds=1)}),
        ),
        "DIAMOND_TIMING",
    )
    assert on["known_at"] == iso(opened) and on["provenance"] == LIVE
    assert just_after["provenance"] == AFTER_MARKET_FORMATION  # one second too late


def test_a_live_breakout_that_arrives_late_stays_live_with_its_delay_visible() -> None:
    candles = zigzag(UP_OUT[0], **UP_OUT[1])
    probe = fact(diamond_now(candles, at_close(candles)), "DIAMOND_TIMING")
    opened = datetime.fromisoformat(probe["breakout_open_time"])
    late = opened + STEP * 6
    timing = fact(diamond_now(candles, receipts_with(candles, {opened: late})), "DIAMOND_TIMING")
    assert timing["provenance"] == LIVE  # the diamond was known when the candle opened
    assert timing["breakout_received_at"] == iso(late)  # and the delay is on the record
    assert timing["breakout_close_time"] == iso(opened + STEP)


def test_out_of_order_arrivals_move_when_the_diamond_is_known_and_the_provenance_follows() -> None:
    """An earlier candle that reaches Freyja after a later one: the diamond depends on it, so it is
    known only then. The calendar order of the candles does not matter, the arrivals do."""
    candles = zigzag(UP_OUT[0], **UP_OUT[1])
    probe = fact(diamond_now(candles, at_close(candles)), "DIAMOND_TIMING")
    opened = datetime.fromisoformat(probe["breakout_open_time"])
    inside = dependency(candles, probe)  # a candle within the figure, long before its end
    arrival = opened + STEP * 2
    receipts = receipts_with(candles, {inside.open_time: arrival})
    timing = fact(diamond_now(candles, receipts), "DIAMOND_TIMING")
    assert timing["known_at"] == iso(arrival)
    assert timing["provenance"] == AFTER_MARKET_FORMATION
    assert fact(diamond_now(candles, at_close(candles)), "DIAMOND_TIMING")["provenance"] == LIVE


def test_the_provenance_is_that_of_the_first_close_beyond_even_if_the_margin_comes_later() -> None:
    candles = zigzag(UP_OUT[0], **UP_OUT[1])
    probe = fact(diamond_now(candles, at_close(candles)), "DIAMOND_TIMING")
    formed = datetime.fromisoformat(probe["market_formed_at"])
    first = datetime.fromisoformat(probe["breakout_open_time"])
    confirmed_open = datetime.fromisoformat(probe["confirmation_close_time"]) - STEP
    assert first < confirmed_open  # the margin was reached on a later candle
    receipts = receipts_with(
        candles, {confirming_candle(candles, formed).open_time: confirmed_open}
    )
    timing = fact(diamond_now(candles, receipts), "DIAMOND_TIMING")
    assert timing["known_at"] == iso(confirmed_open)
    assert timing["provenance"] == AFTER_MARKET_FORMATION  # decided by the first close beyond
    assert timing["confirmation_close_time"] > timing["known_at"]  # although the margin came after


def test_without_arrival_times_a_breakout_is_never_live() -> None:
    candles = zigzag(UP_OUT[0], **UP_OUT[1])
    timing = fact(diamond_now(candles), "DIAMOND_TIMING")
    assert timing["receipts_available"] is False and "known_at" not in timing
    assert timing["provenance"] == AFTER_MARKET_FORMATION
    steep = zigzag([*BASE, 200], tail_to=202)
    assert fact(diamond_now(steep), "DIAMOND_TIMING")["provenance"] == RETROSPECTIVE


def test_a_candle_that_has_not_arrived_by_the_instant_is_not_read() -> None:
    """The figure needs every candle it depends on: while one has not arrived there is a hole, the
    data are not fit, and no diamond is guessed."""
    candles = zigzag(BASE)
    formed = datetime.fromisoformat(
        fact(diamond_now(candles), "DIAMOND_TIMING")["market_formed_at"]
    )
    hole = dependency(candles, fact(diamond_now(candles), "DIAMOND_TIMING"))
    late = {hole.open_time: formed + STEP * 10}
    context = diamond_context(candles, receipts_with(candles, late))
    result = DETECTOR.detect(context, candles)
    assert not result.candidates and MissingDataReason.GAPS_IN_WINDOW in result.unfit_reasons
    unknown = {k: v for k, v in at_close(candles).items() if k != hole.open_time}
    lost = DETECTOR.detect(diamond_context(candles, unknown), candles)
    assert not lost.candidates  # a candle without a receipt cannot be said to have been received


@pytest.mark.parametrize(
    ("opened", "formed", "known", "expected"),
    [
        (10, 5, 8, LIVE),  # opened after it was known
        (8, 5, 8, LIVE),  # exactly when it was known
        (7, 5, 8, AFTER_MARKET_FORMATION),  # existed in the market, not known yet
        (5, 5, 8, AFTER_MARKET_FORMATION),  # opened exactly when the market formed it
        (4, 5, 8, RETROSPECTIVE),  # did not exist yet
        (10, 5, None, AFTER_MARKET_FORMATION),  # no arrival times: never live
        (4, 5, None, RETROSPECTIVE),
    ],
)
def test_the_provenance_rule_at_its_limits(
    opened: int, formed: int, known: int | None, expected: str
) -> None:
    def at(minutes: int) -> datetime:
        return T0 + timedelta(minutes=minutes)

    assert provenance_of(at(opened), at(formed), None if known is None else at(known)) == expected


# -- the apex ----------------------------------------------------------------------------------


def creeping(base: list[Candle], upper: Any, lower: Any, count: int) -> list[Candle]:
    """Candles that stay between the two exit lines (read at each close) and never leave them."""
    tail: list[Candle] = []
    for n in range(1, count + 1):
        opened = base[-1].open_time + STEP * n
        closing = opened + STEP
        mid = (line_at(upper.points, closing) + line_at(lower.points, closing)) / 2
        tail.append(candle_at(opened, mid, STEP))
    return tail


def exit_lines(extremes: Sequence[int | str], **series: Any) -> tuple[Any, Any]:
    figure = diamond_now(zigzag(extremes, **series))
    return figure.evaluation.boundaries[2], figure.evaluation.boundaries[3]


def test_a_diamond_known_after_its_apex_without_an_earlier_exit_is_never_valid_or_recorded() -> (
    None
):
    upper, lower = exit_lines(BASE)
    base = zigzag(BASE, tail=0)
    candles = [*base, *creeping(base, upper, lower, 40)]  # the exit lines meet around candle 68
    on_time = history(candles, at_close(candles))
    assert (
        on_time and states(on_time[0])[-1] is S.INVALIDATED
    )  # known in time, then it ran its course
    assert on_time[0].latest.invalidation_reasons == (InvalidationReason.TOO_LONG,)

    formed = datetime.fromisoformat(
        fact(diamond_now(candles), "DIAMOND_TIMING")["market_formed_at"]
    )
    end = candles[-1].close_time
    late = receipts_with(candles, {confirming_candle(candles, formed).open_time: end})
    assert history(candles, late) == ()  # known only after the apex: there is no figure
    candidate = diamond_now(candles, late)
    assert candidate.evaluation.state is S.INVALIDATED
    assert candidate.evaluation.invalidation_reasons == (InvalidationReason.TOO_LONG,)
    assert fact(candidate, "DIAMOND_TIMING")["apex_passed"] is True
    assert all(
        S.GEOMETRICALLY_VALID not in states(i) for i in replay_all(candles, late)
    )  # not at any instant


def replay_all(
    candles: Sequence[Candle], receipts: Mapping[datetime, datetime]
) -> tuple[PatternInstance, ...]:
    return history(candles, receipts)


def test_a_diamond_known_after_its_apex_is_born_with_an_earlier_exit_but_never_live() -> None:
    candles = zigzag([*BASE, 140], tail=20, tail_to=142)  # leaves at candle ~57, apex at ~68
    formed = datetime.fromisoformat(
        fact(diamond_now(candles), "DIAMOND_TIMING")["market_formed_at"]
    )
    end = candles[-1].close_time
    receipts = receipts_with(candles, {confirming_candle(candles, formed).open_time: end})
    born = history(candles, receipts)
    assert born and born[0].evaluations[0].state is S.CONFIRMED_UP
    timing = fact(born[0], "DIAMOND_TIMING")
    assert timing["apex_passed"] is True and timing["known_at"] == iso(end)
    assert timing["provenance"] != LIVE  # it opened long before Freyja knew the diamond


# -- age: 199, 200 and 201 candles -------------------------------------------------------------


def long_series(age: int) -> list[Candle]:
    """The long diamond with candles that stay inside its exit lines until the last one is `age`
    candles after the first anchor."""
    base = zigzag(LONG, tail=0, leg=25)
    upper, lower = exit_lines(LONG, leg=25)
    anchor = diamond_now(zigzag(LONG, leg=25)).evaluation.anchors[0].open_time
    first = next(k for k, c in enumerate(base) if c.open_time == anchor)
    return [*base, *creeping(base, upper, lower, first + age - (len(base) - 1))]


@pytest.mark.parametrize(
    ("age", "state"),
    [(199, S.GEOMETRICALLY_VALID), (200, S.GEOMETRICALLY_VALID), (201, S.INVALIDATED)],
)
def test_an_unresolved_diamond_is_alive_at_199_and_200_candles_and_stale_at_201(
    age: int, state: PatternState
) -> None:
    candles = long_series(age)
    figure = diamond_now(candles)
    first = next(
        k for k, c in enumerate(candles) if c.open_time == figure.evaluation.anchors[0].open_time
    )
    assert len(candles) - 1 - first == age  # counted in candles from the first anchor to the last
    assert figure.evaluation.state is state
    if state is S.INVALIDATED:
        assert figure.evaluation.invalidation_reasons == (InvalidationReason.TOO_LONG,)
    assert fact(figure, "DIAMOND_TIMING")["apex_passed"] is False  # the apex is not what ends it


def test_a_diamond_known_when_it_is_already_older_than_the_limit_is_not_a_figure() -> None:
    candles = long_series(201)
    formed = datetime.fromisoformat(
        fact(diamond_now(candles), "DIAMOND_TIMING")["market_formed_at"]
    )
    end = candles[-1].close_time
    late = receipts_with(candles, {confirming_candle(candles, formed).open_time: end})
    assert history(candles, late) == ()


def test_the_age_limit_is_the_diamonds_own_parameter() -> None:
    candles = long_series(150)
    assert (
        diamond_now(candles, diamond_max_age_candles=150).evaluation.state is S.GEOMETRICALLY_VALID
    )
    assert diamond_now(candles, diamond_max_age_candles=149).evaluation.state is S.INVALIDATED


# -- what comes after the diamond is formed: facts, not new geometry ---------------------------


def creeping_diamond(count: int = 10) -> list[Candle]:
    upper, lower = exit_lines(BASE)
    base = zigzag(BASE, tail=0)
    return [*base, *creeping(base, upper, lower, count)]


def geometry(instance: PatternInstance) -> set[Any]:
    return {(e.anchors, e.boundaries) for e in instance.evaluations}


def test_a_wick_beyond_an_exit_line_with_the_close_inside_is_a_fact_and_nothing_more() -> None:
    candles = creeping_diamond()
    control = history(candles, at_close(candles))[0]
    upper = control.latest.boundaries[2]
    k = len(candles) - 6
    spike_high = line_at(upper.points, candles[k].close_time) + 3  # 3 above the line
    wicked = list(candles)
    wicked[k] = dataclasses.replace(candles[k], high=spike_high)
    instance = history(wicked, at_close(wicked))[0]

    assert states(instance)[-1] is S.GEOMETRICALLY_VALID  # not a breakout: the close is inside
    assert instance.latest.breakout is None
    wick = fact(instance, "WICK_PENETRATIONS")
    assert wick["wick_candles"] == 1 and wick["deepest_side"] == "UPPER"
    assert wick["first_wick_open_time"] == iso(candles[k].open_time)
    assert wick["deepest_wick_fraction"] > 0
    assert not has(control, "WICK_PENETRATIONS")
    assert geometry(instance) == geometry(control)  # neither invalidated nor redrawn
    assert not any(s in (S.CONFIRMED_UP, S.CONFIRMED_DOWN) for s in states(instance))


def test_a_wick_beyond_the_lower_exit_line_is_the_same_fact_on_the_other_side() -> None:
    candles = creeping_diamond()
    lower = history(candles, at_close(candles))[0].latest.boundaries[3]
    k = len(candles) - 6
    wicked = list(candles)
    wicked[k] = dataclasses.replace(
        candles[k], low=line_at(lower.points, candles[k].close_time) - 2
    )
    wick = fact(history(wicked, at_close(wicked))[0], "WICK_PENETRATIONS")
    assert wick["deepest_side"] == "LOWER" and wick["wick_candles"] == 1


def test_a_swing_beyond_a_vertex_without_a_close_outside_changes_nothing_in_the_instance() -> None:
    candles = creeping_diamond()
    control = history(candles, at_close(candles))[0]
    top = control.latest.anchors[2].price
    k = len(candles) - 6  # far enough from the end for the spike to be a confirmed swing high
    spiked = list(candles)
    spiked[k] = dataclasses.replace(candles[k], high=top + 10)
    instance = next(
        i
        for i in history(spiked, at_close(spiked))
        if i.latest.anchors[0].open_time == control.latest.anchors[0].open_time
    )
    assert has(instance, "WICK_PENETRATIONS")  # the record has it from the spike on...
    assert (
        fact(diamond_now(spiked, at_close(spiked)), "WICK_PENETRATIONS")["beyond_vertex_swings"]
        == 1
    )  # ...and the detector, at the last instant, counts the swing once it is confirmed
    assert states(instance)[-1] is S.GEOMETRICALLY_VALID  # the closes are still inside
    assert geometry(instance) == geometry(control)  # it does not enter the figure: no new anchor
    assert len(instance.latest.anchors) == 6


def test_one_more_contact_is_evidence_and_never_moves_a_boundary() -> None:
    candles = zigzag([*BASE, 124])  # a lower high on the upper exit line, closes still inside
    instance = history(candles, at_close(candles))[0]
    extra = fact(instance, "ADDITIONAL_CONTACTS")
    assert extra["additional_contacts"] == 1 and extra["latest_contact_side"] == "UPPER"
    assert extra["latest_contact_price"] == D("124.5")
    assert len(instance.latest.anchors) == 6  # not an anchor
    assert len(instance.evaluations) > 1  # the new kind of evidence was recorded as news...
    assert len({e.boundaries for e in instance.evaluations}) == 1  # ...and no boundary ever moved
    assert len({e.anchors for e in instance.evaluations}) == 1
    assert states(instance)[-1] is S.GEOMETRICALLY_VALID


def test_every_evaluation_of_an_instance_judges_with_the_same_geometry() -> None:
    for extremes, series in (UP_OUT, DOWN_OUT):
        candles = zigzag(extremes, **series)
        instance = history(candles, at_close(candles))[0]
        assert len(instance.evaluations) > 1
        assert len({e.boundaries for e in instance.evaluations}) == 1
        assert len({e.anchors for e in instance.evaluations}) == 1


# -- units, no look-ahead, determinism ---------------------------------------------------------


def test_the_detector_is_its_own_unit_with_its_own_version_and_parameters() -> None:
    assert DETECTOR.version == "diamond-detector-v1"
    assert DETECTOR.pattern_type is PatternType.DIAMOND
    assert DETECTOR.parameter_version(diamond_context(zigzag(BASE))) == "diamond-params-v1"


def test_data_that_is_not_fit_judges_no_figure_and_says_why() -> None:
    candles = zigzag(BASE)
    holed = [c for i, c in enumerate(candles) if i != 100]
    result = DETECTOR.detect(diamond_context(candles), holed)
    assert result.candidates == () and MissingDataReason.GAPS_IN_WINDOW in result.unfit_reasons
    few = candles[:40]
    assert DETECTOR.detect(diamond_context(few), few).unfit_reasons == (
        MissingDataReason.INSUFFICIENT_HISTORY,
    )


@pytest.mark.parametrize("upside_down", [False, True])
def test_a_figure_at_any_instant_depends_only_on_what_was_closed_and_received_by_then(
    upside_down: bool,
) -> None:
    extremes = UP_OUT[0]
    candles = (
        zigzag(mirror(extremes), tail_to=158) if upside_down else zigzag(extremes, tail_to=142)
    )
    receipts = at_close(candles)
    context = diamond_context(candles, receipts)
    seen_something = False
    for index in range(100, len(candles) - 1):
        at = candles[index].close_time
        upto = [c for c in candles if c.close_time <= at]
        past = DETECTOR.detect(context.at(at), upto)
        assert DETECTOR.detect(context.at(at), candles) == past, f"at {at}"
        assert DETECTOR.detect(context.at(at), wild_future(candles, at)) == past, f"at {at}"
        seen_something = seen_something or bool(past.candidates)
    assert seen_something  # not vacuous


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_random_walks_never_leak_the_future_into_the_detector(seed: int) -> None:
    candles = random_walk(seed, 260)
    context = diamond_context(candles, at_close(candles))
    for index in range(110, 259, 6):
        at = candles[index].close_time
        upto = [c for c in candles if c.close_time <= at]
        assert DETECTOR.detect(context.at(at), candles) == DETECTOR.detect(context.at(at), upto), (
            seed,
            index,
        )


def test_the_same_candles_always_give_the_same_history() -> None:
    candles = zigzag(UP_OUT[0], **UP_OUT[1])
    assert history(candles, at_close(candles)) == history(candles, at_close(candles))
    assert DOWN  # (the series of a fall is built the same way)


_FORBIDDEN = {
    "side_of_trade",
    "action",
    "position",
    "entry",
    "order",
    "signal",
    "confidence",
    "score",
    "probability",
    "recommendation",
    "target",
    "stop_loss",
    "take_profit",
}


def test_a_detector_result_holds_no_signal_no_decision_and_no_probability() -> None:
    candle = diamond_now(zigzag(BASE))
    fields = {f.name for f in dataclasses.fields(type(candle))}
    fields |= {f.name for f in dataclasses.fields(type(candle.evaluation))}
    fields |= {name for item in candle.evaluation.evidence for name, _ in item.facts}
    assert fields.isdisjoint(_FORBIDDEN)


def test_the_detector_only_reads_the_domain_never_a_candlestick_pattern_or_an_indicator() -> None:
    allowed = {"collections.abc", "dataclasses", "datetime", "decimal", "typing"}
    tree = ast.parse(Path(str(pattern_diamond.__file__)).read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    foreign = {
        m for m in imported if m not in allowed and not m.startswith("freyja_backend.domain.")
    }
    assert not foreign, foreign
    forbidden = {"indicators", "candlestick", "market_indicators", "pattern_double"}
    assert not any(any(word in m for word in forbidden) for m in imported)


# -- the rules of a phase, on measures written by hand -----------------------------------------


def a_phase(
    upper: str,
    lower: str,
    highs: tuple[str, ...],
    lows: tuple[str, ...],
) -> Channel:
    return channel(upper_rise=upper, lower_rise=lower, highs=highs, lows=lows)


@pytest.mark.parametrize(
    ("upper", "lower", "highs", "lows", "expanding", "expected"),
    [
        # Expansion: the ceiling rises and the floor falls, by at least 0.15 of 20 (3), in order.
        ("3", "-3", ("100", "110", "120"), ("90", "80"), True, True),
        ("2.99", "-3", ("100", "110", "120"), ("90", "80"), True, False),
        ("3", "-2.99", ("100", "110", "120"), ("90", "80"), True, False),
        ("10", "-10", ("100", "100", "120"), ("90", "80"), True, False),  # equal highs
        ("10", "-10", ("100", "99", "120"), ("90", "80"), True, False),  # a lower high
        ("10", "-10", ("100", "110", "120"), ("90", "90", "80"), True, False),  # equal lows
        ("10", "-10", ("100", "110", "120"), ("90", "91", "80"), True, False),  # a higher low
        ("-10", "10", ("100", "110", "120"), ("90", "80"), True, False),  # converging
        # Contraction: the ceiling falls and the floor rises, in order.
        ("-3", "3", ("120", "110", "100"), ("80", "90"), False, True),
        ("-2.99", "3", ("120", "110", "100"), ("80", "90"), False, False),
        ("-3", "2.99", ("120", "110", "100"), ("80", "90"), False, False),
        ("-10", "10", ("120", "120", "100"), ("80", "90"), False, False),  # equal highs
        ("-10", "10", ("120", "121", "100"), ("80", "90"), False, False),  # a higher high
        ("-10", "10", ("120", "110", "100"), ("80", "80", "90"), False, False),  # equal lows
        ("-10", "10", ("120", "110", "100"), ("80", "79", "90"), False, False),  # a lower low
        ("10", "-10", ("120", "110", "100"), ("80", "90"), False, False),  # diverging
    ],
)
def test_the_slopes_and_the_order_of_contacts_of_each_phase(
    upper: str,
    lower: str,
    highs: tuple[str, ...],
    lows: tuple[str, ...],
    expanding: bool,
    expected: bool,
) -> None:
    fit = a_phase(upper, lower, highs, lows)
    params = DEFAULT_DIAMOND_PARAMS.channel_params()
    assert phase_accepts(fit, params, expanding=expanding) is expected


# -- what the evidence and the window say about what is (and is not) inside --------------------


def test_a_diamond_whose_expansion_is_longer_is_one_figure_not_one_per_starting_swing() -> None:
    """Nine swings: the expansion has seven, and the diamond that begins two swings later (with a
    shorter expansion) ends at the same swing. It is a piece of the first: not another figure."""
    candles = zigzag([*UP, 122, 138, 112, 146, 102, 154, 111, 145])
    found = now(candles)
    assert len(found) == 1
    assert labels_of(found[0]) == [
        "UPPER_1",
        "LOWER_1",
        "UPPER_2",
        "LOWER_2",
        "UPPER_3",
        "LOWER_3",
        "UPPER_4",
        "LOWER_4",
        "UPPER_5",
    ]
    assert fact(found[0], "DIAMOND_PHASES")["expansion_swings"] == 7


@pytest.mark.parametrize(
    ("extremes", "swings", "broadening"),
    [
        ([*UP, 112, 140, 96, 150, 105, 141], 5, True),  # five swings and tall enough
        ([*UP, 108, 142, 94, 133, 103], 4, False),  # tall enough but only four swings
        ([*UP, 122, 138, 108, 146, 117, 137], 5, False),  # five swings but too short (2 of 28)
    ],
)
def test_the_expansion_is_a_broadening_formation_only_with_five_swings_and_enough_height(
    extremes: list[int | str], swings: int, broadening: bool
) -> None:
    phases = fact(diamond_now(zigzag(extremes)), "DIAMOND_PHASES")
    assert phases["expansion_swings"] == swings
    assert phases["expansion_phase_is_broadening"] is broadening


def exact_line(points: Sequence[Any], at: datetime) -> Decimal:
    """The line through two boundary points, multiplying before dividing as the detector does."""
    first, last = points[0], points[-1]
    seconds = D((last.time - first.time).total_seconds())
    return D(
        first.price + (last.price - first.price) * D((at - first.time).total_seconds()) / seconds
    )


def wicked(candles: list[Candle], k: int, **changes: Any) -> list[Candle]:
    replaced = list(candles)
    replaced[k] = dataclasses.replace(candles[k], **changes)
    return replaced


def test_a_high_exactly_on_the_exit_line_is_not_a_penetration_and_one_above_it_is() -> None:
    candles = creeping_diamond()
    boundaries = history(candles, at_close(candles))[0].latest.boundaries
    upper = boundaries[2]
    k = len(candles) - 6
    on_the_line = exact_line(upper.points, candles[k].close_time)
    assert not has(diamond_now(wicked(candles, k, high=on_the_line)), "WICK_PENETRATIONS")
    over = fact(diamond_now(wicked(candles, k, high=on_the_line + D("0.1"))), "WICK_PENETRATIONS")
    assert over["wick_candles"] == 1


def test_a_wick_through_both_lines_by_the_same_amount_is_recorded_on_the_upper_side() -> None:
    candles = creeping_diamond()
    boundaries = history(candles, at_close(candles))[0].latest.boundaries
    k = len(candles) - 6
    closing = candles[k].close_time
    both = wicked(
        candles,
        k,
        high=exact_line(boundaries[2].points, closing) + 2,
        low=exact_line(boundaries[3].points, closing) - 2,
    )
    wick = fact(diamond_now(both), "WICK_PENETRATIONS")
    assert wick["deepest_side"] == "UPPER" and wick["wick_candles"] == 1


def test_a_swing_exactly_at_a_vertex_is_not_beyond_it() -> None:
    candles = creeping_diamond()
    top = history(candles, at_close(candles))[0].latest.anchors[2].price
    k = len(candles) - 6
    level = fact(diamond_now(wicked(candles, k, high=top)), "WICK_PENETRATIONS")
    assert level["beyond_vertex_swings"] == 0  # equal is not beyond
    above = fact(diamond_now(wicked(candles, k, high=top + D("0.1"))), "WICK_PENETRATIONS")
    assert above["beyond_vertex_swings"] == 1


@pytest.mark.parametrize(
    ("swing", "counted"),
    # The upper exit line is worth 124.5 at candle 60 and the tolerance is 0.15 x 43.5 = 6.525:
    # a high of 117.975 is exactly that far below it.
    [("117.5", True), ("117.475", True), ("117.4", False)],
)
def test_a_contact_must_be_within_the_tolerance_of_the_contraction_height(
    swing: str, counted: bool
) -> None:
    candles = zigzag([*BASE, swing])
    assert has(diamond_now(candles, at_close(candles)), "ADDITIONAL_CONTACTS") is counted


def test_wick_facts_stop_at_the_apex() -> None:
    """Near the apex the lines are so close that the wicks of the candles between them touch them:
    that counts. Past the apex the lines have crossed and there is no exit to penetrate."""
    upper, lower = exit_lines(BASE)
    base = zigzag(BASE, tail=0)
    candles = [*base, *creeping(base, upper, lower, 40)]  # well past the apex
    crossed = next(
        c
        for c in candles[len(base) :]
        if line_at(upper.points, c.close_time) <= line_at(lower.points, c.close_time)
    )
    wick = fact(diamond_now(candles, at_close(candles)), "WICK_PENETRATIONS")
    assert D(wick["wick_candles"]) > 0
    assert wick["last_wick_open_time"] < iso(crossed.open_time)


def test_only_a_confirmed_breakout_has_a_confirmation_time() -> None:
    pending = zigzag([*BASE, 126], tail_to=126)
    assert "confirmation_close_time" not in fact(diamond_now(pending), "DIAMOND_TIMING")
    confirmed = zigzag(UP_OUT[0], **UP_OUT[1])
    assert "confirmation_close_time" in fact(diamond_now(confirmed), "DIAMOND_TIMING")
