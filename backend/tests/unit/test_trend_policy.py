"""POINT2-POLICY-001: trend requirements of a strategy.

Trend classifications are built directly, so every state, version and history length is chosen
by the test. The contract's compatibility matrix is written out here on its own, from
``docs/domain/contexto-y-tendencia.md`` section 4, and never derived from the code under test.
"""

import ast
import dataclasses
from datetime import UTC, datetime
from itertools import product
from pathlib import Path

import pytest

from freyja_backend.domain import trend_policy
from freyja_backend.domain.market_calendar import MarketSchedule
from freyja_backend.domain.market_data import Timeframe
from freyja_backend.domain.market_structure import PivotParams
from freyja_backend.domain.market_trend import (
    TREND_DEFINITION_VERSION,
    InsufficientDataReason,
    TrendClassification,
    TrendPair,
    TrendParams,
    TrendState,
    TrendTimeframes,
    classify_trend_pair,
)
from freyja_backend.domain.trend_policy import (
    ConflictRule,
    InvalidTrendPolicyError,
    Orientation,
    PolicyOutcome,
    PolicyReason,
    TrendPolicy,
    TrendRelationship,
    evaluate_trend_policy,
)
from tests.unit.test_market_trend import (
    AUTHORIZED,
    BTC,
    SOURCE,
    hourly,
    observed_after,
    zigzag,
)
from tests.unit.test_market_trend import DOWN as DOWN_EXTREMES
from tests.unit.test_market_trend import UP as UP_EXTREMES

SIGNAL_TF = Timeframe.M5
CONTEXT_TF = Timeframe.H1
NOW = datetime(2026, 9, 25, 18, 0, 15, tzinfo=UTC)

UP, DOWN = TrendState.UPTREND, TrendState.DOWNTREND
RANGE, TRANSITION = TrendState.RANGE, TrendState.TRANSITION
NO_DATA = TrendState.INSUFFICIENT_DATA
CLASSIFIABLE = frozenset({UP, DOWN, RANGE, TRANSITION})
BULLISH, BEARISH = Orientation.BULLISH, Orientation.BEARISH


def trend(
    state: TrendState,
    timeframe: Timeframe,
    *,
    version: str = TREND_DEFINITION_VERSION,
    window: int = 100,
) -> TrendClassification:
    return TrendClassification(
        state=state,
        instrument_id="instrument-1",
        data_source="BINANCE",
        timeframe=timeframe,
        observed_at=NOW,
        as_of=NOW,
        definition_version=version,
        structure_version="pivots-v1",
        params=TrendParams(),
        pivot_params=PivotParams(),
        window_candles=window,
        confirmed_swings=(),
        evidence=(),
        insufficient_data_reasons=((InsufficientDataReason.NO_DATA,) if state is NO_DATA else ()),
    )


def pair(
    signal: TrendState,
    context: TrendState,
    *,
    signal_window: int = 100,
    context_window: int = 100,
    version: str = TREND_DEFINITION_VERSION,
    signal_tf: Timeframe = SIGNAL_TF,
    context_tf: Timeframe = CONTEXT_TF,
) -> TrendPair:
    return TrendPair(
        timeframes=TrendTimeframes(signal_tf, context_tf, "test-config"),
        signal=trend(signal, signal_tf, version=version, window=signal_window),
        context=trend(context, context_tf, version=version, window=context_window),
    )


def policy(**overrides: object) -> TrendPolicy:
    values: dict[str, object] = {
        "version": "strategy-x-trend-v1",
        "signal_timeframe": SIGNAL_TF,
        "context_timeframe": CONTEXT_TF,
        "relationship": TrendRelationship.WITH_TREND,
        "signal_states": CLASSIFIABLE,
        "context_states": frozenset({UP, DOWN}),
        "conflict_rule": ConflictRule.ALLOW_CONFLICT,
        "minimum_history": 100,
        "trend_definition_version": TREND_DEFINITION_VERSION,
    }
    values.update(overrides)
    return TrendPolicy(**values)  # type: ignore[arg-type]


# -- the contract's matrix, written out on its own -------------------------------------------------

# (relationship, context state) -> orientations for which the hypothesis is compatible.
# From contexto-y-tendencia.md section 4. INSUFFICIENT_DATA is compatible with nothing.
MATRIX: dict[tuple[TrendRelationship, TrendState], frozenset[Orientation]] = {}
for _state in (UP, DOWN, RANGE, TRANSITION, NO_DATA):
    for _relationship in TrendRelationship:
        MATRIX[(_relationship, _state)] = frozenset()
MATRIX[(TrendRelationship.WITH_TREND, UP)] = frozenset({BULLISH})
MATRIX[(TrendRelationship.WITH_TREND, DOWN)] = frozenset({BEARISH})
MATRIX[(TrendRelationship.COUNTER_TREND, UP)] = frozenset({BEARISH})
MATRIX[(TrendRelationship.COUNTER_TREND, DOWN)] = frozenset({BULLISH})
MATRIX[(TrendRelationship.RANGE_ONLY, RANGE)] = frozenset({BULLISH, BEARISH})
MATRIX[(TrendRelationship.TRANSITION_ONLY, TRANSITION)] = frozenset({BULLISH, BEARISH})
for _state in (UP, DOWN, RANGE, TRANSITION):
    MATRIX[(TrendRelationship.ANY, _state)] = frozenset({BULLISH, BEARISH})

# The context states a policy of each relationship may admit (any subset, at least one).
REACHABLE = {
    TrendRelationship.WITH_TREND: frozenset({UP, DOWN}),
    TrendRelationship.COUNTER_TREND: frozenset({UP, DOWN}),
    TrendRelationship.RANGE_ONLY: frozenset({RANGE}),
    TrendRelationship.TRANSITION_ONLY: frozenset({TRANSITION}),
    TrendRelationship.ANY: CLASSIFIABLE,
}


@pytest.mark.parametrize(
    ("relationship", "state", "orientation"),
    list(product(TrendRelationship, (UP, DOWN, RANGE, TRANSITION, NO_DATA), Orientation)),
)
def test_every_cell_of_the_contract_matrix(
    relationship: TrendRelationship, state: TrendState, orientation: Orientation
) -> None:
    result = evaluate_trend_policy(
        policy(relationship=relationship, context_states=REACHABLE[relationship]),
        orientation=orientation,
        pair=pair(UP, state),
    )
    expected_compatible = orientation in MATRIX[(relationship, state)]

    assert result.is_compatible is expected_compatible, (relationship, state, orientation)
    if state is NO_DATA:
        # Without context there is no valid signal: not even ANY says yes.
        assert result.outcome is PolicyOutcome.INSUFFICIENT_CONTEXT
    elif not expected_compatible:
        assert result.outcome is PolicyOutcome.INCOMPATIBLE
        # The relationship itself is what fails, whatever else the policy admits or not.
        assert PolicyReason.RELATIONSHIP_NOT_SATISFIED in result.reasons
    else:
        assert result.outcome is PolicyOutcome.COMPATIBLE
        assert result.reasons == ()


def test_any_never_admits_a_context_without_data() -> None:
    result = evaluate_trend_policy(
        policy(relationship=TrendRelationship.ANY, context_states=CLASSIFIABLE),
        orientation=BULLISH,
        pair=pair(UP, NO_DATA),
    )
    assert result.outcome is PolicyOutcome.INSUFFICIENT_CONTEXT
    assert result.reasons == (PolicyReason.CONTEXT_TREND_INSUFFICIENT,)


@pytest.mark.parametrize("relationship", list(TrendRelationship))
@pytest.mark.parametrize("orientation", list(Orientation))
def test_no_relationship_holds_for_a_context_without_data(
    relationship: TrendRelationship, orientation: Orientation
) -> None:
    """Second line of defence: the matrix itself refuses INSUFFICIENT_DATA for every
    relationship, `ANY` included, even if a caller reached it without the earlier checks."""
    assert trend_policy._relationship_holds(relationship, orientation, NO_DATA) is False


# -- fail closed -----------------------------------------------------------------------------------


def test_a_strategy_without_a_policy_answers_insufficient_context() -> None:
    result = evaluate_trend_policy(None, orientation=BULLISH, pair=pair(UP, UP))

    assert result.outcome is PolicyOutcome.INSUFFICIENT_CONTEXT
    assert result.reasons == (PolicyReason.POLICY_MISSING,)
    assert (result.policy_version, result.relationship) == (None, None)
    assert not result.is_compatible


def test_a_signal_timeframe_without_data_is_insufficient_context() -> None:
    result = evaluate_trend_policy(policy(), orientation=BULLISH, pair=pair(NO_DATA, UP))
    assert result.outcome is PolicyOutcome.INSUFFICIENT_CONTEXT
    assert result.reasons == (PolicyReason.SIGNAL_TREND_INSUFFICIENT,)


def test_both_timeframes_without_data_report_both_reasons() -> None:
    result = evaluate_trend_policy(policy(), orientation=BULLISH, pair=pair(NO_DATA, NO_DATA))
    assert result.outcome is PolicyOutcome.INSUFFICIENT_CONTEXT
    assert result.reasons == (
        PolicyReason.SIGNAL_TREND_INSUFFICIENT,
        PolicyReason.CONTEXT_TREND_INSUFFICIENT,
    )


def test_a_lack_of_context_wins_over_an_incompatibility() -> None:
    """The policy also rejects the signal state here, but with no context the honest answer
    is not "incompatible": there is nothing to be compatible or not with."""
    strict = policy(signal_states=frozenset({UP}))
    result = evaluate_trend_policy(strict, orientation=BULLISH, pair=pair(RANGE, NO_DATA))

    assert result.outcome is PolicyOutcome.INSUFFICIENT_CONTEXT
    assert PolicyReason.SIGNAL_STATE_NOT_ADMITTED not in result.reasons


def test_a_trend_from_another_definition_is_not_assumed_to_mean_the_same() -> None:
    result = evaluate_trend_policy(
        policy(), orientation=BULLISH, pair=pair(UP, UP, version="trend-v2")
    )
    assert result.outcome is PolicyOutcome.INSUFFICIENT_CONTEXT
    assert result.reasons == (PolicyReason.TREND_DEFINITION_MISMATCH,)


def test_less_history_than_required_is_insufficient_context() -> None:
    required = policy(minimum_history=100)
    short_signal = evaluate_trend_policy(
        required, orientation=BULLISH, pair=pair(UP, UP, signal_window=99)
    )
    short_context = evaluate_trend_policy(
        required, orientation=BULLISH, pair=pair(UP, UP, context_window=99)
    )
    exact = evaluate_trend_policy(required, orientation=BULLISH, pair=pair(UP, UP))

    assert short_signal.outcome is short_context.outcome is PolicyOutcome.INSUFFICIENT_CONTEXT
    assert short_signal.reasons == short_context.reasons == (PolicyReason.MINIMUM_HISTORY_NOT_MET,)
    assert exact.is_compatible  # exactly the minimum is enough


def test_a_policy_can_ask_for_more_history_than_the_classification_read() -> None:
    demanding = policy(minimum_history=250)
    result = evaluate_trend_policy(demanding, orientation=BULLISH, pair=pair(UP, UP))
    assert result.reasons == (PolicyReason.MINIMUM_HISTORY_NOT_MET,)


def test_history_is_only_judged_where_there_is_a_classification() -> None:
    result = evaluate_trend_policy(
        policy(), orientation=BULLISH, pair=pair(NO_DATA, UP, signal_window=0)
    )
    assert result.reasons == (PolicyReason.SIGNAL_TREND_INSUFFICIENT,)  # not also a history reason


def test_trends_classified_for_other_timeframes_than_the_policy_names_are_refused() -> None:
    wrong = pair(UP, UP, signal_tf=Timeframe.M15, context_tf=Timeframe.H4)
    result = evaluate_trend_policy(policy(), orientation=BULLISH, pair=wrong)
    assert result.outcome is PolicyOutcome.INSUFFICIENT_CONTEXT
    assert PolicyReason.TIMEFRAME_MISMATCH in result.reasons

    swapped = TrendPair(
        timeframes=TrendTimeframes(SIGNAL_TF, CONTEXT_TF, "c"),
        signal=trend(UP, CONTEXT_TF),  # a classification of the wrong timeframe in the slot
        context=trend(UP, CONTEXT_TF),
    )
    assert (
        PolicyReason.TIMEFRAME_MISMATCH
        in evaluate_trend_policy(policy(), orientation=BULLISH, pair=swapped).reasons
    )


def test_the_orientation_of_the_hypothesis_must_be_declared() -> None:
    with pytest.raises(InvalidTrendPolicyError, match="orientation"):
        evaluate_trend_policy(policy(), orientation="BULLISH", pair=pair(UP, UP))  # type: ignore[arg-type]


# -- admitted states and the multi-timeframe conflict rule -----------------------------------------


def test_a_state_the_strategy_does_not_admit_is_incompatible_and_says_which() -> None:
    only_up = policy(signal_states=frozenset({UP}), context_states=frozenset({UP}))

    signal = evaluate_trend_policy(only_up, orientation=BULLISH, pair=pair(RANGE, UP))
    context = evaluate_trend_policy(only_up, orientation=BULLISH, pair=pair(UP, DOWN))
    both = evaluate_trend_policy(only_up, orientation=BULLISH, pair=pair(DOWN, DOWN))

    assert signal.outcome is PolicyOutcome.INCOMPATIBLE
    assert signal.reasons == (PolicyReason.SIGNAL_STATE_NOT_ADMITTED,)
    assert context.reasons[0] is PolicyReason.CONTEXT_STATE_NOT_ADMITTED
    assert PolicyReason.SIGNAL_STATE_NOT_ADMITTED in both.reasons
    assert PolicyReason.CONTEXT_STATE_NOT_ADMITTED in both.reasons


def test_a_conflict_between_two_trends_is_judged_by_the_declared_rule() -> None:
    both_ways = {
        "signal_states": frozenset({UP, DOWN}),
        "context_states": frozenset({UP, DOWN}),
        "relationship": TrendRelationship.ANY,
    }
    strict = policy(conflict_rule=ConflictRule.REJECT_ON_CONFLICT, **both_ways)
    lenient = policy(conflict_rule=ConflictRule.ALLOW_CONFLICT, **both_ways)

    rejected = evaluate_trend_policy(strict, orientation=BULLISH, pair=pair(UP, DOWN))
    allowed = evaluate_trend_policy(lenient, orientation=BULLISH, pair=pair(UP, DOWN))

    assert rejected.outcome is PolicyOutcome.INCOMPATIBLE
    assert rejected.reasons == (PolicyReason.MULTITIMEFRAME_CONFLICT,)
    assert allowed.is_compatible
    # The same rule is silent when the two agree.
    assert evaluate_trend_policy(strict, orientation=BULLISH, pair=pair(UP, UP)).is_compatible
    assert evaluate_trend_policy(strict, orientation=BEARISH, pair=pair(DOWN, DOWN)).is_compatible


def test_only_two_opposite_trends_are_a_conflict() -> None:
    """A range, or a transition, on either side is not a trend against a trend."""
    strict = policy(
        conflict_rule=ConflictRule.REJECT_ON_CONFLICT,
        relationship=TrendRelationship.ANY,
        signal_states=CLASSIFIABLE,
        context_states=CLASSIFIABLE,
    )
    for signal, context in ((RANGE, UP), (UP, RANGE), (TRANSITION, DOWN), (DOWN, TRANSITION)):
        result = evaluate_trend_policy(strict, orientation=BULLISH, pair=pair(signal, context))
        assert PolicyReason.MULTITIMEFRAME_CONFLICT not in result.reasons, (signal, context)


def test_every_failing_check_is_reported_not_only_the_first() -> None:
    picky = policy(
        signal_states=frozenset({UP}),
        conflict_rule=ConflictRule.REJECT_ON_CONFLICT,
        relationship=TrendRelationship.WITH_TREND,
    )
    result = evaluate_trend_policy(picky, orientation=BULLISH, pair=pair(DOWN, DOWN))

    assert result.outcome is PolicyOutcome.INCOMPATIBLE
    assert set(result.reasons) == {
        PolicyReason.SIGNAL_STATE_NOT_ADMITTED,
        PolicyReason.RELATIONSHIP_NOT_SATISFIED,
    }


# -- a policy is explicit and valid, or it does not exist ------------------------------------------


def test_nothing_in_a_policy_has_a_default_so_nothing_is_permitted_by_omission() -> None:
    assert all(
        f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
        for f in dataclasses.fields(TrendPolicy)
    )
    with pytest.raises(TypeError, match="relationship"):
        TrendPolicy(  # type: ignore[call-arg]
            version="v1",
            signal_timeframe=SIGNAL_TF,
            context_timeframe=CONTEXT_TF,
            signal_states=CLASSIFIABLE,
            context_states=frozenset({UP}),
            conflict_rule=ConflictRule.ALLOW_CONFLICT,
            minimum_history=100,
            trend_definition_version="trend-v1",
        )
    with pytest.raises(TypeError, match="conflict_rule"):
        TrendPolicy(  # type: ignore[call-arg]
            version="v1",
            signal_timeframe=SIGNAL_TF,
            context_timeframe=CONTEXT_TF,
            relationship=TrendRelationship.ANY,
            signal_states=CLASSIFIABLE,
            context_states=frozenset({UP}),
            minimum_history=100,
            trend_definition_version="trend-v1",
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"version": ""}, "version"),
        ({"version": "   "}, "version"),
        ({"trend_definition_version": ""}, "trend definition"),
        ({"relationship": "WITH_TREND"}, "relationship"),  # a bare string is not a declaration
        ({"conflict_rule": "ALLOW_CONFLICT"}, "conflict_rule"),
        ({"signal_timeframe": "5m"}, "signal_timeframe"),
        ({"signal_timeframe": Timeframe.H4, "context_timeframe": Timeframe.M5}, "finer"),
        ({"minimum_history": 0}, "minimum_history"),
        ({"minimum_history": -3}, "minimum_history"),
        ({"minimum_history": True}, "minimum_history"),
        ({"minimum_history": 10.5}, "minimum_history"),
        ({"signal_states": frozenset()}, "at least one"),
        ({"context_states": frozenset()}, "at least one"),
        ({"signal_states": frozenset({UP, NO_DATA})}, "INSUFFICIENT_DATA"),
        ({"context_states": frozenset({UP, NO_DATA})}, "INSUFFICIENT_DATA"),
        ({"signal_states": {UP}}, "frozenset"),  # a mutable set is refused
        ({"context_states": frozenset({"UPTREND"})}, "frozenset of TrendState"),
        # A policy cannot admit a context its own relationship can never meet.
        (
            {"relationship": TrendRelationship.WITH_TREND, "context_states": frozenset({RANGE})},
            "never meet",
        ),
        (
            {
                "relationship": TrendRelationship.COUNTER_TREND,
                "context_states": frozenset({UP, TRANSITION}),
            },
            "never meet",
        ),
        (
            {"relationship": TrendRelationship.RANGE_ONLY, "context_states": frozenset({UP})},
            "never meet",
        ),
        (
            {
                "relationship": TrendRelationship.TRANSITION_ONLY,
                "context_states": frozenset({RANGE}),
            },
            "never meet",
        ),
    ],
)
def test_a_policy_that_contradicts_itself_or_leaves_something_implicit_cannot_exist(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(InvalidTrendPolicyError, match=message):
        policy(**overrides)


@pytest.mark.parametrize("relationship", list(TrendRelationship))
def test_every_relationship_can_admit_exactly_its_reachable_states(
    relationship: TrendRelationship,
) -> None:
    reachable = REACHABLE[relationship]
    assert policy(relationship=relationship, context_states=reachable).context_states == reachable
    for state in reachable:
        policy(relationship=relationship, context_states=frozenset({state}))  # any single one too


def test_the_policy_declares_its_pair_of_timeframes_versioned_with_itself() -> None:
    declared = policy(version="strategy-x-trend-v7").timeframes
    assert (declared.signal, declared.context, declared.config_version) == (
        SIGNAL_TF,
        CONTEXT_TF,
        "strategy-x-trend-v7",
    )


# -- versions never rewrite history ----------------------------------------------------------------


def test_a_policy_is_immutable() -> None:
    frozen = policy()
    with pytest.raises(dataclasses.FrozenInstanceError):
        frozen.relationship = TrendRelationship.ANY  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        frozen.minimum_history = 1  # type: ignore[misc]


def test_a_new_version_is_a_new_policy_and_the_old_one_is_untouched() -> None:
    v1 = policy(version="v1", relationship=TrendRelationship.WITH_TREND)
    v2 = v1.as_new_version(
        "v2", relationship=TrendRelationship.COUNTER_TREND, context_states=frozenset({UP, DOWN})
    )

    assert (v1.version, v1.relationship) == ("v1", TrendRelationship.WITH_TREND)
    assert (v2.version, v2.relationship) == ("v2", TrendRelationship.COUNTER_TREND)
    assert v2 is not v1


def test_a_new_version_needs_a_new_identifier_and_is_validated_like_any_policy() -> None:
    v1 = policy(version="v1")
    with pytest.raises(InvalidTrendPolicyError, match="new version identifier"):
        v1.as_new_version("v1")
    with pytest.raises(InvalidTrendPolicyError, match="never meet"):
        v1.as_new_version("v2", relationship=TrendRelationship.RANGE_ONLY)
    assert v1.version == "v1"


def test_an_evaluation_keeps_its_policy_version_when_the_policy_changes_later() -> None:
    v1 = policy(version="v1", relationship=TrendRelationship.WITH_TREND)
    market = pair(UP, UP)
    before = evaluate_trend_policy(v1, orientation=BULLISH, pair=market)

    v2 = v1.as_new_version("v2", relationship=TrendRelationship.COUNTER_TREND)
    after = evaluate_trend_policy(v2, orientation=BULLISH, pair=market)

    assert (before.policy_version, before.outcome) == ("v1", PolicyOutcome.COMPATIBLE)
    assert (after.policy_version, after.outcome) == ("v2", PolicyOutcome.INCOMPATIBLE)
    # The first answer is exactly what it was: publishing v2 rewrote nothing.
    assert before == evaluate_trend_policy(v1, orientation=BULLISH, pair=market)
    with pytest.raises(dataclasses.FrozenInstanceError):
        before.outcome = PolicyOutcome.INCOMPATIBLE  # type: ignore[misc]


def test_the_evaluation_records_what_it_was_made_with() -> None:
    result = evaluate_trend_policy(policy(version="v9"), orientation=BEARISH, pair=pair(DOWN, DOWN))
    assert result.orientation is BEARISH
    assert (result.signal_state, result.context_state) == (DOWN, DOWN)
    assert result.relationship is TrendRelationship.WITH_TREND
    assert result.trend_definition_version == TREND_DEFINITION_VERSION
    assert result.evaluation_version == trend_policy.POLICY_EVALUATION_VERSION == "trend-policy-v1"


def test_the_same_inputs_always_give_the_same_evaluation() -> None:
    args = {"orientation": BULLISH, "pair": pair(UP, DOWN)}
    first = evaluate_trend_policy(policy(), **args)  # type: ignore[arg-type]
    assert all(evaluate_trend_policy(policy(), **args) == first for _ in range(5))  # type: ignore[arg-type]


# -- what this layer must never become -------------------------------------------------------------

_FORBIDDEN_FIELDS = {
    "side",
    "action",
    "position",
    "entry",
    "order",
    "short",
    "long",
    "direction",
    "signal",
    "confidence",
    "score",
    "probability",
    "recommendation",
}


def test_an_evaluation_carries_no_side_no_position_and_no_confidence() -> None:
    """A bearish hypothesis on spot crypto is to stand aside or leave, never a short: this
    layer says whether a hypothesis fits a context, and cannot even express a position."""
    evaluation_fields = {f.name for f in dataclasses.fields(trend_policy.PolicyEvaluation)}
    assert evaluation_fields.isdisjoint(_FORBIDDEN_FIELDS)
    assert {f.name for f in dataclasses.fields(TrendPolicy)}.isdisjoint(_FORBIDDEN_FIELDS)
    # A bearish hypothesis fitting a downtrend is a compatibility, nothing more.
    result = evaluate_trend_policy(policy(), orientation=BEARISH, pair=pair(DOWN, DOWN))
    assert result.is_compatible
    assert not hasattr(result, "short") and not hasattr(result, "position")


def test_an_indicator_can_not_stand_in_for_the_relationship() -> None:
    """The relationship is a declared value of a closed set, not something derived: no
    string, no indicator name and no default can be passed in its place."""
    for indicator in ("FIBONACCI", "RSI", "BOLLINGER", "fibonacci_618"):
        with pytest.raises(InvalidTrendPolicyError, match="relationship"):
            policy(relationship=indicator)
    assert {r.value for r in TrendRelationship} == {
        "WITH_TREND",
        "COUNTER_TREND",
        "RANGE_ONLY",
        "TRANSITION_ONLY",
        "ANY",
    }


def test_the_module_only_depends_on_the_domain_layer() -> None:
    """Pure by construction: nothing from the application, the database, the API, a broker,
    an executor or a notification channel is imported, so none of them can be reached."""
    tree = ast.parse(Path(trend_policy.__file__).read_text(encoding="utf-8"))
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
    stdlib = {"enum", "dataclasses", "typing"}
    foreign = {
        m for m in imported if m not in stdlib and not m.startswith("freyja_backend.domain.")
    }
    assert foreign == set()


# -- with a real classification --------------------------------------------------------------------


def test_a_policy_judges_the_real_classification_of_both_timeframes() -> None:
    def real_pair(signal_extremes: list[int | str], context_extremes: list[int | str]) -> TrendPair:
        signal = zigzag(signal_extremes)
        return classify_trend_pair(
            timeframes=TrendTimeframes(SIGNAL_TF, CONTEXT_TF, "cfg"),
            signal_candles=signal,
            context_candles=hourly(context_extremes, ending_with=signal),
            instrument_id="instrument-1",
            instrument=BTC,
            schedule=MarketSchedule.CONTINUOUS_24_7,
            observed_at=observed_after(signal),
            data_source=SOURCE,
            authorized_sources=AUTHORIZED,
        )

    with_trend = policy()
    bullish_in_uptrend = real_pair(UP_EXTREMES, UP_EXTREMES)
    assert evaluate_trend_policy(
        with_trend, orientation=BULLISH, pair=bullish_in_uptrend
    ).is_compatible
    against = evaluate_trend_policy(with_trend, orientation=BEARISH, pair=bullish_in_uptrend)
    assert against.outcome is PolicyOutcome.INCOMPATIBLE
    assert against.reasons == (PolicyReason.RELATIONSHIP_NOT_SATISFIED,)

    counter = policy(relationship=TrendRelationship.COUNTER_TREND)
    assert evaluate_trend_policy(
        counter, orientation=BEARISH, pair=bullish_in_uptrend
    ).is_compatible

    downtrend_context = real_pair(UP_EXTREMES, DOWN_EXTREMES)
    assert (
        evaluate_trend_policy(with_trend, orientation=BULLISH, pair=downtrend_context).outcome
        is PolicyOutcome.INCOMPATIBLE
    )
