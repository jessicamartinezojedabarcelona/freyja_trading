"""POINT4-MULTI-001 (first delivery): the eight two-candle pattern detectors.

Series are built the same way `test_candlestick_single.py` builds them: a zigzag whose overall
shape is known to classify as UPTREND/DOWNTREND/RANGE, with history candles widened so they never
accidentally match a pattern themselves, and two hand-shaped candles appended right after.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from freyja_backend.domain.candlestick_multi import (
    DEFAULT_MULTI_CANDLE_PARAMS,
    MULTI_CANDLE_DETECTOR_VERSION,
    MULTI_CANDLE_PARAMETER_VERSION,
    MultiCandleContext,
    MultiCandleParams,
    detect_multi_candle_patterns,
    is_bearish_harami,
    is_bullish_harami,
)
from freyja_backend.domain.candlestick_pattern import (
    CandleAnchor,
    CandlePatternState,
    CandlePatternType,
)
from freyja_backend.domain.market_calendar import MarketSchedule
from freyja_backend.domain.market_context import MissingDataReason
from freyja_backend.domain.market_data import Candle, InstrumentRef, Timeframe
from freyja_backend.domain.pattern_detection import InvalidDetectionRequestError
from tests.unit.test_market_trend import DOWN, RANGE, UP, zigzag

S = CandlePatternState
T = CandlePatternType
TF = Timeframe.M5
STEP = TF.duration
SOURCE = "BINANCE"
AUTHORIZED = frozenset({SOURCE})
BTC = InstrumentRef("CRYPTO", "SPOT", "BTC/USDT")


# -- building a series: known trend history + two hand-shaped candles ------------------------


def _ordinary_body(candle: Candle) -> Candle:
    """Same reasoning as `test_candlestick_single.py`: `zigzag()`'s candles have zero body by
    construction, which could accidentally match a pattern on the history candles themselves."""
    span = candle.high - candle.low
    offset = span * Decimal("0.3")
    mid = candle.open
    return Candle(
        candle.open_time,
        candle.close_time,
        mid - offset,
        candle.high,
        candle.low,
        mid + offset,
        candle.volume,
    )


def candle_at(open_time: datetime, o: str, h: str, low: str, c: str) -> Candle:
    return Candle(
        open_time, open_time + STEP, Decimal(o), Decimal(h), Decimal(low), Decimal(c), Decimal("1")
    )


def series(
    history_extremes: list[int | str], c1: tuple[str, str, str, str], c2: tuple[str, str, str, str]
) -> list[Candle]:
    history = [_ordinary_body(c) for c in zigzag(history_extremes, timeframe=TF)]
    first = candle_at(history[-1].close_time, *c1)
    second = candle_at(first.close_time, *c2)
    return [*history, first, second]


def context_for(
    candles: list[Candle],
    *,
    observed_at: datetime | None = None,
    authorized_sources: frozenset[str] = AUTHORIZED,
    params: MultiCandleParams = DEFAULT_MULTI_CANDLE_PARAMS,
) -> MultiCandleContext:
    return MultiCandleContext(
        instrument_id="instrument-1",
        instrument=BTC,
        schedule=MarketSchedule.CONTINUOUS_24_7,
        data_source=SOURCE,
        authorized_sources=authorized_sources,
        timeframe=TF,
        observed_at=(
            observed_at
            if observed_at is not None
            else candles[-1].close_time + timedelta(seconds=15)
        ),
        params=params,
    )


def types_found(candles: list[Candle]) -> set[CandlePatternType]:
    context = context_for(candles)
    return {i.pattern_type for i in detect_multi_candle_patterns(context, candles).instances}


def state_of(candles: list[Candle], pattern_type: CandlePatternType) -> CandlePatternState:
    context = context_for(candles)
    matches = [
        i
        for i in detect_multi_candle_patterns(context, candles).instances
        if i.pattern_type is pattern_type
    ]
    assert len(matches) == 1, f"expected exactly one {pattern_type}, found {len(matches)}"
    return matches[0].state


# Shapes: (open, high, low, close) for candle 1 and candle 2.
BULLISH_ENGULFING = (("1010", "1012", "998", "1000"), ("999", "1015", "997", "1013"))
BEARISH_ENGULFING = (("1000", "1012", "998", "1010"), ("1011", "1013", "985", "997"))
BULLISH_HARAMI = (("1012", "1015", "995", "1000"), ("1003", "1009", "1002", "1008"))
BEARISH_HARAMI = (("1000", "1013", "993", "1012"), ("1008", "1009", "1002", "1003"))
TWEEZER_BOTTOM = (("1010", "1015", "1000", "1012"), ("1012", "1018", "1001", "1016"))
TWEEZER_TOP = (("1010", "1020", "1005", "1008"), ("1008", "1019", "1000", "1006"))
PIERCING_PATTERN = (("1010", "1012", "995", "1000"), ("999", "1009", "997", "1007"))
DARK_CLOUD_COVER = (("1000", "1012", "998", "1010"), ("1011", "1013", "1001", "1003"))


# -- geometry: each pattern confirms with the trend it needs -----------------------------------


@pytest.mark.parametrize(
    ("shape", "pattern_type", "history"),
    [
        (BULLISH_ENGULFING, T.BULLISH_ENGULFING, DOWN),
        (BEARISH_ENGULFING, T.BEARISH_ENGULFING, UP),
        (BULLISH_HARAMI, T.BULLISH_HARAMI, DOWN),
        (BEARISH_HARAMI, T.BEARISH_HARAMI, UP),
        (TWEEZER_BOTTOM, T.TWEEZER_BOTTOM, DOWN),
        (TWEEZER_TOP, T.TWEEZER_TOP, UP),
        (PIERCING_PATTERN, T.PIERCING_PATTERN, DOWN),
        (DARK_CLOUD_COVER, T.DARK_CLOUD_COVER, UP),
    ],
)
def test_each_pattern_confirms_with_its_required_trend(
    shape: tuple[tuple[str, str, str, str], tuple[str, str, str, str]],
    pattern_type: CandlePatternType,
    history: list[int | str],
) -> None:
    candles = series(history, *shape)
    assert pattern_type in types_found(candles)
    assert state_of(candles, pattern_type) is S.CONFIRMED


@pytest.mark.parametrize(
    ("shape", "pattern_type"),
    [
        (BULLISH_ENGULFING, T.BULLISH_ENGULFING),
        (BULLISH_HARAMI, T.BULLISH_HARAMI),
        (TWEEZER_BOTTOM, T.TWEEZER_BOTTOM),
        (PIERCING_PATTERN, T.PIERCING_PATTERN),
    ],
)
def test_geometry_without_the_required_trend_stays_morphologically_valid(
    shape: tuple[tuple[str, str, str, str], tuple[str, str, str, str]],
    pattern_type: CandlePatternType,
) -> None:
    candles = series(UP, *shape)  # these all need a downtrend
    assert pattern_type in types_found(candles)
    assert state_of(candles, pattern_type) is S.MORPHOLOGICALLY_VALID


def test_range_context_also_stays_morphologically_valid() -> None:
    candles = series(RANGE, *BULLISH_ENGULFING)
    assert state_of(candles, T.BULLISH_ENGULFING) is S.MORPHOLOGICALLY_VALID


# -- boundary between piercing/dark-cloud and engulfing -----------------------------------------


def test_a_close_reaching_candle_ones_open_is_engulfing_not_piercing() -> None:
    """The contract draws the line at candle 1's open: reaching or passing it is engulfing;
    piercing is strictly short of it."""
    c1 = ("1010", "1012", "995", "1000")
    c2 = ("999", "1015", "997", "1010")  # closes exactly at c1.open
    candles = series(DOWN, c1, c2)
    found = types_found(candles)
    assert T.BULLISH_ENGULFING in found
    assert T.PIERCING_PATTERN not in found


def test_ordinary_candles_match_no_two_candle_geometry() -> None:
    ordinary = (("1000", "1010", "990", "1005"), ("1005", "1015", "995", "1010"))
    assert types_found(series(RANGE, *ordinary)) == set()


# -- no look-ahead, replay stability, data quality ----------------------------------------------


def test_an_open_second_candle_never_produces_a_pattern() -> None:
    candles = series(DOWN, *BULLISH_ENGULFING)
    still_open_at = candles[-1].open_time + timedelta(seconds=1)
    result = detect_multi_candle_patterns(context_for(candles, observed_at=still_open_at), candles)
    assert result.instances == ()


def test_replay_is_stable_no_future_candle_changes_a_past_pair() -> None:
    candles = series(DOWN, *BULLISH_ENGULFING)
    early = detect_multi_candle_patterns(
        context_for(candles, observed_at=candles[-1].close_time), candles
    )
    later_candles = [*candles, *zigzag(RANGE, start=candles[-1].close_time, timeframe=TF)]
    later = detect_multi_candle_patterns(context_for(later_candles), later_candles)
    early_ids = {i.candle_pattern_instance_id for i in early.instances}
    later_ids = {i.candle_pattern_instance_id for i in later.instances}
    assert early_ids <= later_ids
    for instance in early.instances:
        matching = next(
            i
            for i in later.instances
            if i.candle_pattern_instance_id == instance.candle_pattern_instance_id
        )
        assert matching == instance


def test_an_unauthorized_source_yields_nothing_and_says_why() -> None:
    candles = series(DOWN, *BULLISH_ENGULFING)
    result = detect_multi_candle_patterns(
        context_for(candles, authorized_sources=frozenset({"SOMEONE_ELSE"})), candles
    )
    assert result.instances == ()
    assert result.unfit_reasons == (MissingDataReason.SOURCE_NOT_AUTHORIZED,)


# -- identity, versions, evidence --------------------------------------------------------------


def test_instances_carry_the_shared_detector_and_parameter_version() -> None:
    candles = series(DOWN, *BULLISH_ENGULFING)
    result = detect_multi_candle_patterns(context_for(candles), candles)
    for instance in result.instances:
        assert instance.detector_version == MULTI_CANDLE_DETECTOR_VERSION
        assert instance.parameter_version == MULTI_CANDLE_PARAMETER_VERSION


def test_confirmed_evaluations_carry_context_evidence() -> None:
    candles = series(DOWN, *BULLISH_ENGULFING)
    instance = next(
        i
        for i in detect_multi_candle_patterns(context_for(candles), candles).instances
        if i.pattern_type is T.BULLISH_ENGULFING
    )
    assert {item.code for item in instance.latest.evidence} == {"CONTEXT"}


def test_the_same_pair_found_again_is_the_same_instance() -> None:
    candles = series(DOWN, *BULLISH_ENGULFING)
    first = detect_multi_candle_patterns(context_for(candles), candles).instances
    second = detect_multi_candle_patterns(context_for(candles), candles).instances
    assert {i.candle_pattern_instance_id for i in first} == {
        i.candle_pattern_instance_id for i in second
    }


# -- harami geometry is reusable on its own (for the future THREE_INSIDE_UP/DOWN detectors) -----


def test_harami_geometry_functions_are_reusable_standalone() -> None:
    o1, h1, l1, c1_ = BULLISH_HARAMI[0]
    o2, h2, l2, c2_ = BULLISH_HARAMI[1]
    t0 = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    c1 = CandleAnchor(t0, t0 + STEP, Decimal(o1), Decimal(h1), Decimal(l1), Decimal(c1_), "FIRST")
    c2 = CandleAnchor(
        t0 + STEP, t0 + STEP * 2, Decimal(o2), Decimal(h2), Decimal(l2), Decimal(c2_), "SECOND"
    )
    assert is_bullish_harami(c1, c2, DEFAULT_MULTI_CANDLE_PARAMS)
    assert not is_bearish_harami(c1, c2, DEFAULT_MULTI_CANDLE_PARAMS)


# -- parameters -------------------------------------------------------------------------------


def test_default_params_carry_their_version() -> None:
    assert DEFAULT_MULTI_CANDLE_PARAMS.version == MULTI_CANDLE_PARAMETER_VERSION


def test_a_ratio_outside_zero_one_is_refused() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="between 0 and 1"):
        MultiCandleParams(harami_outer_min_body_ratio=Decimal("1.5"))
    with pytest.raises(InvalidDetectionRequestError, match="between 0 and 1"):
        MultiCandleParams(tweezer_tolerance=Decimal("0"))


def test_min_history_must_be_a_positive_int() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="min_history"):
        MultiCandleParams(min_history=0)


def test_an_unversioned_params_set_is_refused() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="version"):
        MultiCandleParams(version="  ")
