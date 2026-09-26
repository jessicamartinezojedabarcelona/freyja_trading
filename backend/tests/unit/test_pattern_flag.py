"""POINT3-CONTINUATION-001: the flag and pennant detectors.

Series are built leg by leg (ten candles per leg, prices in exact tenths), so every contact, line
and breakout can be read off the numbers and the expected story written from the rules in
``docs/domain/detectores-de-continuacion.md``, never from the code under test. The mast is one
leg: a swing low at 122 whose price rises to a swing high at 150 in ten candles; a swing "at 122"
has its low at 121.5 and a swing "at 150" its high at 150.5.
"""

import ast
import dataclasses
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from freyja_backend.domain import pattern_flag
from freyja_backend.domain.chart_pattern import (
    BoundaryRole,
    BreakoutDirection,
    InvalidationReason,
    PatternBias,
    PatternRole,
    PatternState,
    PatternType,
)
from freyja_backend.domain.market_context import MissingDataReason
from freyja_backend.domain.pattern_detection import (
    ContinuationParams,
    InvalidDetectionRequestError,
    replay_detector,
)
from freyja_backend.domain.pattern_flag import (
    BearFlagDetector,
    BearPennantDetector,
    BullFlagDetector,
    BullPennantDetector,
    MastDetector,
)
from tests.unit.test_market_trend import DOWN, T0, TF, UP, candle_at, random_walk, zigzag
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
_SIX = Decimal("0.000001")

DETECTORS: list[MastDetector] = [
    BullFlagDetector(),
    BearFlagDetector(),
    BullPennantDetector(),
    BearPennantDetector(),
]

# A rising trend, a pullback to 122 (the mast starts there), a mast up to 150 in ten candles, and
# then four contacts of a consolidation: highs 150, 149, 148 and lows 146, 145, 144 (parallel,
# falling one point every twenty candles).
BULL_FLAG = [*UP, 122, 150, 146, 149, 145, 148, 144]
# The same mast and a consolidation that converges: highs 150, 148.5, 147.5 and lows 145, 146.5,
# 146.8 (the lines meet a few dozen candles later).
BULL_PENNANT = [*UP, 122, 150, 145, "148.5", "146.5", "147.5", "146.8"]
# After a downtrend a sharp rise off its low: the mast is 21.0 tall against a recent range of 28.
AFTER_DOWNTREND = [*DOWN, 190, 186, 189, 185, 188, 184]

FIVE = ["MAST_START", "MAST_END", "LOWER_1", "UPPER_2", "LOWER_2"]
FIVE_BEAR = ["MAST_START", "MAST_END", "UPPER_1", "LOWER_2", "UPPER_2"]


# -- the four figures, told from their rules ----------------------------------------------------


def test_a_bull_flag_is_a_mast_a_parallel_pause_and_a_breakout_upwards() -> None:
    figure = the_figure(BullFlagDetector(), [*BULL_FLAG, 156])

    assert figure.pattern_type is PatternType.BULL_FLAG
    assert figure.traditional_bias is PatternBias.BULLISH
    assert states(figure)[0] is S.GEOMETRICALLY_VALID  # nothing is claimed before the 4th contact
    assert S.FORMING not in states(figure) and states(figure)[-1] is S.CONFIRMED_UP
    assert labels(figure) == FIVE  # the mast, and four contacts of which the first is its end
    start, end, *_ = figure.latest.anchors
    assert (start.kind.value, end.kind.value) == ("LOW", "HIGH")  # up: from a low to a high
    upper, lower = figure.latest.boundaries
    assert (upper.role, lower.role) == (BoundaryRole.UPPER, BoundaryRole.LOWER)
    assert upper.contacts[0] == end.open_time  # the end of the mast is the first upper contact
    assert upper.points[0].price > upper.points[-1].price  # drifting down a little...
    assert lower.points[0].price > lower.points[-1].price  # ...on both sides, in parallel
    breakout = figure.latest.breakout
    assert breakout is not None and breakout.confirmed
    assert breakout.direction is BreakoutDirection.UP and breakout.boundary is BoundaryRole.UPPER
    assert figure.detector_version == "bull-flag-detector-v1"
    assert figure.parameter_version == "continuation-params-v1"
    assert PatternRole.CONTINUATION in figure.traditional_roles


def test_a_bear_flag_is_the_same_story_upside_down() -> None:
    figure = the_figure(BearFlagDetector(), mirror([*BULL_FLAG, 156]))

    assert figure.pattern_type is PatternType.BEAR_FLAG
    assert figure.traditional_bias is PatternBias.BEARISH
    assert states(figure)[-1] is S.CONFIRMED_DOWN
    assert labels(figure) == FIVE_BEAR
    start, end, *_ = figure.latest.anchors
    assert (start.kind.value, end.kind.value) == ("HIGH", "LOW")
    breakout = figure.latest.breakout
    assert breakout is not None and breakout.confirmed
    assert breakout.direction is BreakoutDirection.DOWN and breakout.boundary is BoundaryRole.LOWER


def test_a_pennant_is_a_mast_and_a_converging_pause_and_goes_the_way_of_the_mast() -> None:
    bull = the_figure(BullPennantDetector(), [*BULL_PENNANT, 156])
    bear = the_figure(BearPennantDetector(), mirror([*BULL_PENNANT, 156]))

    assert bull.pattern_type is PatternType.BULL_PENNANT
    assert bear.pattern_type is PatternType.BEAR_PENNANT
    assert states(bull)[-1] is S.CONFIRMED_UP and states(bear)[-1] is S.CONFIRMED_DOWN
    assert labels(bull) == FIVE and labels(bear) == FIVE_BEAR
    upper, lower = bull.latest.boundaries
    gap_start = upper.points[0].price - lower.points[0].price
    gap_end = upper.points[-1].price - lower.points[-1].price
    assert gap_end < gap_start  # the boundaries close in on each other
    channel = facts_of(bull, "CHANNEL")
    assert channel["gap_at_end"] <= channel["height"] * Decimal("0.7")


def test_a_flag_is_not_a_pennant_and_a_pennant_is_not_a_flag() -> None:
    for detector in (BullPennantDetector(), BearPennantDetector()):
        assert (
            history(detector, zigzag(BULL_FLAG if detector.thrust.sign > 0 else mirror(BULL_FLAG)))
            == ()
        )
    for flag, pennant, extremes in (
        (BullFlagDetector(), BullPennantDetector(), BULL_PENNANT),
        (BearFlagDetector(), BearPennantDetector(), mirror(BULL_PENNANT)),
    ):
        assert history(flag, zigzag(extremes)) == (), flag.version
        assert history(pennant, zigzag(extremes)), pennant.version


def test_a_mast_up_finds_no_bear_figure_and_a_mast_down_no_bull_one() -> None:
    assert history(BearFlagDetector(), zigzag(BULL_FLAG)) == ()
    assert history(BearPennantDetector(), zigzag(BULL_PENNANT)) == ()
    assert history(BullFlagDetector(), zigzag(mirror(BULL_FLAG))) == ()
    assert history(BullPennantDetector(), zigzag(mirror(BULL_PENNANT))) == ()


def test_every_result_explains_the_mast_and_what_the_pause_did_to_it() -> None:
    figure = the_figure(BullFlagDetector(), [*BULL_FLAG, 156])

    codes = {item.code for item in figure.latest.evidence}
    assert {"FLAGPOLE", "CHANNEL", "PRIOR_TREND", "BREAKOUT_SCAN"} <= codes
    pole = facts_of(figure, "FLAGPOLE")
    assert pole["mast_height"] == Decimal("29.0")  # from the low of 121.5 to the high of 150.5
    assert pole["mast_candles"] == 10 and pole["flag_candles"] == 30
    # The pause gave back 6.0 of it (150.5 down to 144.5), is 4.5 tall and drifts 1.5 down.
    assert pole["retracement_share"] == (Decimal(6) / Decimal(29)).quantize(_SIX)
    assert pole["flag_height_share"] == (Decimal("4.5") / Decimal(29)).quantize(_SIX)
    assert pole["drift_share"] == (Decimal("-1.5") / Decimal(29)).quantize(_SIX)
    assert pole["mast_direction"] == "UP"
    # The volume of the mast and of the pause, side by side (all candles have volume 1 here).
    volume = facts_of(figure, "FLAG_VOLUME")
    assert volume == {
        "mast_mean_volume": Decimal(1),
        "pause_mean_volume": Decimal(1),
        "pause_to_mast": Decimal(1),
    }
    # The mast came out of an uptrend: it continues it.
    assert facts_of(figure, "PRIOR_TREND") == {
        "compatible": True,
        "required": "UPTREND",
        "state": "UPTREND",
    }


def test_a_mast_after_the_wrong_trend_is_observed_but_flagged() -> None:
    figure = the_figure(BullFlagDetector(), [*AFTER_DOWNTREND, 194])
    assert states(figure)[-1] is S.CONFIRMED_UP
    assert facts_of(figure, "PRIOR_TREND") == {
        "compatible": False,
        "required": "UPTREND",
        "state": "DOWNTREND",
    }


# -- the flag breaks out one way only -----------------------------------------------------------


def test_a_breakout_against_the_mast_is_recorded_as_such_and_never_forced_into_a_continuation() -> (
    None
):
    """A bull flag expects to break out upwards. If the price closes below its lower boundary
    instead, that is a breakout downwards, contrary to the expectation: it is recorded with its
    real direction, and the direction the mast pointed is kept in the evidence."""
    for detector, extremes, mast, direction, role in (
        (BullFlagDetector(), [*BULL_FLAG, 120], "UP", BreakoutDirection.DOWN, BoundaryRole.LOWER),
        (
            BearFlagDetector(),
            mirror([*BULL_FLAG, 120]),
            "DOWN",
            BreakoutDirection.UP,
            BoundaryRole.UPPER,
        ),
    ):
        figure = the_figure(detector, extremes)
        assert figure.state in (S.CONFIRMED_DOWN, S.CONFIRMED_UP), detector.version
        breakout = figure.latest.breakout
        assert breakout is not None and breakout.confirmed, detector.version
        assert breakout.direction is direction and breakout.boundary is role
        assert facts_of(figure, "FLAGPOLE")["mast_direction"] == mast
        # What the tradition expected is a fact about the figure, not about this outcome.
        assert figure.traditional_bias is (
            PatternBias.BULLISH if detector.thrust.sign > 0 else PatternBias.BEARISH
        )


def test_a_breakout_that_does_not_reach_the_margin_stays_pending_then_fails() -> None:
    # The upper line is at about 147.5 when the price gets there; the margin is 0.10 of a height
    # of 4.5, that is 0.45: a close at 147.6 is beyond it but short of the margin; 148 is not.
    pending = the_figure(BullFlagDetector(), [*BULL_FLAG, "147.6"], tail_to="147.6", tail=1)
    assert states(pending)[-1] is S.BREAKOUT_PENDING_CONFIRMATION
    confirmed = the_figure(BullFlagDetector(), [*BULL_FLAG, 148], tail_to=148, tail=1)
    assert states(confirmed)[-1] is S.CONFIRMED_UP
    failed = the_figure(BullFlagDetector(), [*BULL_FLAG, "147.6", 143, 140], tail_to=139)
    assert states(failed)[-1] is S.FAILED_BREAKOUT and failed.is_terminal


# -- what makes a mast and what makes a flag ----------------------------------------------------


def _both(extremes: list[int | str], bull: MastDetector, bear: MastDetector) -> Any:
    """The same story told both ways: the figure, and its mirror image for the mirror detector."""
    return [(bull, zigzag(extremes)), (bear, zigzag(mirror(extremes)))]


_FLAGS = _both([*BULL_FLAG, 156], BullFlagDetector(), BearFlagDetector())


@pytest.mark.parametrize(("detector", "candles"), _FLAGS)
def test_a_mast_is_short_and_a_ten_candle_one_is_short_enough(
    detector: MastDetector, candles: Any
) -> None:
    assert history(detector, candles, mast_max_candles=10)
    assert history(detector, candles, mast_max_candles=9) == ()


@pytest.mark.parametrize(
    ("detector", "candles"),
    _both([*AFTER_DOWNTREND, 194], BullFlagDetector(), BearFlagDetector()),
)
def test_a_mast_stands_out_from_the_recent_range(detector: MastDetector, candles: Any) -> None:
    # A mast of 21.0 in a range of 28.0: 0.75.
    assert history(detector, candles, mast_min_height_fraction=Decimal("0.7"))
    assert history(detector, candles, mast_min_height_fraction=Decimal("0.8")) == ()


@pytest.mark.parametrize(("detector", "candles"), _FLAGS)
def test_a_flag_gives_back_only_part_of_the_mast(detector: MastDetector, candles: Any) -> None:
    # It gives back 6.0 of 29.0, about 0.21.
    assert history(detector, candles, max_retrace=Decimal("0.3"))
    assert history(detector, candles, max_retrace=Decimal("0.2")) == ()


@pytest.mark.parametrize(("detector", "candles"), _FLAGS)
def test_a_flag_is_small_next_to_its_mast(detector: MastDetector, candles: Any) -> None:
    # 4.5 tall against 29.0: about 0.155.
    assert history(detector, candles, flag_max_height_fraction=Decimal("0.16"))
    assert history(detector, candles, flag_max_height_fraction=Decimal("0.15")) == ()


@pytest.mark.parametrize(("detector", "candles"), _FLAGS)
def test_a_flag_is_brief_and_thirty_candles_are_enough_for_four_contacts(
    detector: MastDetector, candles: Any
) -> None:
    assert history(detector, candles, min_flag_candles=30)  # the four contacts span 30 candles
    assert history(detector, candles, min_flag_candles=31, max_flag_candles=60) == ()
    assert history(detector, candles, max_flag_candles=29) == ()
    # Allowed to be longer, the same figure takes the fifth and sixth contacts as well.
    longer = figure_of(history(detector, candles, max_flag_candles=60))
    assert len(longer.latest.anchors) == 7
    assert labels(longer)[-2:] == (
        ["UPPER_3", "LOWER_3"] if detector.thrust.sign > 0 else ["LOWER_3", "UPPER_3"]
    )


def test_a_consolidation_that_goes_on_with_the_mast_is_no_flag() -> None:
    """Highs at 123, 126, 129 rising as the mast did: a channel that goes on climbing is not a
    pause. Neither is a pennant. And the same, downwards, after a mast down."""
    rising = [*UP, 122, 150, 147, 153, 150, 156, 153, 162]
    for detector, extremes in (
        (BullFlagDetector(), rising),
        (BullPennantDetector(), rising),
        (BearFlagDetector(), mirror(rising)),
        (BearPennantDetector(), mirror(rising)),
    ):
        assert history(detector, zigzag(extremes)) == (), detector.version


def test_a_consolidation_that_widens_is_neither_a_flag_nor_a_pennant() -> None:
    widening = [*UP, 122, 150, 146, 149, 143, 148, 140, 156]
    for detector in (BullFlagDetector(), BullPennantDetector()):
        assert history(detector, zigzag(widening)) == (), detector.version


# -- the volume and instances between instants --------------------------------------------------


def test_the_first_close_beyond_a_boundary_decides_even_if_the_other_one_follows() -> None:
    """The price falls through the lower boundary of a bull flag and only then rallies through the
    upper one. The fall is the breakout on record; the rally is not a second one."""
    candles = zigzag([*BULL_FLAG, 120, 156])
    now = BullFlagDetector().detect(context_for(candles), candles)
    (candidate,) = now.candidates
    assert candidate.evaluation.breakout is not None
    assert candidate.evaluation.breakout.direction is BreakoutDirection.DOWN
    assert candidate.evaluation.state in (S.CONFIRMED_DOWN, S.FAILED_BREAKOUT)


def test_a_pennant_closes_in_from_both_sides_or_it_is_a_wedge() -> None:
    """A mast, then highs falling 150.5, 148.0 and lows falling 144.5, 143.5: the boundaries do
    close in (the height goes from 5.5 to 3.25), but both slope down, which makes a wedge (a
    figure of POINT3-EXPANSION-001), not a pennant. Nor is it a flag: they are not parallel."""
    wedge = [*UP, 122, 150, 145, "147.5", 144, 156]
    for detector, extremes in (
        (BullPennantDetector(), wedge),
        (BullFlagDetector(), wedge),
        (BearPennantDetector(), mirror(wedge)),
        (BearFlagDetector(), mirror(wedge)),
    ):
        assert history(detector, zigzag(extremes)) == (), detector.version


def test_a_pennant_ends_at_its_apex_if_the_price_never_left() -> None:
    """The pennant's lines (the ceiling from 150.5 falling 0.075 a candle, the floor from 144.5
    rising as much) meet at candle 175, fifteen after the last contact. The price climbs from the
    last contact to the middle of the two lines, 147.1, and creeps up from there, always inside
    until they meet and past it. It never makes a swing. The figure ran its course."""
    base = zigzag([*UP, 122, 150, 145, "148.5", "146.5"], tail=0)  # the last contact is candle 160
    assert len(base) == 161
    mids = [Decimal("146.5") + Decimal("0.06") * (i - 160) for i in range(161, 171)]
    mids += [Decimal("147.1") + Decimal("0.001") * (i - 170) for i in range(171, 191)]
    tail = [candle_at(T0 + TF.duration * (161 + n), mid, TF.duration) for n, mid in enumerate(mids)]
    figure = figure_of(history(BullPennantDetector(), [*base, *tail]))
    assert figure.state is S.INVALIDATED
    assert figure.latest.invalidation_reasons == (InvalidationReason.TOO_LONG,)
    assert figure.latest.breakout is None and len(figure.latest.anchors) == 5


def test_the_volume_of_the_breakout_is_measured_against_the_pause_not_against_the_mast() -> None:
    candles = zigzag([*BULL_FLAG, 156])
    plain = figure_of(history(BullFlagDetector(), candles))
    end, breakout = plain.latest.anchors[1], plain.latest.breakout
    assert breakout is not None
    volumes = [
        dataclasses.replace(
            c,
            volume=Decimal(
                30
                if c.open_time == breakout.candle_open_time
                else 10
                if c.open_time >= end.open_time
                else 1000  # the mast, and everything before it: loud
            ),
        )
        for c in candles
    ]
    loud = figure_of(history(BullFlagDetector(), volumes))
    volume = facts_of(loud, "BREAKOUT_VOLUME")
    assert volume["mean_volume"] == Decimal(10) and volume["ratio"] == Decimal(3)
    assert states(loud) == states(plain)  # and it decides nothing


def test_the_volume_of_the_mast_and_of_the_pause_are_recorded_side_by_side() -> None:
    """Loud before the mast (1000), 100 during it with a spike of 200 on its last candle, and 10
    in the pause: the classical description, recorded and never demanded."""
    candles = zigzag([*BULL_FLAG, 156])
    plain = figure_of(history(BullFlagDetector(), candles))
    start, end = plain.latest.anchors[0], plain.latest.anchors[1]

    def volume(candle: Any) -> Decimal:
        if candle.open_time < start.open_time:
            return Decimal(1000)
        if candle.open_time < end.open_time:
            return Decimal(100)
        return Decimal(200) if candle.open_time == end.open_time else Decimal(10)

    loud = [dataclasses.replace(c, volume=volume(c)) for c in candles]
    facts = facts_of(figure_of(history(BullFlagDetector(), loud)), "FLAG_VOLUME")
    assert facts["mast_mean_volume"] == Decimal(1200) / Decimal(11)  # the mast, its end included
    assert facts["pause_mean_volume"] == Decimal(10)  # after the mast's last candle
    assert facts["pause_to_mast"] == (Decimal(10) / (Decimal(1200) / Decimal(11))).quantize(_SIX)
    # Without volume in the mast (a source that reports none) there is nothing to divide by.
    silent = [dataclasses.replace(c, volume=Decimal(0)) for c in candles]
    quiet = facts_of(figure_of(history(BullFlagDetector(), silent)), "FLAG_VOLUME")
    assert "pause_to_mast" not in quiet and quiet["mast_mean_volume"] == Decimal(0)


def test_data_that_is_not_fit_judges_no_figure_and_says_why() -> None:
    candles = zigzag([*BULL_FLAG, 156])
    detector = BullFlagDetector()
    holed = [c for i, c in enumerate(candles) if i != 100]
    result = detector.detect(context_for(candles), holed)
    assert result.candidates == ()
    assert MissingDataReason.GAPS_IN_WINDOW in result.unfit_reasons
    few = candles[:40]
    assert detector.detect(context_for(few), few).unfit_reasons == (
        MissingDataReason.INSUFFICIENT_HISTORY,
    )


def test_a_different_parameter_version_is_another_instance() -> None:
    candles = zigzag([*BULL_FLAG, 156])
    default = figure_of(history(BullFlagDetector(), candles))
    tuned = figure_of(history(BullFlagDetector(), candles, version="continuation-params-v2"))
    assert default.pattern_instance_id != tuned.pattern_instance_id


# -- no look-ahead, determinism -----------------------------------------------------------------

_FIGURES: dict[str, tuple[MastDetector, list[int | str]]] = {
    "bull flag": (BullFlagDetector(), [*BULL_FLAG, 156]),
    "bear flag": (BearFlagDetector(), mirror([*BULL_FLAG, 156])),
    "bull pennant": (BullPennantDetector(), [*BULL_PENNANT, 156]),
    "bear pennant": (BearPennantDetector(), mirror([*BULL_PENNANT, 156])),
}


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
    candles = zigzag([*BULL_FLAG, 156])
    assert history(BullFlagDetector(), candles) == history(BullFlagDetector(), candles)


# -- the units, the parameters and what a detector never does -----------------------------------


def test_each_detector_is_its_own_unit_with_its_own_version() -> None:
    assert {d.version for d in DETECTORS} == {
        "bull-flag-detector-v1",
        "bear-flag-detector-v1",
        "bull-pennant-detector-v1",
        "bear-pennant-detector-v1",
    }
    assert {d.pattern_type for d in DETECTORS} == {
        PatternType.BULL_FLAG,
        PatternType.BEAR_FLAG,
        PatternType.BULL_PENNANT,
        PatternType.BEAR_PENNANT,
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"mast_min_height_fraction": Decimal(0)},
        {"max_retrace": Decimal(1)},
        {"flag_max_height_fraction": 0.5},
        {"parallel_tolerance": Decimal("0.3")},  # parallel up to what already counts as converging
        {"pennant_convergence_min": Decimal("0.2")},
        {"mast_max_candles": 0},
        {"min_flag_candles": 0},
        {"min_flag_candles": 31},  # longer than the longest allowed
        {"max_flag_candles": False},
    ],
)
def test_parameters_that_make_no_sense_are_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(InvalidDetectionRequestError):
        ContinuationParams(**bad)


def test_the_detectors_only_read_the_domain_never_a_candlestick_pattern_or_an_indicator() -> None:
    allowed = {"abc", "collections.abc", "dataclasses", "datetime", "decimal", "enum", "typing"}
    tree = ast.parse(Path(str(pattern_flag.__file__)).read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    foreign = {
        m for m in imported if m not in allowed and not m.startswith("freyja_backend.domain.")
    }
    assert not foreign, foreign
    forbidden = {"indicators", "candlestick", "market_indicators", "pattern_double"}
    assert not any(any(word in m for word in forbidden) for m in imported)
