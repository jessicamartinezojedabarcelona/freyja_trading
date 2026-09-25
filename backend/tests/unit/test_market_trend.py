"""POINT2-TREND-001: the structural trend classifier.

Series are built candle by candle as zigzags between chosen extremes, so every swing point,
and therefore every expected state, can be read off the numbers. The look-ahead and
reproducibility checks run over seeded random walks, exhaustively (every instant).
"""

import ast
import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import pytest

from freyja_backend.domain import market_trend
from freyja_backend.domain.market_calendar import MarketSchedule
from freyja_backend.domain.market_context import InvalidContextRequestError, MissingDataReason
from freyja_backend.domain.market_data import Candle, InstrumentRef, Timeframe
from freyja_backend.domain.market_structure import Pivot, PivotKind, PivotParams, PivotStatus
from freyja_backend.domain.market_trend import (
    DEFAULT_TREND_PARAMS,
    TREND_DEFINITION_VERSION,
    EvidenceCode,
    InsufficientDataReason,
    InvalidTrendRequestError,
    TrendClassification,
    TrendPair,
    TrendParams,
    TrendState,
    TrendTimeframes,
    classify_trend,
    classify_trend_pair,
)

TF = Timeframe.M5
STEP = TF.duration
T0 = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)  # a Monday: Forex is open all day
SOURCE = "BINANCE"
AUTHORIZED = frozenset({SOURCE})
BTC = InstrumentRef("CRYPTO", "SPOT", "BTC/USDT")
EURUSD = InstrumentRef("FOREX", "SPOT", "EUR/USD")
HALF = Decimal("0.5")
LEG = 10  # candles per leg of a zigzag: prices move in exact tenths
DEFAULT_PIVOTS = PivotParams()


def candle_at(open_time: datetime, mid: Decimal, step: timedelta = STEP) -> Candle:
    return Candle(
        open_time=open_time,
        close_time=open_time + step,
        open=mid,
        high=mid + HALF,
        low=mid - HALF,
        close=mid,
        volume=Decimal("1"),
    )


def zigzag(
    extremes: Sequence[int | str],
    *,
    tail: int = 4,
    tail_to: int | None = None,
    leg: int = LEG,
    timeframe: Timeframe = TF,
    start: datetime = T0,
) -> list[Candle]:
    """Candles whose middle price moves in straight legs from extreme to extreme.

    After the last extreme, `tail` candles retreat towards `tail_to` (by default a quarter
    of the way back to the previous extreme, so nothing breaks): enough for the last
    extreme to become a confirmed swing.
    """
    prices = [Decimal(str(e)) for e in extremes]
    mids = [prices[0]]
    for a, b in pairwise(prices):
        mids.extend(a + (b - a) * j / leg for j in range(1, leg + 1))
    if tail:
        last, previous = prices[-1], prices[-2]
        target = Decimal(str(tail_to)) if tail_to is not None else last + (previous - last) / 4
        mids.extend(last + (target - last) * j / tail for j in range(1, tail + 1))
    return [
        candle_at(start + timeframe.duration * i, m, timeframe.duration) for i, m in enumerate(mids)
    ]


def observed_after(candles: list[Candle]) -> datetime:
    """A moment just after the last candle closed: it is the newest one that must exist."""
    return candles[-1].close_time + timedelta(seconds=15)


def classify(
    candles: list[Candle],
    *,
    observed_at: datetime | None = None,
    instrument: InstrumentRef = BTC,
    schedule: MarketSchedule = MarketSchedule.CONTINUOUS_24_7,
    timeframe: Timeframe = TF,
    source: str = SOURCE,
    authorized: frozenset[str] = AUTHORIZED,
    params: TrendParams = DEFAULT_TREND_PARAMS,
    pivot_params: PivotParams = DEFAULT_PIVOTS,
    min_history: int = 100,
) -> TrendClassification:
    return classify_trend(
        instrument_id="instrument-1",
        instrument=instrument,
        schedule=schedule,
        timeframe=timeframe,
        observed_at=observed_at if observed_at is not None else observed_after(candles),
        data_source=source,
        authorized_sources=authorized,
        candles=candles,
        params=params,
        pivot_params=pivot_params,
        min_history=min_history,
    )


# Eleven-plus extremes make well over the 100 candles the context requires.
UP: list[int | str] = [100, 110, 103, 114, 107, 118, 111, 122, 115, 126, 119, 130]
DOWN: list[int | str] = [300 - int(p) for p in UP]
RANGE: list[int | str] = [
    100,
    110,
    "100.5",
    "109.5",
    "100.2",
    "110.3",
    "100.4",
    "110.1",
    "100.3",
    "110.2",
    "100.1",
    "110.3",
]


def evidence_codes(result: TrendClassification) -> list[EvidenceCode]:
    return [e.code for e in result.evidence]


# -- the four states, read off the swings --------------------------------------------------


def test_higher_highs_and_higher_lows_are_an_uptrend() -> None:
    result = classify(zigzag(UP))

    assert result.state is TrendState.UPTREND
    assert result.insufficient_data_reasons == ()
    assert [(s.kind, s.price) for s in result.confirmed_swings] == [
        (PivotKind.LOW, Decimal("114.5")),
        (PivotKind.HIGH, Decimal("126.5")),
        (PivotKind.LOW, Decimal("118.5")),
        (PivotKind.HIGH, Decimal("130.5")),
    ]
    assert evidence_codes(result) == [EvidenceCode.HIGHER_HIGHS, EvidenceCode.HIGHER_LOWS]
    assert "126.5" in result.evidence[0].detail and "130.5" in result.evidence[0].detail


def test_lower_highs_and_lower_lows_are_a_downtrend() -> None:
    result = classify(zigzag(DOWN))

    assert result.state is TrendState.DOWNTREND
    assert evidence_codes(result) == [EvidenceCode.LOWER_HIGHS, EvidenceCode.LOWER_LOWS]
    assert result.insufficient_data_reasons == ()


def test_limits_touched_again_and_again_are_a_range() -> None:
    result = classify(zigzag(RANGE))

    assert result.state is TrendState.RANGE
    assert evidence_codes(result) == [EvidenceCode.LEVEL_HIGHS, EvidenceCode.LEVEL_LOWS]


@pytest.mark.parametrize(
    ("extremes", "why"),
    [
        # Highs rise while lows fall: the swings widen, neither a trend nor a range.
        ([100, 110, 100, 110, 100, 110, 100, 110, 100, 110, 80, 130], "expanding"),
        # Highs fall while lows rise: they squeeze together.
        ([80, 130, 80, 130, 80, 130, 80, 130, 80, 130, 100, 110], "contracting"),
        # Level highs over rising lows (an ascending triangle): a conflict, not a trend.
        ([100, 120, 100, 120, 100, 120, 100, 120, 104, 120, 112, 120], "level highs, rising lows"),
    ],
)
def test_a_conflict_between_highs_and_lows_is_a_transition(extremes: list[int], why: str) -> None:
    result = classify(zigzag(extremes))

    assert result.state is TrendState.TRANSITION, why
    assert evidence_codes(result)[0] is EvidenceCode.MIXED_STRUCTURE
    assert result.insufficient_data_reasons == ()


def test_an_uptrend_whose_last_swing_low_is_closed_below_is_a_transition() -> None:
    # After the last high the price falls through the last higher low (118.5).
    result = classify(zigzag(UP, tail=6, tail_to=105))

    assert result.state is TrendState.TRANSITION
    assert evidence_codes(result)[-1] is EvidenceCode.STRUCTURE_BROKEN
    assert "below the last swing low 118.5" in result.evidence[-1].detail
    # The two sequences that made it an uptrend are still on record as evidence.
    assert EvidenceCode.HIGHER_HIGHS in evidence_codes(result)


def test_a_downtrend_whose_last_swing_high_is_closed_above_is_a_transition() -> None:
    result = classify(zigzag(DOWN, tail=6, tail_to=195))

    assert result.state is TrendState.TRANSITION
    assert evidence_codes(result)[-1] is EvidenceCode.STRUCTURE_BROKEN
    assert "above the last swing high" in result.evidence[-1].detail


def test_a_range_closed_out_of_on_either_side_is_a_transition() -> None:
    up = classify(zigzag(RANGE, tail=6, tail_to=118))
    down = classify(zigzag(RANGE, tail=6, tail_to=92))

    for result, side in ((up, "above the upper"), (down, "below the lower")):
        assert result.state is TrendState.TRANSITION
        assert evidence_codes(result)[-1] is EvidenceCode.RANGE_BROKEN
        assert side in result.evidence[-1].detail


def test_only_a_close_breaks_a_structure_not_a_wick() -> None:
    """A wick through the last low is not a break: the candle closed back above it."""
    candles = zigzag(UP)
    last = candles[-1]
    wick = Candle(
        open_time=last.open_time + STEP,
        close_time=last.close_time + STEP,
        open=last.close,
        high=last.close + HALF,
        low=Decimal("100"),  # far below the last swing low...
        close=last.close,  # ...but it closes where it opened
        volume=Decimal("1"),
    )
    result = classify([*candles, wick])
    assert result.state is TrendState.UPTREND


# -- how a step is judged ------------------------------------------------------------------


def swing(price: str, kind: PivotKind = PivotKind.HIGH) -> Pivot:
    return Pivot(kind, PivotStatus.CONFIRMED, T0, Decimal(price), T0)


def test_a_step_counts_only_when_strictly_larger_than_the_band() -> None:
    band = Decimal("2")
    steps = market_trend._steps
    assert steps([swing("10"), swing("12.1")], band) is market_trend._Steps.RISING
    assert steps([swing("10"), swing("12")], band) is market_trend._Steps.LEVEL  # exactly the band
    assert steps([swing("12"), swing("10")], band) is market_trend._Steps.LEVEL
    assert steps([swing("12.1"), swing("10")], band) is market_trend._Steps.FALLING
    assert steps([swing("10"), swing("10")], band) is market_trend._Steps.LEVEL  # equal is level


def test_rising_and_level_can_never_both_hold() -> None:
    """One band decides both, so a sequence is never directional and level at once."""
    rng = random.Random(3)
    for _ in range(2000):
        prices = [Decimal(rng.randint(0, 100)) for _ in range(rng.choice((2, 3)))]
        band = Decimal(rng.randint(1, 30))
        kind = market_trend._steps([swing(str(p)) for p in prices], band)
        diffs = [b - a for a, b in pairwise(prices)]
        if kind in (market_trend._Steps.RISING, market_trend._Steps.FALLING):
            assert max(prices) - min(prices) > band
        if all(d > band for d in diffs):
            assert kind is market_trend._Steps.RISING


def test_significance_decides_how_much_of_a_move_is_real() -> None:
    gentle = [100, 110, 104, 113, 108, 116, 112, 118, 116, 120, 119, 121]
    strict = classify(zigzag(gentle), params=TrendParams(significance=Decimal("0.60")))
    loose = classify(zigzag(gentle), params=TrendParams(significance=Decimal("0.05")))

    assert strict.state is not TrendState.UPTREND
    assert loose.state is TrendState.UPTREND


def test_a_window_of_six_swings_needs_three_highs_and_three_lows_in_order() -> None:
    wide = TrendParams(window_swings=6)
    assert classify(zigzag(UP), params=wide).state is TrendState.UPTREND
    assert len(classify(zigzag(UP), params=wide).confirmed_swings) == 6

    # The last two highs and lows rise, but a low before them fell: with six swings it is a
    # conflict, with four it is not even in view.
    broken_before = [100, 110, 103, 114, 107, 118, 111, 122, 105, 126, 119, 130]
    assert classify(zigzag(broken_before)).state is TrendState.UPTREND
    assert classify(zigzag(broken_before), params=wide).state is TrendState.TRANSITION


# -- fail closed ------------------------------------------------------------------------


def test_too_few_confirmed_swings_is_insufficient_data_not_a_guess() -> None:
    steady_climb = zigzag([100, 300], leg=110, tail=0)  # 111 candles, no turning point at all
    result = classify(steady_climb)

    assert result.state is TrendState.INSUFFICIENT_DATA
    assert result.insufficient_data_reasons == (InsufficientDataReason.INSUFFICIENT_SWINGS,)
    assert evidence_codes(result) == [EvidenceCode.SWING_COUNT]
    assert "0 confirmed swing point(s)" in result.evidence[0].detail
    assert result.as_of == steady_climb[-1].close_time  # the data itself was fine


def test_exactly_the_swings_needed_is_enough_and_one_fewer_is_not() -> None:
    three = classify(zigzag([100, 140, 110, 150], leg=35))  # high, low, high: three swings
    four = classify(zigzag([100, 140, 110, 150, 120], leg=26))  # a fourth one: a low

    assert three.state is TrendState.INSUFFICIENT_DATA
    assert three.insufficient_data_reasons == (InsufficientDataReason.INSUFFICIENT_SWINGS,)
    assert "3 confirmed swing point(s)" in three.evidence[0].detail
    assert three.confirmed_swings != ()  # what there was is reported, not hidden
    assert four.state is TrendState.UPTREND
    assert len(four.confirmed_swings) == 4


def test_a_side_with_a_single_swing_is_refused_not_read_as_a_direction() -> None:
    with pytest.raises(ValueError, match="at least two"):
        market_trend._steps([swing("10")], Decimal("1"))
    with pytest.raises(ValueError, match="at least two"):
        market_trend._steps([], Decimal("1"))


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda c: c[-60:], MissingDataReason.INSUFFICIENT_HISTORY),
        (lambda c: c[:0], MissingDataReason.NO_DATA),
        (lambda c: [*c[:-40], *c[-39:]], MissingDataReason.GAPS_IN_WINDOW),
    ],
)
def test_data_the_context_finds_unfit_is_insufficient_data_with_the_same_reason(
    mutate: object, expected: MissingDataReason
) -> None:
    candles = zigzag(UP)
    observed = observed_after(candles)
    result = classify(mutate(candles), observed_at=observed)  # type: ignore[operator]

    assert result.state is TrendState.INSUFFICIENT_DATA
    assert InsufficientDataReason(expected.value) in result.insufficient_data_reasons
    assert result.confirmed_swings == ()
    assert result.evidence == ()


def test_stale_data_is_insufficient_data() -> None:
    candles = zigzag(UP)
    result = classify(candles, observed_at=observed_after(candles) + timedelta(hours=3))
    assert result.state is TrendState.INSUFFICIENT_DATA
    assert InsufficientDataReason.STALE_DATA in result.insufficient_data_reasons


def test_a_source_that_is_not_authorized_is_never_read() -> None:
    result = classify(zigzag(UP), authorized=frozenset({"SOMEONE_ELSE"}))
    assert result.state is TrendState.INSUFFICIENT_DATA
    assert result.insufficient_data_reasons == (InsufficientDataReason.SOURCE_NOT_AUTHORIZED,)
    assert result.confirmed_swings == ()


def test_a_broker_defined_schedule_is_insufficient_until_an_adapter_supplies_it() -> None:
    result = classify(zigzag(UP), schedule=MarketSchedule.BROKER_DEFINED)
    assert result.insufficient_data_reasons == (InsufficientDataReason.SCHEDULE_UNKNOWN,)


def test_contradictory_candles_are_insufficient_data_not_an_error() -> None:
    candles = zigzag(UP)
    changed = Candle(
        open_time=candles[-1].open_time,
        close_time=candles[-1].close_time,
        open=candles[-1].open,
        high=candles[-1].high,
        low=candles[-1].low,
        close=candles[-1].close + Decimal("0.1"),
        volume=candles[-1].volume,
    )
    result = classify([*candles, changed])
    assert result.state is TrendState.INSUFFICIENT_DATA
    assert InsufficientDataReason.INVALID_CANDLES in result.insufficient_data_reasons


def test_every_reason_the_context_can_give_has_a_counterpart_here() -> None:
    for reason in MissingDataReason:
        assert InsufficientDataReason(reason.value).value == reason.value


def test_a_state_is_directional_only_with_no_reasons_and_insufficient_only_with_some() -> None:
    rng = random.Random(11)
    seen: set[TrendState] = set()
    for _ in range(40):
        candles = random_walk(rng.randint(0, 10**6), 260)
        for i in range(60, 261, 7):
            result = classify(candles[:i], observed_at=observed_after(candles[:i]))
            seen.add(result.state)
            assert (result.state is TrendState.INSUFFICIENT_DATA) == bool(
                result.insufficient_data_reasons
            )
            if result.state is not TrendState.INSUFFICIENT_DATA:
                assert len(result.confirmed_swings) == DEFAULT_TREND_PARAMS.window_swings
                kinds = [s.kind for s in result.confirmed_swings]
                assert all(a is not b for a, b in pairwise(kinds))  # strictly alternating
                assert all(s.status is PivotStatus.CONFIRMED for s in result.confirmed_swings)
    assert TrendState.UPTREND in seen and TrendState.DOWNTREND in seen  # the walks do trend


# -- no look-ahead, reproducible --------------------------------------------------------------


def random_walk(seed: int, count: int, timeframe: Timeframe = TF) -> list[Candle]:
    rng = random.Random(seed)
    price = 100_000  # cents
    out: list[Candle] = []
    for i in range(count):
        opened = price
        price = max(1000, price + rng.randint(-300, 300))
        high = max(opened, price) + rng.randint(0, 150)
        low = min(opened, price) - rng.randint(0, 150)
        out.append(
            Candle(
                open_time=T0 + timeframe.duration * i,
                close_time=T0 + timeframe.duration * (i + 1),
                open=Decimal(opened) / 100,
                high=Decimal(high) / 100,
                low=Decimal(low) / 100,
                close=Decimal(price) / 100,
                volume=Decimal("1"),
            )
        )
    return out


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_the_answer_at_any_instant_never_depends_on_what_came_after(seed: int) -> None:
    """For every instant: classifying with the whole series equals classifying with only
    the candles that had closed by then. Nothing later can change the answer."""
    candles = random_walk(seed, 280)
    for i in range(100, 281):
        observed = candles[i - 1].close_time + timedelta(seconds=15)
        with_future = classify(candles, observed_at=observed)
        only_past = classify(candles[:i], observed_at=observed)
        assert with_future == only_past, f"instant {i}"


def test_a_candle_still_open_at_the_observed_instant_is_ignored() -> None:
    candles = zigzag(UP)
    observed = observed_after(candles)
    open_candle = candle_at(candles[-1].open_time + STEP, Decimal("10"))  # crash, still in progress
    assert classify([*candles, open_candle], observed_at=observed) == classify(
        candles, observed_at=observed
    )


def test_the_same_inputs_always_give_the_same_classification() -> None:
    candles = zigzag(UP)
    first = classify(candles)
    assert all(classify(candles) == first for _ in range(5))
    assert classify(list(candles)) == first  # a copy, not the same object


def test_the_result_records_what_produced_it() -> None:
    candles = zigzag(UP)
    observed = observed_after(candles)
    result = classify(candles, observed_at=observed)

    assert result.definition_version == TREND_DEFINITION_VERSION == "trend-v1"
    assert result.structure_version == "pivots-v1"
    assert result.params == TrendParams(window_swings=4, significance=Decimal("0.15"))
    assert result.pivot_params == PivotParams(k=3)
    assert (result.instrument_id, result.data_source, result.timeframe) == (
        "instrument-1",
        SOURCE,
        TF,
    )
    assert result.observed_at == observed
    assert result.as_of == candles[-1].close_time  # the newest closed candle, never a later one
    assert result.window_candles == 100


def test_every_price_in_the_evidence_is_an_exact_decimal_text() -> None:
    result = classify(zigzag(UP))
    for evidence in result.evidence:
        assert "e+" not in evidence.detail.lower() and "nan" not in evidence.detail.lower()
    assert all(isinstance(s.price, Decimal) for s in result.confirmed_swings)


# -- two timeframes, never merged ---------------------------------------------------------------


def pair_inputs(signal: list[Candle], context: list[Candle]) -> dict[str, object]:
    return {
        "signal_candles": signal,
        "context_candles": context,
        "instrument_id": "instrument-1",
        "instrument": BTC,
        "schedule": MarketSchedule.CONTINUOUS_24_7,
        "observed_at": observed_after(signal),
        "data_source": SOURCE,
        "authorized_sources": AUTHORIZED,
    }


def hourly(extremes: Sequence[int | str], *, ending_with: list[Candle]) -> list[Candle]:
    """Hourly candles on the 1h grid whose last one closes at the hour that contains the end
    of `ending_with` (the newest hourly candle that has closed at that moment)."""
    count = 1 + (len(extremes) - 1) * LEG + 4
    end = Timeframe.H1.floor(ending_with[-1].close_time)
    return zigzag(extremes, timeframe=Timeframe.H1, start=end - Timeframe.H1.duration * count)


def test_signal_and_context_are_classified_independently_and_can_disagree() -> None:
    timeframes = TrendTimeframes(TF, Timeframe.H1, config_version="strategy-x-v3")
    # Both series end at the same instant: 105 five-minute candles vs 105 hourly ones.
    signal = zigzag(UP)
    context = hourly(DOWN, ending_with=signal)
    pair = classify_trend_pair(timeframes=timeframes, **pair_inputs(signal, context))  # type: ignore[arg-type]

    assert isinstance(pair, TrendPair)
    assert pair.signal.state is TrendState.UPTREND
    assert pair.context.state is TrendState.DOWNTREND
    assert pair.signal.timeframe is TF and pair.context.timeframe is Timeframe.H1
    assert pair.timeframes == timeframes


def test_one_timeframe_never_reads_the_other_s_candles() -> None:
    timeframes = TrendTimeframes(TF, Timeframe.H1, config_version="v1")
    signal = zigzag(UP)
    context_a = hourly(UP, ending_with=signal)
    context_b = hourly(DOWN, ending_with=signal)

    pair_a = classify_trend_pair(timeframes=timeframes, **pair_inputs(signal, context_a))  # type: ignore[arg-type]
    pair_b = classify_trend_pair(timeframes=timeframes, **pair_inputs(signal, context_b))  # type: ignore[arg-type]

    assert pair_a.signal == pair_b.signal  # changing the context changed nothing of the signal
    assert pair_a.context != pair_b.context


def test_the_pair_has_no_combined_label() -> None:
    assert set(TrendPair.__dataclass_fields__) == {"timeframes", "signal", "context"}


def test_an_insufficient_context_does_not_make_the_signal_insufficient() -> None:
    timeframes = TrendTimeframes(TF, Timeframe.H1, config_version="v1")
    signal = zigzag(UP)
    pair = classify_trend_pair(timeframes=timeframes, **pair_inputs(signal, []))  # type: ignore[arg-type]

    assert pair.context.state is TrendState.INSUFFICIENT_DATA
    assert pair.signal.state is TrendState.UPTREND


def test_the_timeframe_pair_is_strategy_configuration_with_a_version() -> None:
    assert TrendTimeframes(TF, TF, config_version="v1").context is TF  # equal is allowed
    with pytest.raises(InvalidTrendRequestError, match="finer"):
        TrendTimeframes(Timeframe.H1, TF, config_version="v1")
    for blank in ("", "   "):
        with pytest.raises(InvalidTrendRequestError, match="config version"):
            TrendTimeframes(TF, Timeframe.H1, config_version=blank)


def test_no_universal_signal_to_context_map_exists_in_the_module() -> None:
    module = ast.parse(Path(market_trend.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(module):
        if isinstance(node, ast.Dict) and node.keys:
            keys = [k for k in node.keys if isinstance(k, ast.Attribute)]
            assert not any(
                isinstance(k.value, ast.Name) and k.value.id == "Timeframe" for k in keys
            ), "a Timeframe -> Timeframe mapping would be a hardcoded universal pair"


# -- Forex goes through the same path -------------------------------------------------------------


def test_a_forex_series_is_classified_with_the_forex_calendar() -> None:
    candles = zigzag(UP)  # Monday 10:00-19:15 UTC: inside the Forex week
    result = classify(candles, instrument=EURUSD, schedule=MarketSchedule.FOREX_WEEKLY)
    assert result.state is TrendState.UPTREND


# -- parameters and requests --------------------------------------------------------------------


@pytest.mark.parametrize("window", [0, 2, 3, 5, 7, -4, True, 4.0])
def test_window_swings_must_be_an_even_integer_of_at_least_four(window: object) -> None:
    with pytest.raises(ValueError, match="window_swings"):
        TrendParams(window_swings=window)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value", [Decimal(0), Decimal(1), Decimal("-0.1"), Decimal("1.5"), 0.15, 1]
)
def test_significance_must_be_a_decimal_strictly_between_zero_and_one(value: object) -> None:
    with pytest.raises(ValueError, match="significance"):
        TrendParams(significance=value)  # type: ignore[arg-type]


def test_a_wrong_request_raises_but_bad_data_does_not() -> None:
    candles = zigzag(UP)
    with pytest.raises(Exception, match="UTC"):
        classify(candles, observed_at=datetime(2026, 1, 5, 19, 0))
    with pytest.raises(InvalidContextRequestError):
        classify(candles, min_history=0)


# -- what this layer must never become -----------------------------------------------------------


_ACTION_WORDS = ("buy", "sell", "enter", "entry", "long", "short", "order", "signal", "opportunity")


def test_a_classification_carries_no_signal_vocabulary() -> None:
    fields = set(TrendClassification.__dataclass_fields__)
    assert fields.isdisjoint({"signal", "entry", "opportunity", "recommendation", "action", "side"})
    for extremes in (UP, DOWN, RANGE, [100, 110, 100, 110, 100, 110, 100, 110, 100, 110, 80, 130]):
        for evidence in classify(zigzag(extremes)).evidence:
            words = evidence.detail.lower().replace("-", " ").split()
            assert not [w for w in _ACTION_WORDS if w in words], evidence.detail


def test_the_classifier_only_depends_on_the_domain_layer() -> None:
    """Pure by construction: no application, database, API, broker, executor or
    notification code is imported, so none of them can be invoked from here."""
    tree = ast.parse(Path(market_trend.__file__).read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    stdlib = {"enum", "collections.abc", "dataclasses", "datetime", "decimal", "itertools"}
    foreign = {
        m for m in imported if m not in stdlib and not m.startswith("freyja_backend.domain.")
    }
    assert foreign == set()
