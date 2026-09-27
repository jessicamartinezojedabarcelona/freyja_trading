"""POINT3-HYPOTHESIS-001: combining coexisting figures as evidence.

The expected story of every case is written from the contract
(``docs/domain/hipotesis-de-figura.md``), never from the code under test. Instances are built
directly (anchors and evidence handed over explicitly), the same way ``test_pattern_diamond.py``
and ``test_chart_pattern.py`` build theirs, so every instant and every fact is known.
"""

import dataclasses
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from freyja_backend.domain.chart_pattern import (
    AnchorPivot,
    Boundary,
    BoundaryPoint,
    BoundaryRole,
    Breakout,
    BreakoutDirection,
    EvidenceValue,
    InvalidationReason,
    PatternEvaluation,
    PatternInstance,
    PatternState,
    PatternType,
    evidence,
    start_pattern_instance,
)
from freyja_backend.domain.market_context import MissingDataReason
from freyja_backend.domain.market_data import Timeframe
from freyja_backend.domain.market_structure import PivotKind
from freyja_backend.domain.market_trend import TrendState
from freyja_backend.domain.pattern_detection import AFTER_MARKET_FORMATION, LIVE, RETROSPECTIVE
from freyja_backend.domain.pattern_hypothesis import (
    UNPROVEN,
    HypothesisDirection,
    HypothesisKind,
    InvalidHypothesisError,
    Operability,
    TargetScope,
    derive_pattern_hypothesis_id,
    evidence_provenance,
    hypothesis_for,
)

T0 = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
STEP = timedelta(minutes=5)
TF = Timeframe.M5
S = PatternState


# -- builders -------------------------------------------------------------------------------


def anchors(n: int, *, start: datetime = T0) -> tuple[AnchorPivot, ...]:
    kinds = (PivotKind.HIGH, PivotKind.LOW)
    return tuple(
        AnchorPivot(
            kinds[i % 2],
            start + STEP * 10 * i,
            Decimal(100 + i),
            start + STEP * 10 * i + STEP * 4,
            f"A{i}",
        )
        for i in range(n)
    )


def boundary_for(anchor_list: tuple[AnchorPivot, ...]) -> Boundary:
    return Boundary(
        BoundaryRole.NECKLINE,
        (
            BoundaryPoint(anchor_list[0].open_time, anchor_list[0].price),
            BoundaryPoint(anchor_list[-1].open_time, anchor_list[-1].price),
        ),
        (anchor_list[0].open_time,),
    )


def evaluation(
    state: PatternState,
    anchor_list: tuple[AnchorPivot, ...],
    *,
    step: int,
    prior_trend: TrendState = TrendState.UPTREND,
    direction: BreakoutDirection = BreakoutDirection.UP,
    provenance: str = LIVE,
    known: bool = True,
) -> PatternEvaluation:
    evaluated_at = anchor_list[-1].confirmed_at + STEP * (step + 1)
    values: dict[str, Any] = {
        "evaluated_at": evaluated_at,
        "as_of": evaluated_at,
        "candle_count": 20 + step,
        "state": state,
        "anchors": anchor_list,
    }
    if state not in (S.FORMING, S.INVALIDATED, S.INSUFFICIENT_DATA):
        values["boundaries"] = (boundary_for(anchor_list),)
    items = [evidence("PRIOR_TREND", f"trend before: {prior_trend.value}", state=prior_trend.value)]
    breakout_confirmed = {
        S.BREAKOUT_PENDING_CONFIRMATION: False,
        S.CONFIRMED_UP: True,
        S.CONFIRMED_DOWN: True,
        S.FAILED_BREAKOUT: False,
    }
    if state in breakout_confirmed:
        actual_direction = {
            S.CONFIRMED_UP: BreakoutDirection.UP,
            S.CONFIRMED_DOWN: BreakoutDirection.DOWN,
        }.get(state, direction)
        values["breakout"] = Breakout(
            actual_direction,
            BoundaryRole.NECKLINE,
            evaluated_at - STEP,
            evaluated_at,
            Decimal("99.5"),
            breakout_confirmed[state],
        )
        formed_at = anchor_list[-1].confirmed_at
        facts: dict[str, EvidenceValue] = {
            "market_formed_at": formed_at.isoformat(),
            "receipts_available": known,
        }
        if known:
            facts["known_at"] = formed_at.isoformat()
            facts["provenance"] = provenance
        items.append(evidence("BREAKOUT_TIMING", "test timing", **facts))
    if state is S.INVALIDATED:
        values["invalidation_reasons"] = (InvalidationReason.GEOMETRY_BROKEN,)
    if state is S.INSUFFICIENT_DATA:
        values["insufficient_data_reasons"] = (MissingDataReason.NO_DATA,)
    values["evidence"] = tuple(items)
    return PatternEvaluation(**values)


def instance(
    pattern_type: PatternType,
    states: Sequence[PatternState],
    *,
    anchor_count: int,
    prior_trend: TrendState = TrendState.UPTREND,
    direction: BreakoutDirection = BreakoutDirection.UP,
    provenance: str = LIVE,
    known: bool = True,
    instrument_id: str = "instrument-1",
    data_source: str = "BINANCE",
    timeframe: Timeframe = TF,
    detector_version: str = "test-detector-v1",
    start: datetime = T0,
) -> PatternInstance:
    anchor_list = anchors(anchor_count, start=start)

    def eval_at(state: PatternState, step: int) -> PatternEvaluation:
        return evaluation(
            state,
            anchor_list,
            step=step,
            prior_trend=prior_trend,
            direction=direction,
            provenance=provenance,
            known=known,
        )

    built = start_pattern_instance(
        pattern_type=pattern_type,
        instrument_id=instrument_id,
        data_source=data_source,
        timeframe=timeframe,
        detector_version=detector_version,
        parameter_version="test-params-v1",
        first_evaluation=eval_at(states[0], 0),
    )
    for step, state in enumerate(states[1:], start=1):
        built = built.advance(eval_at(state, step))
    return built


# -- when a hypothesis exists at all -------------------------------------------------------------


def test_no_hypothesis_before_a_real_breakout() -> None:
    forming = instance(PatternType.ASCENDING_TRIANGLE, [S.GEOMETRICALLY_VALID], anchor_count=4)
    assert hypothesis_for(forming) is None


def test_an_instance_invalidated_without_ever_breaking_out_has_no_hypothesis() -> None:
    dead_on_arrival = instance(PatternType.ASCENDING_TRIANGLE, [S.INVALIDATED], anchor_count=4)
    assert hypothesis_for(dead_on_arrival) is None


def test_a_hypothesis_is_born_at_the_first_real_breakout_state() -> None:
    source = instance(
        PatternType.ASCENDING_TRIANGLE,
        [S.GEOMETRICALLY_VALID, S.BREAKOUT_PENDING_CONFIRMATION],
        anchor_count=4,
        direction=BreakoutDirection.UP,
    )
    built = hypothesis_for(source)
    assert built is not None
    assert len(built.evaluations) == 1  # GEOMETRICALLY_VALID produced nothing
    assert built.latest.hypothesis_direction is HypothesisDirection.UP
    assert built.source_pattern_instance_id == source.pattern_instance_id


# -- hypothesis_kind and context_compatible: section 3.1 -----------------------------------------


def test_reversal_when_the_role_and_the_opposite_prior_trend_agree() -> None:
    """Ascending triangle (roles CONTINUATION, REVERSAL), breaking up after a downtrend: a real
    reversal of what came before."""
    source = instance(
        PatternType.ASCENDING_TRIANGLE,
        [S.CONFIRMED_UP],
        anchor_count=4,
        prior_trend=TrendState.DOWNTREND,
        direction=BreakoutDirection.UP,
    )
    latest = hypothesis_for(source).latest  # type: ignore[union-attr]
    assert latest.hypothesis_kind is HypothesisKind.REVERSAL
    assert latest.context_compatible is True


def test_continuation_when_the_role_and_the_same_prior_trend_agree() -> None:
    source = instance(
        PatternType.ASCENDING_TRIANGLE,
        [S.CONFIRMED_UP],
        anchor_count=4,
        prior_trend=TrendState.UPTREND,
        direction=BreakoutDirection.UP,
    )
    latest = hypothesis_for(source).latest  # type: ignore[union-attr]
    assert latest.hypothesis_kind is HypothesisKind.CONTINUATION
    assert latest.context_compatible is True


def test_breakout_when_there_is_no_trend_to_continue_or_reverse() -> None:
    source = instance(
        PatternType.ASCENDING_TRIANGLE,
        [S.CONFIRMED_UP],
        anchor_count=4,
        prior_trend=TrendState.RANGE,
        direction=BreakoutDirection.UP,
    )
    latest = hypothesis_for(source).latest  # type: ignore[union-attr]
    assert latest.hypothesis_kind is HypothesisKind.BREAKOUT
    assert latest.context_compatible is False


def test_volatility_expansion_wins_regardless_of_context() -> None:
    """Broadening formation (roles REVERSAL, EXPANSION): EXPANSION has priority 1, so it is the
    kind even when the context would also make it a REVERSAL."""
    source = instance(
        PatternType.BROADENING_FORMATION,
        [S.CONFIRMED_DOWN],
        anchor_count=5,
        prior_trend=TrendState.UPTREND,
        direction=BreakoutDirection.DOWN,
    )
    latest = hypothesis_for(source).latest  # type: ignore[union-attr]
    assert latest.hypothesis_kind is HypothesisKind.VOLATILITY_EXPANSION
    assert latest.context_compatible is True  # still computed: reversal of the uptrend held


def test_hypothesis_direction_is_the_real_breakout_never_the_traditional_bias() -> None:
    """DOUBLE_TOP is traditionally BEARISH; here it breaks UP (against tradition), and the
    hypothesis says so plainly."""
    source = instance(
        PatternType.DOUBLE_TOP,
        [S.CONFIRMED_UP],
        anchor_count=3,
        prior_trend=TrendState.DOWNTREND,
        direction=BreakoutDirection.UP,
    )
    latest = hypothesis_for(source).latest  # type: ignore[union-attr]
    assert latest.hypothesis_direction is HypothesisDirection.UP


def test_target_scope_is_always_market_direction() -> None:
    source = instance(PatternType.DOUBLE_TOP, [S.CONFIRMED_UP], anchor_count=3)
    assert hypothesis_for(source).latest.target_scope is TargetScope.MARKET_DIRECTION  # type: ignore[union-attr]


# -- procedencia y operabilidad: secciones 4 y 5 --------------------------------------------------


@pytest.mark.parametrize(
    ("source_provenance", "known", "expected"),
    [
        (LIVE, True, Operability.OPERABLE),
        (AFTER_MARKET_FORMATION, True, Operability.RETROSPECTIVE),
        (RETROSPECTIVE, True, Operability.RETROSPECTIVE),
        (LIVE, False, Operability.UNPROVEN),  # known_at absent: never trusted, whatever the label
    ],
)
def test_operability_follows_the_source_s_own_provenance_only(
    source_provenance: str, known: bool, expected: Operability
) -> None:
    source = instance(
        PatternType.DOUBLE_TOP,
        [S.CONFIRMED_UP],
        anchor_count=3,
        provenance=source_provenance,
        known=known,
    )
    assert hypothesis_for(source).latest.operability is expected  # type: ignore[union-attr]


def test_evidence_provenance_is_unproven_without_known_at_even_if_the_detector_says_operable() -> (
    None
):
    """Same rule as `hipotesis-de-figura.md` section 4.3: a `provenance` fact is not trusted
    unless `known_at` is present too."""
    source = instance(
        PatternType.DOUBLE_TOP, [S.CONFIRMED_UP], anchor_count=3, provenance=LIVE, known=False
    )
    assert evidence_provenance(source.latest) == UNPROVEN


def test_an_unproven_source_never_becomes_operable_however_good_its_support() -> None:
    """A supporting figure with LIVE provenance never launders an UNPROVEN source (section 5:
    operability depends solely on the source)."""
    source = instance(
        PatternType.DOUBLE_TOP,
        [S.CONFIRMED_UP],
        anchor_count=3,
        provenance=LIVE,
        known=False,  # UNPROVEN despite the label
    )
    supporter = instance(
        PatternType.TRIPLE_TOP,
        [S.CONFIRMED_UP],
        anchor_count=5,
        provenance=LIVE,
        known=True,
        start=T0 - STEP * 200,  # already resolved well before the source's own evaluation
    )
    built = hypothesis_for(source, pool=[supporter])
    assert built is not None
    assert built.latest.operability is Operability.UNPROVEN
    assert len(built.latest.supporting_patterns) == 1  # still recorded, just does not decide


# -- supporting y conflicting: sección 3.3 --------------------------------------------------------


def test_supporting_conflicting_and_neutral_are_told_apart() -> None:
    source = instance(
        PatternType.DOUBLE_TOP, [S.CONFIRMED_UP], anchor_count=3, direction=BreakoutDirection.UP
    )
    early = T0 - STEP * 200  # already resolved well before the source's own evaluation
    agrees = instance(
        PatternType.TRIPLE_TOP,
        [S.CONFIRMED_UP],
        anchor_count=5,
        direction=BreakoutDirection.UP,
        start=early,
    )
    disagrees = instance(
        PatternType.TRIPLE_BOTTOM,
        [S.CONFIRMED_DOWN],
        anchor_count=5,
        direction=BreakoutDirection.DOWN,
        start=early,
    )
    neutral = instance(
        PatternType.ASCENDING_TRIANGLE, [S.GEOMETRICALLY_VALID], anchor_count=4, start=early
    )

    built = hypothesis_for(source, pool=[agrees, disagrees, neutral])
    assert built is not None
    supporting_ids = {p.pattern_instance_id for p in built.latest.supporting_patterns}
    conflicting_ids = {p.pattern_instance_id for p in built.latest.conflicting_patterns}
    assert supporting_ids == {agrees.pattern_instance_id}
    assert conflicting_ids == {disagrees.pattern_instance_id}
    assert neutral.pattern_instance_id not in supporting_ids | conflicting_ids


def test_a_different_series_never_supports_or_conflicts() -> None:
    source = instance(
        PatternType.DOUBLE_TOP, [S.CONFIRMED_UP], anchor_count=3, data_source="BINANCE"
    )
    other_source = instance(
        PatternType.TRIPLE_TOP, [S.CONFIRMED_UP], anchor_count=5, data_source="KRAKEN"
    )
    built = hypothesis_for(source, pool=[other_source])
    assert built is not None
    assert built.latest.supporting_patterns == ()
    assert built.latest.conflicting_patterns == ()


def test_a_pool_instance_only_counts_from_when_it_was_itself_known() -> None:
    """No look-ahead in the aggregation itself: a supporting figure that only reaches its own
    breakout later does not support a hypothesis evaluated before that."""
    source = instance(
        PatternType.DOUBLE_TOP,
        [S.BREAKOUT_PENDING_CONFIRMATION, S.CONFIRMED_UP],
        anchor_count=3,
        direction=BreakoutDirection.UP,
    )
    late_supporter = instance(
        PatternType.TRIPLE_TOP,
        [S.GEOMETRICALLY_VALID, S.GEOMETRICALLY_VALID, S.CONFIRMED_UP],
        anchor_count=5,
        direction=BreakoutDirection.UP,
    )
    built = hypothesis_for(source, pool=[late_supporter])
    assert built is not None
    first, second = built.evaluations
    assert first.supporting_patterns == ()  # not confirmed yet at that instant
    # By the source's second evaluation, does the supporter's confirmation predate it?
    supporter_confirmed_at = late_supporter.evaluations[-1].evaluated_at
    if supporter_confirmed_at <= second.evaluated_at:
        assert late_supporter.pattern_instance_id in {
            p.pattern_instance_id for p in second.supporting_patterns
        }


def test_a_window_covered_by_overlap_is_not_evidence() -> None:
    early = T0 - STEP * 200
    covered = instance(
        PatternType.DIAMOND,
        [S.CONFIRMED_UP],
        anchor_count=6,
        direction=BreakoutDirection.UP,
        start=early,
    )
    held = replace(
        covered.evaluations[0],
        evidence=(
            *covered.evaluations[0].evidence,
            evidence("DIAMOND_TIMING", "held by a larger diamond", held_by_overlap=True),
        ),
    )
    covered_instance = replace(covered, evaluations=(held,))

    source = instance(
        PatternType.DOUBLE_TOP, [S.CONFIRMED_UP], anchor_count=3, direction=BreakoutDirection.UP
    )
    built = hypothesis_for(source, pool=[covered_instance])
    assert built is not None
    assert built.latest.supporting_patterns == ()


# -- cierre y no reescritura: secciones 2 y 6 ------------------------------------------------------


def test_a_failed_breakout_closes_the_hypothesis_with_unknown_direction() -> None:
    source = instance(
        PatternType.DOUBLE_TOP,
        [S.BREAKOUT_PENDING_CONFIRMATION, S.FAILED_BREAKOUT],
        anchor_count=3,
        direction=BreakoutDirection.DOWN,
    )
    built = hypothesis_for(source)
    assert built is not None
    assert built.is_terminal
    assert built.latest.hypothesis_direction is HypothesisDirection.UNKNOWN


def test_an_invalidation_after_confirmation_closes_the_hypothesis_too() -> None:
    source = instance(PatternType.DOUBLE_TOP, [S.CONFIRMED_UP], anchor_count=3)
    closing = evaluation(S.INVALIDATED, source.evaluations[0].anchors, step=1)
    closing = PatternEvaluation(
        evaluated_at=closing.evaluated_at,
        as_of=closing.as_of,
        candle_count=closing.candle_count,
        state=S.INVALIDATED,
        anchors=source.evaluations[0].anchors,
        invalidation_reasons=(InvalidationReason.SUPERSEDED,),
        evidence=source.evaluations[0].evidence,
    )
    source = source.advance(closing)
    built = hypothesis_for(source)
    assert built is not None
    assert built.is_terminal
    assert built.latest.hypothesis_direction is HypothesisDirection.UNKNOWN
    # Kind, compatibility and operability are carried forward: they are not re-derived from
    # nothing just because the closing evaluation itself carries no fresh breakout.
    assert built.evaluations[-2].hypothesis_kind == built.latest.hypothesis_kind


def test_nothing_follows_a_closed_hypothesis() -> None:
    source = instance(
        PatternType.DOUBLE_TOP,
        [S.BREAKOUT_PENDING_CONFIRMATION, S.FAILED_BREAKOUT],
        anchor_count=3,
    )
    built = hypothesis_for(source)
    assert built is not None
    later = replace(built.latest, evaluated_at=built.latest.evaluated_at + STEP)
    with pytest.raises(InvalidHypothesisError, match="UNKNOWN closes"):
        built.advance(later)


# -- identidad y replay: secciones 6, 9 ----------------------------------------------------------


def test_identity_is_derived_from_the_source_alone() -> None:
    source = instance(PatternType.DOUBLE_TOP, [S.CONFIRMED_UP], anchor_count=3)
    built = hypothesis_for(source)
    assert built is not None
    assert built.pattern_hypothesis_id == derive_pattern_hypothesis_id(source.pattern_instance_id)
    again = hypothesis_for(source)
    assert again is not None
    assert again.pattern_hypothesis_id == built.pattern_hypothesis_id


def test_replay_is_stable_a_prefix_of_the_series_gives_the_same_early_evaluations() -> None:
    """Section 6: what a hypothesis said at an instant does not change when later data (of the
    source or of the pool) is added."""
    source = instance(
        PatternType.DOUBLE_TOP,
        [S.BREAKOUT_PENDING_CONFIRMATION, S.CONFIRMED_UP],
        anchor_count=3,
        direction=BreakoutDirection.UP,
    )
    supporter_full = instance(
        PatternType.TRIPLE_TOP, [S.CONFIRMED_UP], anchor_count=5, direction=BreakoutDirection.UP
    )
    full = hypothesis_for(source, pool=[supporter_full])
    assert full is not None

    prefix_source = PatternInstance(
        source.pattern_type,
        source.instrument_id,
        source.data_source,
        source.timeframe,
        source.detector_version,
        source.parameter_version,
        source.evaluations[:1],
    )
    prefix = hypothesis_for(prefix_source, pool=[])
    assert prefix is not None
    assert prefix.latest == full.evaluations[0]


def test_a_hypothesis_never_carries_a_probability_or_a_score() -> None:
    source = instance(PatternType.DOUBLE_TOP, [S.CONFIRMED_UP], anchor_count=3)
    built = hypothesis_for(source)
    assert built is not None
    names = {f.name for f in dataclasses.fields(built.latest)}
    assert not any("probability" in name or "score" in name for name in names)
