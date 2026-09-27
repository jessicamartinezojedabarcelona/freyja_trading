"""POINT3-TEST-001: the integrated case PATTERN-PROVENANCE-001 and POINT3-HYPOTHESIS-001 leave
untested on their own — every other bullet of the task (per detector: positive/negative/forming/
confirmed/failed/invalidated, no look-ahead, exact tolerances, telling figures apart, prior trend,
provenance) already has its own tests in each ``test_pattern_*.py`` file and in
``test_pattern_hypothesis.py``; repeating them here would only duplicate, not validate anything new
(see the task's own Notion note). What is still untested is **several real detectors, on the same
real candle series, feeding one aggregator** — coexistence and hypotheses end to end, not in
isolation, still without look-ahead.
"""

from dataclasses import replace
from datetime import datetime

from freyja_backend.domain.chart_pattern import (
    PATTERN_CATALOGUE,
    PatternInstance,
    PatternState,
    PatternType,
)
from freyja_backend.domain.market_data import Candle
from freyja_backend.domain.pattern_broadening import BroadeningFormationDetector
from freyja_backend.domain.pattern_channel import (
    AscendingTriangleDetector,
    DescendingTriangleDetector,
    RectangleDetector,
    SymmetricalTriangleDetector,
)
from freyja_backend.domain.pattern_detection import PatternDetector, replay_detector
from freyja_backend.domain.pattern_double import DoubleBottomDetector, DoubleTopDetector
from freyja_backend.domain.pattern_flag import (
    BearFlagDetector,
    BearPennantDetector,
    BullFlagDetector,
    BullPennantDetector,
)
from freyja_backend.domain.pattern_head_shoulders import (
    HeadAndShouldersBottomDetector,
    HeadAndShouldersTopDetector,
)
from freyja_backend.domain.pattern_hypothesis import (
    HypothesisDirection,
    Operability,
    hypothesis_for,
)
from freyja_backend.domain.pattern_rounding import RoundingBottomDetector, RoundingTopDetector
from freyja_backend.domain.pattern_triple import TripleBottomDetector, TripleTopDetector
from freyja_backend.domain.pattern_wedge import FallingWedgeDetector, RisingWedgeDetector
from tests.unit.test_market_trend import zigzag
from tests.unit.test_pattern_detection import TRIPLE_TOP, context_for, the_one

S = PatternState

ALL_DETECTORS: dict[PatternType, PatternDetector] = {
    PatternType.DOUBLE_TOP: DoubleTopDetector(),
    PatternType.DOUBLE_BOTTOM: DoubleBottomDetector(),
    PatternType.TRIPLE_TOP: TripleTopDetector(),
    PatternType.TRIPLE_BOTTOM: TripleBottomDetector(),
    PatternType.HEAD_AND_SHOULDERS_TOP: HeadAndShouldersTopDetector(),
    PatternType.HEAD_AND_SHOULDERS_BOTTOM: HeadAndShouldersBottomDetector(),
    PatternType.ROUNDING_TOP: RoundingTopDetector(),
    PatternType.ROUNDING_BOTTOM: RoundingBottomDetector(),
    PatternType.RECTANGLE: RectangleDetector(),
    PatternType.ASCENDING_TRIANGLE: AscendingTriangleDetector(),
    PatternType.DESCENDING_TRIANGLE: DescendingTriangleDetector(),
    PatternType.SYMMETRICAL_TRIANGLE: SymmetricalTriangleDetector(),
    PatternType.BULL_FLAG: BullFlagDetector(),
    PatternType.BEAR_FLAG: BearFlagDetector(),
    PatternType.BULL_PENNANT: BullPennantDetector(),
    PatternType.BEAR_PENNANT: BearPennantDetector(),
    PatternType.RISING_WEDGE: RisingWedgeDetector(),
    PatternType.FALLING_WEDGE: FallingWedgeDetector(),
    PatternType.BROADENING_FORMATION: BroadeningFormationDetector(),
    # DIAMOND is deliberately absent: `DiamondDetector` needs `context.diamond`/`received_at`
    # wiring `context_for` here does not provide; its own coexistence and hypothesis behaviour
    # is exercised in `test_pattern_diamond.py` and `test_pattern_hypothesis.py`.
}


def test_every_catalogue_entry_but_the_diamond_has_a_registered_detector() -> None:
    """The twenty figures are covered across the whole suite (each `test_pattern_*.py` reaches
    every state for its own); this only checks nothing was left disconnected from the catalogue."""
    missing = set(PATTERN_CATALOGUE) - set(ALL_DETECTORS) - {PatternType.DIAMOND}
    assert missing == set(), f"no detector registered for {missing}"


def test_bidirectional_is_reserved_and_never_produced() -> None:
    """Decision recorded in `hipotesis-de-figura.md` section 2: v1 never emits a pre-breakout
    hypothesis, so `BIDIRECTIONAL` must never come out of `hypothesis_for` for any figure."""
    candles = zigzag(TRIPLE_TOP, tail_to=99)
    context = context_for(candles)
    instances = replay_detector(TripleTopDetector(), context, candles) + replay_detector(
        DoubleTopDetector(), context, candles
    )
    for source in instances:
        built = hypothesis_for(source, pool=instances)
        if built is None:
            continue
        for evaluation in built.evaluations:
            assert evaluation.hypothesis_direction is not HypothesisDirection.BIDIRECTIONAL


# -- coexistence end to end: two real detectors, one series, one aggregator ---------------------


def _built(
    received_at: dict[datetime, datetime] | None,
) -> tuple[
    list[Candle],
    tuple[PatternInstance, ...],
    tuple[PatternInstance, ...],
    tuple[PatternInstance, ...],
]:
    candles = zigzag(TRIPLE_TOP, tail_to=99)
    context = context_for(candles, received_at=received_at)
    triples = replay_detector(TripleTopDetector(), context, candles)
    doubles = replay_detector(DoubleTopDetector(), context, candles)
    return candles, tuple(triples) + tuple(doubles), triples, doubles


def test_two_coexisting_real_detectors_support_each_other_in_their_hypotheses() -> None:
    """The triple top and the double top(s) inside it (`test_pattern_detection.py`'s own
    coexistence fixture) all resolve `CONFIRMED_DOWN`: each one's hypothesis should find the
    others as `supporting_patterns`, never as neutral or conflicting, once each was itself known."""
    _, pool, triples, doubles = _built(received_at=None)
    triple = the_one(triples, compatible=True)
    double = the_one(doubles, compatible=True)
    assert triple.state is S.CONFIRMED_DOWN and double.state is S.CONFIRMED_DOWN

    triple_hyp = hypothesis_for(triple, pool=pool)
    double_hyp = hypothesis_for(double, pool=pool)
    assert triple_hyp is not None and double_hyp is not None
    assert triple_hyp.latest.hypothesis_direction is HypothesisDirection.DOWN
    assert double_hyp.latest.hypothesis_direction is HypothesisDirection.DOWN

    triple_related = {
        p.pattern_instance_id
        for p in (*triple_hyp.latest.supporting_patterns, *triple_hyp.latest.conflicting_patterns)
    }
    double_related = {
        p.pattern_instance_id
        for p in (*double_hyp.latest.supporting_patterns, *double_hyp.latest.conflicting_patterns)
    }
    # Whichever one resolves first cannot yet know about the other (no look-ahead); by the time
    # both exist, each one that knows of the other must place it as supporting, never conflicting.
    if double.pattern_instance_id in triple_related:
        assert double.pattern_instance_id in {
            p.pattern_instance_id for p in triple_hyp.latest.supporting_patterns
        }
    if triple.pattern_instance_id in double_related:
        assert triple.pattern_instance_id in {
            p.pattern_instance_id for p in double_hyp.latest.supporting_patterns
        }
    # At least one direction of support was actually observed: the coexistence is not vacuous.
    assert (double.pattern_instance_id in triple_related) or (
        triple.pattern_instance_id in double_related
    )


def test_without_receipts_the_coexisting_hypotheses_stay_unproven() -> None:
    _, pool, triples, _doubles = _built(received_at=None)
    triple_hyp = hypothesis_for(the_one(triples, compatible=True), pool=pool)
    assert triple_hyp is not None
    assert triple_hyp.latest.operability is Operability.UNPROVEN


def test_with_full_receipts_a_coexisting_hypothesis_can_be_operable() -> None:
    candles = zigzag(TRIPLE_TOP, tail_to=99)
    received_at = {c.open_time: c.close_time for c in candles}
    _, pool, triples, _doubles = _built(received_at=received_at)
    triple_hyp = hypothesis_for(the_one(triples, compatible=True), pool=pool)
    assert triple_hyp is not None
    assert triple_hyp.latest.operability in (Operability.OPERABLE, Operability.RETROSPECTIVE)


def test_the_coexisting_hypotheses_are_replay_stable() -> None:
    """No look-ahead in the aggregation itself: what a hypothesis said at an instant does not
    depend on candles the series had not reached yet, real detectors and coexistence included."""
    candles = zigzag(TRIPLE_TOP, tail_to=99)
    received_at_full = {c.open_time: c.close_time for c in candles}
    context = context_for(candles, received_at=received_at_full)
    triples = replay_detector(TripleTopDetector(), context, candles)
    doubles = replay_detector(DoubleTopDetector(), context, candles)
    pool = tuple(triples) + tuple(doubles)
    triple = the_one(triples, compatible=True)
    full = hypothesis_for(triple, pool=pool)
    assert full is not None

    cutoff = full.evaluations[0].evaluated_at  # the instant the hypothesis itself was first born
    early_pool = tuple(
        replace(
            instance, evaluations=tuple(e for e in instance.evaluations if e.evaluated_at <= cutoff)
        )
        for instance in pool
        if instance.evaluations[0].evaluated_at <= cutoff
    )
    early_triple = replace(
        triple, evaluations=tuple(e for e in triple.evaluations if e.evaluated_at <= cutoff)
    )
    early = hypothesis_for(early_triple, pool=early_pool)
    assert early is not None
    assert early.latest == full.evaluations[0]
