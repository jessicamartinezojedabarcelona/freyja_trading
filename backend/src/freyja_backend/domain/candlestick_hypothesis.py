"""Candle pattern hypothesis: descriptive evidence, never a prediction (POINT4-HYPOTHESIS-001).

The contract lives in ``docs/domain/hipotesis-de-patron-de-vela.md``. A `CandleHypothesis` records
what a `CandlePatternInstance` (``candlestick_single.py``/``multi.py``) looked like once it reached
``CONFIRMED``: its own traditional bias (tradition, never evidence — ``candlestick_pattern.py``),
its location (``candlestick_location.py``, when available) and which other candle patterns of the
same series agree or disagree with it. It never says the next candle, or any candle, will move a
certain way: ``CONFIRMED`` means the morphology and its required context matched the catalogue, not
that a prediction came true (contract, section 1).

Deliberately its own record, not `pattern_hypothesis.PatternHypothesis`: a candle pattern has no
breakout to trigger on (``HypothesisDirection``'s closing semantics and its real-breakout-derived
direction do not describe this domain — contract, section 2 bis). What *is* reused, literally, not
reinvented: `Operability`/`worst_operability` (``pattern_hypothesis.py``/
``candlestick_location.py``), `PatternEvidence`/``evidence()`` (``chart_pattern.py``), and the same
append-only, replay-stable record shape `PatternLocation`/`PatternHypothesis` already established.

Pure and free of I/O: no database, no clock, no provider.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise

from freyja_backend.domain.candlestick_location import (
    LocationEvaluation,
    PatternLocation,
    worst_operability,
)
from freyja_backend.domain.candlestick_pattern import (
    CandleBias,
    CandlePatternEvaluation,
    CandlePatternInstance,
    CandlePatternState,
)
from freyja_backend.domain.chart_pattern import PatternEvidence, evidence
from freyja_backend.domain.market_data import _require_utc
from freyja_backend.domain.pattern_detection import InvalidDetectionRequestError
from freyja_backend.domain.pattern_hypothesis import Operability, TargetScope

# Bump on ANY change to what an evaluation contains, how it is derived or how it may evolve.
HYPOTHESIS_MODEL_VERSION = "candle-hypothesis-v1"

_NAMESPACE = uuid.UUID("7c5e9a3f-2d8b-4c16-9e0a-3f7b5d1c8a62")

_TRIGGER_STATES = frozenset({CandlePatternState.CONFIRMED})
_CLOSING_STATES = frozenset({CandlePatternState.INVALIDATED})

# A candle pattern has a comparable reading only when the catalogue fixes it (BULLISH/BEARISH).
# CONTEXT_DEPENDENT patterns (HAMMER/HANGING_MAN...) are CONFIRMED — their context requirement was
# already met — but deriving an "effective" bias from which trend each one demanded would be a new
# inference this task does not make (contract, section 5, "decisión de alcance v1"): they are
# recorded as evidence when they are the source, never compared against other patterns.
_FIXED_BIAS = frozenset({CandleBias.BULLISH, CandleBias.BEARISH})

# candlestick_single.py/multi.py set a pattern's own `evaluated_at` to its last anchor's market
# close time, never to when Freyja actually received that candle (no such concept exists there —
# localizacion-de-patron-de-vela.md, section 2 bis, documented limitation). Without a way to prove
# a candle pattern was knowable live, this layer's own tier can never be better than UNPROVEN: not
# a special case, the honest consequence of what the model beneath it can and cannot prove today.
_CANDLE_OWN_OPERABILITY = Operability.UNPROVEN


@dataclass(frozen=True, slots=True)
class RelatedCandlePattern:
    """Another candle pattern's own fixed-bias reading, as evidence for or against a hypothesis,
    with its own operability kept apart (never changes the hypothesis's own, contract section 5)."""

    candle_pattern_instance_id: uuid.UUID
    pattern_type: str
    bias: CandleBias
    operability: Operability

    def __post_init__(self) -> None:
        if self.bias not in _FIXED_BIAS:
            raise InvalidDetectionRequestError(
                "a related candle pattern's bias must be fixed (BULLISH/BEARISH) to be comparable"
            )


@dataclass(frozen=True, slots=True)
class CandleHypothesisEvaluation:
    """What the hypothesis said at one instant. Autosufficient: it names the source's own state
    (``HYPOTHESIS_SOURCE`` evidence) and every supporting/conflicting pattern, so nothing has to be
    looked up later to understand it."""

    evaluated_at: datetime
    as_of: datetime | None
    target_scope: TargetScope
    # True only for the source's own closing evaluation (INVALIDATED): nothing follows it.
    is_final: bool
    supporting_candles: tuple[RelatedCandlePattern, ...]
    conflicting_candles: tuple[RelatedCandlePattern, ...]
    evidence: tuple[PatternEvidence, ...]
    operability: Operability
    definition_version: str = HYPOTHESIS_MODEL_VERSION

    def __post_init__(self) -> None:
        _require_utc(self.evaluated_at, "evaluated_at")
        if self.as_of is not None:
            _require_utc(self.as_of, "as_of")
            if self.as_of > self.evaluated_at:
                raise InvalidDetectionRequestError(
                    "a candle that closes after the evaluation was read"
                )
        if self.target_scope is not TargetScope.MARKET_DIRECTION:
            raise InvalidDetectionRequestError(
                "target_scope is always MARKET_DIRECTION until a StrategySpec asks otherwise "
                "(contract, section 2 bis): NEXT_CANDLE/MULTI_CANDLE_MOVE stay reserved"
            )
        if not any(item.code == "HYPOTHESIS_SOURCE" for item in self.evidence):
            raise InvalidDetectionRequestError(
                "a candle hypothesis evaluation names its source's own state"
            )
        for group in (self.supporting_candles, self.conflicting_candles):
            ids = [related.candle_pattern_instance_id for related in group]
            if len(set(ids)) != len(ids):
                raise InvalidDetectionRequestError(
                    "a related candle pattern is listed at most once"
                )
        overlap = {r.candle_pattern_instance_id for r in self.supporting_candles} & {
            r.candle_pattern_instance_id for r in self.conflicting_candles
        }
        if overlap:
            raise InvalidDetectionRequestError(
                "a related candle pattern cannot both support and conflict at the same instant"
            )
        own_tier: Operability | None = None
        location_tier: Operability | None = None
        for item in self.evidence:
            facts = dict(item.facts)
            if item.code == "HYPOTHESIS_SOURCE":
                own_tier = Operability(str(facts["own_availability_operability"]))
            elif item.code == "LOCATION":
                location_tier = Operability(str(facts["operability"]))
        expected_inputs = ([own_tier] if own_tier is not None else []) + (
            [location_tier] if location_tier is not None else []
        )
        if self.operability is not worst_operability(expected_inputs):
            raise InvalidDetectionRequestError(
                "operability must be the worst of the source's own tier and its location's tier "
                "— never optimistic about what the evidence itself proves"
            )


def derive_candle_hypothesis_id(
    source_candle_pattern_instance_id: uuid.UUID,
    definition_version: str = HYPOTHESIS_MODEL_VERSION,
) -> uuid.UUID:
    """The identity of a hypothesis: its origin and the version that derived it. The same origin
    always produces the same hypothesis, evolving without ever changing identity."""
    key = f"{definition_version}|{source_candle_pattern_instance_id}"
    return uuid.uuid5(_NAMESPACE, key)


@dataclass(frozen=True, slots=True)
class CandleHypothesis:
    """One candle pattern's append-only history of hypothesis evaluations."""

    source_candle_pattern_instance_id: uuid.UUID
    evaluations: tuple[CandleHypothesisEvaluation, ...]
    definition_version: str = HYPOTHESIS_MODEL_VERSION

    def __post_init__(self) -> None:
        if not self.evaluations:
            raise InvalidDetectionRequestError("a candle hypothesis is born from an evaluation")
        for earlier, later in pairwise(self.evaluations):
            if later.evaluated_at <= earlier.evaluated_at:
                raise InvalidDetectionRequestError("evaluations move strictly forward in time")
        for earlier in self.evaluations[:-1]:
            if earlier.is_final:
                raise InvalidDetectionRequestError("a final evaluation closes it: nothing follows")

    @property
    def candle_hypothesis_id(self) -> uuid.UUID:
        return derive_candle_hypothesis_id(
            self.source_candle_pattern_instance_id, self.definition_version
        )

    @property
    def latest(self) -> CandleHypothesisEvaluation:
        return self.evaluations[-1]

    def advance(self, evaluation: CandleHypothesisEvaluation) -> "CandleHypothesis":
        """The same hypothesis one evaluation later. Earlier evaluations are untouched."""
        return CandleHypothesis(
            self.source_candle_pattern_instance_id,
            (*self.evaluations, evaluation),
            self.definition_version,
        )


# -- deriving a hypothesis from a source instance, its coexisting pool and its location ----------


def _pattern_as_of(instance: CandlePatternInstance, at: datetime) -> CandlePatternEvaluation | None:
    """The instance's own latest evaluation known at or before `at`, or `None` if it did not yet
    exist: never a future one (no look-ahead)."""
    known = [e for e in instance.evaluations if e.evaluated_at <= at]
    return known[-1] if known else None


def _location_as_of(location: PatternLocation, at: datetime) -> LocationEvaluation | None:
    known = [e for e in location.evaluations if e.evaluated_at <= at]
    return known[-1] if known else None


def _related_candles(
    source_bias: CandleBias, at: datetime, pool: Sequence[CandlePatternInstance]
) -> tuple[tuple[RelatedCandlePattern, ...], tuple[RelatedCandlePattern, ...]]:
    if source_bias not in _FIXED_BIAS:
        return (), ()
    supporting: list[RelatedCandlePattern] = []
    conflicting: list[RelatedCandlePattern] = []
    for other in sorted(pool, key=lambda i: str(i.candle_pattern_instance_id)):
        seen = _pattern_as_of(other, at)
        if seen is None or seen.state is not CandlePatternState.CONFIRMED:
            continue
        bias = other.traditional_bias
        if bias not in _FIXED_BIAS:
            continue
        related = RelatedCandlePattern(
            other.candle_pattern_instance_id,
            other.pattern_type.value,
            bias,
            _CANDLE_OWN_OPERABILITY,
        )
        (supporting if bias is source_bias else conflicting).append(related)
    return tuple(supporting), tuple(conflicting)


def _source_evidence(evaluation: CandlePatternEvaluation, bias: CandleBias) -> PatternEvidence:
    return evidence(
        "HYPOTHESIS_SOURCE",
        f"{evaluation.state.value} pattern, traditional bias {bias.value}",
        source_state=evaluation.state.value,
        traditional_bias=bias.value,
        own_availability_operability=_CANDLE_OWN_OPERABILITY.value,
    )


def _location_evidence(location_eval: LocationEvaluation) -> PatternEvidence:
    return evidence(
        "LOCATION",
        f"{location_eval.state.value} as of {location_eval.evaluated_at.isoformat()}",
        state=location_eval.state.value,
        evaluated_at=location_eval.evaluated_at.isoformat(),
        operability=location_eval.operability.value,
    )


def _build(
    source: CandlePatternInstance,
    current: CandlePatternEvaluation,
    pool: Sequence[CandlePatternInstance],
    location: PatternLocation | None,
) -> CandleHypothesisEvaluation:
    is_final = current.state in _CLOSING_STATES
    supporting, conflicting = (
        ((), ())
        if is_final
        else _related_candles(source.traditional_bias, current.evaluated_at, pool)
    )
    items = [_source_evidence(current, source.traditional_bias)]
    operability_inputs = [_CANDLE_OWN_OPERABILITY]
    if location is not None:
        location_eval = _location_as_of(location, current.evaluated_at)
        if location_eval is not None:
            items.append(_location_evidence(location_eval))
            operability_inputs.append(location_eval.operability)
    operability = worst_operability(operability_inputs)
    return CandleHypothesisEvaluation(
        current.evaluated_at,
        current.as_of,
        TargetScope.MARKET_DIRECTION,
        is_final,
        supporting,
        conflicting,
        tuple(items),
        operability,
    )


def _same_content(before: CandleHypothesisEvaluation, after: CandleHypothesisEvaluation) -> bool:
    return (
        before.is_final == after.is_final
        and before.supporting_candles == after.supporting_candles
        and before.conflicting_candles == after.conflicting_candles
        and before.operability is after.operability
        and before.evidence == after.evidence
    )


def hypothesis_for(
    source: CandlePatternInstance,
    pool: Sequence[CandlePatternInstance] = (),
    location: PatternLocation | None = None,
) -> CandleHypothesis | None:
    """The hypothesis `source` produces, evolving through every instant its own evaluations reach
    `CONFIRMED` (contract, section 2). `pool` is every other instance of the *same* series
    (instrument, source, timeframe); it is filtered here, so passing every instance Freyja knows
    about, for every series, is safe and simplest for a caller. `location` (if given) must be
    `source`'s own `PatternLocation` (``candlestick_location.py``) — never another pattern's.

    `None` if `source` never reaches `CONFIRMED`: a pattern that stays `FORMING`,
    `MORPHOLOGICALLY_VALID`, `CONTEXT_VALID`, `PENDING_CONFIRMATION`, is invalidated first, or
    `FAILED` (three-candle patterns that never confirm) never had a hypothesis to give.
    """
    same_series = [
        other
        for other in pool
        if other.candle_pattern_instance_id != source.candle_pattern_instance_id
        and other.instrument_id == source.instrument_id
        and other.data_source == source.data_source
        and other.timeframe == source.timeframe
    ]
    first = next((i for i, e in enumerate(source.evaluations) if e.state in _TRIGGER_STATES), None)
    if first is None:
        return None

    evaluations: list[CandleHypothesisEvaluation] = []
    previous: CandleHypothesisEvaluation | None = None
    for current in source.evaluations[first:]:
        if current.state not in _TRIGGER_STATES and current.state not in _CLOSING_STATES:
            continue  # defensive: unreachable once CONFIRMED, per candlestick_pattern.py's _NEXT
        built = _build(source, current, same_series, location)
        if previous is None or not _same_content(previous, built):
            evaluations.append(built)
            previous = built
        if built.is_final:
            break  # closed: nothing follows
    if not evaluations:
        return None
    return CandleHypothesis(source.candle_pattern_instance_id, tuple(evaluations))
