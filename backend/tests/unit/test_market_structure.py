"""POINT2-STRUCTURE-001: pivots and swing points.

Pure functions, no database and no network: the input is built here, candle by
candle, so every expected pivot can be checked by hand.
"""

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise

import pytest

from freyja_backend.domain.market_data import Candle, InvalidMarketDataError, Timeframe
from freyja_backend.domain.market_structure import (
    STRUCTURE_ALGORITHM_VERSION,
    PivotKind,
    PivotParams,
    PivotResult,
    PivotStatus,
    detect_pivots,
    swing_points,
)

TF = Timeframe.M5
STEP = TF.duration
T0 = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)


def candle(index: int, high: str | int, low: str | int) -> Candle:
    """Candle `index` steps after T0. open/close sit at the middle of the range."""
    high_d, low_d = Decimal(str(high)), Decimal(str(low))
    middle = (high_d + low_d) / 2
    open_time = T0 + index * STEP
    return Candle(
        open_time=open_time,
        close_time=open_time + STEP,
        open=middle,
        high=high_d,
        low=low_d,
        close=middle,
        volume=Decimal("1"),
    )


def series(highs: list[int], lows: list[int] | None = None) -> list[Candle]:
    lows = lows if lows is not None else [h - 2 for h in highs]
    return [candle(i, h, low) for i, (h, low) in enumerate(zip(highs, lows, strict=True))]


def close_of(index: int) -> datetime:
    return T0 + (index + 1) * STEP


def pivots_at(candles: list[Candle], index: int) -> PivotResult:
    """Pivots knowable right after candle `index` closed."""
    return detect_pivots(
        candles, timeframe=TF, observed_at=close_of(index), params=PivotParams(k=2)
    )


def describe(result: PivotResult) -> list[tuple[str, str, int]]:
    return [(p.kind.value, p.status.value, int((p.open_time - T0) / STEP)) for p in result.pivots]


# --- What a pivot is ---------------------------------------------------------------


def test_a_high_is_a_pivot_when_it_beats_k_candles_on_each_side() -> None:
    candles = series([10, 11, 12, 15, 12, 11, 10])  # peak at index 3

    result = pivots_at(candles, 6)

    highs = [p for p in result.pivots if p.kind is PivotKind.HIGH]
    assert [(p.open_time, p.price, p.status) for p in highs] == [
        (candles[3].open_time, Decimal("15"), PivotStatus.CONFIRMED)
    ]


def test_a_low_is_a_pivot_when_it_undercuts_k_candles_on_each_side() -> None:
    candles = series([20, 19, 18, 15, 18, 19, 20], lows=[18, 17, 16, 10, 16, 17, 18])

    result = pivots_at(candles, 6)

    lows = [p for p in result.pivots if p.kind is PivotKind.LOW]
    assert [(p.open_time, p.price) for p in lows] == [(candles[3].open_time, Decimal("10"))]


def test_pivot_price_is_the_exact_high_or_low_not_a_float() -> None:
    candles = series([10, 11, 12, 15, 12, 11, 10])
    candles[3] = candle(3, "15.123456789012345678", 13)

    (pivot,) = [p for p in pivots_at(candles, 6).pivots if p.kind is PivotKind.HIGH]

    assert pivot.price == Decimal("15.123456789012345678")


def test_the_first_k_candles_can_never_be_pivots_and_the_last_k_are_only_provisional() -> None:
    candles = series([15, 11, 10, 9, 8, 9, 10])  # the max is the very first candle

    result = pivots_at(candles, 6)

    assert [p for p in result.confirmed if p.kind is PivotKind.HIGH] == []
    assert all(p.open_time >= candles[2].open_time for p in result.pivots)
    # A candle with fewer than k candles after it is never more than provisional.
    assert all(
        p.status is PivotStatus.PROVISIONAL
        for p in result.pivots
        if p.open_time >= candles[5].open_time
    )


def test_k_is_honoured() -> None:
    # The peak at index 3 beats two candles per side (k=2) but not the three-candle
    # neighbourhood, because index 0 is higher.
    candles = series([20, 11, 12, 15, 12, 11, 10])

    k2 = detect_pivots(candles, timeframe=TF, observed_at=close_of(6), params=PivotParams(k=2))
    k3 = detect_pivots(candles, timeframe=TF, observed_at=close_of(6), params=PivotParams(k=3))

    assert [p.open_time for p in k2.pivots if p.kind is PivotKind.HIGH] == [candles[3].open_time]
    assert [p for p in k3.pivots if p.kind is PivotKind.HIGH] == []


@pytest.mark.parametrize("bad", [0, -1, 1.5, True])
def test_k_must_be_a_positive_integer(bad: object) -> None:
    with pytest.raises(ValueError, match="k must be"):
        PivotParams(k=bad)  # type: ignore[arg-type]


# --- Ties ----------------------------------------------------------------------------


def test_a_plateau_of_equal_highs_yields_exactly_one_pivot_the_first() -> None:
    candles = series([10, 11, 15, 15, 12, 11, 10])  # indexes 2 and 3 tie at 15

    result = pivots_at(candles, 6)

    assert [p.open_time for p in result.pivots if p.kind is PivotKind.HIGH] == [
        candles[2].open_time
    ]


def test_a_tie_with_a_candle_on_the_left_disqualifies() -> None:
    candles = series([10, 10, 15, 12, 15, 12, 11, 10])  # index 4 ties with index 2 (within k=2)

    result = pivots_at(candles, 7)

    assert [p.open_time for p in result.pivots if p.kind is PivotKind.HIGH] == [
        candles[2].open_time
    ]


def test_equal_extremes_further_apart_than_k_are_both_pivots() -> None:
    candles = series([10, 11, 15, 11, 10, 11, 12, 15, 12, 11, 10])

    result = detect_pivots(candles, timeframe=TF, observed_at=close_of(10), params=PivotParams(k=2))

    assert [int((p.open_time - T0) / STEP) for p in result.pivots if p.kind is PivotKind.HIGH] == [
        2,
        7,
    ]


def test_a_flat_series_has_no_pivots() -> None:
    result = pivots_at(series([10] * 12), 11)

    assert result.pivots == ()


# --- When a pivot becomes knowable ---------------------------------------------------


def _highs(result: PivotResult) -> list[tuple[str, int]]:
    return [
        (p.status.value, int((p.open_time - T0) / STEP))
        for p in result.pivots
        if p.kind is PivotKind.HIGH
    ]


def test_a_pivot_is_provisional_until_the_kth_candle_after_it_closes() -> None:
    candles = series([10, 11, 12, 15, 14, 13, 12, 11])  # peak at index 3, k = 2

    assert _highs(pivots_at(candles, 3)) == [("PROVISIONAL", 3)]  # just closed: k=0 of 2 seen
    assert _highs(pivots_at(candles, 4)) == [("PROVISIONAL", 3)]  # 1 of 2
    assert _highs(pivots_at(candles, 5)) == [("CONFIRMED", 3)]  # 2 of 2: now knowable


def test_confirmed_at_is_the_close_of_the_kth_candle_after_the_pivot() -> None:
    candles = series([10, 11, 12, 15, 14, 13, 12, 11])

    (pivot,) = [p for p in pivots_at(candles, 7).pivots if p.kind is PivotKind.HIGH]

    assert pivot.confirmed_at == close_of(5)  # peak is index 3; k=2 -> candle 5


def test_a_provisional_pivot_has_no_confirmation_time() -> None:
    candles = series([10, 11, 12, 15, 14])

    (pivot,) = [p for p in pivots_at(candles, 4).pivots if p.kind is PivotKind.HIGH]

    assert pivot.status is PivotStatus.PROVISIONAL
    assert pivot.confirmed_at is None


def test_a_provisional_pivot_can_vanish_when_the_next_candle_beats_it() -> None:
    candles = series([10, 11, 12, 15, 14, 16, 13])  # index 5 (16) exceeds the peak at 3

    before = pivots_at(candles, 4)
    after = pivots_at(candles, 5)

    assert _highs(before) == [("PROVISIONAL", 3)]
    assert ("PROVISIONAL", 3) not in _highs(after)
    assert all(p.open_time != candles[3].open_time for p in after.pivots)


def test_a_confirmed_pivot_never_disappears_later() -> None:
    rng = random.Random(7)
    candles = _random_walk(rng, 80)

    previous: set[tuple[PivotKind, datetime, Decimal]] = set()
    for index in range(len(candles)):
        result = pivots_at(candles, index)
        confirmed = {(p.kind, p.open_time, p.price) for p in result.confirmed}
        assert previous <= confirmed
        previous = confirmed


# --- No look-ahead -------------------------------------------------------------------


def _random_walk(rng: random.Random, count: int) -> list[Candle]:
    price = 1000
    out: list[Candle] = []
    for index in range(count):
        price = max(50, price + rng.randint(-30, 30))
        spread = rng.randint(1, 20)
        out.append(candle(index, price + spread, price - spread))
    return out


@pytest.mark.parametrize("seed", range(6))
def test_confirmed_pivots_at_any_instant_equal_those_computed_on_only_the_past(seed: int) -> None:
    """The definitive no-look-ahead check: for EVERY instant, the pivots known then
    are identical whether or not the future candles were even supplied."""
    candles = _random_walk(random.Random(seed), 120)
    params = PivotParams(k=3)

    for index in range(len(candles)):
        with_future = detect_pivots(
            candles, timeframe=TF, observed_at=close_of(index), params=params
        )
        past_only = detect_pivots(
            candles[: index + 1], timeframe=TF, observed_at=close_of(index), params=params
        )
        assert with_future.pivots == past_only.pivots


def test_changing_the_future_never_changes_what_was_already_knowable() -> None:
    rng = random.Random(3)
    candles = _random_walk(rng, 100)
    tampered = candles[:60] + _random_walk(random.Random(99), 100)[60:]
    tampered = [candle(i, int(c.high), int(c.low)) for i, c in enumerate(tampered)]

    observed = close_of(59)
    original = detect_pivots(candles, timeframe=TF, observed_at=observed)
    other = detect_pivots(tampered, timeframe=TF, observed_at=observed)

    assert original.pivots == other.pivots


def test_candles_closing_after_observed_at_are_ignored_not_used() -> None:
    candles = series([10, 11, 12, 15, 14, 13, 12])

    result = pivots_at(candles, 3)

    assert result.candles_used == 4


def test_a_candle_closing_exactly_at_observed_at_is_known() -> None:
    candles = series([10, 11, 12, 15, 14, 13, 12])

    result = detect_pivots(
        candles, timeframe=TF, observed_at=candles[5].close_time, params=PivotParams(k=2)
    )

    assert result.candles_used == 6


# --- Reproducibility ------------------------------------------------------------------


def test_same_input_and_version_give_the_same_pivots() -> None:
    candles = _random_walk(random.Random(11), 150)

    first = detect_pivots(candles, timeframe=TF, observed_at=close_of(149))
    second = detect_pivots(list(candles), timeframe=TF, observed_at=close_of(149))

    assert first == second
    assert first.algorithm_version == STRUCTURE_ALGORITHM_VERSION


def test_a_pivot_does_not_depend_on_where_the_window_starts() -> None:
    candles = _random_walk(random.Random(5), 150)
    full = detect_pivots(candles, timeframe=TF, observed_at=close_of(149))

    trimmed = detect_pivots(candles[20:], timeframe=TF, observed_at=close_of(149))

    # Every pivot with a full neighbourhood inside the trimmed window is the same one.
    assert trimmed.pivots == tuple(p for p in full.pivots if p.open_time >= candles[23].open_time)


def test_the_result_records_the_parameters_and_the_algorithm_version() -> None:
    result = pivots_at(series([10, 11, 12, 15, 12, 11, 10]), 6)

    assert result.params == PivotParams(k=2)
    assert result.algorithm_version == "pivots-v1"
    assert result.observed_at == close_of(6)


# --- Missing and bad data --------------------------------------------------------------


def test_no_pivot_is_produced_next_to_a_missing_candle() -> None:
    candles = series([10, 11, 12, 15, 12, 11, 10])
    del candles[4]  # a hole right after the peak: its neighbourhood is no longer complete

    result = pivots_at(candles, 6)

    assert [p for p in result.pivots if p.open_time == candles[3].open_time] == []


def test_a_gap_far_from_a_pivot_does_not_affect_it() -> None:
    candles = series([5, 5, 5, 10, 11, 12, 15, 12, 11, 10])
    del candles[1]  # far from the peak at index 6

    result = detect_pivots(candles, timeframe=TF, observed_at=close_of(9), params=PivotParams(k=2))

    assert [p.open_time for p in result.pivots if p.kind is PivotKind.HIGH] == [T0 + 6 * STEP]


def test_too_few_candles_yield_no_pivots_rather_than_an_error() -> None:
    assert pivots_at(series([10, 11]), 1).pivots == ()
    assert detect_pivots([], timeframe=TF, observed_at=close_of(3)).pivots == ()


def test_duplicate_or_unordered_candles_are_rejected() -> None:
    candles = series([10, 11, 12, 15, 12])

    with pytest.raises(InvalidMarketDataError):
        detect_pivots([candles[0], candles[0]], timeframe=TF, observed_at=close_of(9))
    with pytest.raises(InvalidMarketDataError):
        detect_pivots(list(reversed(candles)), timeframe=TF, observed_at=close_of(9))


def test_a_candle_off_the_timeframe_grid_is_rejected() -> None:
    off_grid = Candle(
        open_time=T0 + timedelta(minutes=1),
        close_time=T0 + timedelta(minutes=6),
        open=Decimal(10),
        high=Decimal(11),
        low=Decimal(9),
        close=Decimal(10),
        volume=Decimal(1),
    )

    with pytest.raises(InvalidMarketDataError):
        detect_pivots([off_grid], timeframe=TF, observed_at=close_of(9))


def test_observed_at_must_be_timezone_aware_utc() -> None:
    with pytest.raises(InvalidMarketDataError):
        detect_pivots(series([10, 11]), timeframe=TF, observed_at=datetime(2026, 1, 5, 12, 0))


# --- A candle that is both a high and a low pivot --------------------------------------


def test_an_outside_candle_can_be_both_pivots() -> None:
    highs = [10, 10, 10, 30, 10, 10, 10]
    lows = [8, 8, 8, 1, 8, 8, 8]

    result = pivots_at(series(highs, lows), 6)

    assert describe(result) == [("HIGH", "CONFIRMED", 3), ("LOW", "CONFIRMED", 3)]


# --- Swing points ----------------------------------------------------------------------


def _zigzag() -> list[Candle]:
    #            0   1   2   3   4   5   6   7   8   9  10  11  12  13  14
    highs = [10, 11, 12, 20, 12, 11, 10, 11, 12, 22, 12, 11, 10, 9, 8]
    lows = [8, 9, 10, 18, 10, 9, 4, 9, 10, 20, 10, 9, 8, 7, 6]
    return series(highs, lows)


def test_swing_points_alternate_high_and_low() -> None:
    result = detect_pivots(
        _zigzag(), timeframe=TF, observed_at=close_of(14), params=PivotParams(k=2)
    )

    swings = swing_points(result.pivots)

    kinds = [p.kind for p in swings]
    assert all(a is not b for a, b in pairwise(kinds))
    assert [(p.kind.value, int((p.open_time - T0) / STEP)) for p in swings] == [
        ("HIGH", 3),
        ("LOW", 6),
        ("HIGH", 9),
    ]


def test_consecutive_highs_collapse_into_the_higher_one() -> None:
    #            0   1   2   3   4   5   6   7   8   9  10
    highs = [10, 11, 12, 20, 12, 11, 12, 25, 12, 11, 10]
    lows = [5] * 11  # constant lows: no low pivot can separate the two highs
    result = detect_pivots(
        series(highs, lows), timeframe=TF, observed_at=close_of(10), params=PivotParams(k=2)
    )

    swings = swing_points(result.pivots)

    highs_kept = [p for p in swings if p.kind is PivotKind.HIGH]
    assert [p.price for p in highs_kept] == [Decimal("25")]


def test_consecutive_lows_collapse_into_the_lower_one_and_ties_keep_the_earlier() -> None:
    highs = [30] * 11  # constant highs: no high pivot can separate the two lows
    lower = detect_pivots(
        series(highs, [20, 19, 18, 10, 18, 19, 18, 5, 18, 19, 20]),
        timeframe=TF,
        observed_at=close_of(10),
        params=PivotParams(k=2),
    )
    tied = detect_pivots(
        series(highs, [20, 19, 18, 10, 18, 19, 18, 10, 18, 19, 20]),
        timeframe=TF,
        observed_at=close_of(10),
        params=PivotParams(k=2),
    )

    assert [p.price for p in swing_points(lower.pivots)] == [Decimal("5")]
    assert [int((p.open_time - T0) / STEP) for p in swing_points(tied.pivots)] == [3]


def test_consecutive_equal_highs_keep_the_earlier_one() -> None:
    highs = [10, 11, 12, 20, 12, 11, 12, 20, 12, 11, 10]
    lows = [5] * 11  # constant lows: no low pivot can separate the two highs
    result = detect_pivots(
        series(highs, lows), timeframe=TF, observed_at=close_of(10), params=PivotParams(k=2)
    )

    swings = swing_points(result.pivots)

    assert [int((p.open_time - T0) / STEP) for p in swings if p.kind is PivotKind.HIGH] == [3]


def test_swing_points_ignore_provisional_pivots() -> None:
    result = detect_pivots(
        _zigzag(), timeframe=TF, observed_at=close_of(9), params=PivotParams(k=2)
    )

    assert any(p.status is PivotStatus.PROVISIONAL for p in result.pivots)
    assert all(p.status is PivotStatus.CONFIRMED for p in swing_points(result.pivots))


def test_an_outside_candle_is_left_out_of_the_swing_sequence() -> None:
    highs = [10, 10, 10, 30, 10, 10, 10]
    lows = [8, 8, 8, 1, 8, 8, 8]
    result = pivots_at(series(highs, lows), 6)

    assert swing_points(result.pivots) == ()


def test_swing_points_of_nothing_is_nothing() -> None:
    assert swing_points(()) == ()
