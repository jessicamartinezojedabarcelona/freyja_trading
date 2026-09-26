"""POINT3-REVERSAL-001: the head and shoulders detectors.

Same method as the doubles and triples (see test_pattern_detection.py): series built leg by leg
so every pivot is known, and expected stories written from the rules in
``docs/domain/detectores-de-reversion.md``. What is specific here is the **neckline**: a straight
line through the two troughs that may slope, and the head and the shoulders it is judged against.
"""

from decimal import Decimal
from typing import Any

import pytest

from freyja_backend.domain.chart_pattern import (
    BoundaryRole,
    BreakoutDirection,
    InvalidationReason,
    PatternBias,
    PatternState,
    PatternType,
    pattern_instance_from_document,
)
from freyja_backend.domain.pattern_detection import (
    InvalidDetectionRequestError,
    ReversalParams,
    Side,
    judge,
    line_through,
    replay_detector,
)
from freyja_backend.domain.pattern_double import DoubleTopDetector
from freyja_backend.domain.pattern_head_shoulders import (
    HeadAndShouldersBottomDetector,
    HeadAndShouldersTopDetector,
)
from tests.unit.test_market_trend import DOWN, T0, TF, UP, candle_at, zigzag
from tests.unit.test_pattern_detection import (
    context_for,
    facts_of,
    instances_of,
    mirror,
    prior_compatible,
    states,
    the_one,
)

S = PatternState
STEP = TF.duration

# An uptrend that peaks at 130 (the left shoulder), a head at 140, a right shoulder at 131.
FLAT_NECKLINE = [*UP, 118, 140, 119, 131, 105]
# The same, but the second trough is higher: the neckline rises from 118 to 124.
RISING_NECKLINE = [*UP, 118, 140, 124, 133, 108]


# -- the line through the troughs ---------------------------------------------------------------


def test_the_neckline_is_the_straight_line_through_two_points_exactly() -> None:
    line = line_through(T0, Decimal("100"), T0 + STEP * 10, Decimal("110"))
    assert line(T0) == Decimal("100")
    assert line(T0 + STEP * 10) == Decimal("110")
    assert line(T0 + STEP * 5) == Decimal("105")
    # Before the first point and after the second: the same straight line.
    assert line(T0 - STEP * 10) == Decimal("90")
    assert line(T0 + STEP * 20) == Decimal("120")
    falling = line_through(T0, Decimal("110"), T0 + STEP * 10, Decimal("100"))
    assert falling(T0 + STEP * 5) == Decimal("105") and falling(T0 + STEP * 20) == Decimal("90")


def test_a_level_that_does_not_divide_evenly_is_rounded_to_the_stored_precision() -> None:
    line = line_through(T0, Decimal("100"), T0 + STEP * 3, Decimal("101"))
    value = line(T0 + STEP)
    assert value == Decimal("100.333333333333")  # 12 decimals, as prices are stored
    assert isinstance(value, Decimal) and value.as_tuple().exponent == -12


def test_a_line_needs_two_different_instants() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="two different instants"):
        line_through(T0, Decimal(1), T0, Decimal(2))
    with pytest.raises(InvalidDetectionRequestError):
        line_through(T0 + STEP, Decimal(1), T0, Decimal(2))


def judged_against(neckline_at: Any, closes: list[int | str]) -> Any:
    candles = [candle_at(T0 + STEP * n, Decimal(str(mid)), STEP) for n, mid in enumerate(closes)]
    return judge(
        candles,
        side=Side.TOP,
        params=ReversalParams(),
        start_index=0,
        exceed_from=0,
        breakout_from=1,
        complete=True,
        forming=False,
        neckline_at=neckline_at,
        height=Decimal(10),
        extreme_price=Decimal(106),
        exceed_margin=Decimal("0.15"),
    )


def test_a_close_beyond_a_rising_neckline_is_no_break_of_the_lower_trough() -> None:
    """The reason the neckline is a line: with troughs at 96 then 104 the neckline reaches 102 at
    the close of the third candle, so a close of 101 is beyond it; against the lower trough alone
    (96) the same close is nowhere near a break."""
    line = line_through(T0, Decimal("96"), T0 + STEP * 4, Decimal("104"))
    closes: list[int | str] = [100, 100, 101]
    assert judged_against(lambda c: line(c.close_time), closes).state is S.CONFIRMED_DOWN
    assert judged_against(lambda _c: Decimal(96), closes).state is S.GEOMETRICALLY_VALID
    # A close exactly on the line is not through it.
    assert judged_against(lambda c: line(c.close_time), [100, 100, 102]).state is (
        S.GEOMETRICALLY_VALID
    )
    # A falling neckline is followed just the same: it is at 106 when the second candle closes at
    # 105, a break, though 105 is well above the lower trough (102) a flat level would use.
    falling = line_through(T0, Decimal("110"), T0 + STEP * 4, Decimal("102"))
    assert judged_against(lambda c: falling(c.close_time), [105, 105]).state is S.CONFIRMED_DOWN
    assert judged_against(lambda _c: Decimal(102), [105, 105]).state is S.GEOMETRICALLY_VALID


# -- the figure, told from its rules ------------------------------------------------------------


def test_a_head_and_shoulders_top_forms_becomes_valid_and_is_broken_out_of() -> None:
    figure = the_one(
        instances_of(HeadAndShouldersTopDetector(), FLAT_NECKLINE, tail_to=104), compatible=True
    )

    assert figure.pattern_type is PatternType.HEAD_AND_SHOULDERS_TOP
    assert states(figure)[0] is S.FORMING and states(figure)[-1] is S.CONFIRMED_DOWN
    assert S.GEOMETRICALLY_VALID in states(figure)
    assert [a.label for a in figure.evaluations[0].anchors] == [
        "LEFT_SHOULDER",
        "LEFT_TROUGH",
        "HEAD",
        "RIGHT_TROUGH",
    ]
    left, left_trough, head, right_trough, right = figure.latest.anchors
    assert right.label == "RIGHT_SHOULDER"
    assert head.price > left.price and head.price > right.price  # the head stands out
    assert abs(left.price - right.price) < Decimal("3")  # comparable shoulders
    assert (left.kind.value, left_trough.kind.value, head.kind.value) == ("HIGH", "LOW", "HIGH")
    (neckline,) = figure.latest.boundaries
    assert neckline.role is BoundaryRole.NECKLINE
    assert [p.price for p in neckline.points] == [left_trough.price, right_trough.price]
    assert neckline.contacts == (left_trough.open_time, right_trough.open_time)
    breakout = figure.latest.breakout
    assert breakout is not None and breakout.confirmed
    assert breakout.direction is BreakoutDirection.DOWN
    assert figure.traditional_bias is PatternBias.BEARISH
    assert figure.detector_version == "head-and-shoulders-top-detector-v1"


def test_the_result_explains_the_head_the_shoulders_and_the_height() -> None:
    figure = the_one(
        instances_of(HeadAndShouldersTopDetector(), FLAT_NECKLINE, tail_to=104), compatible=True
    )
    facts = facts_of(figure, "HEAD_AND_SHOULDERS")
    assert facts["head_prominence"] >= facts["head_prominence_required"] > 0
    assert facts["shoulder_gap"] <= facts["height"] * Decimal("0.30")
    assert facts["height"] > facts["head_prominence"]
    assert facts_of(figure, "PRIOR_TREND") == {
        "compatible": True,
        "required": "UPTREND",
        "state": "UPTREND",
    }
    assert {"HEAD_AND_SHOULDERS", "PRIOR_TREND", "BREAKOUT_SCAN"} <= {
        e.code for e in figure.latest.evidence
    }


def test_the_inverse_head_and_shoulders_is_the_same_story_upside_down() -> None:
    figure = the_one(
        instances_of(HeadAndShouldersBottomDetector(), mirror(FLAT_NECKLINE), tail_to=196),
        compatible=True,
    )
    assert figure.pattern_type is PatternType.HEAD_AND_SHOULDERS_BOTTOM
    assert states(figure)[0] is S.FORMING and states(figure)[-1] is S.CONFIRMED_UP
    left, _, head, _, right = figure.latest.anchors
    assert head.price < left.price and head.price < right.price  # the head is the lowest
    breakout = figure.latest.breakout
    assert breakout is not None and breakout.direction is BreakoutDirection.UP
    assert facts_of(figure, "PRIOR_TREND")["state"] == "DOWNTREND"
    assert figure.traditional_bias is PatternBias.BULLISH


def test_a_rising_neckline_is_broken_where_the_line_is_not_at_the_level_of_a_trough() -> None:
    figure = the_one(
        instances_of(HeadAndShouldersTopDetector(), RISING_NECKLINE, tail_to=107), compatible=True
    )
    assert figure.state is S.CONFIRMED_DOWN
    _, left_trough, _, right_trough, _ = figure.latest.anchors
    assert right_trough.price > left_trough.price  # the neckline really rises
    assert facts_of(figure, "HEAD_AND_SHOULDERS")["neckline_rise_per_hour"] > 0

    line = line_through(
        left_trough.open_time, left_trough.price, right_trough.open_time, right_trough.price
    )
    breakout = figure.latest.breakout
    assert breakout is not None
    # The breakout closed beyond the line *as it is at that candle*, by at least the margin.
    assert breakout.close_price < line(breakout.candle_close_time)
    height = facts_of(figure, "HEAD_AND_SHOULDERS")["height"]
    assert line(breakout.candle_close_time) - breakout.close_price >= height * Decimal("0.10")

    # And the FIRST close beyond the line is where the detector says it is: found here by
    # brute force against the line, candle by candle, after the right shoulder.
    candles = zigzag(RISING_NECKLINE, tail_to=107)
    right_shoulder = figure.latest.anchors[-1]
    first = next(
        k
        for k, c in enumerate(candles)
        if c.open_time > right_shoulder.open_time and c.close < line(c.close_time)
    )
    scan = facts_of(figure, "BREAKOUT_SCAN")
    evaluated = next(
        k for k, c in enumerate(candles) if c.close_time == figure.last_evaluated_at
    )  # the evidence describes the instant it was recorded, not the end of the series
    assert scan["candles_since_first_close_beyond"] == evaluated - first
    # A flat level at the first trough would have found it at a different candle.
    flat_first = next(
        k
        for k, c in enumerate(candles)
        if c.open_time > right_shoulder.open_time and c.close < left_trough.price
    )
    assert flat_first != first


# -- what is not a head and shoulders -----------------------------------------------------------


def test_it_is_only_forming_once_the_price_is_back_at_the_level_of_the_first_shoulder() -> None:
    """Four confirmed anchors are not yet a figure in formation: the price has to have come back
    up to the first shoulder's level. Right when the second trough is confirmed it has not."""
    candles = zigzag(FLAT_NECKLINE, tail_to=104)
    detector = HeadAndShouldersTopDetector()
    figure = the_one(replay_detector(detector, context_for(candles), candles), compatible=True)
    right_trough = figure.latest.anchors[3]
    left_shoulder = figure.latest.anchors[0]

    def forming_at(instant: Any) -> list[Any]:
        upto = [c for c in candles if c.close_time <= instant]
        result = detector.detect(context_for(candles).at(instant), upto)
        return [c for c in result.candidates if c.evaluation.anchors[0] == left_shoulder]

    assert forming_at(right_trough.confirmed_at) == []  # the price is still down at the trough
    assert forming_at(figure.evaluations[0].evaluated_at)  # ... and once it is back, it forms


def test_a_fall_right_after_the_right_shoulder_is_the_breakout_at_its_first_candle() -> None:
    base = zigzag([*UP, 118, 140, 119, 131], tail=0)
    last = base[-1]
    crash = [
        candle_at(last.open_time + STEP * (n + 1), Decimal(mid), STEP)
        for n, mid in enumerate((110, 105, 105, 105, 105))
    ]
    candles = [*base, *crash]
    figure = the_one(
        replay_detector(HeadAndShouldersTopDetector(), context_for(candles), candles),
        compatible=True,
    )
    assert figure.state is S.CONFIRMED_DOWN
    breakout = figure.latest.breakout
    assert breakout is not None and breakout.candle_open_time == crash[0].open_time


def test_a_middle_extreme_that_does_not_stand_out_is_no_head() -> None:
    found = instances_of(HeadAndShouldersTopDetector(), [*UP, 118, 131, 119, 131, 105], tail_to=104)
    assert not [i for i in found if i.latest.anchors[0].price >= Decimal("130")]


def test_the_head_needs_to_stand_out_by_the_parameter_and_no_less() -> None:
    candles = zigzag(FLAT_NECKLINE, tail_to=104)
    demanding = replay_detector(
        HeadAndShouldersTopDetector(),
        context_for(candles, head_prominence=Decimal("0.6")),
        candles,
    )
    relaxed = replay_detector(HeadAndShouldersTopDetector(), context_for(candles), candles)
    assert the_one(relaxed, compatible=True).state is S.CONFIRMED_DOWN
    assert not [i for i in demanding if i.latest.anchors[0].price >= Decimal("130")]


def test_a_head_that_only_just_clears_the_right_shoulder_is_no_head() -> None:
    """The head clears the left shoulder well and the shoulders agree with each other, but it
    barely clears the right one: the prominence is against the *higher* shoulder."""
    candles = zigzag([*UP, 118, 137, 119, "135.5", 105], tail_to=104)
    found = replay_detector(HeadAndShouldersTopDetector(), context_for(candles), candles)
    assert not [i for i in found if i.state in (S.GEOMETRICALLY_VALID, S.CONFIRMED_DOWN)]
    # It did look like one while the right shoulder was still to come, and stopped being one.
    ended = [i for i in found if i.latest.anchors[0].price >= Decimal("130")]
    assert ended and all(i.state is S.INVALIDATED for i in ended)


def test_a_wiggle_too_small_to_matter_is_not_a_head_and_shoulders() -> None:
    small = instances_of(
        HeadAndShouldersTopDetector(), [*UP, 127, 133, "127.5", "130.5", 124], tail_to=123
    )
    assert not [i for i in small if i.latest.anchors[0].price >= Decimal("130")]


def test_shoulders_that_are_far_apart_are_no_head_and_shoulders() -> None:
    found = instances_of(HeadAndShouldersTopDetector(), [*UP, 118, 140, 119, 122, 105], tail_to=104)
    assert not [i for i in found if i.state in (S.GEOMETRICALLY_VALID, S.CONFIRMED_DOWN)]


def test_the_shoulder_tolerance_is_the_parameter() -> None:
    candles = zigzag([*UP, 118, 140, 119, 124, 105], tail_to=104)
    detector = HeadAndShouldersTopDetector()
    loose = replay_detector(
        detector, context_for(candles, shoulder_tolerance=Decimal("0.6")), candles
    )
    strict = replay_detector(
        detector, context_for(candles, shoulder_tolerance=Decimal("0.1")), candles
    )
    assert the_one(loose, compatible=True).state in (S.GEOMETRICALLY_VALID, S.CONFIRMED_DOWN)
    assert not [i for i in strict if i.state in (S.GEOMETRICALLY_VALID, S.CONFIRMED_DOWN)]


def test_a_right_shoulder_that_reaches_the_head_ends_the_figure() -> None:
    found = instances_of(HeadAndShouldersTopDetector(), [*UP, 118, 140, 119, 145, 105], tail_to=104)
    ended = [
        i for i in found if i.latest.anchors[0].price >= Decimal("130") and i.state is S.INVALIDATED
    ]
    assert ended
    reasons = {r for i in ended for r in i.latest.invalidation_reasons}
    assert reasons <= {
        InvalidationReason.ANCHOR_EXCEEDED,
        InvalidationReason.CLOSED_THROUGH_AGAINST_BIAS,
    }
    assert not [i for i in found if i.state in (S.GEOMETRICALLY_VALID, S.CONFIRMED_DOWN)]


def test_without_an_uptrend_before_it_the_figure_is_seen_but_flagged() -> None:
    after_a_fall = the_one(
        instances_of(
            HeadAndShouldersTopDetector(), [*DOWN, 185, 175, 195, 176, 186, 165], tail_to=164
        )
    )
    assert prior_compatible(after_a_fall) is False
    assert facts_of(after_a_fall, "PRIOR_TREND")["state"] != "UPTREND"
    assert after_a_fall.state in (
        S.GEOMETRICALLY_VALID,
        S.BREAKOUT_PENDING_CONFIRMATION,
        S.CONFIRMED_DOWN,
    )


def test_a_head_and_shoulders_does_not_look_like_the_other_families() -> None:
    """The middle extreme of a double top does not have to stand out and its two extremes must
    be level; a head and shoulders needs a head and only roughly level shoulders. Same candles,
    different figures: neither detector lends its rules to the other."""
    candles = zigzag(FLAT_NECKLINE, tail_to=104)
    head_shoulders = replay_detector(HeadAndShouldersTopDetector(), context_for(candles), candles)
    doubles = replay_detector(DoubleTopDetector(), context_for(candles), candles)
    assert {i.pattern_type for i in head_shoulders} == {PatternType.HEAD_AND_SHOULDERS_TOP}
    assert {i.pattern_type for i in doubles} == {PatternType.DOUBLE_TOP}
    hs_ids = {i.pattern_instance_id for i in head_shoulders}
    assert not hs_ids & {i.pattern_instance_id for i in doubles}


def test_an_instance_of_it_survives_the_document_round_trip() -> None:
    figure = the_one(
        instances_of(HeadAndShouldersTopDetector(), FLAT_NECKLINE, tail_to=104), compatible=True
    )
    assert pattern_instance_from_document(figure.document()) == figure


def test_the_height_is_measured_from_the_line_at_the_time_of_the_head() -> None:
    figure = the_one(
        instances_of(HeadAndShouldersTopDetector(), RISING_NECKLINE, tail_to=107), compatible=True
    )
    _, left_trough, head, right_trough, _ = figure.latest.anchors
    assert left_trough.open_time < head.open_time < right_trough.open_time
    line = line_through(
        left_trough.open_time, left_trough.price, right_trough.open_time, right_trough.price
    )
    # Vertically at the head's time, from the line, not from either trough.
    assert facts_of(figure, "HEAD_AND_SHOULDERS")["height"] == head.price - line(head.open_time)
    assert head.price - line(head.open_time) not in (
        head.price - left_trough.price,
        head.price - right_trough.price,
    )
