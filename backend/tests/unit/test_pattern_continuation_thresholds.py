"""POINT3-CONTINUATION-001: every threshold, exactly at its value and at both of its neighbours.

The detectors compare with `<`, `<=`, `>` and `>=`, and the difference between them is one value:
the one that is exactly the threshold. Each rule below is tested there (it must be as the contract
says: accepted or refused *at* the value) and one step to each side. The examples of the contract
(``docs/domain/detectores-de-continuacion.md``, section 11) are these very cases.

Two kinds of test: the rules of a flag or a pennant (`MastDetector.accepts`, a pure function of a
consolidation's measures) are tried on measures written by hand, so that "exactly the threshold" is
exact; and the rules that need candles are tried on series whose prices were chosen so that the
measure comes out as an exact decimal.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from freyja_backend.domain.market_structure import Pivot, PivotKind, PivotStatus
from freyja_backend.domain.pattern_channel import Channel, RectangleDetector
from freyja_backend.domain.pattern_detection import DEFAULT_CONTINUATION_PARAMS, ContinuationParams
from freyja_backend.domain.pattern_flag import (
    BearFlagDetector,
    BearPennantDetector,
    BullFlagDetector,
    BullPennantDetector,
    MastDetector,
    Thrust,
)
from tests.unit.test_market_trend import DOWN, T0, TF, UP, candle_at, zigzag
from tests.unit.test_pattern_channel import history, labels, mirror
from tests.unit.test_pattern_flag import BULL_FLAG

D = Decimal
PARAMS = DEFAULT_CONTINUATION_PARAMS


# -- the consolidation's rules, on measures written by hand ------------------------------------

MAST = D(100)  # a mast of 100, ending at a price of 200 (bull) or 100 (bear)


def pivot(kind: PivotKind, price: Decimal) -> Pivot:
    return Pivot(kind, PivotStatus.CONFIRMED, T0, price, T0 + timedelta(minutes=5))


def consolidation(
    thrust: Thrust,
    *,
    height: Decimal | None = None,
    gap_at_end: Decimal | None = None,
    rise: Decimal | None = None,
    give_back: Decimal | None = None,
    candles: int = 20,
    upper_rise: Decimal | None = None,
    lower_rise: Decimal | None = None,
) -> tuple[Channel, Pivot]:
    """A consolidation after a mast of 100 that is ordinary in every measure (20 tall, 20 candles,
    drifting 5 against the mast, giving back 15), with one of them replaced. `rise` is how far the
    boundaries move (up is positive) from the first contact to the last, for a bull figure;
    `give_back` is how far the contact that went furthest against the mast is from its end.
    For a mirror (bear) figure the same measures are turned over."""
    height = D(20) if height is None else height
    rise = D(-5) if rise is None else rise
    give_back = D(15) if give_back is None else give_back
    sign = thrust.sign
    end_price = D(200) if sign > 0 else D(100)
    counter = end_price - sign * give_back
    end = pivot(thrust.end_kind, end_price)
    against = pivot(PivotKind.LOW if sign > 0 else PivotKind.HIGH, counter)
    upper = rise * sign if upper_rise is None else upper_rise
    lower = rise * sign if lower_rise is None else lower_rise
    channel = Channel(
        window=(end, against, end, against),
        upper=lambda _at: D(0),
        lower=lambda _at: D(0),
        highs=(end, end) if sign > 0 else (against, against),
        lows=(against, against) if sign > 0 else (end, end),
        height=height,
        gap_at_end=height if gap_at_end is None else gap_at_end,
        upper_rise=upper,
        lower_rise=lower,
        reference=D(50),
        first_index=0,
        last_index=candles,
        expires_after=None,
    )
    return channel, end


def accepted(detector: MastDetector, params: ContinuationParams = PARAMS, **measures: Any) -> bool:
    fit, end = consolidation(detector.thrust, **measures)
    return detector.accepts(fit, end, MAST, params)


FLAGS = [BullFlagDetector(), BearFlagDetector()]
PENNANTS = [BullPennantDetector(), BearPennantDetector()]


@pytest.mark.parametrize("detector", FLAGS + PENNANTS, ids=lambda d: d.version)
def test_an_ordinary_consolidation_is_accepted_so_that_each_change_below_is_the_only_cause(
    detector: MastDetector,
) -> None:
    measures: dict[str, Any] = {}
    if detector.converging:
        measures = {"gap_at_end": D(14), "upper_rise": D(-5), "lower_rise": D(5)}
    assert accepted(detector, **measures)


@pytest.mark.parametrize("detector", FLAGS + PENNANTS, ids=lambda d: d.version)
@pytest.mark.parametrize(
    ("height", "expected"),
    [
        (D("49.99"), True),
        (D(50), True),
        (D("50.01"), False),
    ],  # flag_max_height_fraction 0.50 of 100
)
def test_a_pause_at_most_half_as_tall_as_the_mast(
    detector: MastDetector, height: Decimal, expected: bool
) -> None:
    measures: dict[str, Any] = {"height": height, "gap_at_end": height}
    if detector.converging:
        measures = {
            "height": height,
            "gap_at_end": height * D("0.7"),
            "upper_rise": D(-5),
            "lower_rise": D(5),
        }
    assert accepted(detector, **measures) is expected


@pytest.mark.parametrize("detector", FLAGS + PENNANTS, ids=lambda d: d.version)
@pytest.mark.parametrize(
    ("give_back", "expected"),
    [(D("49.99"), True), (D(50), True), (D("50.01"), False)],  # max_retrace 0.50 of 100
)
def test_a_pause_that_gives_back_at_most_half_of_the_mast(
    detector: MastDetector, give_back: Decimal, expected: bool
) -> None:
    measures: dict[str, Any] = {"give_back": give_back}
    if detector.converging:
        measures |= {"gap_at_end": D(14), "upper_rise": D(-5), "lower_rise": D(5)}
    assert accepted(detector, **measures) is expected


@pytest.mark.parametrize("detector", FLAGS, ids=lambda d: d.version)
@pytest.mark.parametrize(
    ("rise", "expected"),
    # The drift with the mast (rise is "with the mast" when positive after the sign is applied for
    # a bear figure): at most flat_tolerance 0.10 of 100, that is 10.
    [(D("-30"), True), (D("9.99"), True), (D(10), True), (D("10.01"), False)],
)
def test_a_pause_may_drift_with_the_mast_by_at_most_a_tenth_of_it(
    detector: MastDetector, rise: Decimal, expected: bool
) -> None:
    assert accepted(detector, rise=rise) is expected


@pytest.mark.parametrize("detector", FLAGS + PENNANTS, ids=lambda d: d.version)
@pytest.mark.parametrize(
    ("candles", "expected"),
    [(29, True), (30, True), (31, False)],  # max_flag_candles 30
)
def test_a_pause_of_at_most_thirty_candles(
    detector: MastDetector, candles: int, expected: bool
) -> None:
    measures: dict[str, Any] = {"candles": candles}
    if detector.converging:
        measures |= {"gap_at_end": D(14), "upper_rise": D(-5), "lower_rise": D(5)}
    assert accepted(detector, **measures) is expected


@pytest.mark.parametrize("detector", FLAGS, ids=lambda d: d.version)
@pytest.mark.parametrize(
    ("gap_at_end", "expected"),
    # Parallel: the height ends within parallel_tolerance 0.20 of what it began at (20): 16 to 24.
    [
        (D("15.99"), False),
        (D(16), True),
        (D("16.01"), True),
        (D("23.99"), True),
        (D(24), True),
        (D("24.01"), False),
    ],
)
def test_a_flags_boundaries_stay_parallel_within_a_fifth_of_the_height(
    detector: MastDetector, gap_at_end: Decimal, expected: bool
) -> None:
    assert accepted(detector, gap_at_end=gap_at_end) is expected


@pytest.mark.parametrize("detector", PENNANTS, ids=lambda d: d.version)
@pytest.mark.parametrize(
    ("gap_at_end", "expected"),
    # Converging: the height ends at most 1 - 0.30 of what it began at (20): 14 or less.
    [(D("13.99"), True), (D(14), True), (D("14.01"), False)],
)
def test_a_pennants_boundaries_close_in_by_at_least_thirty_percent(
    detector: MastDetector, gap_at_end: Decimal, expected: bool
) -> None:
    assert accepted(detector, gap_at_end=gap_at_end, upper_rise=D(-5), lower_rise=D(5)) is expected


@pytest.mark.parametrize("detector", PENNANTS, ids=lambda d: d.version)
@pytest.mark.parametrize(
    ("upper_rise", "lower_rise", "expected"),
    # A pennant closes in from both sides: the ceiling falls and the floor rises. Flat is neither.
    [
        (D("-0.01"), D("0.01"), True),
        (D(0), D("0.01"), False),
        (D("-0.01"), D(0), False),
        (D("0.01"), D("0.02"), False),  # both rising: a wedge
        (D("-0.02"), D("-0.01"), False),  # both falling: a wedge
    ],
)
def test_a_pennant_needs_a_falling_ceiling_and_a_rising_floor(
    detector: MastDetector, upper_rise: Decimal, lower_rise: Decimal, expected: bool
) -> None:
    # (Sloping the same way is a wedge even when the lines do close in: gap_at_end is 14 of 20.)
    measures: dict[str, Any] = {
        "gap_at_end": D(14),
        "upper_rise": upper_rise,
        "lower_rise": lower_rise,
    }
    assert accepted(detector, **measures) is expected


# -- the rules that need candles ----------------------------------------------------------------

# After a downtrend: a mast of 21.0 from the low of 169.5 to a high of 190.5, in a recent range of
# 28.0. That is exactly 0.75 of it.
AFTER_DOWNTREND = [*DOWN, 190, 186, 189, 185, 188, 184]


@pytest.mark.parametrize("upside_down", [False, True])
@pytest.mark.parametrize(
    ("fraction", "expected"),
    [("0.74", True), ("0.75", True), ("0.76", False)],
)
def test_a_mast_at_least_a_quarter_or_here_three_quarters_of_the_recent_range(
    upside_down: bool, fraction: str, expected: bool
) -> None:
    detector = BearFlagDetector() if upside_down else BullFlagDetector()
    extremes = [*AFTER_DOWNTREND, 194]
    candles = zigzag(mirror(extremes) if upside_down else extremes)
    found = history(detector, candles, mast_min_height_fraction=D(fraction))
    assert bool(found) is expected


@pytest.mark.parametrize(
    ("last_mast_mid", "expected"),
    # The mast rises from a low of 169.5 to the high of the last candle (its mid plus 0.5), in a
    # recent range of 28.0. The default asks for a quarter of it: 7.0, that is a mid of 176.
    [("175.9", False), ("176", True), ("176.1", True)],
)
def test_the_default_asks_for_a_mast_of_a_quarter_of_the_recent_range_and_no_less(
    last_mast_mid: str, expected: bool
) -> None:
    # After the mast, a pause that gives back a third of it and is a third as tall.
    top = D(last_mast_mid)
    pause = [top - D("1.5"), top - D("0.5"), top - D("2"), top - D("1")]
    extremes: list[int | str] = [*DOWN, str(top), *(str(price) for price in pause)]
    found = history(BullFlagDetector(), zigzag(extremes))
    assert bool(found) is expected


def build(mast_candles: int, extremes_after: list[int | str]) -> Any:
    """A rise of 122 to 150 in exactly `mast_candles` candles (not necessarily the ten of a leg),
    after the usual uptrend and before the usual pause."""
    prefix = zigzag([*UP, 122], tail=0)  # its last candle is the low the mast starts from
    start = len(prefix)
    step = (D(150) - D(122)) / mast_candles
    mast = [
        candle_at(T0 + TF.duration * (start + n), D(122) + step * (n + 1), TF.duration)
        for n in range(mast_candles)
    ]
    after = zigzag(
        [150, *extremes_after], tail=4, start=T0 + TF.duration * (start + mast_candles - 1)
    )
    return [*prefix, *mast, *after[1:]]


@pytest.mark.parametrize(
    ("mast_candles", "expected"),
    [(11, True), (12, True), (13, False)],  # mast_max_candles 12
)
def test_a_mast_of_at_most_twelve_candles(mast_candles: int, expected: bool) -> None:
    candles = build(mast_candles, [146, 149, 145, 148, 144, 156])
    found = history(BullFlagDetector(), candles)
    assert bool(found) is expected


# -- the two exact equalities of the channel ------------------------------------------------------


@pytest.mark.parametrize("upside_down", [False, True])
@pytest.mark.parametrize(
    ("tolerance", "expected"),
    # A floor at 110.5 and a ceiling of 130.5 make a height of 20. The second ceiling contact is a
    # swing at 130.5 whose wick reaches 131.0, half a point above the line through the first and
    # the last (130.5): exactly 0.025 of the height. Its close stays on the line. Upside down, the
    # same with the floor.
    [("0.0249", False), ("0.025", True), ("0.0251", True)],
)
def test_a_contact_exactly_at_the_tolerance_is_still_a_contact(
    upside_down: bool, tolerance: str, expected: bool
) -> None:
    extremes: list[int | str] = [*UP, 111, "130.5", 111, 130, 111]
    candles = zigzag(mirror(extremes) if upside_down else extremes)
    found = history(RectangleDetector(), candles, contact_tolerance=D(tolerance))
    first = next(f for f in found if labels(f)[0] == ("LOWER_1" if upside_down else "UPPER_1"))
    assert (len(first.latest.anchors) == 6) is expected


def bull_pennant(upper_second: str) -> list[int | str]:
    """A pennant whose lines close in by exactly 30 percent when `upper_second` is 148.9.

    The mast ends at 150.5; the floor's contacts are 140.5 and 141.5; the second ceiling contact
    is at 149.4 (a mid of 148.9). The height is 10.5 at the end of the mast and 7.35 at the last
    contact: 0.7 of it, to the last decimal."""
    return [*UP, 122, 150, 141, upper_second, 142]


@pytest.mark.parametrize(
    ("convergence_min", "expected"),
    [("0.29", True), ("0.30", True), ("0.31", False)],
)
def test_a_pennant_closing_in_by_exactly_the_minimum_is_a_pennant(
    convergence_min: str, expected: bool
) -> None:
    candles = zigzag(bull_pennant("148.9"))
    found = history(BullPennantDetector(), candles, pennant_convergence_min=D(convergence_min))
    assert bool(found) is expected
    if found:
        (pennant,) = found
        gap = {
            name: value
            for e in pennant.latest.evidence
            if e.code == "CHANNEL"
            for name, value in e.facts
        }
        assert gap["height"] == D("10.5") and gap["gap_at_end"] == D("7.35")


def test_the_examples_of_the_contract_are_the_defaults() -> None:
    """Section 11 of the contract quotes these values: if a default changes, the examples do."""
    assert (PARAMS.mast_max_candles, PARAMS.mast_min_height_fraction) == (12, D("0.25"))
    assert (PARAMS.max_retrace, PARAMS.flag_max_height_fraction) == (D("0.50"), D("0.50"))
    assert (PARAMS.flat_tolerance, PARAMS.max_flag_candles) == (D("0.10"), 30)
    assert (PARAMS.parallel_tolerance, PARAMS.pennant_convergence_min) == (D("0.20"), D("0.30"))
    assert BULL_FLAG and UP  # the series the examples are built on
