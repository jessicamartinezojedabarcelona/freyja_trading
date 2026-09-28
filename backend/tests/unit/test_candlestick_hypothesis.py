"""POINT4-HYPOTHESIS-001: candle pattern hypothesis, descriptive only, never a prediction.

The three scenarios Jessica required before this could be considered done (contract, section 8):
an `AmbiguousGeometry` never counting as evidence, overlapping patterns both counted correctly, and
contradictory evidence staying visible instead of being netted away. Plus the two structural
guarantees that make "CONFIRMED is not a prediction" true by construction, not by convention: no
`RETROSPECTIVE`/`UNPROVEN` evidence can ever produce `OPERABLE`, and no evaluation carries anything
resembling an affirmed next-candle direction.
"""

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from freyja_backend.domain.candlestick_hypothesis import (
    HYPOTHESIS_MODEL_VERSION,
    CandleHypothesis,
    CandleHypothesisEvaluation,
    RelatedCandlePattern,
    derive_candle_hypothesis_id,
    hypothesis_for,
)
from freyja_backend.domain.candlestick_location import (
    LocationEvaluation,
    LocationState,
    PatternLocation,
)
from freyja_backend.domain.candlestick_pattern import (
    CANDLE_PATTERN_CATALOGUE,
    CandleAnchor,
    CandleBias,
    CandlePatternEvaluation,
    CandlePatternInstance,
    CandlePatternState,
    CandlePatternType,
    InvalidationReason,
    start_candle_pattern_instance,
)
from freyja_backend.domain.candlestick_single import AmbiguousGeometry, SharedGeometry
from freyja_backend.domain.chart_pattern import PatternEvidence, evidence
from freyja_backend.domain.market_data import Timeframe
from freyja_backend.domain.market_trend import TrendState
from freyja_backend.domain.pattern_detection import InvalidDetectionRequestError
from freyja_backend.domain.pattern_hypothesis import Operability, TargetScope

TF = Timeframe.M5
STEP = TF.duration
SOURCE = "BINANCE"
INSTRUMENT = "instrument-1"
T0 = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)


# -- building fixtures ------------------------------------------------------------------------


def _context_evidence() -> PatternEvidence:
    return evidence("CONTEXT", "no context required", required="NONE", compatible=True)


def confirmed_pattern(
    pattern_type: CandlePatternType, first_open: datetime, price: str = "110"
) -> CandlePatternInstance:
    """A minimal, hand-built CONFIRMED instance with exactly the candle count its catalogue entry
    needs. Real detection is already covered elsewhere (test_candlestick_single/multi.py); this
    tests only the aggregator's own consumption of a confirmed instance."""
    needed = CANDLE_PATTERN_CATALOGUE[pattern_type].candle_count
    p = Decimal(price)
    anchors = tuple(
        CandleAnchor(
            first_open + STEP * i,
            first_open + STEP * (i + 1),
            p,
            p + Decimal("1"),
            p - Decimal("1"),
            p,
            f"ANCHOR_{i}",
        )
        for i in range(needed)
    )
    evaluated_at = anchors[-1].close_time
    ev = CandlePatternEvaluation(
        evaluated_at,
        evaluated_at,
        CandlePatternState.CONFIRMED,
        anchors,
        evidence=(_context_evidence(),),
    )
    return start_candle_pattern_instance(
        pattern_type=pattern_type,
        instrument_id=INSTRUMENT,
        data_source=SOURCE,
        timeframe=TF,
        detector_version="test-fixture-v1",
        parameter_version="test-fixture-v1",
        first_evaluation=ev,
    )


def location_with(
    source_id: uuid.UUID, at: datetime, state: LocationState, operability: Operability
) -> PatternLocation:
    """A minimal, hand-built `PatternLocation` for `source_id` — direct construction, same style
    as `test_candlestick_location.py`'s own validation tests, no need to re-run the full pipeline
    (`evaluate_location`) just to get a specific `state`/`operability` combination."""
    if state is LocationState.NEAR_LEVEL:
        items = (
            evidence(
                "LEVEL",
                "HIGH pivot at 110, 0.10 away",
                kind="PIVOT",
                label="HIGH pivot",
                price=Decimal("110"),
                distance_fraction=Decimal("0.10"),
                source_known_at=at.isoformat(),
                source_operability=operability.value,
            ),
        )
    else:
        items = (evidence("LEVELS_CHECKED", "0 checked", levels_checked=0),)
    ev = LocationEvaluation(at, at, state, at, operability, evidence=items)
    return PatternLocation(source_id, (ev,))


# -- required scenario: an ambiguous geometry never counts as evidence --------------------------


def test_an_ambiguous_geometry_cannot_be_used_as_evidence_even_by_mistake() -> None:
    """`AmbiguousGeometry` (`candlestick_single.py`) deliberately has no
    `candle_pattern_instance_id` or `evaluations` — the exact fields `hypothesis_for`'s pool scan
    reads. A caller that, by mistake, fed one into `pool` (instead of a real
    `CandlePatternInstance`) gets a loud failure, never a silent "it just doesn't count": it
    structurally cannot be read as one."""
    ambiguous = AmbiguousGeometry(
        SharedGeometry.HAMMER_OR_HANGING_MAN,
        INSTRUMENT,
        SOURCE,
        TF,
        CandleAnchor(
            T0, T0 + STEP, Decimal("110"), Decimal("111"), Decimal("109"), Decimal("110"), "FIRST"
        ),
        T0 + STEP,
        TrendState.RANGE,
        "test-fixture-v1",
        "test-fixture-v1",
    )
    source = confirmed_pattern(CandlePatternType.BULLISH_ENGULFING, T0 + STEP * 10)
    with pytest.raises(AttributeError):
        hypothesis_for(source, pool=[ambiguous])  # type: ignore[list-item]


def test_an_ambiguous_geometry_elsewhere_never_changes_the_result() -> None:
    """The same hypothesis, computed with only real confirmed instances in `pool`, is identical
    whether or not an `AmbiguousGeometry` also exists in the caller's own data — because nothing
    here ever reaches for it (it is not even a parameter of `hypothesis_for`)."""
    supporting = confirmed_pattern(CandlePatternType.PIERCING_PATTERN, T0)
    source = confirmed_pattern(CandlePatternType.BULLISH_ENGULFING, T0 + STEP * 10)
    without_ambiguous = hypothesis_for(source, pool=[supporting])

    AmbiguousGeometry(
        SharedGeometry.HAMMER_OR_HANGING_MAN,
        INSTRUMENT,
        SOURCE,
        TF,
        CandleAnchor(
            T0 + STEP * 20,
            T0 + STEP * 21,
            Decimal("110"),
            Decimal("111"),
            Decimal("109"),
            Decimal("110"),
            "FIRST",
        ),
        T0 + STEP * 21,
        TrendState.RANGE,
        "test-fixture-v1",
        "test-fixture-v1",
    )  # exists in scope, never passed anywhere
    with_ambiguous_present = hypothesis_for(source, pool=[supporting])

    assert without_ambiguous is not None and with_ambiguous_present is not None
    assert without_ambiguous.evaluations == with_ambiguous_present.evaluations
    assert without_ambiguous.latest.supporting_candles != ()  # a real result, not a vacuous match


# -- required scenario: overlapping patterns -----------------------------------------------------


def test_overlapping_patterns_are_both_counted_as_coexisting_evidence() -> None:
    """A `PIERCING_PATTERN` on candles [X, A] and a `BULLISH_ENGULFING` on candles [A, B] share
    candle A. Sharing an anchor is not a reason to exclude either from the pool (contract, section
    5): the source detector already resolved any real geometric conflict before either instance
    existed. `overlapping` resolves at or before `source`'s own instant, so it is genuinely known
    by then — no look-ahead."""
    overlapping = confirmed_pattern(CandlePatternType.PIERCING_PATTERN, T0 - STEP)
    source = confirmed_pattern(CandlePatternType.BULLISH_ENGULFING, T0)
    assert overlapping.latest.evaluated_at <= source.latest.evaluated_at

    hyp = hypothesis_for(source, pool=[overlapping])
    assert hyp is not None
    supporting_ids = {r.candle_pattern_instance_id for r in hyp.latest.supporting_candles}
    assert overlapping.candle_pattern_instance_id in supporting_ids  # both BULLISH


# -- required scenario: contradictory evidence stays visible -------------------------------------


def test_contradictory_evidence_remains_visible_never_silently_resolved() -> None:
    supporting = confirmed_pattern(CandlePatternType.PIERCING_PATTERN, T0)
    conflicting = confirmed_pattern(CandlePatternType.BEARISH_ENGULFING, T0 + STEP * 10)
    source = confirmed_pattern(CandlePatternType.BULLISH_ENGULFING, T0 + STEP * 30)

    hyp = hypothesis_for(source, pool=[supporting, conflicting])
    assert hyp is not None
    assert len(hyp.latest.supporting_candles) == 1
    assert len(hyp.latest.conflicting_candles) == 1
    assert hyp.latest.supporting_candles[0].candle_pattern_instance_id == (
        supporting.candle_pattern_instance_id
    )
    assert hyp.latest.conflicting_candles[0].candle_pattern_instance_id == (
        conflicting.candle_pattern_instance_id
    )


def test_context_dependent_patterns_are_never_compared_only_observed() -> None:
    """HAMMER/HANGING_MAN (CandleBias.CONTEXT_DEPENDENT) are CONFIRMED — their required context was
    met — but deriving an "effective" bias for them is a new inference this task does not make
    (contract, section 5). A confirmed HAMMER in the pool never enters supporting nor conflicting,
    even next to a fixed-bias source."""
    context_dependent = confirmed_pattern(CandlePatternType.HAMMER, T0)
    source = confirmed_pattern(CandlePatternType.BULLISH_ENGULFING, T0 + STEP * 10)

    hyp = hypothesis_for(source, pool=[context_dependent])
    assert hyp is not None
    assert hyp.latest.supporting_candles == ()
    assert hyp.latest.conflicting_candles == ()


# -- required guarantee: no RETROSPECTIVE/UNPROVEN evidence ever enables OPERABLE ----------------


def test_no_evidence_ever_makes_a_v1_hypothesis_operable() -> None:
    """candlestick_single.py/multi.py never prove a candle pattern was knowable live (no
    `received_at` concept there — contract, section 4): this layer's own tier is always UNPROVEN,
    so nothing it produces in v1 can ever be OPERABLE, however clean its location evidence is."""
    source = confirmed_pattern(CandlePatternType.BULLISH_ENGULFING, T0)
    location = location_with(
        source.candle_pattern_instance_id,
        T0 + STEP * 2,
        LocationState.NEAR_LEVEL,
        Operability.OPERABLE,
    )

    hyp = hypothesis_for(source, location=location)
    assert hyp is not None
    assert hyp.latest.operability is Operability.UNPROVEN  # never promoted by a clean location


def test_a_retrospective_location_is_reflected_not_hidden() -> None:
    source = confirmed_pattern(CandlePatternType.BULLISH_ENGULFING, T0)
    location = location_with(
        source.candle_pattern_instance_id,
        T0 + STEP * 2,
        LocationState.NEAR_LEVEL,
        Operability.RETROSPECTIVE,
    )
    hyp = hypothesis_for(source, location=location)
    assert hyp is not None
    location_evidence = next(item for item in hyp.latest.evidence if item.code == "LOCATION")
    assert dict(location_evidence.facts)["operability"] == "RETROSPECTIVE"
    assert hyp.latest.operability is Operability.UNPROVEN  # worst of UNPROVEN and RETROSPECTIVE


# -- required guarantee: CONFIRMED is not a prediction -------------------------------------------


def test_confirmed_carries_no_affirmed_direction_only_market_direction_scope() -> None:
    """No field on `CandleHypothesisEvaluation` resembles an affirmed UP/DOWN reading of what
    comes next; `target_scope` is always `MARKET_DIRECTION`, never `NEXT_CANDLE`/`MULTI_CANDLE_MOVE`
    (contract, section 2 bis)."""
    source = confirmed_pattern(CandlePatternType.BULLISH_ENGULFING, T0)
    hyp = hypothesis_for(source)
    assert hyp is not None
    assert hyp.latest.target_scope is TargetScope.MARKET_DIRECTION
    field_names = set(CandleHypothesisEvaluation.__dataclass_fields__)
    assert "hypothesis_direction" not in field_names
    assert "direction" not in field_names


def test_target_scope_other_than_market_direction_is_refused() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="MARKET_DIRECTION"):
        CandleHypothesisEvaluation(
            T0,
            T0,
            TargetScope.NEXT_CANDLE,
            False,
            (),
            (),
            (
                evidence(
                    "HYPOTHESIS_SOURCE",
                    "CONFIRMED",
                    source_state="CONFIRMED",
                    traditional_bias="BULLISH",
                    own_availability_operability="UNPROVEN",
                ),
            ),
            Operability.UNPROVEN,
        )


# -- lifecycle: no CONFIRMED, no hypothesis; INVALIDATED closes it -------------------------------


def test_a_pattern_that_never_confirms_has_no_hypothesis() -> None:
    p = Decimal("110")
    anchor = CandleAnchor(T0, T0 + STEP, p, p + Decimal("1"), p - Decimal("1"), p, "FIRST")
    ev = CandlePatternEvaluation(
        T0 + STEP, T0 + STEP, CandlePatternState.MORPHOLOGICALLY_VALID, (anchor,)
    )
    source = start_candle_pattern_instance(
        pattern_type=CandlePatternType.DOJI,
        instrument_id=INSTRUMENT,
        data_source=SOURCE,
        timeframe=TF,
        detector_version="test-fixture-v1",
        parameter_version="test-fixture-v1",
        first_evaluation=ev,
    )
    assert hypothesis_for(source) is None


def test_invalidation_closes_the_hypothesis_nothing_follows() -> None:
    source = confirmed_pattern(CandlePatternType.BULLISH_ENGULFING, T0)
    invalidated_ev = CandlePatternEvaluation(
        source.latest.evaluated_at + STEP,
        source.latest.evaluated_at + STEP,
        CandlePatternState.INVALIDATED,
        source.latest.anchors,
        invalidation_reasons=(InvalidationReason.GEOMETRY_BROKEN,),
    )
    source = source.advance(invalidated_ev)
    hyp = hypothesis_for(source)
    assert hyp is not None
    assert hyp.latest.is_final is True
    later = replace(hyp.latest, evaluated_at=hyp.latest.evaluated_at + STEP, is_final=False)
    with pytest.raises(InvalidDetectionRequestError, match="nothing follows"):
        CandleHypothesis(
            source.candle_pattern_instance_id,
            (*hyp.evaluations, later),
        )


# -- identity and structural validation -----------------------------------------------------------


def test_identity_is_derived_from_source_and_version() -> None:
    source = confirmed_pattern(CandlePatternType.BULLISH_ENGULFING, T0)
    hyp = hypothesis_for(source)
    assert hyp is not None
    assert hyp.candle_hypothesis_id == derive_candle_hypothesis_id(
        source.candle_pattern_instance_id, HYPOTHESIS_MODEL_VERSION
    )


def test_a_related_pattern_cannot_both_support_and_conflict() -> None:
    shared_id = uuid.uuid4()
    related = RelatedCandlePattern(
        shared_id, "PIERCING_PATTERN", CandleBias.BULLISH, Operability.UNPROVEN
    )
    with pytest.raises(InvalidDetectionRequestError, match="both support and conflict"):
        CandleHypothesisEvaluation(
            T0,
            T0,
            TargetScope.MARKET_DIRECTION,
            False,
            (related,),
            (related,),
            (
                evidence(
                    "HYPOTHESIS_SOURCE",
                    "CONFIRMED",
                    source_state="CONFIRMED",
                    traditional_bias="BULLISH",
                    own_availability_operability="UNPROVEN",
                ),
            ),
            Operability.UNPROVEN,
        )


def test_a_related_pattern_with_context_dependent_bias_is_refused() -> None:
    with pytest.raises(InvalidDetectionRequestError, match="fixed"):
        RelatedCandlePattern(
            uuid.uuid4(), "HAMMER", CandleBias.CONTEXT_DEPENDENT, Operability.UNPROVEN
        )


def test_evaluations_must_move_strictly_forward() -> None:
    source = confirmed_pattern(CandlePatternType.BULLISH_ENGULFING, T0)
    hyp = hypothesis_for(source)
    assert hyp is not None
    with pytest.raises(InvalidDetectionRequestError, match="forward"):
        CandleHypothesis(source.candle_pattern_instance_id, (hyp.latest, hyp.latest))
