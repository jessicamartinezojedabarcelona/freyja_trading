"""POINT4-SINGLE-001: the nine single-candle pattern detectors.

Series are built the same way `test_market_trend.py` builds them (a zigzag whose overall shape
is known to classify as UPTREND/DOWNTREND/RANGE), with one hand-shaped candle appended right
after: geometry and context are then both known quantities, so every expected outcome can be
read off the numbers.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from freyja_backend.domain.candlestick_pattern import CandlePatternState, CandlePatternType
from freyja_backend.domain.candlestick_single import (
    DEFAULT_SINGLE_CANDLE_PARAMS,
    SINGLE_CANDLE_DETECTOR_VERSION,
    SINGLE_CANDLE_PARAMETER_VERSION,
    SingleCandleContext,
    SingleCandleParams,
    detect_single_candle_patterns,
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


# -- building a series: known trend history + one hand-shaped candle -------------------------


def shaped(open_time: datetime, *, body: str, upper: str, lower: str, base: str = "1000") -> Candle:
    """A candle whose body/upper wick/lower wick are exactly these many hundredths of its range
    (e.g. body="20" is 20 % of the range): bullish (close >= open) unless body is "0"."""
    b, u, lo = Decimal(body), Decimal(upper), Decimal(lower)
    o = Decimal(base)
    c = o + b
    h = c + u
    lw = o - lo
    return Candle(open_time, open_time + STEP, o, h, lw, c, Decimal("1"))


def _ordinary_body(candle: Candle) -> Candle:
    """`zigzag()`'s own candles have `open == close` (zero body) by construction, which would
    trivially match `DOJI`'s geometry for every single history candle. Widen the body (keeping
    high/low, and so the trend classifier's read of the series, unchanged) so history candles
    never accidentally match any single-candle pattern themselves; only the hand-shaped target
    candle appended after them should."""
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


def series(history_extremes: list[int | str], **shape: str) -> list[Candle]:
    history = [_ordinary_body(c) for c in zigzag(history_extremes, timeframe=TF)]
    target = shaped(history[-1].close_time, **shape)
    return [*history, target]


def context_for(
    candles: list[Candle],
    *,
    observed_at: datetime | None = None,
    authorized_sources: frozenset[str] = AUTHORIZED,
    params: SingleCandleParams = DEFAULT_SINGLE_CANDLE_PARAMS,
) -> SingleCandleContext:
    return SingleCandleContext(
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


def types_found(
    candles: list[Candle],
    *,
    observed_at: datetime | None = None,
    authorized_sources: frozenset[str] = AUTHORIZED,
) -> set[CandlePatternType]:
    context = context_for(candles, observed_at=observed_at, authorized_sources=authorized_sources)
    result = detect_single_candle_patterns(context, candles)
    return {i.pattern_type for i in result.instances}


def state_of(
    candles: list[Candle],
    pattern_type: CandlePatternType,
    *,
    observed_at: datetime | None = None,
) -> CandlePatternState:
    context = context_for(candles, observed_at=observed_at)
    result = detect_single_candle_patterns(context, candles)
    matches = [i for i in result.instances if i.pattern_type is pattern_type]
    assert len(matches) == 1, f"expected exactly one {pattern_type}, found {len(matches)}"
    return matches[0].state


# Shapes, each isolated from the others' geometry (see docstring math in comments).
DOJI_ONLY = {"body": "5", "upper": "45", "lower": "50"}  # body 5%, neither wick long enough
HAMMER_ONLY = {"body": "28", "upper": "5", "lower": "67"}  # body too big for doji or pin bar
INVERTED_HAMMER_ONLY = {"body": "28", "upper": "67", "lower": "5"}
BULLISH_PIN_BAR_ONLY = {"body": "15", "upper": "15", "lower": "70"}  # upper 15% fails hammer
BEARISH_PIN_BAR_ONLY = {"body": "15", "upper": "70", "lower": "15"}
DRAGONFLY_AND_HAMMER = {"body": "5", "upper": "5", "lower": "90"}  # extreme: qualifies both
GRAVESTONE_AND_INVERTED = {"body": "5", "upper": "90", "lower": "5"}
NOT_A_PATTERN = {"body": "60", "upper": "20", "lower": "20"}  # ordinary candle, no geometry matches


# -- geometry: independent of context ----------------------------------------------------------


def test_a_zero_range_candle_produces_nothing() -> None:
    flat = series(RANGE, body="0", upper="0", lower="0")
    assert types_found(flat) == set()


def test_an_ordinary_candle_matches_no_geometry() -> None:
    assert types_found(series(RANGE, **NOT_A_PATTERN)) == set()


def test_doji_needs_no_context_and_is_always_confirmed() -> None:
    for history in (UP, DOWN, RANGE):
        candles = series(history, **DOJI_ONLY)
        assert T.DOJI in types_found(candles)
        assert state_of(candles, T.DOJI) is S.CONFIRMED


def test_doji_geometry_alone_does_not_produce_dragonfly_or_gravestone() -> None:
    candles = series(DOWN, **DOJI_ONLY)
    found = types_found(candles)
    assert T.DRAGONFLY_DOJI not in found
    assert T.GRAVESTONE_DOJI not in found


# -- single-name context-dependent patterns -----------------------------------------------------


def test_dragonfly_doji_confirms_after_a_downtrend() -> None:
    candles = series(DOWN, **DRAGONFLY_AND_HAMMER)
    assert state_of(candles, T.DRAGONFLY_DOJI) is S.CONFIRMED


def test_dragonfly_doji_stays_morphologically_valid_without_a_downtrend() -> None:
    for history in (UP, RANGE):
        candles = series(history, **DRAGONFLY_AND_HAMMER)
        assert state_of(candles, T.DRAGONFLY_DOJI) is S.MORPHOLOGICALLY_VALID


def test_gravestone_doji_confirms_after_an_uptrend() -> None:
    candles = series(UP, **GRAVESTONE_AND_INVERTED)
    assert state_of(candles, T.GRAVESTONE_DOJI) is S.CONFIRMED


def test_gravestone_doji_stays_morphologically_valid_without_an_uptrend() -> None:
    for history in (DOWN, RANGE):
        candles = series(history, **GRAVESTONE_AND_INVERTED)
        assert state_of(candles, T.GRAVESTONE_DOJI) is S.MORPHOLOGICALLY_VALID


def test_bullish_pin_bar_confirms_after_a_downtrend_and_waits_otherwise() -> None:
    confirmed = series(DOWN, **BULLISH_PIN_BAR_ONLY)
    assert state_of(confirmed, T.BULLISH_PIN_BAR) is S.CONFIRMED
    waiting = series(UP, **BULLISH_PIN_BAR_ONLY)
    assert state_of(waiting, T.BULLISH_PIN_BAR) is S.MORPHOLOGICALLY_VALID


def test_bearish_pin_bar_confirms_after_an_uptrend_and_waits_otherwise() -> None:
    confirmed = series(UP, **BEARISH_PIN_BAR_ONLY)
    assert state_of(confirmed, T.BEARISH_PIN_BAR) is S.CONFIRMED
    waiting = series(DOWN, **BEARISH_PIN_BAR_ONLY)
    assert state_of(waiting, T.BEARISH_PIN_BAR) is S.MORPHOLOGICALLY_VALID


def test_pin_bar_and_hammer_can_coexist_on_the_same_candle() -> None:
    """The domain doc says so explicitly: an extreme rejection candle is both, independently."""
    candles = series(DOWN, **DRAGONFLY_AND_HAMMER)
    found = types_found(candles)
    assert T.DRAGONFLY_DOJI in found
    assert T.HAMMER in found
    assert T.DOJI in found


# -- shared-geometry pairs: hammer/hanging man, inverted hammer/shooting star -------------------


def test_hammer_shape_after_a_downtrend_is_hammer_not_hanging_man() -> None:
    candles = series(DOWN, **HAMMER_ONLY)
    found = types_found(candles)
    assert found == {T.HAMMER}
    assert state_of(candles, T.HAMMER) is S.CONFIRMED


def test_hammer_shape_after_an_uptrend_is_hanging_man_not_hammer() -> None:
    candles = series(UP, **HAMMER_ONLY)
    found = types_found(candles)
    assert found == {T.HANGING_MAN}
    assert state_of(candles, T.HANGING_MAN) is S.CONFIRMED


def test_hammer_shape_in_a_range_declares_neither_name() -> None:
    candles = series(RANGE, **HAMMER_ONLY)
    found = types_found(candles)
    assert T.HAMMER not in found
    assert T.HANGING_MAN not in found


def test_inverted_hammer_shape_after_a_downtrend_is_inverted_hammer() -> None:
    candles = series(DOWN, **INVERTED_HAMMER_ONLY)
    assert types_found(candles) == {T.INVERTED_HAMMER}
    assert state_of(candles, T.INVERTED_HAMMER) is S.CONFIRMED


def test_inverted_hammer_shape_after_an_uptrend_is_shooting_star() -> None:
    candles = series(UP, **INVERTED_HAMMER_ONLY)
    assert types_found(candles) == {T.SHOOTING_STAR}
    assert state_of(candles, T.SHOOTING_STAR) is S.CONFIRMED


def test_inverted_hammer_shape_in_a_range_declares_neither_name() -> None:
    found = types_found(series(RANGE, **INVERTED_HAMMER_ONLY))
    assert T.INVERTED_HAMMER not in found
    assert T.SHOOTING_STAR not in found


# -- no look-ahead, no open candles ---------------------------------------------------------


def test_an_open_candle_never_produces_a_pattern() -> None:
    candles = series(DOWN, **HAMMER_ONLY)
    still_open_at = candles[-1].open_time + timedelta(seconds=1)
    result = detect_single_candle_patterns(context_for(candles, observed_at=still_open_at), candles)
    assert result.instances == ()


def test_replay_is_stable_no_future_candle_changes_a_past_one() -> None:
    """Same principle as every other detector in the codebase: what was found for a candle at the
    instant it closed never changes because more candles arrived later."""
    candles = series(DOWN, **HAMMER_ONLY)
    early = detect_single_candle_patterns(
        context_for(candles, observed_at=candles[-1].close_time), candles
    )
    later_candles = [*candles, *zigzag(RANGE, start=candles[-1].close_time, timeframe=TF)]
    later = detect_single_candle_patterns(context_for(later_candles), later_candles)
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


# -- data quality gates ----------------------------------------------------------------------


def test_an_unauthorized_source_yields_nothing_and_says_why() -> None:
    candles = series(DOWN, **HAMMER_ONLY)
    result = detect_single_candle_patterns(
        context_for(candles, authorized_sources=frozenset({"SOMEONE_ELSE"})), candles
    )
    assert result.instances == ()
    assert result.unfit_reasons == (MissingDataReason.SOURCE_NOT_AUTHORIZED,)


# -- identity, versions, evidence -------------------------------------------------------------


def test_instances_carry_the_shared_detector_and_parameter_version() -> None:
    candles = series(DOWN, **HAMMER_ONLY)
    result = detect_single_candle_patterns(context_for(candles), candles)
    for instance in result.instances:
        assert instance.detector_version == SINGLE_CANDLE_DETECTOR_VERSION
        assert instance.parameter_version == SINGLE_CANDLE_PARAMETER_VERSION


def test_confirmed_evaluations_carry_context_evidence() -> None:
    candles = series(DOWN, **HAMMER_ONLY)
    result = detect_single_candle_patterns(context_for(candles), candles)
    hammer = next(i for i in result.instances if i.pattern_type is T.HAMMER)
    codes = {item.code for item in hammer.latest.evidence}
    assert "CONTEXT" in codes


def test_morphologically_valid_evaluations_carry_no_context_evidence_yet() -> None:
    candles = series(RANGE, **DRAGONFLY_AND_HAMMER)
    result = detect_single_candle_patterns(context_for(candles), candles)
    dragonfly = next(i for i in result.instances if i.pattern_type is T.DRAGONFLY_DOJI)
    assert dragonfly.state is S.MORPHOLOGICALLY_VALID
    assert dragonfly.latest.evidence == ()


def test_the_same_candle_found_again_is_the_same_instance() -> None:
    candles = series(DOWN, **HAMMER_ONLY)
    first = detect_single_candle_patterns(context_for(candles), candles).instances
    second = detect_single_candle_patterns(context_for(candles), candles).instances
    assert {i.candle_pattern_instance_id for i in first} == {
        i.candle_pattern_instance_id for i in second
    }


# -- parameters -------------------------------------------------------------------------------


def test_default_params_carry_their_version() -> None:
    assert DEFAULT_SINGLE_CANDLE_PARAMS.version == SINGLE_CANDLE_PARAMETER_VERSION


def test_a_ratio_outside_zero_one_is_refused() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="between 0 and 1"):
        SingleCandleParams(doji_max_body_ratio=Decimal("1.5"))
    with pytest.raises(InvalidDetectionRequestError, match="between 0 and 1"):
        SingleCandleParams(pin_bar_min_wick_ratio=Decimal("0"))


def test_short_wick_ceiling_must_be_below_long_wick_floor() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="short wick ceiling"):
        SingleCandleParams(
            short_wick_max_ratio=Decimal("0.70"), long_wick_min_ratio=Decimal("0.60")
        )


def test_min_history_must_be_a_positive_int() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="min_history"):
        SingleCandleParams(min_history=0)
    with pytest.raises(InvalidDetectionRequestError, match="min_history"):
        SingleCandleParams(min_history=True)


def test_an_unversioned_params_set_is_refused() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="version"):
        SingleCandleParams(version="  ")
