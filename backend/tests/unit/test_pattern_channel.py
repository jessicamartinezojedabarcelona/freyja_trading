"""POINT3-CONTINUATION-001: the triangle and rectangle detectors.

Series are built leg by leg (ten candles per leg, prices in exact tenths) so every contact, line
and breakout can be read off the numbers, and the expected story is written from the rules in
``docs/domain/detectores-de-continuacion.md``, never from the code under test. The lines run
through the wicks of the swing points: a swing "at 130" has its high at 130.5 and a swing "at
118" its low at 117.5.
"""

import ast
import dataclasses
import re
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from freyja_backend.domain import pattern_channel, pattern_detection
from freyja_backend.domain.chart_pattern import (
    BoundaryRole,
    BreakoutDirection,
    InvalidationReason,
    PatternBias,
    PatternInstance,
    PatternState,
    PatternType,
)
from freyja_backend.domain.market_calendar import MarketSchedule
from freyja_backend.domain.market_context import MissingDataReason
from freyja_backend.domain.market_data import Candle
from freyja_backend.domain.pattern_channel import (
    AscendingTriangleDetector,
    ChannelDetector,
    ContinuationDetector,
    DescendingTriangleDetector,
    RectangleDetector,
    SymmetricalTriangleDetector,
    falling,
    flat,
    rising,
)
from freyja_backend.domain.pattern_detection import (
    DEFAULT_CONTINUATION_PARAMS,
    ContinuationParams,
    DetectionContext,
    InvalidDetectionRequestError,
    replay_detector,
    update_instances,
)
from tests.unit.test_market_trend import (
    AUTHORIZED,
    BTC,
    SOURCE,
    T0,
    TF,
    UP,
    candle_at,
    random_walk,
    zigzag,
)

REPO = Path(__file__).resolve().parents[3]
S = PatternState
STEP = TF.duration

DETECTORS: list[ChannelDetector] = [
    RectangleDetector(),
    AscendingTriangleDetector(),
    DescendingTriangleDetector(),
    SymmetricalTriangleDetector(),
]

# The price runs up to 130 (the first upper contact), then bounces between the lines.
# Ascending: a flat ceiling at 130 (high 130.5) and lows that rise 4 at a time: 118, 122, 126.
ASCENDING = [*UP, 118, 130, 122, 130, 126, 130]
# Rectangle: flat ceiling at 130 and flat floor at 118.
RECTANGLE = [*UP, 118, 130, 118, 130, 118]
# Symmetrical: highs falling 130, 128, 126 and lows rising 116, 118, 120 (lines meet around
# candle 190 of the series).
SYMMETRICAL = [*UP, 116, 128, 118, 126, 120]


def mirror(extremes: Sequence[int | str]) -> list[int | str]:
    """The same figure upside down: every price p becomes 300 - p."""
    return [str(Decimal(300) - Decimal(str(e))) for e in extremes]


def context_for(candles: Sequence[Candle], **params: Any) -> DetectionContext:
    return DetectionContext(
        instrument_id="instrument-1",
        instrument=BTC,
        schedule=MarketSchedule.CONTINUOUS_24_7,
        data_source=SOURCE,
        authorized_sources=AUTHORIZED,
        timeframe=TF,
        observed_at=candles[-1].close_time,
        continuation=ContinuationParams(**params) if params else DEFAULT_CONTINUATION_PARAMS,
    )


def history(
    detector: ContinuationDetector, candles: Sequence[Candle], **params: Any
) -> tuple[PatternInstance, ...]:
    return replay_detector(detector, context_for(candles, **params), candles)


def figure_of(instances: Sequence[PatternInstance]) -> PatternInstance:
    """The figure the test is about: the one that got furthest."""
    assert instances, "no figure was found"
    order = list(PatternState)
    return max(instances, key=lambda i: (len(i.latest.anchors), order.index(i.state)))


def the_figure(
    detector: ContinuationDetector, extremes: Sequence[int | str], **series: Any
) -> PatternInstance:
    return figure_of(history(detector, zigzag(extremes, **series)))


def states(instance: PatternInstance) -> list[PatternState]:
    return [e.state for e in instance.evaluations]


def facts_of(instance: PatternInstance, code: str) -> dict[str, Any]:
    return dict(next(e for e in instance.latest.evidence if e.code == code).facts)


def labels(instance: PatternInstance) -> list[str]:
    return [a.label for a in instance.latest.anchors]


# -- the slopes: what is flat, what rises and what falls ----------------------------------------


def test_a_boundary_is_flat_within_its_tolerance_and_sloping_beyond_the_minimum() -> None:
    params = DEFAULT_CONTINUATION_PARAMS  # flat: up to 0.10 of the height; sloping: from 0.15
    height = Decimal(20)
    assert flat(Decimal(2), height, params) and flat(Decimal(-2), height, params)  # exactly 0.10
    assert not flat(Decimal("2.01"), height, params) and not flat(Decimal("-2.01"), height, params)
    assert rising(Decimal(3), height, params) and not rising(Decimal("2.99"), height, params)
    assert falling(Decimal(-3), height, params) and not falling(Decimal("-2.99"), height, params)
    # Between the two a boundary is neither: it makes no figure of this family.
    assert not (flat(Decimal("2.5"), height, params) or rising(Decimal("2.5"), height, params))


# -- the four figures, told from their rules ----------------------------------------------------


def test_an_ascending_triangle_is_valid_and_then_broken_out_of_upwards() -> None:
    figure = the_figure(AscendingTriangleDetector(), [*ASCENDING, 136])

    assert figure.pattern_type is PatternType.ASCENDING_TRIANGLE
    assert figure.traditional_bias is PatternBias.BULLISH
    assert states(figure)[0] is S.GEOMETRICALLY_VALID  # nothing is claimed before the 4th contact
    assert S.FORMING not in states(figure)
    assert states(figure)[-1] is S.CONFIRMED_UP
    assert labels(figure) == ["UPPER_1", "LOWER_1", "UPPER_2", "LOWER_2", "UPPER_3", "LOWER_3"]
    upper, lower = figure.latest.boundaries
    assert (upper.role, lower.role) == (BoundaryRole.UPPER, BoundaryRole.LOWER)
    assert {p.price for p in upper.points} == {Decimal("130.5")}  # a flat ceiling
    assert [p.price for p in lower.points] == [Decimal("117.5"), Decimal("125.5")]  # a rising floor
    assert len(upper.contacts) == 3 and len(lower.contacts) == 3
    breakout = figure.latest.breakout
    assert breakout is not None and breakout.confirmed
    assert breakout.direction is BreakoutDirection.UP and breakout.boundary is BoundaryRole.UPPER
    assert breakout.close_price > Decimal("130.5")
    assert figure.detector_version == "ascending-triangle-detector-v1"
    assert figure.parameter_version == "continuation-params-v1"


def test_a_descending_triangle_is_the_same_story_upside_down() -> None:
    figure = the_figure(DescendingTriangleDetector(), mirror([*ASCENDING, 136]))

    assert figure.pattern_type is PatternType.DESCENDING_TRIANGLE
    assert figure.traditional_bias is PatternBias.BEARISH
    assert states(figure)[-1] is S.CONFIRMED_DOWN
    upper, lower = figure.latest.boundaries
    assert {p.price for p in lower.points} == {Decimal("169.5")}  # a flat floor
    assert upper.points[0].price > upper.points[-1].price  # a falling ceiling
    breakout = figure.latest.breakout
    assert breakout is not None and breakout.confirmed
    assert breakout.direction is BreakoutDirection.DOWN and breakout.boundary is BoundaryRole.LOWER


def test_a_symmetrical_triangle_goes_the_way_the_price_breaks_and_expects_neither() -> None:
    up = the_figure(SymmetricalTriangleDetector(), [*SYMMETRICAL, 130])
    down = the_figure(SymmetricalTriangleDetector(), [*SYMMETRICAL, 108])

    assert up.pattern_type is PatternType.SYMMETRICAL_TRIANGLE
    assert up.traditional_bias is PatternBias.BREAKOUT_DEPENDENT
    assert states(up)[-1] is S.CONFIRMED_UP and states(down)[-1] is S.CONFIRMED_DOWN
    assert up.latest.breakout is not None and down.latest.breakout is not None
    assert up.latest.breakout.boundary is BoundaryRole.UPPER
    assert down.latest.breakout.boundary is BoundaryRole.LOWER
    upper, lower = up.latest.boundaries
    assert upper.points[0].price > upper.points[-1].price  # falling highs
    assert lower.points[0].price < lower.points[-1].price  # rising lows
    # While the two series are the same series the two stories are one story: no direction was
    # anticipated. (They part ways as soon as the price leaves the last floor contact.)
    up_candles, down_candles = zigzag([*SYMMETRICAL, 130]), zigzag([*SYMMETRICAL, 108])
    shared_until = next(
        a.open_time for a, b in zip(up_candles, down_candles, strict=True) if a != b
    )
    before_up = [e for e in up.evaluations if e.evaluated_at <= shared_until]
    before_down = [e for e in down.evaluations if e.evaluated_at <= shared_until]
    assert before_up and before_up == before_down
    assert all(e.state is S.GEOMETRICALLY_VALID and e.breakout is None for e in before_up)
    # The trend that came before is context and nothing more.
    trend = facts_of(up, "PRIOR_TREND")
    assert trend == {"state": "UPTREND"}


def test_a_rectangle_is_flat_on_both_sides_and_breaks_either_way() -> None:
    down = the_figure(RectangleDetector(), [*RECTANGLE, 111])
    up = the_figure(RectangleDetector(), [*RECTANGLE, 130, 137])

    assert down.pattern_type is PatternType.RECTANGLE
    assert down.traditional_bias is PatternBias.BREAKOUT_DEPENDENT
    upper, lower = down.latest.boundaries
    assert {p.price for p in upper.points} == {Decimal("130.5")}
    assert {p.price for p in lower.points} == {Decimal("117.5")}
    assert states(down)[-1] is S.CONFIRMED_DOWN and states(up)[-1] is S.CONFIRMED_UP
    assert down.latest.breakout is not None and up.latest.breakout is not None
    assert down.latest.breakout.boundary is BoundaryRole.LOWER
    assert up.latest.breakout.boundary is BoundaryRole.UPPER


def test_every_result_explains_its_lines_and_where_the_price_came_from() -> None:
    figure = the_figure(AscendingTriangleDetector(), [*ASCENDING, 136])

    codes = {item.code for item in figure.latest.evidence}
    assert {"CHANNEL", "PRIOR_TREND", "BREAKOUT_SCAN"} <= codes
    channel = facts_of(figure, "CHANNEL")
    assert channel["upper_contacts"] == 3 and channel["lower_contacts"] == 3
    assert channel["height"] == Decimal("15")  # 130.5 down to the floor's line, 115.5, at the start
    assert channel["upper_rise"] == Decimal(0) and channel["lower_rise"] == Decimal(10)
    assert channel["span_candles"] == 50  # from the first upper contact to the last lower one
    assert channel["flat_tolerance"] == Decimal("0.10") and channel["slope_min"] == Decimal("0.15")
    assert facts_of(figure, "PRIOR_TREND") == {"state": "UPTREND"}


def test_a_figure_that_is_not_one_of_the_four_is_none_of_them() -> None:
    """Both boundaries rising and converging is a wedge; both diverging is a broadening formation;
    neither belongs to this family (POINT3-EXPANSION-001)."""
    wedge = zigzag([*UP, 116, 132, 122, 134, 128, 136])
    broadening = zigzag([*UP, 124, 132, 118, 136, 112, 140])
    for candles in (wedge, broadening):
        for detector in DETECTORS:
            assert history(detector, candles) == (), detector.version


# -- what is, and is not, one figure ------------------------------------------------------------


def test_a_channel_needs_its_fourth_contact_and_its_time_and_its_height() -> None:
    three = zigzag([*UP, 118, 130])  # a ceiling contact, a floor contact, a ceiling contact
    assert history(AscendingTriangleDetector(), three) == ()  # the floor has no line yet
    candles = zigzag([*ASCENDING, 136])
    assert history(AscendingTriangleDetector(), candles, min_channel_candles=999) == ()
    assert history(AscendingTriangleDetector(), candles, min_height_fraction=Decimal("0.99")) == ()


def test_a_channel_spans_at_least_the_minimum_number_of_candles_and_exactly_that_is_enough() -> (
    None
):
    candles = zigzag([*ASCENDING, 136])
    # Four contacts (the smallest figure) span 30 candles: first ceiling to second floor.
    assert history(AscendingTriangleDetector(), candles, min_channel_candles=30)
    assert history(AscendingTriangleDetector(), candles, min_channel_candles=31) == ()


def test_a_contact_that_strays_from_its_line_stops_the_figure_growing_at_that_point() -> None:
    """The second ceiling contact is a swing at 130.5: its wick reaches 131.0, half a point above
    the line through the first and the last contact (130.5), though its close stays on the line.
    With the default tolerance (0.15 of a height of 13) that is a contact; with 0.03 (0.39) it is
    not, and the figure stops growing before the contact that would keep it. Upside down, the same
    for the floor."""
    stray: list[int | str] = [*UP, 118, "130.5", 118, 130, 118]
    for extremes, first in ((stray, "UPPER_1"), (mirror(stray), "LOWER_1")):
        candles = zigzag(extremes)
        whole = next(f for f in history(RectangleDetector(), candles) if labels(f)[0] == first)
        assert len(whole.latest.anchors) == 6
        tight = history(RectangleDetector(), candles, contact_tolerance=Decimal("0.03"))
        early = next(f for f in tight if labels(f)[0] == first)
        assert len(early.latest.anchors) == 4, labels(early)


def test_a_close_beyond_a_line_between_two_contacts_stops_the_figure_growing_there() -> None:
    """The second ceiling contact is at 130.6: its close (130.6) is above the line through the
    first and the last contact (130.5), so between those two the price had already left the
    channel. Upside down, the same with the floor."""
    stray: list[int | str] = [*UP, 118, "130.6", 118, 130, 118]
    for extremes, first in ((stray, "UPPER_1"), (mirror(stray), "LOWER_1")):
        figures = history(RectangleDetector(), zigzag(extremes))
        early = next(f for f in figures if labels(f)[0] == first)
        assert len(early.latest.anchors) == 4, labels(early)


def test_one_triangle_is_one_instance_not_one_per_starting_swing() -> None:
    candles = zigzag([*ASCENDING, 136])
    instances = history(AscendingTriangleDetector(), candles)
    assert len(instances) == 1  # the pieces of a figure that began earlier are not other figures
    assert instances[0].latest.anchors[0].label == "UPPER_1"


def test_a_contact_that_strays_from_its_line_ends_the_figure_there() -> None:
    stray = zigzag([*UP, 118, 130, 122, "127", 126, 130, 136])  # the second ceiling contact sags
    figure = figure_of(history(AscendingTriangleDetector(), stray))
    assert len(figure.latest.anchors) <= 4  # it stays what it was; it never grows past the stray


# -- breakouts: only closes, the margin, failure, and what comes first --------------------------


def test_a_breakout_that_does_not_reach_the_margin_stays_pending() -> None:
    # The price closes 0.2 beyond the ceiling: the margin is 0.10 of a height of 15, that is 1.5.
    figure = the_figure(AscendingTriangleDetector(), [*ASCENDING, "130.7"], tail_to="130.6", tail=1)
    assert states(figure)[-1] is S.BREAKOUT_PENDING_CONFIRMATION
    breakout = figure.latest.breakout
    assert breakout is not None and not breakout.confirmed


def test_a_breakout_that_closes_back_inside_fails_and_stays_failed() -> None:
    # Up through the ceiling by 0.2, back inside, then down through the floor: the first attempt
    # is the one on record and it failed; what came after does not undo or replace it.
    figure = the_figure(AscendingTriangleDetector(), [*ASCENDING, "130.7", 125, 100], tail_to=101)
    assert states(figure)[-1] is S.FAILED_BREAKOUT
    breakout = figure.latest.breakout
    assert breakout is not None and breakout.direction is BreakoutDirection.UP
    assert figure.is_terminal
    # What the detector says at the last instant on its own is the same: the first attempt, up.
    candles = zigzag([*ASCENDING, "130.7", 125, 100], tail_to=101)
    now = AscendingTriangleDetector().detect(context_for(candles), candles)
    (candidate,) = [c for c in now.candidates if len(c.evaluation.anchors) == 6]
    assert candidate.evaluation.state is S.FAILED_BREAKOUT
    assert candidate.evaluation.breakout is not None
    assert candidate.evaluation.breakout.direction is BreakoutDirection.UP


def test_a_wick_through_a_boundary_is_not_a_breakout() -> None:
    candles = zigzag(ASCENDING)
    spiked = [
        dataclasses.replace(c, high=Decimal("140")) if i == len(candles) - 3 else c
        for i, c in enumerate(candles)
    ]
    figure = figure_of(history(AscendingTriangleDetector(), spiked))
    assert figure.latest.breakout is None and states(figure)[-1] is S.GEOMETRICALLY_VALID


def test_a_breakout_that_began_before_a_new_contact_is_never_forgotten() -> None:
    """Growing moves the lines (they pass through the first and the last contact). The price here
    slides below the rising floor, and then a real floor contact at 128 forms and would flatten
    the floor so much that the close through the old floor looks as if it had never left the
    channel. The figure must keep the breakout it already had, and never take that contact."""
    candles = zigzag([*ASCENDING, 128, 136])
    detector = AscendingTriangleDetector()
    figure = figure_of(history(detector, candles))
    assert not any(
        InvalidationReason.SUPERSEDED in e.invalidation_reasons for e in figure.evaluations
    )
    assert figure.latest.breakout is not None
    assert figure.latest.breakout.direction is BreakoutDirection.DOWN  # the slide, not the rally
    assert len(figure.latest.anchors) <= 7
    assert "LOWER_4" not in labels(figure)


@pytest.mark.parametrize("upside_down", [False, True])
def test_a_converging_figure_ends_at_its_apex_if_the_price_never_left(upside_down: bool) -> None:
    """The lines of an ascending triangle meet (around candle 184 of this series); after that the
    ceiling is below the floor and no breakout means anything. The price here creeps up from the
    last ceiling contact, always between the lines until the floor overtakes it, and goes on past
    the apex. It never makes a swing, so nothing changes the lines. The figure ran its course.
    Upside down, the price would be through the other line after the apex."""
    extremes = mirror(ASCENDING) if upside_down else ASCENDING
    detector = DescendingTriangleDetector() if upside_down else AscendingTriangleDetector()
    base = zigzag(extremes, tail=0)  # the last contact with the flat line is candle 170
    start = len(base)
    mids = [Decimal("130") + Decimal("0.025") * (i - 170) for i in range(start, start + 19)]
    assert mids == sorted(set(mids)) and max(mids) < Decimal("130.5")
    if upside_down:
        mids = [Decimal(300) - mid for mid in mids]
    tail = [candle_at(T0 + STEP * (start + n), mid, STEP) for n, mid in enumerate(mids)]
    figure = figure_of(history(detector, [*base, *tail]))
    assert figure.state is S.INVALIDATED
    assert figure.latest.invalidation_reasons == (InvalidationReason.TOO_LONG,)
    assert figure.latest.breakout is None
    assert len(figure.latest.anchors) == 6


def test_an_unresolved_figure_goes_stale() -> None:
    candles = zigzag([*RECTANGLE, 124], tail=0)
    flat_tail = [
        candle_at(candles[-1].open_time + STEP * n, Decimal(124), STEP) for n in range(1, 120)
    ]
    figure = figure_of(history(RectangleDetector(), [*candles, *flat_tail]))
    assert figure.state is S.INVALIDATED
    assert figure.latest.invalidation_reasons == (InvalidationReason.TOO_LONG,)


# -- the retest and the volume: evidence, never a condition -------------------------------------


def test_a_return_to_the_broken_line_is_recorded_as_a_retest_and_confirms_nothing_more() -> None:
    # After the breakout the price comes back to 131: its wick touches the ceiling (130.5), its
    # close stays above it. The breakout was already confirmed; the retest is only evidence.
    figure = the_figure(AscendingTriangleDetector(), [*ASCENDING, 136, 131, 140])
    assert states(figure)[-1] is S.CONFIRMED_UP
    retest = facts_of(figure, "RETEST")
    assert retest["held"] is True and retest["candles_after_confirmation"] >= 1
    # It is a new fact, so it is a new evaluation: the history says when it happened.
    assert states(figure).count(S.CONFIRMED_UP) >= 2


def test_a_breakout_that_is_never_retested_has_no_retest() -> None:
    figure = the_figure(AscendingTriangleDetector(), [*ASCENDING, 136, 140])
    assert states(figure)[-1] is S.CONFIRMED_UP
    assert "RETEST" not in {e.code for e in figure.latest.evidence}


def test_a_retest_whose_close_is_back_inside_is_recorded_as_not_held() -> None:
    # A fast fall after the breakout: the candle that reaches the ceiling with its wick also
    # closes below it. The breakout was confirmed and, being past the failure window, stands.
    figure = the_figure(AscendingTriangleDetector(), [*ASCENDING, 136, 120], tail_to=119)
    assert states(figure)[-1] is S.CONFIRMED_UP
    retest = facts_of(figure, "RETEST")
    assert retest["held"] is False and retest["candles_after_confirmation"] >= 1


def test_the_volume_of_the_breakout_is_recorded_against_the_figures_mean_and_decides_nothing() -> (
    None
):
    candles = zigzag([*ASCENDING, 136])
    plain = figure_of(history(AscendingTriangleDetector(), candles))
    assert states(plain)[-1] is S.CONFIRMED_UP
    breakout = plain.latest.breakout
    assert breakout is not None
    heavy = [
        dataclasses.replace(
            c, volume=Decimal(10 if c.open_time != breakout.candle_open_time else 25)
        )
        for c in candles
    ]
    loud = figure_of(history(AscendingTriangleDetector(), heavy))
    # The volume changes nothing about what the figure is or whether it broke out.
    assert states(loud) == states(plain)
    volume = facts_of(loud, "BREAKOUT_VOLUME")
    first_beyond = loud.latest.breakout
    assert first_beyond is not None
    assert volume["ratio"] == volume["breakout_volume"] / volume["mean_volume"]
    assert volume["breakout_volume"] in (Decimal(25), Decimal(10))
    assert volume["mean_volume"] == Decimal(10)
    # Without volume to compare (an all-zero history) the ratio is simply absent.
    silent = [dataclasses.replace(c, volume=Decimal(0)) for c in candles]
    quiet = figure_of(history(AscendingTriangleDetector(), silent))
    assert "ratio" not in facts_of(quiet, "BREAKOUT_VOLUME")
    assert states(quiet) == states(plain)


# -- instances between instants and data that is not fit ----------------------------------------


def test_data_that_is_not_fit_judges_no_figure_and_says_why() -> None:
    candles = zigzag([*ASCENDING, 136])
    detector = AscendingTriangleDetector()
    holed = [c for i, c in enumerate(candles) if i != 100]
    result = detector.detect(context_for(candles), holed)
    assert result.candidates == ()
    assert MissingDataReason.GAPS_IN_WINDOW in result.unfit_reasons

    few = candles[:40]
    assert detector.detect(context_for(few), few).unfit_reasons == (
        MissingDataReason.INSUFFICIENT_HISTORY,
    )
    unauthorised = dataclasses.replace(context_for(candles), authorized_sources=frozenset({"X"}))
    assert detector.detect(unauthorised, candles).unfit_reasons == (
        MissingDataReason.SOURCE_NOT_AUTHORIZED,
    )


def test_open_figures_are_paused_when_the_data_becomes_unfit_and_go_on_afterwards() -> None:
    candles = zigzag([*ASCENDING, 136])
    detector = AscendingTriangleDetector()
    full = history(detector, candles)
    valid = figure_of(full)
    at = next(e.evaluated_at for e in valid.evaluations if e.state is S.GEOMETRICALLY_VALID)
    upto = [c for c in candles if c.close_time <= at]
    before = replay_detector(detector, context_for(upto).at(at), upto)
    assert figure_of(before).state is S.GEOMETRICALLY_VALID

    later = at + STEP
    holed = [c for c in candles if c.close_time <= later and c.open_time != upto[-30].open_time]
    paused = update_instances(
        before, detector.detect(context_for(holed).at(later), holed), observed_at=later
    )
    paused_figure = next(i for i in paused if i.pattern_instance_id == valid.pattern_instance_id)
    assert paused_figure.state is S.INSUFFICIENT_DATA
    clean = [c for c in candles if c.close_time <= later + STEP]
    resumed = update_instances(
        paused,
        detector.detect(context_for(clean).at(later + STEP), clean),
        observed_at=later + STEP,
    )
    figure = next(i for i in resumed if i.pattern_instance_id == valid.pattern_instance_id)
    assert figure.state is S.GEOMETRICALLY_VALID  # from where it was, not from the start


def test_a_different_parameter_version_is_another_instance() -> None:
    candles = zigzag([*ASCENDING, 136])
    detector = AscendingTriangleDetector()
    default = figure_of(history(detector, candles))
    tuned = figure_of(history(detector, candles, version="continuation-params-v2"))
    assert default.pattern_instance_id != tuned.pattern_instance_id
    assert tuned.parameter_version == "continuation-params-v2"


# -- no look-ahead, determinism -----------------------------------------------------------------

_FIGURES: dict[str, tuple[ChannelDetector, list[int | str]]] = {
    "ascending": (AscendingTriangleDetector(), [*ASCENDING, 136]),
    "descending": (DescendingTriangleDetector(), mirror([*ASCENDING, 136])),
    "symmetrical": (SymmetricalTriangleDetector(), [*SYMMETRICAL, 130]),
    "rectangle": (RectangleDetector(), [*RECTANGLE, 111]),
}


def wild_future(candles: Sequence[Candle], after: Any) -> list[Candle]:
    return [
        c if c.close_time <= after else candle_at(c.open_time, Decimal(1 + i % 2) * 5000)
        for i, c in enumerate(candles)
    ]


@pytest.mark.parametrize("name", list(_FIGURES))
def test_a_figure_at_any_instant_depends_only_on_what_was_closed_by_then(name: str) -> None:
    detector, extremes = _FIGURES[name]
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


@pytest.mark.parametrize("name", list(_FIGURES))
def test_the_history_a_detector_builds_is_the_same_whatever_comes_later(name: str) -> None:
    detector, extremes = _FIGURES[name]
    candles = zigzag(extremes)
    for cut in (len(candles) - 25, len(candles) - 12, len(candles) - 1):
        at = candles[cut].close_time
        upto = [c for c in candles if c.close_time <= at]
        assert replay_detector(detector, context_for(candles).at(at), candles) == replay_detector(
            detector, context_for(upto).at(at), upto
        )


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_random_walks_never_leak_the_future_into_any_detector(seed: int) -> None:
    candles = random_walk(seed, 260)
    for index in range(110, 259, 6):
        at = candles[index].close_time
        upto = [c for c in candles if c.close_time <= at]
        context = context_for(candles).at(at)
        for detector in DETECTORS:
            past = detector.detect(context, upto)
            assert detector.detect(context, candles) == past, (seed, index, detector.version)


def test_the_same_candles_always_give_the_same_history() -> None:
    candles = zigzag([*ASCENDING, 136])
    detector = AscendingTriangleDetector()
    first = history(detector, candles)
    assert history(detector, candles) == first


def test_remembering_a_prior_trend_never_changes_an_answer() -> None:
    candles = zigzag([*SYMMETRICAL, 130])
    detector = SymmetricalTriangleDetector()
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


# -- the units, the parameters and what a detector never does -----------------------------------


def test_each_detector_is_its_own_unit_with_its_own_version() -> None:
    assert {d.version for d in DETECTORS} == {
        "rectangle-detector-v1",
        "ascending-triangle-detector-v1",
        "descending-triangle-detector-v1",
        "symmetrical-triangle-detector-v1",
    }
    assert {d.pattern_type for d in DETECTORS} == {
        PatternType.RECTANGLE,
        PatternType.ASCENDING_TRIANGLE,
        PatternType.DESCENDING_TRIANGLE,
        PatternType.SYMMETRICAL_TRIANGLE,
    }


def _doc_parameters() -> dict[str, Decimal]:
    text = (REPO / "docs" / "domain" / "detectores-de-continuacion.md").read_text(encoding="utf-8")
    section = text.split("## 2. Parámetros")[1].split("## 3.")[0]
    found: dict[str, Decimal] = {}
    for line in section.splitlines():
        match = re.match(r"\|\s*`([a-z_.]+)`\s*\|\s*([0-9,]+)\s*\|", line)
        if match:
            found[match.group(1)] = Decimal(match.group(2).replace(",", "."))
    return found


def test_the_documented_parameters_are_exactly_the_default_ones() -> None:
    params = DEFAULT_CONTINUATION_PARAMS
    documented = _doc_parameters()
    expected = {
        "min_height_fraction": params.min_height_fraction,
        "range_window_candles": Decimal(params.range_window_candles),
        "contact_tolerance": params.contact_tolerance,
        "flat_tolerance": params.flat_tolerance,
        "slope_min": params.slope_min,
        "min_channel_candles": Decimal(params.min_channel_candles),
        "breakout_margin": params.breakout_margin,
        "failure_window_candles": Decimal(params.failure_window_candles),
        "max_age_candles": Decimal(params.max_age_candles),
        "min_history": Decimal(params.min_history),
        "pivot_params.k": Decimal(params.pivot_params.k),
        "mast_max_candles": Decimal(params.mast_max_candles),
        "mast_min_height_fraction": params.mast_min_height_fraction,
        "max_retrace": params.max_retrace,
        "flag_max_height_fraction": params.flag_max_height_fraction,
        "min_flag_candles": Decimal(params.min_flag_candles),
        "max_flag_candles": Decimal(params.max_flag_candles),
        "parallel_tolerance": params.parallel_tolerance,
        "pennant_convergence_min": params.pennant_convergence_min,
        "wedge_convergence_min": params.wedge_convergence_min,
    }
    assert documented == expected
    assert params.version == "continuation-params-v1"


@pytest.mark.parametrize(
    "bad",
    [
        {"contact_tolerance": Decimal(0)},
        {"contact_tolerance": Decimal(1)},
        {"contact_tolerance": 0.15},
        {"min_height_fraction": Decimal("1.5")},
        {"flat_tolerance": Decimal("0.2")},  # flat at 0.2 and sloping from 0.15: at once both
        {"flat_tolerance": Decimal("0.15")},  # flat up to what already counts as sloping
        {"slope_min": Decimal("0.1")},
        {"breakout_margin": Decimal("-0.1")},
        {"min_channel_candles": 0},
        {"failure_window_candles": 0},
        {"max_age_candles": True},
        {"min_history": 1.5},
        {"version": " "},
    ],
)
def test_parameters_that_make_no_sense_are_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(InvalidDetectionRequestError):
        ContinuationParams(**bad)


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
    candles = zigzag([*ASCENDING, 136])
    result = AscendingTriangleDetector().detect(context_for(candles), candles)
    assert result.candidates
    fields = {f.name for f in dataclasses.fields(pattern_detection.DetectorResult)}
    fields |= {f.name for f in dataclasses.fields(type(result.candidates[0]))}
    assert fields.isdisjoint(_FORBIDDEN)


def test_the_detectors_only_read_the_domain_never_a_candlestick_pattern_or_an_indicator() -> None:
    allowed = {"abc", "collections.abc", "dataclasses", "datetime", "decimal", "typing"}
    tree = ast.parse(Path(str(pattern_channel.__file__)).read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    foreign = {
        m for m in imported if m not in allowed and not m.startswith("freyja_backend.domain.")
    }
    assert not foreign, foreign
    forbidden = {"indicators", "candlestick", "market_indicators", "pattern_double"}
    assert not any(any(word in m for word in forbidden) for m in imported)
