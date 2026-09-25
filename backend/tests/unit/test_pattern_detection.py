"""POINT3-REVERSAL-001: the reversal detectors (doubles and triples).

Series are built candle by candle as zigzags between chosen extremes, so every pivot, level and
breakout can be read off the numbers and the expected story written from the rules in
``docs/domain/detectores-de-reversion.md``, never from the code under test. No look-ahead is
checked at every instant, on the figures and on seeded random walks.
"""

import ast
import dataclasses
import re
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from freyja_backend.domain import pattern_detection, pattern_double, pattern_triple
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
from freyja_backend.domain.market_data import Candle, InvalidMarketDataError
from freyja_backend.domain.pattern_detection import (
    DEFAULT_REVERSAL_PARAMS,
    DetectionContext,
    DetectorResult,
    InvalidDetectionRequestError,
    PatternDetector,
    ReversalParams,
    Side,
    replay_detector,
    update_instances,
)
from freyja_backend.domain.pattern_double import DoubleBottomDetector, DoubleTopDetector
from freyja_backend.domain.pattern_triple import TripleBottomDetector, TripleTopDetector
from tests.unit.test_market_trend import (
    AUTHORIZED,
    BTC,
    DOWN,
    SOURCE,
    T0,
    TF,
    UP,
    candle_at,
    random_walk,
    zigzag,
)

REPO = Path(__file__).resolve().parents[3]
TF_START = T0
S = PatternState
DETECTORS: list[PatternDetector] = [
    DoubleTopDetector(),
    DoubleBottomDetector(),
    TripleTopDetector(),
    TripleBottomDetector(),
]


# -- builders -----------------------------------------------------------------------------------


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
        params=ReversalParams(**params) if params else DEFAULT_REVERSAL_PARAMS,
    )


# An uptrend that peaks at 130, then the figure, then what the price does next.
DOUBLE_TOP = [*UP, 118, "130.5", 105]
TRIPLE_TOP = [*UP, 118, "130.2", "117.6", "129.8", 100]


def instances_of(
    detector: PatternDetector, extremes: Sequence[int | str], **series: Any
) -> tuple[PatternInstance, ...]:
    candles = zigzag(extremes, **series)
    return replay_detector(detector, context_for(candles), candles)


def the_one(
    instances: Sequence[PatternInstance], *, compatible: bool | None = None
) -> PatternInstance:
    """The figure the test is about: the one that got furthest (the noise around it is checked
    on its own)."""
    pool = [i for i in instances if compatible is None or prior_compatible(i) is compatible]
    assert pool, "no instance found"
    order = list(PatternState)
    return max(pool, key=lambda i: (len(i.latest.anchors), order.index(i.state)))


def prior_compatible(instance: PatternInstance) -> bool:
    return bool(facts_of(instance, "PRIOR_TREND")["compatible"])


def facts_of(instance: PatternInstance, code: str) -> dict[str, Any]:
    """The facts of one piece of evidence of the latest evaluation, by name."""
    return dict(next(e for e in instance.latest.evidence if e.code == code).facts)


def states(instance: PatternInstance) -> list[PatternState]:
    return [e.state for e in instance.evaluations]


# -- the double top, told from its rules --------------------------------------------------------


def test_a_double_top_is_seen_forming_then_valid_then_broken_out_of() -> None:
    figure = the_one(instances_of(DoubleTopDetector(), DOUBLE_TOP, tail_to=104), compatible=True)

    assert figure.pattern_type is PatternType.DOUBLE_TOP
    assert states(figure) == [S.FORMING, S.GEOMETRICALLY_VALID, S.CONFIRMED_DOWN]
    assert [a.label for a in figure.latest.anchors] == [
        "FIRST_EXTREME",
        "INTERMEDIATE",
        "SECOND_EXTREME",
    ]
    first, trough, second = figure.latest.anchors
    assert (first.kind.value, trough.kind.value, second.kind.value) == ("HIGH", "LOW", "HIGH")
    assert abs(first.price - second.price) < Decimal("1")  # comparable peaks
    # The neckline is the level of the trough, and the breakout closed below it.
    (neckline,) = figure.latest.boundaries
    assert neckline.role is BoundaryRole.NECKLINE
    assert {point.price for point in neckline.points} == {trough.price}
    assert neckline.contacts == (trough.open_time,)
    breakout = figure.latest.breakout
    assert breakout is not None and breakout.confirmed
    assert breakout.direction is BreakoutDirection.DOWN and breakout.close_price < trough.price
    assert breakout.candle_close_time <= figure.last_evaluated_at


def test_every_result_explains_its_pivots_levels_and_state() -> None:
    figure = the_one(instances_of(DoubleTopDetector(), DOUBLE_TOP, tail_to=104), compatible=True)

    codes = {item.code for item in figure.latest.evidence}
    assert {"EXTREME_LEVELS", "PRIOR_TREND", "BREAKOUT_SCAN"} <= codes
    levels = facts_of(figure, "EXTREME_LEVELS")
    assert levels["height"] > 0 and levels["extreme_gap"] < levels["height"] * Decimal("0.15")
    assert levels["level_tolerance"] == Decimal("0.15")
    trend = facts_of(figure, "PRIOR_TREND")
    assert trend == {"compatible": True, "required": "UPTREND", "state": "UPTREND"}
    assert figure.traditional_bias is PatternBias.BEARISH
    assert figure.detector_version == "double-top-detector-v1"
    assert figure.parameter_version == "reversal-params-v1"


def test_a_double_bottom_is_the_same_story_upside_down() -> None:
    figure = the_one(
        instances_of(DoubleBottomDetector(), mirror(DOUBLE_TOP), tail_to=196), compatible=True
    )

    assert figure.pattern_type is PatternType.DOUBLE_BOTTOM
    assert states(figure) == [S.FORMING, S.GEOMETRICALLY_VALID, S.CONFIRMED_UP]
    first, peak, second = figure.latest.anchors
    assert (first.kind.value, peak.kind.value, second.kind.value) == ("LOW", "HIGH", "LOW")
    breakout = figure.latest.breakout
    assert breakout is not None and breakout.direction is BreakoutDirection.UP
    assert breakout.close_price > peak.price
    trend = facts_of(figure, "PRIOR_TREND")
    assert trend["state"] == "DOWNTREND" and trend["compatible"] is True
    assert figure.traditional_bias is PatternBias.BULLISH


def test_a_top_finds_no_bottom_and_a_bottom_no_top() -> None:
    top_series = zigzag(DOUBLE_TOP, tail_to=104)
    on_a_top = replay_detector(DoubleBottomDetector(), context_for(top_series), top_series)
    assert not any(prior_compatible(i) for i in on_a_top)  # any bottom is not after a downtrend
    bottom_series = zigzag(mirror(DOUBLE_TOP), tail_to=196)
    on_a_bottom = replay_detector(DoubleTopDetector(), context_for(bottom_series), bottom_series)
    assert not any(prior_compatible(i) for i in on_a_bottom)


def test_a_breakout_that_does_not_reach_the_margin_stays_pending() -> None:
    figure = the_one(
        instances_of(DoubleTopDetector(), [*UP, 118, "130.5", "117.0"], tail_to=116.6),
        compatible=True,
    )

    assert figure.state is S.BREAKOUT_PENDING_CONFIRMATION
    breakout = figure.latest.breakout
    assert breakout is not None and not breakout.confirmed
    scan = facts_of(figure, "BREAKOUT_SCAN")
    assert scan["resolved"] is False


def test_a_breakout_that_closes_back_inside_fails() -> None:
    figure = the_one(
        instances_of(DoubleTopDetector(), [*UP, 118, "130.5", "117.0", 128], tail_to=127),
        compatible=True,
    )

    assert figure.state is S.FAILED_BREAKOUT and figure.is_terminal
    assert S.BREAKOUT_PENDING_CONFIRMATION in states(figure) or S.CONFIRMED_DOWN in states(figure)
    scan = facts_of(figure, "BREAKOUT_SCAN")
    assert scan["resolved"] is True


def test_the_price_going_the_other_way_before_any_breakout_ends_the_figure() -> None:
    figure = the_one(instances_of(DoubleTopDetector(), [*UP, 118, 136], tail_to=135))
    assert figure.state is S.INVALIDATED
    assert figure.latest.invalidation_reasons == (InvalidationReason.CLOSED_THROUGH_AGAINST_BIAS,)


def test_a_second_extreme_that_does_not_agree_is_not_a_double_top() -> None:
    """A lower second peak, far from the first: not comparable, and it never was one."""
    found = instances_of(DoubleTopDetector(), [*UP, 118, 124, 105], tail_to=104)
    assert not any(
        i.latest.anchors[0].price == Decimal("130.5") and len(i.latest.anchors) >= 3 for i in found
    )
    assert not any(
        i.state in (S.GEOMETRICALLY_VALID, S.CONFIRMED_DOWN)
        for i in found
        if i.latest.anchors[0].price >= Decimal("130")
    )


def test_a_wiggle_too_small_to_matter_is_not_a_figure() -> None:
    small = instances_of(DoubleTopDetector(), [*UP, "128.5", "130.2", 127], tail_to=126)
    assert not [i for i in small if i.latest.anchors[0].price >= Decimal("130")]


def test_an_unresolved_figure_goes_stale() -> None:
    aged = instances_of(DoubleTopDetector(), [*UP, 118, "130.5", 124], tail_to=125)
    stale_params = context_for(zigzag([*UP, 118, "130.5", 124], tail_to=125), max_age_candles=25)
    candles = zigzag([*UP, 118, "130.5", 124], tail_to=125)
    tight = replay_detector(DoubleTopDetector(), stale_params, candles)

    assert the_one(aged, compatible=True).state in (S.GEOMETRICALLY_VALID, S.FORMING)
    figure = the_one(tight, compatible=True)
    assert figure.state is S.INVALIDATED
    assert figure.latest.invalidation_reasons == (InvalidationReason.TOO_LONG,)


def test_without_an_uptrend_before_it_the_top_is_seen_but_flagged() -> None:
    """A double top after a downtrend: observed, the fact recorded, never dropped or assumed."""
    after_a_fall = the_one(
        instances_of(DoubleTopDetector(), [*DOWN, 190, 180, "190.2", 170], tail_to=169),
    )
    trend = facts_of(after_a_fall, "PRIOR_TREND")
    assert trend["state"] != "UPTREND" and trend["compatible"] is False  # a rally from a low
    assert trend["required"] == "UPTREND"
    assert after_a_fall.state in (
        S.CONFIRMED_DOWN,
        S.GEOMETRICALLY_VALID,
        S.BREAKOUT_PENDING_CONFIRMATION,
    )


def test_a_fall_right_after_the_second_peak_is_the_breakout_not_the_end_of_the_figure() -> None:
    """A pivot is confirmed k candles late: when the crash follows the peak at once, the figure
    becomes knowable already broken out. It goes straight from forming to confirmed."""
    base = zigzag([*UP, 118, "130.5"], tail=0)
    last = base[-1]
    crash = [
        candle_at(last.open_time + TF.duration * (n + 1), Decimal(mid), TF.duration)
        for n, mid in enumerate((112, 108, 108, 108, 108))
    ]
    candles = [*base, *crash]
    figure = the_one(
        replay_detector(DoubleTopDetector(), context_for(candles), candles), compatible=True
    )

    assert states(figure) == [S.FORMING, S.CONFIRMED_DOWN]  # no stop at GEOMETRICALLY_VALID
    assert figure.latest.invalidation_reasons == ()
    breakout = figure.latest.breakout
    assert breakout is not None and breakout.confirmed
    assert breakout.candle_open_time == crash[0].open_time  # the very first crash candle


def test_a_figure_is_not_made_smaller_by_what_the_price_does_after_it() -> None:
    """Its size is judged against the range where it began, a fixed yardstick: a later crash that
    widens the recent range must not turn a confirmed figure into a wiggle."""
    candles = zigzag([*UP, 118, "130.5", 60], tail_to=59)
    figure = the_one(
        replay_detector(DoubleTopDetector(), context_for(candles), candles), compatible=True
    )
    assert figure.state is S.CONFIRMED_DOWN
    # And what the detector says at the last instant, not only what the history kept:
    now = DoubleTopDetector().detect(context_for(candles), candles)
    assert any(
        c.evaluation.state is S.CONFIRMED_DOWN and c.evaluation.anchors[0].price == Decimal("130.5")
        for c in now.candidates
    )
    levels = facts_of(figure, "EXTREME_LEVELS")
    assert levels["reference_range"] < levels["height"] * 4  # measured where it began, not at 60


# -- how a breakout is judged: only closes, strictly beyond, what came first wins ------------------


def judged(mids: Sequence[float], **params: Any) -> Any:
    candles = [
        candle_at(TF_START + TF.duration * n, Decimal(str(mid)), TF.duration)
        for n, mid in enumerate(mids)
    ]
    return pattern_detection.judge(
        candles,
        side=Side.TOP,
        params=ReversalParams(**params) if params else DEFAULT_REVERSAL_PARAMS,
        start_index=0,
        exceed_from=0,
        breakout_from=1,
        complete=True,
        forming=False,
        neckline_at=lambda _candle: Decimal(100),
        height=Decimal(10),
        extreme_price=Decimal(106),
    )


def test_a_close_exactly_on_the_neckline_is_not_beyond_it_and_a_small_one_is_only_pending() -> None:
    assert judged([105, 100, 100]).state is S.GEOMETRICALLY_VALID  # on the level: not through it
    assert judged([105, 99.9]).state is S.BREAKOUT_PENDING_CONFIRMATION  # 0.1 < margin (1.0)
    assert judged([105, 99.0]).state is S.CONFIRMED_DOWN  # exactly the margin: confirmed
    assert judged([105, 98.9]).state is S.CONFIRMED_DOWN


def test_a_wick_through_the_neckline_is_not_a_breakout() -> None:
    wick = candle_at(TF_START + TF.duration, Decimal("101"), TF.duration)  # low 100.5 ... close 101
    deep_wick = dataclasses.replace(wick, low=Decimal("90"))  # the wick pierces, the close does not
    first = candle_at(TF_START, Decimal(105), TF.duration)
    judgement = pattern_detection.judge(
        [first, deep_wick],
        side=Side.TOP,
        params=DEFAULT_REVERSAL_PARAMS,
        start_index=0,
        exceed_from=0,
        breakout_from=1,
        complete=True,
        forming=False,
        neckline_at=lambda _candle: Decimal(100),
        height=Decimal(10),
        extreme_price=Decimal(106),
    )
    assert judgement is not None and judgement.state is S.GEOMETRICALLY_VALID


def test_a_return_inside_only_counts_as_failure_within_the_window() -> None:
    inside_the_window = judged([105, 98, 103], failure_window_candles=3)
    assert inside_the_window.state is S.FAILED_BREAKOUT
    after_the_window = judged([105, 98, 97, 97, 97, 97, 103], failure_window_candles=3)
    assert after_the_window.state is S.CONFIRMED_DOWN  # the breakout stands
    assert after_the_window.first_beyond_index == 1


def test_what_came_first_wins_between_a_breakout_and_the_price_going_the_other_way() -> None:
    other_way_first = judged([105, 120, 98])
    assert other_way_first.state is S.INVALIDATED
    assert other_way_first.invalidation_reasons == (InvalidationReason.CLOSED_THROUGH_AGAINST_BIAS,)
    breakout_first = judged([105, 98, 97, 97, 97, 120], failure_window_candles=2)
    assert breakout_first.state is S.CONFIRMED_DOWN  # not "invalidated" by what happens later


# -- the triple top -----------------------------------------------------------------------------


def test_a_triple_top_needs_all_three_extremes_to_agree() -> None:
    figure = the_one(instances_of(TripleTopDetector(), TRIPLE_TOP, tail_to=99), compatible=True)

    assert figure.pattern_type is PatternType.TRIPLE_TOP
    assert states(figure) == [S.FORMING, S.GEOMETRICALLY_VALID, S.CONFIRMED_DOWN]
    assert [a.label for a in figure.evaluations[0].anchors] == [
        "EXTREME_1",
        "INTERMEDIATE_1",
        "EXTREME_2",
        "INTERMEDIATE_2",
    ]  # forming with four
    assert len(figure.latest.anchors) == 5
    (neckline,) = figure.latest.boundaries
    lower_trough = min(a.price for a in figure.latest.anchors if a.label.startswith("INTER"))
    assert {p.price for p in neckline.points} == {lower_trough}  # the lower of the two troughs
    assert len(neckline.contacts) == 2
    levels = facts_of(figure, "EXTREME_LEVELS")
    assert levels["largest_peak_gap"] <= levels["height"] * Decimal("0.15")
    assert levels["trough_gap"] <= levels["height"] * Decimal("0.15")


def test_a_triple_bottom_is_the_same_story_upside_down() -> None:
    figure = the_one(
        instances_of(TripleBottomDetector(), mirror(TRIPLE_TOP), tail_to=201), compatible=True
    )
    assert figure.pattern_type is PatternType.TRIPLE_BOTTOM
    assert states(figure) == [S.FORMING, S.GEOMETRICALLY_VALID, S.CONFIRMED_UP]
    assert figure.traditional_bias is PatternBias.BULLISH


def test_two_agreeing_peaks_and_one_that_does_not_are_no_triple_top() -> None:
    found = instances_of(TripleTopDetector(), [*UP, 118, "130.2", "117.6", 124, 100], tail_to=99)
    assert not [i for i in found if i.state in (S.GEOMETRICALLY_VALID, S.CONFIRMED_DOWN)]


def test_troughs_that_do_not_agree_are_no_triple_top() -> None:
    found = instances_of(TripleTopDetector(), [*UP, 118, "130.2", 112, "129.8", 100], tail_to=99)
    assert not [i for i in found if i.state in (S.GEOMETRICALLY_VALID, S.CONFIRMED_DOWN)]


def test_a_third_peak_that_does_not_agree_with_the_other_two_is_no_triple_top() -> None:
    """The first two agree with each other and with the mean; the third is the one that does not:
    it must agree with both, so this is a double top with a stray, not a triple top."""
    found = instances_of(
        TripleTopDetector(), [*UP, 118, "130.2", "117.6", "125.7", 100], tail_to=99
    )
    assert not [i for i in found if i.state in (S.GEOMETRICALLY_VALID, S.CONFIRMED_DOWN)]


def test_a_triple_wiggle_too_small_to_matter_is_not_a_figure() -> None:
    small = instances_of(
        TripleTopDetector(), [*UP, "128.5", "130.2", "128.3", "130.0", 127], tail_to=126
    )
    assert not [i for i in small if i.latest.anchors[0].price >= Decimal("130")]


def test_a_triple_top_and_the_double_tops_inside_it_coexist() -> None:
    candles = zigzag(TRIPLE_TOP, tail_to=99)
    triple = replay_detector(TripleTopDetector(), context_for(candles), candles)
    doubles = replay_detector(DoubleTopDetector(), context_for(candles), candles)

    both = {*(i.pattern_instance_id for i in triple), *(i.pattern_instance_id for i in doubles)}
    assert len(both) == len(triple) + len(doubles)  # none replaces or hides another
    assert the_one(triple, compatible=True).state is S.CONFIRMED_DOWN
    assert the_one(doubles, compatible=True).state is S.CONFIRMED_DOWN
    # The double top that starts at the second peak follows a market that was not rising into
    # it: seen, and flagged as such.
    late_start = max(doubles, key=lambda i: i.started_at)
    assert prior_compatible(late_start) is False


# -- the data has to be fit, or nothing is judged -----------------------------------------------


def test_data_that_is_not_fit_judges_no_figure_and_says_why() -> None:
    candles = zigzag(DOUBLE_TOP, tail_to=104)
    holed = [c for i, c in enumerate(candles) if i != 100]
    result = DoubleTopDetector().detect(context_for(candles), holed)
    assert result.candidates == ()
    assert MissingDataReason.GAPS_IN_WINDOW in result.unfit_reasons
    assert result.as_of == candles[-1].close_time

    few = candles[:40]
    assert DoubleTopDetector().detect(context_for(few), few).unfit_reasons == (
        MissingDataReason.INSUFFICIENT_HISTORY,
    )
    unauthorised = dataclasses.replace(context_for(candles), authorized_sources=frozenset({"X"}))
    assert DoubleTopDetector().detect(unauthorised, candles).unfit_reasons == (
        MissingDataReason.SOURCE_NOT_AUTHORIZED,
    )


def test_bad_data_never_raises_but_a_wrong_request_does() -> None:
    candles = zigzag(DOUBLE_TOP, tail_to=104)
    contradictory = [*candles, candle_at(candles[-1].open_time, Decimal("50"))]
    result = DoubleTopDetector().detect(context_for(candles), contradictory)
    assert result.candidates == () and result.unfit_reasons  # contradicts itself: refused, quietly

    naive = dataclasses.replace(
        context_for(candles), observed_at=candles[-1].close_time.replace(tzinfo=None)
    )
    with pytest.raises(InvalidMarketDataError):
        DoubleTopDetector().detect(naive, candles)


def test_open_figures_are_paused_when_the_data_becomes_unfit_and_go_on_afterwards() -> None:
    candles = zigzag(DOUBLE_TOP, tail_to=104)
    detector = DoubleTopDetector()
    full = replay_detector(detector, context_for(candles), candles)
    valid = the_one(full, compatible=True)
    at = next(e.evaluated_at for e in valid.evaluations if e.state is S.GEOMETRICALLY_VALID)
    upto = [c for c in candles if c.close_time <= at]
    before = replay_detector(detector, context_for(upto).at(at), upto)
    assert the_one(before, compatible=True).state is S.GEOMETRICALLY_VALID

    hole = upto[-30].open_time
    holed = [c for c in candles if c.close_time <= at + TF.duration and c.open_time != hole]
    later = at + TF.duration
    result = detector.detect(context_for(holed).at(later), holed)
    paused = update_instances(before, result, observed_at=later)

    paused_figure = next(i for i in paused if i.pattern_instance_id == valid.pattern_instance_id)
    assert paused_figure.state is S.INSUFFICIENT_DATA
    assert MissingDataReason.GAPS_IN_WINDOW in paused_figure.latest.insufficient_data_reasons
    # The data comes back: it goes on from the state it had, it does not start over.
    clean = [c for c in candles if c.close_time <= later + TF.duration]
    again = detector.detect(context_for(clean).at(later + TF.duration), clean)
    resumed = update_instances(paused, again, observed_at=later + TF.duration)
    figure = next(i for i in resumed if i.pattern_instance_id == valid.pattern_instance_id)
    assert figure.state in (
        S.GEOMETRICALLY_VALID,
        S.CONFIRMED_DOWN,
        S.BREAKOUT_PENDING_CONFIRMATION,
    )
    assert figure.pattern_instance_id == valid.pattern_instance_id


# -- carrying instances from one instant to the next --------------------------------------------


def one_result(instant_index: int, extremes: Sequence[int | str] = DOUBLE_TOP) -> Any:
    candles = zigzag(extremes, tail_to=104)
    detector = DoubleTopDetector()
    at = candles[instant_index].close_time
    upto = [c for c in candles if c.close_time <= at]
    return candles, detector, at, detector.detect(context_for(candles).at(at), upto)


def test_a_figure_that_was_invalidated_from_the_start_never_becomes_an_instance() -> None:
    _, _, at, result = one_result(len(zigzag(DOUBLE_TOP, tail_to=104)) - 1)
    invalidated = tuple(
        dataclasses.replace(
            c,
            evaluation=dataclasses.replace(
                c.evaluation,
                state=S.INVALIDATED,
                breakout=None,
                boundaries=(),
                invalidation_reasons=(InvalidationReason.GEOMETRY_BROKEN,),
            ),
        )
        for c in result.candidates
    )
    assert (
        update_instances((), dataclasses.replace(result, candidates=invalidated), observed_at=at)
        == ()
    )


def test_a_figure_the_detector_no_longer_sees_is_invalidated_unless_it_was_confirmed() -> None:
    candles = zigzag(DOUBLE_TOP, tail_to=104)
    detector = DoubleTopDetector()
    full = replay_detector(detector, context_for(candles), candles)
    forming = min(
        (i for i in full if S.FORMING in states(i) and len(i.evaluations[0].anchors) == 2),
        key=lambda i: len(i.evaluations),
    )
    at = forming.evaluations[0].evaluated_at
    first_only = PatternInstance(
        forming.pattern_type,
        forming.instrument_id,
        forming.data_source,
        forming.timeframe,
        forming.detector_version,
        forming.parameter_version,
        forming.evaluations[:1],
    )
    nothing = DetectorResult((), (), at + TF.duration)
    after = update_instances((first_only,), nothing, observed_at=at + TF.duration)
    assert after[0].state is S.INVALIDATED
    assert after[0].latest.invalidation_reasons == (InvalidationReason.GEOMETRY_BROKEN,)

    confirmed = the_one(full, compatible=True)
    kept = update_instances((confirmed,), nothing, observed_at=candles[-1].close_time + TF.duration)
    assert kept == (confirmed,)  # a confirmed figure stays as it was confirmed


def test_anchors_that_are_no_longer_the_figures_supersede_it_and_nothing_is_rewritten() -> None:
    candles = zigzag(DOUBLE_TOP, tail_to=104)
    detector = DoubleTopDetector()
    full = replay_detector(detector, context_for(candles), candles)
    figure = the_one(full, compatible=True)
    first_only = PatternInstance(
        figure.pattern_type,
        figure.instrument_id,
        figure.data_source,
        figure.timeframe,
        figure.detector_version,
        figure.parameter_version,
        figure.evaluations[:1],
    )
    at = figure.evaluations[1].evaluated_at
    upto = [c for c in candles if c.close_time <= at]
    result = detector.detect(context_for(candles).at(at), upto)
    (candidate,) = [
        c for c in result.candidates if c.pattern_instance_id == figure.pattern_instance_id
    ]
    moved = dataclasses.replace(
        candidate.evaluation.anchors[1], price=candidate.evaluation.anchors[1].price + 1
    )
    other_anchors = (candidate.evaluation.anchors[0], moved, *candidate.evaluation.anchors[2:])
    changed = dataclasses.replace(
        candidate,
        evaluation=dataclasses.replace(candidate.evaluation, anchors=other_anchors),
    )
    after = update_instances(
        (first_only,), dataclasses.replace(result, candidates=(changed,)), observed_at=at
    )
    (superseded,) = [i for i in after if i.pattern_instance_id == figure.pattern_instance_id]
    assert superseded.state is S.INVALIDATED
    assert superseded.latest.invalidation_reasons == (InvalidationReason.SUPERSEDED,)
    assert superseded.evaluations[0] == first_only.evaluations[0]  # the past is untouched


def test_a_finished_figure_is_never_touched_again() -> None:
    candles = zigzag([*UP, 118, "130.5", "117.0", 128], tail_to=127)
    detector = DoubleTopDetector()
    failed = the_one(replay_detector(detector, context_for(candles), candles), compatible=True)
    assert failed.is_terminal

    result = detector.detect(context_for(candles), candles)
    after = update_instances((failed,), result, observed_at=candles[-1].close_time)
    assert failed in after  # exactly as it was, whatever the detector says now


def test_an_evaluation_is_only_added_when_something_changes() -> None:
    figure = the_one(instances_of(DoubleTopDetector(), DOUBLE_TOP, tail_to=104), compatible=True)
    assert len(figure.evaluations) == 3  # not one per candle
    assert len({e.evaluated_at for e in figure.evaluations}) == 3


# -- no look-ahead, reproducible ----------------------------------------------------------------

_FIGURES = {
    "double top": (DoubleTopDetector, DOUBLE_TOP, 104),
    "double bottom": (DoubleBottomDetector, mirror(DOUBLE_TOP), 196),
    "triple top": (TripleTopDetector, TRIPLE_TOP, 99),
    "triple bottom": (TripleBottomDetector, mirror(TRIPLE_TOP), 201),
}


def wild_future(candles: Sequence[Candle], after: Any) -> list[Candle]:
    return [
        c if c.close_time <= after else candle_at(c.open_time, Decimal(1 + i % 2) * 5000)
        for i, c in enumerate(candles)
    ]


@pytest.mark.parametrize("name", list(_FIGURES))
def test_a_figure_at_any_instant_depends_only_on_what_was_closed_by_then(name: str) -> None:
    make, extremes, tail_to = _FIGURES[name]
    detector = make()
    candles = zigzag(extremes, tail_to=tail_to)
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
def test_random_walks_never_leak_the_future_into_any_detector(seed: int) -> None:
    candles = random_walk(seed, 260)
    found = 0
    for index in range(110, 259, 6):
        at = candles[index].close_time
        upto = [c for c in candles if c.close_time <= at]
        context = context_for(candles).at(at)
        for detector in DETECTORS:
            past = detector.detect(context, upto)
            assert detector.detect(context, candles) == past, (seed, index, detector.version)
            found += len(past.candidates)
    assert found > 0  # the walks do produce candidates: the equality is not between empty results


@pytest.mark.parametrize("name", ["double top", "triple top"])
def test_the_history_a_detector_builds_is_the_same_whatever_comes_later(name: str) -> None:
    make, extremes, tail_to = _FIGURES[name]
    detector = make()
    candles = zigzag(extremes, tail_to=tail_to)
    for cut in (len(candles) - 25, len(candles) - 12, len(candles) - 1):
        at = candles[cut].close_time
        upto = [c for c in candles if c.close_time <= at]
        assert replay_detector(detector, context_for(candles).at(at), candles) == replay_detector(
            detector, context_for(upto).at(at), upto
        )


def test_the_same_candles_always_give_the_same_history() -> None:
    candles = zigzag(TRIPLE_TOP, tail_to=99)
    detector = TripleTopDetector()
    first = replay_detector(detector, context_for(candles), candles)
    assert replay_detector(detector, context_for(candles), candles) == first
    ids = [i.pattern_instance_id for i in first]
    assert ids == [
        i.pattern_instance_id for i in replay_detector(detector, context_for(candles), candles)
    ]


def test_remembering_a_prior_trend_never_changes_an_answer() -> None:
    candles = zigzag(DOUBLE_TOP, tail_to=104)
    detector = DoubleTopDetector()
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


# -- the units are independent, the parameters are versioned, and nothing decides ---------------


def test_each_detector_is_its_own_unit_with_its_own_version() -> None:
    versions = {d.version for d in DETECTORS}
    assert versions == {
        "double-top-detector-v1",
        "double-bottom-detector-v1",
        "triple-top-detector-v1",
        "triple-bottom-detector-v1",
    }
    assert {d.pattern_type for d in DETECTORS} == {
        PatternType.DOUBLE_TOP,
        PatternType.DOUBLE_BOTTOM,
        PatternType.TRIPLE_TOP,
        PatternType.TRIPLE_BOTTOM,
    }
    assert {(d.pattern_type, d.side) for d in DETECTORS} == {
        (PatternType.DOUBLE_TOP, Side.TOP),
        (PatternType.DOUBLE_BOTTOM, Side.BOTTOM),
        (PatternType.TRIPLE_TOP, Side.TOP),
        (PatternType.TRIPLE_BOTTOM, Side.BOTTOM),
    }
    # Double and triple share only the plumbing: neither imports the other's geometry.
    for module in (pattern_double, pattern_triple):
        text = Path(str(module.__file__)).read_text(encoding="utf-8")
        assert (
            "pattern_triple" not in text
            if module is pattern_double
            else "pattern_double" not in text
        )


def _doc_parameters() -> dict[str, Decimal]:
    text = (REPO / "docs" / "domain" / "detectores-de-reversion.md").read_text(encoding="utf-8")
    section = text.split("## 2. Parámetros")[1].split("## 3.")[0]
    found: dict[str, Decimal] = {}
    for line in section.splitlines():
        match = re.match(r"\|\s*`([a-z_.]+)`\s*\|\s*([0-9,]+)\s*\|", line)
        if match:
            found[match.group(1)] = Decimal(match.group(2).replace(",", "."))
    return found


def test_the_documented_parameters_are_exactly_the_default_ones() -> None:
    documented = _doc_parameters()
    params = DEFAULT_REVERSAL_PARAMS
    assert documented == {
        "level_tolerance": params.level_tolerance,
        "min_height_fraction": params.min_height_fraction,
        "range_window_candles": Decimal(params.range_window_candles),
        "breakout_margin": params.breakout_margin,
        "failure_window_candles": Decimal(params.failure_window_candles),
        "max_age_candles": Decimal(params.max_age_candles),
        "exceed_margin": params.exceed_margin,
        "min_history": Decimal(params.min_history),
        "pivot_params.k": Decimal(params.pivot_params.k),
    }
    assert params.version == "reversal-params-v1"


@pytest.mark.parametrize(
    "bad",
    [
        {"level_tolerance": Decimal(0)},
        {"level_tolerance": Decimal(1)},
        {"level_tolerance": 0.15},
        {"min_height_fraction": Decimal("1.5")},
        {"breakout_margin": Decimal("-0.1")},
        {"exceed_margin": Decimal(0)},
        {"failure_window_candles": 0},
        {"max_age_candles": True},
        {"min_history": 1.5},
        {"range_window_candles": -1},
        {"version": " "},
    ],
)
def test_parameters_that_make_no_sense_are_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(InvalidDetectionRequestError):
        ReversalParams(**bad)


def test_a_different_parameter_version_is_another_instance() -> None:
    candles = zigzag(DOUBLE_TOP, tail_to=104)
    detector = DoubleTopDetector()
    default = the_one(replay_detector(detector, context_for(candles), candles), compatible=True)
    tuned = the_one(
        replay_detector(detector, context_for(candles, version="reversal-params-v2"), candles),
        compatible=True,
    )
    assert default.pattern_instance_id != tuned.pattern_instance_id
    assert tuned.parameter_version == "reversal-params-v2"


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
    candles = zigzag(DOUBLE_TOP, tail_to=104)
    result = DoubleTopDetector().detect(context_for(candles), candles)
    assert result.candidates
    fields = {f.name for f in dataclasses.fields(DetectorResult)}
    fields |= {f.name for f in dataclasses.fields(type(result.candidates[0]))}
    assert fields.isdisjoint(_FORBIDDEN)


def test_the_detectors_only_read_the_domain_never_a_candlestick_pattern_or_an_indicator() -> None:
    allowed = {
        "abc",
        "enum",
        "uuid",
        "collections.abc",
        "dataclasses",
        "datetime",
        "decimal",
        "typing",
    }
    for module in (pattern_detection, pattern_double, pattern_triple):
        tree = ast.parse(Path(str(module.__file__)).read_text(encoding="utf-8"))
        imported = {
            n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
        } | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        foreign = {
            m for m in imported if m not in allowed and not m.startswith("freyja_backend.domain.")
        }
        assert foreign == set(), module.__name__
        assert not {m for m in imported if "indicator" in m or "candlestick" in m}
