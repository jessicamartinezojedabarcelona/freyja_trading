"""FIB-DETECT-001 (first part): the search for impulses.

Expected impulses are written from the policy in ``docs/domain/fibonacci-retroceso.md`` (section
16): the dominant leg that ends at each confirmed swing, no further back than the search window.
Series are built leg by leg (ten candles per leg, prices in exact tenths) so that every swing and
every wick is known. A swing "at 140" has its high at 140.5 and a swing "at 118" its low at 117.5.
"""

import ast
import dataclasses
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from freyja_backend.domain import fibonacci_detection
from freyja_backend.domain.fibonacci import (
    DEFAULT_FIBONACCI_PARAMS,
    FibonacciParams,
    Impulse,
    ImpulseDirection,
    check_impulse,
)
from freyja_backend.domain.fibonacci_detection import (
    FibonacciSeries,
    ImpulseSearch,
    find_impulses,
    search_impulses,
)
from freyja_backend.domain.market_calendar import MarketSchedule
from freyja_backend.domain.market_context import MissingDataReason
from freyja_backend.domain.market_data import Candle, InvalidMarketDataError, Timeframe
from freyja_backend.domain.market_structure import detect_pivots, swing_points
from tests.unit.test_market_trend import (
    AUTHORIZED,
    BTC,
    SOURCE,
    T0,
    UP,
    candle_at,
    random_walk,
    zigzag,
)

D = Decimal
REPO = Path(__file__).resolve().parents[3]
BULLISH, BEARISH = ImpulseDirection.BULLISH, ImpulseDirection.BEARISH

# A rising staircase to 130, a pullback to 118, a high of 140, a pullback to 126, a high of 133.
EXTREMES: list[int | str] = [*UP, 118, 140, 126, 133, 128]


def mirror(extremes: Sequence[int | str]) -> list[int | str]:
    """The same figure upside down: every price p becomes 300 - p."""
    return [str(D(300) - D(str(e))) for e in extremes]


def series_for(
    candles: Sequence[Candle], timeframe: Timeframe = Timeframe.M5, **params: Any
) -> FibonacciSeries:
    return FibonacciSeries(
        instrument_id="instrument-1",
        instrument=BTC,
        schedule=MarketSchedule.CONTINUOUS_24_7,
        data_source=SOURCE,
        authorized_sources=AUTHORIZED,
        timeframe=timeframe,
        observed_at=candles[-1].close_time,
        params=FibonacciParams(**params) if params else DEFAULT_FIBONACCI_PARAMS,
    )


def search(extremes: Sequence[int | str], **params: Any) -> tuple[Impulse, ...]:
    candles = zigzag(extremes)
    result = search_impulses(series_for(candles, **params), candles)
    assert result.unfit_reasons == ()
    return result.impulses


def shape(impulse: Impulse) -> tuple[str, str, str, int]:
    """Direction, A, B and length in candles: what the tests compare."""
    return (
        impulse.direction.value,
        str(impulse.start.price),
        str(impulse.end.price),
        impulse.impulse_candles,
    )


# -- the dominant leg ending at each swing ------------------------------------------------------


def test_the_impulse_ending_at_a_high_starts_at_the_lowest_low_since_the_price_went_beyond_it() -> (
    None
):
    """B = the high of 140.5. Nothing before it went higher, so the dominant leg starts at the
    lowest low within the search window (100 candles: from candle 30): the swing low of 106.5 at
    candle 40 (the low of 102.5 at candle 20 is further back than the window)."""
    impulses = search(EXTREMES)
    by_end = {(i.direction, i.end.price): i for i in impulses}
    leg = by_end[(BULLISH, D("140.5"))]
    assert (leg.start.price, leg.end.price) == (D("106.5"), D("140.5"))
    assert leg.impulse_candles == 90 and leg.direction is BULLISH
    # The lowest low since then is 106.5: no wick of any candle from A's to B's goes below it.
    assert leg.size == D(34)


def test_the_impulse_that_ends_at_a_low_starts_at_the_highest_high_and_is_bearish() -> None:
    impulses = search(EXTREMES)
    by_end = {(i.direction, i.end.price): i for i in impulses}
    leg = by_end[(BEARISH, D("125.5"))]  # the low of 125.5 after the high of 140.5
    assert (leg.start.price, leg.end.price) == (D("140.5"), D("125.5"))
    assert leg.direction is BEARISH and leg.impulse_candles == 10


def test_one_impulse_at_most_ends_at_each_swing_and_they_come_oldest_first() -> None:
    impulses = search(EXTREMES)
    ends = [i.end.open_time for i in impulses]
    assert ends == sorted(ends) and len(set(ends)) == len(ends)
    assert len(impulses) == 13  # the swings of the series that admit a dominant leg


def test_every_impulse_found_is_a_valid_impulse_by_the_rules_of_the_contract() -> None:
    candles = zigzag(EXTREMES)
    result = search_impulses(series_for(candles), candles)
    swings = swing_points(
        detect_pivots(candles, timeframe=Timeframe.M5, observed_at=candles[-1].close_time).confirmed
    )
    assert result.impulses
    for impulse in result.impulses:
        assert check_impulse(candles, impulse.start, impulse.end).impulse == impulse
        assert impulse.start in swings and impulse.end in swings
        assert impulse.pivot_confirmed_market_time <= candles[-1].close_time


def test_the_price_going_beyond_b_earlier_stops_the_look_back() -> None:
    """The high of 133.5 comes after the higher one of 140.5. An impulse to 133.5 cannot start
    before that 140.5 (its wick is beyond 133.5): it can only start at the low of 125.5 after it."""
    small = search(EXTREMES, min_impulse_fraction=D("0.05"))
    leg = next(i for i in small if (i.direction, i.end.price) == (BULLISH, D("133.5")))
    assert (leg.start.price, leg.end.price) == (D("125.5"), D("133.5"))
    assert leg.impulse_candles == 10
    # And with the default size that small leg is not an impulse at all (8 < a quarter of 34).
    assert all((i.direction, i.end.price) != (BULLISH, D("133.5")) for i in search(EXTREMES))


@pytest.mark.parametrize("upside_down", [False, True])
def test_an_equal_extreme_is_not_beyond_b_so_a_double_top_does_not_cut_the_look_back(
    upside_down: bool,
) -> None:
    """Two highs of exactly 130.5 (the staircase's top and a second one 20 candles later): the wick
    of the first is equal to B, not beyond it, so the second high's impulse still starts at the same
    low as the first one's, and not at the pullback between them (with a window wide enough for both
    to reach it). Upside down, the same for lows."""
    extremes: list[int | str] = [*UP, 118, 130, 122]
    expected_key = (BEARISH, D("169.5")) if upside_down else (BULLISH, D("130.5"))
    found = search(mirror(extremes) if upside_down else extremes, search_window_candles=200)
    twice = [i for i in found if (i.direction, i.end.price) == expected_key]
    assert len(twice) == 2  # both highs (lows) admit an impulse
    first, second = twice
    assert first.start == second.start  # same start: the equal extreme did not cut the look-back
    assert second.impulse_candles == first.impulse_candles + 20


def test_the_search_window_bounds_how_far_back_the_start_may_lie() -> None:
    wide = {(i.direction, i.end.price): i for i in search(EXTREMES, search_window_candles=200)}
    default = {(i.direction, i.end.price): i for i in search(EXTREMES)}
    narrow = {(i.direction, i.end.price): i for i in search(EXTREMES, search_window_candles=60)}
    key = (BULLISH, D("140.5"))
    # The window is a limit on the length of the impulse, inclusive: 90 candles fit in 90.
    assert wide[key].start.price == D("102.5") and wide[key].impulse_candles == 110
    assert default[key].start.price == D("106.5") and default[key].impulse_candles == 90
    assert narrow[key].start.price == D("114.5") and narrow[key].impulse_candles == 50
    exact = {(i.direction, i.end.price): i for i in search(EXTREMES, search_window_candles=90)}
    assert exact[key].impulse_candles == 90
    tighter = {(i.direction, i.end.price): i for i in search(EXTREMES, search_window_candles=89)}
    assert tighter[key].impulse_candles == 70  # the next start: candle 60, at 110.5
    for window in (60, 89, 90, 100, 200):
        for impulse in search(EXTREMES, search_window_candles=window):
            assert impulse.impulse_candles <= window


def test_a_bearish_search_is_the_bullish_one_upside_down() -> None:
    up = {
        (i.direction.value, i.start.price, i.end.price, i.impulse_candles) for i in search(EXTREMES)
    }
    down = {
        (i.direction.value, i.start.price, i.end.price, i.impulse_candles)
        for i in search(mirror(EXTREMES))
    }
    flipped = {
        (
            "BEARISH" if direction == "BULLISH" else "BULLISH",
            D(300) - start,
            D(300) - end,
            length,
        )
        for direction, start, end, length in up
    }
    assert flipped == down


@pytest.mark.parametrize("timeframe", list(Timeframe), ids=lambda t: t.value)
def test_the_same_shape_gives_the_same_impulses_on_every_timeframe(timeframe: Timeframe) -> None:
    reference = [shape(i) for i in search(EXTREMES)]
    candles = zigzag(EXTREMES, timeframe=timeframe, start=timeframe.floor(T0))
    result = search_impulses(series_for(candles, timeframe), candles)
    assert result.unfit_reasons == ()
    assert [shape(i) for i in result.impulses] == reference


# -- it depends on the candles around B, not on where the history begins ------------------------


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_the_impulses_of_recent_swings_do_not_depend_on_how_much_history_is_supplied(
    seed: int,
) -> None:
    """An impulse is measured against the candles around B: the look-back (100) and the range
    before A (another 100). So dropping the oldest 100 candles of a long series changes nothing
    for the swings that lie more than 200 candles after the start of the shorter one."""
    candles = random_walk(seed, 520)
    shorter = candles[100:]
    full = search_impulses(series_for(candles), candles).impulses
    part = search_impulses(series_for(shorter), shorter).impulses
    boundary = shorter[210].open_time
    recent_full = [shape(i) for i in full if i.end.open_time >= boundary]
    recent_part = [shape(i) for i in part if i.end.open_time >= boundary]
    assert recent_full == recent_part
    assert recent_full  # not vacuous


# -- data that is not fit -----------------------------------------------------------------------


def test_data_that_is_not_fit_yields_no_impulse_and_says_why() -> None:
    candles = zigzag(EXTREMES)
    holed = [c for i, c in enumerate(candles) if i != 100]
    result = search_impulses(series_for(candles), holed)
    assert result.impulses == () and MissingDataReason.GAPS_IN_WINDOW in result.unfit_reasons
    assert result.as_of == candles[-1].close_time
    few = candles[:40]
    assert search_impulses(series_for(few), few).unfit_reasons == (
        MissingDataReason.INSUFFICIENT_HISTORY,
    )
    unauthorised = dataclasses.replace(series_for(candles), authorized_sources=frozenset({"X"}))
    assert search_impulses(unauthorised, candles).unfit_reasons == (
        MissingDataReason.SOURCE_NOT_AUTHORIZED,
    )


def test_bad_data_never_raises_but_a_wrong_request_does() -> None:
    candles = zigzag(EXTREMES)
    contradictory = [*candles, candle_at(candles[-1].open_time, D("50"))]
    result = search_impulses(series_for(candles), contradictory)
    assert result.impulses == () and result.unfit_reasons  # it contradicts itself: refused quietly
    naive = dataclasses.replace(
        series_for(candles), observed_at=candles[-1].close_time.replace(tzinfo=None)
    )
    with pytest.raises(InvalidMarketDataError):
        search_impulses(naive, candles)


# -- no look-ahead, determinism -----------------------------------------------------------------


def wild(candles: Sequence[Candle], after: datetime) -> list[Candle]:
    return [
        c if c.close_time <= after else candle_at(c.open_time, D(1 + i % 2) * 5000)
        for i, c in enumerate(candles)
    ]


@pytest.mark.parametrize("name", ["bullish", "bearish"])
def test_the_impulses_at_any_instant_depend_only_on_what_was_closed_by_then(name: str) -> None:
    candles = zigzag(EXTREMES if name == "bullish" else mirror(EXTREMES))
    seen_something = False
    for index in range(len(candles) - 1):
        at = candles[index].close_time
        upto = [c for c in candles if c.close_time <= at]
        series = series_for(candles).at(at)
        past = search_impulses(series, upto)
        assert search_impulses(series, candles) == past, f"{name} at {at}"
        assert search_impulses(series, wild(candles, at)) == past, f"{name} at {at}"
        seen_something = seen_something or bool(past.impulses)
    assert seen_something  # not vacuous


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_random_walks_never_leak_the_future_into_the_search(seed: int) -> None:
    candles = random_walk(seed, 300)
    found = 0
    for index in range(110, 299, 7):
        at = candles[index].close_time
        upto = [c for c in candles if c.close_time <= at]
        series = series_for(candles).at(at)
        past = search_impulses(series, upto)
        assert search_impulses(series, candles) == past, (seed, index)
        found += len(past.impulses)
    assert found > 0


def test_the_same_candles_always_give_the_same_impulses() -> None:
    candles = zigzag(EXTREMES)
    assert search_impulses(series_for(candles), candles) == search_impulses(
        series_for(candles), candles
    )


def test_a_swing_whose_candle_is_not_in_the_series_yields_no_impulse() -> None:
    candles = zigzag(EXTREMES)
    swings = swing_points(
        detect_pivots(candles, timeframe=Timeframe.M5, observed_at=candles[-1].close_time).confirmed
    )
    full = find_impulses(candles, swings)
    target = next(i.end for i in full if i.end.price == D("140.5"))
    without = [c for c in candles if c.open_time != target.open_time]
    less = find_impulses(without, swings)
    assert any(i.end == target for i in full)
    assert all(i.end != target for i in less)


# -- units and what the search never does -------------------------------------------------------


def test_the_search_result_holds_no_zone_signal_entry_or_expiry() -> None:
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
        "confirmation",
    }
    names = {f.name for f in dataclasses.fields(ImpulseSearch)}
    names |= {f.name for f in dataclasses.fields(FibonacciSeries)}
    assert names.isdisjoint(forbidden)


def test_the_search_only_reads_the_domain_never_a_pattern_an_indicator_or_a_float() -> None:
    allowed = {"collections.abc", "dataclasses", "datetime"}
    source = Path(str(fibonacci_detection.__file__)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    foreign = {
        m for m in imported if m not in allowed and not m.startswith("freyja_backend.domain.")
    }
    assert not foreign, foreign
    assert not any(
        any(w in m for w in ("indicators", "pattern_", "market_trend")) for m in imported
    )
    assert "float(" not in source


def test_the_documented_search_parameters_are_the_default_ones() -> None:
    text = (REPO / "docs" / "domain" / "fibonacci-retroceso.md").read_text(encoding="utf-8")
    params = DEFAULT_FIBONACCI_PARAMS
    assert params.search_version == "fibonacci-search-v1" and "`fibonacci-search-v1`" in text
    assert f"| `search_window_candles` | {params.search_window_candles} |" in text
    assert "## 16. Búsqueda de impulsos" in text


@pytest.mark.parametrize(
    "bad",
    [
        {"search_window_candles": 0},
        {"search_window_candles": True},
        {"search_window_candles": 1.5},
        {"search_version": " "},
    ],
)
def test_search_parameters_that_make_no_sense_are_refused(bad: dict[str, Any]) -> None:
    from freyja_backend.domain.fibonacci import InvalidFibonacciRequestError

    with pytest.raises(InvalidFibonacciRequestError):
        FibonacciParams(**bad)
