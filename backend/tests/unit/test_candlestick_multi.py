"""POINT4-MULTI-001: the fourteen two- and three-candle pattern detectors.

Series are built the same way `test_candlestick_single.py` builds them: a zigzag whose overall
shape is known to classify as UPTREND/DOWNTREND/RANGE, with history candles widened so they never
accidentally match a pattern themselves, and two or three hand-shaped candles appended right
after.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from freyja_backend.domain.candlestick_multi import (
    DEFAULT_MULTI_CANDLE_PARAMS,
    DEFAULT_THREE_CANDLE_PARAMS,
    MULTI_CANDLE_DETECTOR_VERSION,
    MULTI_CANDLE_PARAMETER_VERSION,
    THREE_CANDLE_DETECTOR_VERSION,
    THREE_CANDLE_PARAMETER_VERSION,
    GapPolicy,
    MultiCandleContext,
    MultiCandleParams,
    ThreeCandleParams,
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


def series3(
    history_extremes: list[int | str],
    c1: tuple[str, str, str, str],
    c2: tuple[str, str, str, str],
    c3: tuple[str, str, str, str],
) -> list[Candle]:
    history = [_ordinary_body(c) for c in zigzag(history_extremes, timeframe=TF)]
    first = candle_at(history[-1].close_time, *c1)
    second = candle_at(first.close_time, *c2)
    third = candle_at(second.close_time, *c3)
    return [*history, first, second, third]


def context_for(
    candles: list[Candle],
    *,
    observed_at: datetime | None = None,
    authorized_sources: frozenset[str] = AUTHORIZED,
    params: MultiCandleParams = DEFAULT_MULTI_CANDLE_PARAMS,
    triple: ThreeCandleParams = DEFAULT_THREE_CANDLE_PARAMS,
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
        triple=triple,
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


def test_a_late_arriving_candle_does_not_leave_a_stale_prior_trend_cached() -> None:
    """POINT4-MULTI-001 review (2026-09-28): `_prior_trends` was keyed only by `at`, so reusing
    the same context (via `.at()`, its own documented replay mechanism) across two calls where a
    previously-missing candle arrives late returned the trend classification computed from the
    earlier, incomplete history instead of recomputing. Reproduced against a real zigzag downtrend
    (60 recent candles: INSUFFICIENT_DATA; the same 115 candles complete: DOWNTREND) before fixing
    the cache key to include `len(before)`."""
    full_history = [_ordinary_body(c) for c in zigzag(DOWN, timeframe=TF)]
    c1 = candle_at(full_history[-1].close_time, *BULLISH_ENGULFING[0])
    c2 = candle_at(c1.close_time, *BULLISH_ENGULFING[1])
    only_recent = full_history[-60:]  # not enough leading history to classify a trend
    candles_incomplete = [*only_recent, c1, c2]
    candles_complete = [*full_history, c1, c2]

    context = context_for(candles_incomplete)
    first = detect_multi_candle_patterns(context, candles_incomplete)
    incomplete = next(i for i in first.instances if i.pattern_type is T.BULLISH_ENGULFING)
    assert incomplete.state is S.MORPHOLOGICALLY_VALID  # not enough history yet to confirm

    later_context = context.at(candles_complete[-1].close_time + timedelta(seconds=15))
    second = detect_multi_candle_patterns(later_context, candles_complete)
    confirmed = next(i for i in second.instances if i.pattern_type is T.BULLISH_ENGULFING)
    assert confirmed.state is S.CONFIRMED  # the now-complete history must not be shadowed


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


# -- three candles: geometry, gaps, harami reuse, independent versioning -----------------------

# Shapes: (open, high, low, close) for candles 1, 2 and 3. GAP_NOT_APPLICABLE (the default) does
# not need a real gap between candle 1 and candle 2.
MORNING_STAR = (
    ("1010", "1012", "990", "992"),
    ("991", "993", "989", "990"),
    ("990", "1005", "989", "1003"),
)
EVENING_STAR = (
    ("990", "1010", "988", "1008"),
    ("1009", "1013", "1007", "1008"),
    ("1008", "1009", "994", "996"),
)
THREE_WHITE_SOLDIERS = (
    ("1000", "1011", "999", "1010"),
    ("1005", "1021", "1004", "1020"),
    ("1015", "1031", "1014", "1030"),
)
THREE_BLACK_CROWS = (
    ("1010", "1011", "999", "1000"),
    ("1005", "1006", "989", "990"),
    ("995", "996", "979", "980"),
)
THREE_INSIDE_UP = (*BULLISH_HARAMI, ("1008", "1020", "1007", "1018"))  # c1.high = 1015
THREE_INSIDE_DOWN = (*BEARISH_HARAMI, ("1003", "1004", "985", "988"))  # c1.low = 993


@pytest.mark.parametrize(
    ("shape", "pattern_type", "history"),
    [
        (MORNING_STAR, T.MORNING_STAR, DOWN),
        (EVENING_STAR, T.EVENING_STAR, UP),
        (THREE_INSIDE_UP, T.THREE_INSIDE_UP, DOWN),
        (THREE_INSIDE_DOWN, T.THREE_INSIDE_DOWN, UP),
    ],
)
def test_each_three_candle_pattern_confirms_with_its_required_trend(
    shape: tuple[tuple[str, str, str, str], ...],
    pattern_type: CandlePatternType,
    history: list[int | str],
) -> None:
    candles = series3(history, *shape)
    assert pattern_type in types_found(candles)
    assert state_of(candles, pattern_type) is S.CONFIRMED


@pytest.mark.parametrize(
    ("shape", "pattern_type"),
    [(MORNING_STAR, T.MORNING_STAR), (THREE_INSIDE_UP, T.THREE_INSIDE_UP)],
)
def test_three_candle_geometry_without_the_required_trend_stays_morphologically_valid(
    shape: tuple[tuple[str, str, str, str], ...], pattern_type: CandlePatternType
) -> None:
    candles = series3(UP, *shape)  # these both need a downtrend
    assert pattern_type in types_found(candles)
    assert state_of(candles, pattern_type) is S.MORPHOLOGICALLY_VALID


@pytest.mark.parametrize("history", [DOWN, UP, RANGE])
def test_three_soldiers_and_three_crows_confirm_regardless_of_trend(
    history: list[int | str],
) -> None:
    """patrones-de-vela.md: no strict context requirement for these two, unlike the rest."""
    soldiers = series3(history, *THREE_WHITE_SOLDIERS)
    assert state_of(soldiers, T.THREE_WHITE_SOLDIERS) is S.CONFIRMED
    crows = series3(history, *THREE_BLACK_CROWS)
    assert state_of(crows, T.THREE_BLACK_CROWS) is S.CONFIRMED


def test_three_inside_up_coexists_with_the_bullish_harami_it_is_built_on() -> None:
    candles = series3(DOWN, *THREE_INSIDE_UP)
    found = types_found(candles)
    assert T.THREE_INSIDE_UP in found
    assert T.BULLISH_HARAMI in found


def test_three_inside_down_coexists_with_the_bearish_harami_it_is_built_on() -> None:
    candles = series3(UP, *THREE_INSIDE_DOWN)
    found = types_found(candles)
    assert T.THREE_INSIDE_DOWN in found
    assert T.BEARISH_HARAMI in found


# -- gap policy ---------------------------------------------------------------------------------


def test_gap_not_applicable_is_the_default_and_needs_no_real_gap() -> None:
    assert DEFAULT_THREE_CANDLE_PARAMS.gap_policy is GapPolicy.GAP_NOT_APPLICABLE
    candles = series3(DOWN, *MORNING_STAR)
    assert state_of(candles, T.MORNING_STAR) is S.CONFIRMED


def test_gap_required_rejects_a_morning_star_whose_gap_is_too_small() -> None:
    strict = ThreeCandleParams(gap_policy=GapPolicy.GAP_REQUIRED)
    candles = series3(DOWN, *MORNING_STAR)
    context = context_for(candles, triple=strict)
    found = {i.pattern_type for i in detect_multi_candle_patterns(context, candles).instances}
    assert T.MORNING_STAR not in found


def test_gap_required_accepts_a_morning_star_with_a_real_gap() -> None:
    strict = ThreeCandleParams(gap_policy=GapPolicy.GAP_REQUIRED)
    gapped = (
        ("1010", "1012", "990", "992"),
        ("970", "972", "968", "970"),
        ("969", "1005", "968", "1003"),
    )
    candles = series3(DOWN, *gapped)
    context = context_for(candles, triple=strict)
    instance = next(
        i
        for i in detect_multi_candle_patterns(context, candles).instances
        if i.pattern_type is T.MORNING_STAR
    )
    assert instance.state is S.CONFIRMED
    assert {item.code for item in instance.latest.evidence} == {"CONTEXT", "GAP"}


# -- independent versioning: the two families never share an identity --------------------------


def test_two_and_three_candle_instances_carry_their_own_family_versions() -> None:
    candles = series3(DOWN, *THREE_INSIDE_UP)
    result = detect_multi_candle_patterns(context_for(candles), candles)
    harami = next(i for i in result.instances if i.pattern_type is T.BULLISH_HARAMI)
    inside_up = next(i for i in result.instances if i.pattern_type is T.THREE_INSIDE_UP)
    assert harami.detector_version == MULTI_CANDLE_DETECTOR_VERSION
    assert harami.parameter_version == MULTI_CANDLE_PARAMETER_VERSION
    assert inside_up.detector_version == THREE_CANDLE_DETECTOR_VERSION
    assert inside_up.parameter_version == THREE_CANDLE_PARAMETER_VERSION


def test_changing_three_candle_params_never_changes_a_two_candle_instances_identity() -> None:
    """The whole point of splitting the two families' versions (POINT4-MULTI-001 review,
    2026-09-28): a change that only affects three-candle patterns must not shift
    BULLISH_HARAMI's own identity, even though THREE_INSIDE_UP reuses its geometry check."""
    candles = series3(DOWN, *THREE_INSIDE_UP)
    baseline = detect_multi_candle_patterns(context_for(candles), candles)
    baseline_harami = next(i for i in baseline.instances if i.pattern_type is T.BULLISH_HARAMI)

    changed_triple = ThreeCandleParams(min_body_ratio=Decimal("0.20"))  # unrelated to the harami
    changed = detect_multi_candle_patterns(context_for(candles, triple=changed_triple), candles)
    changed_harami = next(i for i in changed.instances if i.pattern_type is T.BULLISH_HARAMI)

    assert baseline_harami.candle_pattern_instance_id == changed_harami.candle_pattern_instance_id
    assert (
        baseline_harami.parameter_version
        == changed_harami.parameter_version
        == MULTI_CANDLE_PARAMETER_VERSION
    )


def test_changing_two_candle_params_never_changes_a_three_candle_instances_identity() -> None:
    candles = series3(DOWN, *THREE_INSIDE_UP)
    baseline = detect_multi_candle_patterns(context_for(candles), candles)
    baseline_inside = next(i for i in baseline.instances if i.pattern_type is T.THREE_INSIDE_UP)

    changed_pair = MultiCandleParams(tweezer_tolerance=Decimal("0.20"))  # unrelated to the harami
    changed = detect_multi_candle_patterns(context_for(candles, params=changed_pair), candles)
    changed_inside = next(i for i in changed.instances if i.pattern_type is T.THREE_INSIDE_UP)

    assert baseline_inside.candle_pattern_instance_id == changed_inside.candle_pattern_instance_id
    assert (
        baseline_inside.parameter_version
        == changed_inside.parameter_version
        == THREE_CANDLE_PARAMETER_VERSION
    )


def test_harami_params_stamps_its_own_version_not_multi_candle_params() -> None:
    triple = ThreeCandleParams(version="three-candle-params-v2-test")
    stamped = triple.harami_params()
    assert stamped.version == "three-candle-params-v2-test"
    assert stamped.harami_outer_min_body_ratio == triple.harami_outer_min_body_ratio


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


def test_default_triple_params_carry_their_version() -> None:
    assert DEFAULT_THREE_CANDLE_PARAMS.version == THREE_CANDLE_PARAMETER_VERSION


def test_a_triple_ratio_outside_zero_one_is_refused() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="between 0 and 1"):
        ThreeCandleParams(min_body_ratio=Decimal("0"))
    with pytest.raises(InvalidDetectionRequestError, match="between 0 and 1"):
        ThreeCandleParams(gap_min_fraction=Decimal("1"))


def test_triple_min_history_must_be_a_positive_int() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="min_history"):
        ThreeCandleParams(min_history=0)


def test_an_unversioned_triple_params_set_is_refused() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="version"):
        ThreeCandleParams(version="  ")
