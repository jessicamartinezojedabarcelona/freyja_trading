"""FIB-CALC-001: the Fibonacci retracement tool.

Expected values are written from the contract (``docs/domain/fibonacci-retroceso.md``), never from
the code under test: levels worked out by hand, instants worked out from the timeframes, and the
mirror property (a bearish impulse is a bullish one upside down) checked on exact decimals. The
impulses are built directly (two pivots and some candles) so that every price and instant is known.
"""

import ast
import dataclasses
import random
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from freyja_backend.domain import fibonacci
from freyja_backend.domain.fibonacci import (
    DEFAULT_FIBONACCI_PARAMS,
    DEFAULT_LEVEL_RATIOS,
    FibonacciParams,
    Impulse,
    ImpulseDirection,
    ImpulseRejection,
    InvalidFibonacciRequestError,
    check_impulse,
    closed_beyond,
    observe,
    retracement_levels,
    touches,
)
from freyja_backend.domain.market_data import Candle, InvalidMarketDataError, Timeframe
from freyja_backend.domain.market_structure import (
    Pivot,
    PivotKind,
    PivotStatus,
    detect_pivots,
    swing_points,
)
from tests.unit.test_market_trend import T0, UP, zigzag

D = Decimal
REPO = Path(__file__).resolve().parents[3]
BULLISH, BEARISH = ImpulseDirection.BULLISH, ImpulseDirection.BEARISH
K = DEFAULT_FIBONACCI_PARAMS.pivot_params.k  # 3


# -- builders -----------------------------------------------------------------------------------


def candle(
    open_time: datetime,
    duration: timedelta,
    *,
    low: str,
    high: str,
    close: str,
    open_: str | None = None,
) -> Candle:
    close_d = D(close)
    open_d = D(open_) if open_ is not None else close_d
    return Candle(
        open_time=open_time,
        close_time=open_time + duration,
        open=open_d,
        high=D(high),
        low=D(low),
        close=close_d,
        volume=D(1),
    )


def pivot(kind: PivotKind, open_time: datetime, price: str, duration: timedelta) -> Pivot:
    """A confirmed pivot: known at the close of the K-th candle after it (`pivots-v1`)."""
    return Pivot(kind, PivotStatus.CONFIRMED, open_time, D(price), open_time + duration * (K + 1))


def impulse(
    direction: ImpulseDirection,
    a: str,
    b: str,
    *,
    at: datetime = T0,
    duration: timedelta = timedelta(minutes=5),
) -> Impulse:
    """An impulse whose B pivot is the candle that opens at `at` (A came twenty candles before)."""
    a_time = at - duration * 20
    return Impulse(
        direction,
        pivot(direction.start_kind, a_time, a, duration),
        pivot(direction.end_kind, at, b, duration),
        20,
        D(100),
    )


BULL = impulse(BULLISH, "100", "120")
BEAR = impulse(BEARISH, "120", "100")


def prices(observed: Any) -> dict[str, Decimal]:
    return {str(level.level.ratio): level.level.price for level in observed.levels}


# -- the levels, from the formulas --------------------------------------------------------------


def test_the_bullish_levels_are_b_minus_r_times_d() -> None:
    # An impulse from 100 to 120: D = 20, so each level is 120 - r * 20.
    assert {str(x.ratio): x.price for x in retracement_levels(BULL)} == {
        "0.236": D("115.28"),
        "0.382": D("112.36"),
        "0.5": D("110"),
        "0.618": D("107.64"),
        "0.786": D("104.28"),
    }


def test_the_bearish_levels_are_b_plus_r_times_d() -> None:
    # An impulse from 120 to 100: D = 20, so each level is 100 + r * 20.
    assert {str(x.ratio): x.price for x in retracement_levels(BEAR)} == {
        "0.236": D("104.72"),
        "0.382": D("107.64"),
        "0.5": D("110"),
        "0.618": D("112.36"),
        "0.786": D("115.72"),
    }


def test_the_documented_levels_are_the_contract_examples() -> None:
    levels = {str(x.ratio): x.price for x in retracement_levels(BULL)}
    assert levels["0.5"] == D(110) and levels["0.618"] == D("107.64")
    bearish = {str(x.ratio): x.price for x in retracement_levels(BEAR)}
    assert bearish["0.5"] == D(110) and bearish["0.618"] == D("112.36")


def test_a_bearish_impulse_is_a_bullish_one_upside_down_on_exact_decimals() -> None:
    """For every impulse, replacing each price p by 1000 - p turns the levels of one into those of
    the other exactly (ties in the rounding included), for every ratio."""
    rng = random.Random(7)
    for _ in range(300):
        low = D(rng.randint(1, 100_000_000_000)) / D(1_000_000_000)  # up to 9 decimals
        high = low + D(rng.randint(1, 100_000_000_000)) / D(1_000_000_000)
        mirrored_low, mirrored_high = D(1000) - high, D(1000) - low
        if mirrored_low <= 0:
            continue
        bullish = impulse(BULLISH, str(low), str(high))
        bearish = impulse(BEARISH, str(mirrored_high), str(mirrored_low))
        up = retracement_levels(bullish)
        down = retracement_levels(bearish)
        assert [D(1000) - x.price for x in up] == [x.price for x in down], (low, high)
        assert [x.ratio for x in up] == [x.ratio for x in down]


def test_levels_are_exact_decimals_rounded_to_the_stored_precision() -> None:
    # D = 3e-12: 0.5 of it is 1.5e-12, a tie, rounded (half to even) to 2e-12; 0.236 of it is
    # 0.708e-12, rounded to 1e-12. Nothing finer than 12 decimals is ever returned.
    tiny = impulse(BULLISH, "1", "1.000000000003")
    levels = {str(x.ratio): x.price for x in retracement_levels(tiny)}
    assert levels["0.5"] == D("1.000000000001")
    assert levels["0.236"] == D("1.000000000002")
    for price in levels.values():
        assert price.as_tuple().exponent == -12 and isinstance(price, Decimal)
    big = impulse(BULLISH, "1000000000000.000000000001", "3000000000000.000000000001")
    assert retracement_levels(big)[2].price == D("2000000000000.000000000001")  # exact, no float


def test_the_levels_are_the_same_whatever_the_timeframe() -> None:
    for timeframe in Timeframe:
        stepped = impulse(BULLISH, "100", "120", duration=timeframe.duration)
        assert [x.price for x in retracement_levels(stepped)] == [
            x.price for x in retracement_levels(BULL)
        ]


# -- when the Fibonacci exists ------------------------------------------------------------------


@pytest.mark.parametrize("timeframe", list(Timeframe), ids=lambda t: t.value)
def test_it_is_known_at_the_close_of_the_third_candle_after_b_and_not_a_moment_before(
    timeframe: Timeframe,
) -> None:
    duration = timeframe.duration
    fib = impulse(BULLISH, "100", "120", duration=duration)
    # B's candle opens at T0; the candles after it open at T0+d, T0+2d and T0+3d, and the third one
    # closes at T0+4d: that is when B becomes a pivot.
    assert fib.known_at == T0 + duration * 4
    with pytest.raises(InvalidFibonacciRequestError, match="not known yet"):
        observe(fib, [], observed_at=fib.known_at - timedelta(seconds=1))
    assert observe(fib, [], observed_at=fib.known_at).candles_observed == 0


@pytest.mark.parametrize("timeframe", list(Timeframe), ids=lambda t: t.value)
@pytest.mark.parametrize("direction", [BULLISH, BEARISH])
def test_a_touch_in_the_candle_that_confirms_b_is_retrospective_and_the_next_one_is_operable(
    timeframe: Timeframe, direction: ImpulseDirection
) -> None:
    d = timeframe.duration
    fib = (
        impulse(BULLISH, "100", "120", duration=d)
        if direction is BULLISH
        else impulse(BEARISH, "120", "100", duration=d)
    )
    # The 50 % level is at 110 in both. The candle that closes at known_at reaches it; so does the
    # one that opens at known_at.
    confirming = candle(T0 + d * 3, d, low="109", high="111", close="110")
    first_operable = candle(T0 + d * 4, d, low="109.5", high="110.5", close="110")
    before = candle(T0 + d, d, low="115", high="116", close="115.5")
    seen = observe(fib, [before, confirming, first_operable], observed_at=T0 + d * 5)
    half = next(x for x in seen.levels if x.level.ratio == D("0.5"))
    assert half.first_touch is not None and half.first_touch.retrospective is True
    assert half.first_touch.candle_open_time == T0 + d * 3
    assert half.first_operable_touch is not None
    assert half.first_operable_touch.retrospective is False
    assert half.first_operable_touch.candle_open_time == T0 + d * 4  # opens exactly at known_at
    # Without the operable candle, nothing operable was seen: only the retrospective touch.
    only_past = observe(fib, [before, confirming], observed_at=T0 + d * 4)
    half = next(x for x in only_past.levels if x.level.ratio == D("0.5"))
    assert half.first_touch is not None and half.first_operable_touch is None


def test_the_candle_of_b_itself_is_not_observed_and_nor_is_one_that_closes_later() -> None:
    d = timedelta(minutes=5)
    b_candle = candle(T0, d, low="100", high="121", close="110")  # its range holds the 50 %
    early = candle(T0 + d, d, low="111", high="112", close="111.5")
    late = candle(T0 + d * 5, d, low="109", high="111", close="110")  # closes after observed_at
    seen = observe(BULL, [b_candle, early, late], observed_at=T0 + d * 5)
    assert seen.candles_observed == 1  # `late` closes at T0 + 6d
    # A candle closing exactly at observed_at is read; one closing a moment later is not.
    edge = observe(BULL, [early, late], observed_at=T0 + d * 6)
    assert edge.candles_observed == 2
    half = next(x for x in seen.levels if x.level.ratio == D("0.5"))
    assert half.first_touch is None


# -- what a touch and a close beyond are --------------------------------------------------------


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [
        ("109.99", "110.01", True),  # straddles the level
        ("110", "111", True),  # the low is exactly the level
        ("109", "110", True),  # the high is exactly the level
        ("110", "110", True),  # a candle of a single price
        ("110.01", "111", False),  # wholly above it
        ("109", "109.99", False),  # wholly below it
    ],
)
def test_a_candle_touches_a_level_when_low_is_at_most_it_and_high_at_least_it(
    low: str, high: str, expected: bool
) -> None:
    c = candle(T0, timedelta(minutes=5), low=low, high=high, close=low)
    assert touches(D(110), c) is expected


@pytest.mark.parametrize(
    ("direction", "close", "expected"),
    [
        (BULLISH, "109.99", True),  # below the level: beyond, on the side of A
        (BULLISH, "110", False),  # on the level: a touch, not beyond
        (BULLISH, "110.01", False),
        (BEARISH, "110.01", True),  # above the level: beyond, on the side of A
        (BEARISH, "110", False),
        (BEARISH, "109.99", False),
    ],
)
def test_a_close_is_beyond_a_level_on_the_side_of_a_and_strictly(
    direction: ImpulseDirection, close: str, expected: bool
) -> None:
    c = candle(T0, timedelta(minutes=5), low="100", high="120", close=close)
    assert closed_beyond(direction, D(110), c) is expected


def test_touching_and_closing_beyond_are_independent_facts() -> None:
    d = timedelta(minutes=5)
    # A candle that crosses the 50 % of the bullish impulse but closes above it: a touch only.
    crossing = candle(T0 + d * 4, d, low="108", high="112", close="111")
    # A gap: the next candle lies wholly below the level: no touch, but it closes beyond.
    gap = candle(T0 + d * 5, d, low="100", high="105", close="102")
    seen = observe(BULL, [crossing, gap], observed_at=T0 + d * 6)
    half = next(x for x in seen.levels if x.level.ratio == D("0.5"))
    assert half.first_touch is not None and half.first_touch.candle_open_time == T0 + d * 4
    assert half.first_close_beyond is not None
    assert half.first_close_beyond.candle_open_time == T0 + d * 5  # the gap, not the crossing
    hundred = next(x for x in seen.levels if x.level.ratio == D("0.786"))  # at 104.28
    assert hundred.first_touch is not None  # the gap candle (100 to 105) spans 104.28
    assert hundred.first_close_beyond is not None


def test_nothing_in_a_result_attributes_entry_or_a_signal_to_a_touch() -> None:
    forbidden = {
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
        "expiry",
        "zone",
    }
    names: set[str] = set()
    for cls in (
        fibonacci.LevelEvent,
        fibonacci.LevelObservation,
        fibonacci.FibonacciObservation,
        fibonacci.Impulse,
        fibonacci.FibonacciLevel,
    ):
        names |= {f.name for f in dataclasses.fields(cls)}
    assert names.isdisjoint(forbidden)


def test_the_retracement_and_the_distance_to_the_nearest_level_are_fractions_of_d() -> None:
    d = timedelta(minutes=5)
    # Bullish, 100 to 120 (D = 20). The price went down to a low of 108 (wicks: 12/20 = 0.6) and its
    # lowest close was 110.5 (closes: 9.5/20 = 0.475); the last close, 111, is 1 from the level at
    # 110 (the 50 %): 1/20 = 0.05.
    candles = [
        candle(T0 + d * 4, d, low="108", high="118", close="110.5"),
        candle(T0 + d * 5, d, low="110", high="112", close="111"),
    ]
    seen = observe(BULL, candles, observed_at=T0 + d * 6)
    assert seen.max_retracement_by_wicks == D("0.6")
    assert seen.max_retracement_by_closes == D("0.475")
    assert seen.nearest_level_distance == D("0.05")
    # Bearish, 120 to 100: the retracement goes up.
    up = [
        candle(T0 + d * 4, d, low="101", high="112", close="111"),
        candle(T0 + d * 5, d, low="101", high="110", close="104"),
    ]
    seen = observe(BEAR, up, observed_at=T0 + d * 6)
    assert seen.max_retracement_by_wicks == D("0.6")  # (112 - 100) / 20
    assert seen.max_retracement_by_closes == D("0.55")  # (111 - 100) / 20
    # A price that never went back gives zero, not a negative retracement.
    away = observe(
        BULL,
        [candle(T0 + d * 4, d, low="121", high="125", close="124")],
        observed_at=T0 + d * 5,
    )
    assert away.max_retracement_by_wicks == D(0) and away.max_retracement_by_closes == D(0)
    empty = observe(BULL, [], observed_at=T0 + d * 4)
    assert empty.nearest_level_distance is None
    assert empty.max_retracement_by_wicks == D(0)


# -- what is an impulse -------------------------------------------------------------------------


def stretch(
    direction: ImpulseDirection,
    *,
    start_price: str = "100",
    end_price: str = "120",
    middle_low: str = "101",
    middle_high: str = "119",
    before_range: tuple[str, str] = ("99", "121"),
) -> tuple[list[Candle], Pivot, Pivot]:
    """Twenty candles before A, then A, a middle candle and B. For a bearish impulse the same shape
    upside down. `before_range` is the (low, high) of the candles before A."""
    d = timedelta(minutes=5)
    sign = direction.sign
    a_time, mid_time, b_time = T0 + d * 20, T0 + d * 21, T0 + d * 22
    low_before, high_before = before_range
    candles = [
        candle(T0 + d * n, d, low=low_before, high=high_before, close=low_before) for n in range(20)
    ]
    if sign > 0:
        candles.append(candle(a_time, d, low=start_price, high="105", close="104"))
        candles.append(candle(mid_time, d, low=middle_low, high=middle_high, close=middle_low))
        candles.append(candle(b_time, d, low="112", high=end_price, close="118"))
    else:
        candles.append(candle(a_time, d, low="115", high=start_price, close="116"))
        candles.append(candle(mid_time, d, low=middle_low, high=middle_high, close=middle_low))
        candles.append(candle(b_time, d, low=end_price, high="108", close="102"))
    a = pivot(direction.start_kind, a_time, start_price, d)
    b = pivot(direction.end_kind, b_time, end_price, d)
    return candles, a, b


def test_a_pair_of_pivots_with_no_candle_beyond_the_extremes_is_an_impulse() -> None:
    candles, a, b = stretch(BULLISH)
    check = check_impulse(candles, a, b)
    assert check.rejection is None and check.impulse is not None
    assert check.impulse.direction is BULLISH and check.impulse.impulse_candles == 2
    assert check.impulse.size == D(20) and check.impulse.known_at == b.confirmed_at
    assert check.impulse.reference_range == D(22)  # 121 down to 99, the candles ending at A
    bearish = check_impulse(*_args(stretch(BEARISH, start_price="120", end_price="100")))
    assert bearish.impulse is not None and bearish.impulse.direction is BEARISH


def _args(built: tuple[list[Candle], Pivot, Pivot]) -> Any:
    return built[0], built[1], built[2]


@pytest.mark.parametrize("direction", [BULLISH, BEARISH])
@pytest.mark.parametrize(
    ("low_delta", "high_delta", "expected"),
    [
        ("0", "0", None),  # a wick exactly at the anchors is not beyond them
        ("-0.01", "0", ImpulseRejection.CANDLE_OUTSIDE_EXTREMES),  # a wick beyond A
        ("0", "0.01", ImpulseRejection.CANDLE_OUTSIDE_EXTREMES),  # a wick beyond B
    ],
)
def test_no_candle_from_a_to_b_may_have_a_wick_beyond_the_extremes_but_equal_is_fine(
    direction: ImpulseDirection, low_delta: str, high_delta: str, expected: ImpulseRejection | None
) -> None:
    if direction is BULLISH:
        built = stretch(
            direction,
            middle_low=str(D(100) + D(low_delta)),
            middle_high=str(D(120) + D(high_delta)),
        )
    else:
        # Upside down: the extremes are A = 120 (high) and B = 100 (low).
        built = stretch(
            direction,
            start_price="120",
            end_price="100",
            middle_low=str(D(100) - D(high_delta)),
            middle_high=str(D(120) - D(low_delta)),
        )
    assert check_impulse(*_args(built)).rejection is expected


@pytest.mark.parametrize("direction", [BULLISH, BEARISH])
def test_the_candles_of_a_and_of_b_themselves_are_within_the_extremes_too(
    direction: ImpulseDirection,
) -> None:
    """A wide candle at A (its far wick beyond B) or at B (its far wick beyond A) is no impulse: the
    tramo runs from A's candle to B's, both included."""
    if direction is BULLISH:
        built = stretch(direction)
        wide_a = dataclasses.replace(built[0][20], high=D("120.01"))
        wide_b = dataclasses.replace(built[0][22], low=D("99.99"))
    else:
        built = stretch(direction, start_price="120", end_price="100")
        wide_a = dataclasses.replace(built[0][20], low=D("99.99"))
        wide_b = dataclasses.replace(built[0][22], high=D("120.01"))
    candles, a, b = built
    assert check_impulse(candles, a, b).rejection is None
    with_a = [*candles[:20], wide_a, *candles[21:]]
    with_b = [*candles[:22], wide_b]
    assert check_impulse(with_a, a, b).rejection is ImpulseRejection.CANDLE_OUTSIDE_EXTREMES
    assert check_impulse(with_b, a, b).rejection is ImpulseRejection.CANDLE_OUTSIDE_EXTREMES


def test_the_reference_range_is_the_hundred_candles_that_end_at_a_and_no_more() -> None:
    d = timedelta(minutes=5)
    quiet = [candle(T0 + d * n, d, low="90", high="130", close="100") for n in range(150)]
    # A is candle 120; the hundred that end at it are candles 21 to 120. Candle 20 is out of them.
    a_time, b_time = T0 + d * 120, T0 + d * 121
    a_candle = candle(a_time, d, low="100", high="105", close="102")
    b_candle = candle(b_time, d, low="101", high="120", close="118")
    a = pivot(PivotKind.LOW, a_time, "100", d)
    b = pivot(PivotKind.HIGH, b_time, "120", d)
    calm = [*quiet[:120], a_candle, b_candle]
    inside = check_impulse(calm, a, b)
    assert inside.impulse is not None and inside.impulse.reference_range == D(40)
    # Candle 20 (the oldest that would only count with a window of 101) is wild: it must not count.
    wild_old = candle(T0 + d * 20, d, low="1", high="999", close="100")
    outside = [*quiet[:20], wild_old, *quiet[21:120], a_candle, b_candle]
    assert check_impulse(outside, a, b).impulse is not None  # not counted: the range stays 40
    # Candle 21 is the oldest inside the window: it does count.
    wild_first = candle(T0 + d * 21, d, low="1", high="999", close="100")
    counted = [*quiet[:21], wild_first, *quiet[22:120], a_candle, b_candle]
    assert check_impulse(counted, a, b).rejection is ImpulseRejection.TOO_SMALL


def test_candles_before_a_and_after_b_do_not_count_for_the_extremes() -> None:
    candles, a, b = stretch(BULLISH, before_range=("50", "300"))
    small = FibonacciParams(min_impulse_fraction=D("0.05"))
    check = check_impulse(candles, a, b, small)
    assert check.rejection is None  # the wild candles before A only widen the reference range
    after = candle(
        T0 + timedelta(minutes=5) * 23, timedelta(minutes=5), low="1", high="999", close="5"
    )
    assert check_impulse([*candles, after], a, b, small).rejection is None


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        ("unconfirmed_a", ImpulseRejection.PIVOT_NOT_CONFIRMED),
        ("unconfirmed_b", ImpulseRejection.PIVOT_NOT_CONFIRMED),
        ("same_kind", ImpulseRejection.WRONG_PIVOT_KINDS),
        ("reversed", ImpulseRejection.NOT_IN_ORDER),
        ("same_time", ImpulseRejection.NOT_IN_ORDER),
        ("candles_missing", ImpulseRejection.CANDLES_MISSING),
    ],
)
def test_what_is_not_an_impulse_is_refused_with_the_reason(
    build: str, expected: ImpulseRejection
) -> None:
    candles, a, b = stretch(BULLISH)
    if build == "unconfirmed_a":
        a = dataclasses.replace(a, status=PivotStatus.PROVISIONAL, confirmed_at=None)
    elif build == "unconfirmed_b":
        b = dataclasses.replace(b, confirmed_at=None)
    elif build == "same_kind":
        b = dataclasses.replace(b, kind=a.kind)
    elif build == "reversed":
        a, b = b, a
        a = dataclasses.replace(a, kind=PivotKind.LOW)
        b = dataclasses.replace(b, kind=PivotKind.HIGH)
    elif build == "same_time":
        b = dataclasses.replace(b, open_time=a.open_time)
    elif build == "candles_missing":
        candles = candles[:21]
    assert check_impulse(candles, a, b).rejection is expected


def test_the_size_is_relative_to_the_recent_range_and_exactly_the_fraction_is_enough() -> None:
    # D = 20 against the range of the twenty candles before A: 80 -> 25 per cent, 0.25 * 80 = 20.
    exact = stretch(BULLISH, before_range=("40", "120"))
    assert check_impulse(*_args(exact)).rejection is None  # 20 >= 0.25 * 80, exactly
    smaller = stretch(BULLISH, before_range=("40", "120.01"))
    assert check_impulse(*_args(smaller)).rejection is ImpulseRejection.TOO_SMALL  # 20 < 20.0025
    larger = stretch(BULLISH, before_range=("40.01", "120"))
    assert check_impulse(*_args(larger)).rejection is None  # 20 > 0.25 * 79.99


def test_no_reference_range_is_refused() -> None:
    d = timedelta(minutes=5)
    a_time, b_time = T0, T0 + d
    flat = candle(a_time, d, low="100", high="100", close="100")
    other = candle(b_time, d, low="100", high="100", close="100")
    a = pivot(PivotKind.LOW, a_time, "100", d)
    b = pivot(PivotKind.HIGH, b_time, "100", d)
    assert check_impulse([flat, other], a, b).rejection is ImpulseRejection.NO_REFERENCE_RANGE


def test_a_zero_size_impulse_is_too_small() -> None:
    d = timedelta(minutes=5)
    wide = candle(T0, d, low="90", high="110", close="100")  # gives the recent range some width
    first = candle(T0 + d, d, low="100", high="100", close="100")
    second = candle(T0 + d * 2, d, low="100", high="100", close="100")
    a = pivot(PivotKind.LOW, T0 + d, "100", d)
    b = pivot(PivotKind.HIGH, T0 + d * 2, "100", d)
    assert check_impulse([wide, first, second], a, b).rejection is ImpulseRejection.TOO_SMALL


def test_a_bearish_impulse_is_judged_exactly_as_its_mirror_image() -> None:
    # Bullish: a wick of 99.99 is beyond A (100). Bearish: a wick of 120.01 is beyond A (120).
    built = stretch(BULLISH, middle_low="99.99")
    mirrored = stretch(BEARISH, start_price="120", end_price="100", middle_high="120.01")
    assert check_impulse(*_args(built)).rejection is ImpulseRejection.CANDLE_OUTSIDE_EXTREMES
    assert check_impulse(*_args(mirrored)).rejection is ImpulseRejection.CANDLE_OUTSIDE_EXTREMES


# -- from the real pivots, on every timeframe ---------------------------------------------------


def swings_of(candles: Sequence[Candle], timeframe: Timeframe) -> tuple[Pivot, ...]:
    pivots = detect_pivots(candles, timeframe=timeframe, observed_at=candles[-1].close_time)
    return swing_points(pivots.confirmed)


@pytest.mark.parametrize("timeframe", list(Timeframe), ids=lambda t: t.value)
@pytest.mark.parametrize("upside_down", [False, True])
def test_the_same_shape_gives_the_same_levels_and_the_same_touches_on_every_timeframe(
    timeframe: Timeframe, upside_down: bool
) -> None:
    extremes: list[int | str] = [*UP, 118, 140, 126, 133, 128]
    if upside_down:
        extremes = [str(300 - int(x)) for x in extremes]
    candles = zigzag(extremes, timeframe=timeframe, start=timeframe.floor(T0))
    swings = swings_of(candles, timeframe)
    a_kind = PivotKind.HIGH if upside_down else PivotKind.LOW
    a = next(s for s in swings if s.kind is a_kind and s.price in (D("117.5"), D("182.5")))
    b = next(s for s in swings if s.open_time > a.open_time and s.kind is not a_kind)
    check = check_impulse(candles, a, b)
    assert check.impulse is not None
    fib = check.impulse
    assert fib.direction is (BEARISH if upside_down else BULLISH)
    assert fib.size == D(23)  # 117.5 to 140.5 (or its mirror)
    assert fib.known_at == b.open_time + timeframe.duration * (K + 1)
    observed = observe(fib, candles, observed_at=candles[-1].close_time)
    assert observed.candles_observed == len([c for c in candles if c.open_time > b.open_time])
    # Levels 135.072, 131.714, 129.0, 126.286 and 122.422 (bullish; its mirror otherwise). The price
    # came down in steps of 1.4 (mids 138.6, 137.2, 135.8, 134.4...): the 135.072 falls between the
    # range of one candle (135.3 to 136.3) and the next (133.9 to 134.9), so no candle touches it;
    # the price then came back to 126 (low 125.5): the 122.422 was never reached.
    touched = {str(o.level.ratio): o.first_touch is not None for o in observed.levels}
    assert touched == {"0.236": False, "0.382": True, "0.5": True, "0.618": True, "0.786": False}
    price = {str(o.level.ratio): o.level.price for o in observed.levels}
    up = D(300) - fib.end.price if upside_down else fib.end.price
    assert price["0.5"] == (D("129") if not upside_down else D(300) - D("129"))
    assert up == D("140.5")


# -- no look-ahead, determinism -----------------------------------------------------------------


def wild(candles: Sequence[Candle], after: datetime) -> list[Candle]:
    return [
        c
        if c.close_time <= after
        else dataclasses.replace(c, low=D("1"), high=D("9999"), close=D("5000"), open=D("5000"))
        for c in candles
    ]


@pytest.mark.parametrize("upside_down", [False, True])
def test_an_observation_at_an_instant_depends_only_on_what_was_closed_by_then(
    upside_down: bool,
) -> None:
    timeframe = Timeframe.M5
    extremes: list[int | str] = [*UP, 118, 140, 126, 133, 128]
    if upside_down:
        extremes = [str(300 - int(x)) for x in extremes]
    candles = zigzag(extremes, timeframe=timeframe)
    swings = swings_of(candles, timeframe)
    a_kind = PivotKind.HIGH if upside_down else PivotKind.LOW
    a = next(s for s in swings if s.kind is a_kind and s.price in (D("117.5"), D("182.5")))
    b = next(s for s in swings if s.open_time > a.open_time and s.kind is not a_kind)
    fib = check_impulse(candles, a, b).impulse
    assert fib is not None
    seen_touch = False
    for c in candles:
        at = c.close_time
        if at < fib.known_at:
            continue
        upto = [k for k in candles if k.close_time <= at]
        past = observe(fib, upto, observed_at=at)
        assert observe(fib, candles, observed_at=at) == past, at
        assert observe(fib, wild(candles, at), observed_at=at) == past, at
        seen_touch = seen_touch or any(x.first_touch for x in past.levels)
    assert seen_touch  # not vacuous


def test_the_same_candles_always_give_the_same_observation() -> None:
    d = timedelta(minutes=5)
    candles = [candle(T0 + d * 4, d, low="108", high="118", close="110.5")]
    assert observe(BULL, candles, observed_at=T0 + d * 5) == observe(
        BULL, candles, observed_at=T0 + d * 5
    )


def test_a_naive_instant_is_a_wrong_request() -> None:
    with pytest.raises(InvalidMarketDataError):
        observe(BULL, [], observed_at=datetime(2026, 1, 5, 10, 0))


# -- parameters and units -----------------------------------------------------------------------


def test_the_documented_parameters_and_levels_are_the_default_ones() -> None:
    text = (REPO / "docs" / "domain" / "fibonacci-retroceso.md").read_text(encoding="utf-8")
    params = DEFAULT_FIBONACCI_PARAMS
    assert params.version == "fibonacci-params-v1" and "`fibonacci-params-v1`" in text
    assert params.levels_version in text and params.convention_version in text
    assert "0,236; 0,382; 0,5; 0,618; 0,786" in text
    assert [str(r).replace(".", ",") for r in DEFAULT_LEVEL_RATIOS] == [
        "0,236",
        "0,382",
        "0,5",
        "0,618",
        "0,786",
    ]
    assert (
        f"| `min_impulse_fraction` | {str(params.min_impulse_fraction).replace('.', ',')} |" in text
    )
    assert f"| `range_window_candles` | {params.range_window_candles} |" in text
    assert f"| `pivot_params.k` | {params.pivot_params.k} |" in text


@pytest.mark.parametrize(
    "bad",
    [
        {"ratios": ()},
        {"ratios": (D(0), D("0.5"))},
        {"ratios": (D("0.5"), D(1))},
        {"ratios": (D("0.5"), D("0.5"))},  # not strictly increasing
        {"ratios": (D("0.618"), D("0.5"))},
        {"ratios": (0.5,)},
        {"min_impulse_fraction": D(0)},
        {"min_impulse_fraction": D(1)},
        {"min_impulse_fraction": 0.25},
        {"range_window_candles": 0},
        {"range_window_candles": True},
        {"version": " "},
        {"levels_version": ""},
        {"convention_version": " "},
    ],
)
def test_parameters_that_make_no_sense_are_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(InvalidFibonacciRequestError):
        FibonacciParams(**bad)


def test_a_different_set_of_levels_is_used_when_the_parameters_say_so() -> None:
    only_half = FibonacciParams(ratios=(D("0.5"),), levels_version="fibonacci-levels-v2")
    assert [x.price for x in retracement_levels(BULL, only_half)] == [D(110)]


def test_the_tool_only_reads_the_domain_never_a_pattern_an_indicator_or_a_float() -> None:
    allowed = {"enum", "collections.abc", "dataclasses", "datetime", "decimal"}
    tree = ast.parse(Path(str(fibonacci.__file__)).read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    foreign = {
        m for m in imported if m not in allowed and not m.startswith("freyja_backend.domain.")
    }
    assert not foreign, foreign
    forbidden = ("indicators", "pattern_", "chart_pattern", "market_trend")
    assert not any(any(word in m for word in forbidden) for m in imported)
    source = Path(str(fibonacci.__file__)).read_text(encoding="utf-8")
    assert "float(" not in source
