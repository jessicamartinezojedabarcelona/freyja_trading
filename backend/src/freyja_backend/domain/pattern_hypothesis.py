"""Pattern hypothesis: combining coexisting figures as evidence (POINT3-HYPOTHESIS-001).

The contract lives in ``docs/domain/hipotesis-de-figura.md``. A hypothesis is a **verifiable
directional claim** derived from one source ``PatternInstance``, together with which other
figures of the same series support it, contradict it, or stay neutral. Like ``PatternInstance``
it is a record: immutable values, append-only history, autosufficient evaluations.

It generates no signal, no order, no probability. Its own operability
(``OPERABLE``/``RETROSPECTIVE``/``UNPROVEN``) depends solely on the provenance of its source's
breakout, read from the timing evidence ``PATTERN-PROVENANCE-001`` already attaches to every
figure (``BREAKOUT_TIMING``/``DIAMOND_TIMING``) — never recomputed here, and never trusted as
``LIVE``/operable unless that evidence actually proves ``known_at`` (section 4.3 of the contract).

**Known v1 limitation** (undocumented in the contract, disclosed here): a hypothesis gains a new
evaluation only when its *source* instance advances. A change in the pool of coexisting figures
that happens between two of the source's own evaluations is folded into the *next* source
evaluation, not given one of its own the instant it happens. This is still look-ahead free (each
evaluation only reads pool instances as of its own instant), just coarser than theoretically
possible; a future version may re-evaluate on every pool change too.

Pure and free of I/O: no database, no clock, no provider.
"""

import enum
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from freyja_backend.domain.chart_pattern import (
    BreakoutDirection,
    EvidenceValue,
    PatternEvaluation,
    PatternEvidence,
    PatternInstance,
    PatternRole,
    PatternState,
    evidence,
)
from freyja_backend.domain.market_trend import TrendState
from freyja_backend.domain.pattern_detection import (
    AFTER_MARKET_FORMATION,
    LIVE,
    RETROSPECTIVE,
)

# Bump on ANY change to what a hypothesis contains, how it is derived or how it may evolve.
HYPOTHESIS_MODEL_VERSION = "hypothesis-v1"

UNPROVEN = "UNPROVEN"

_NAMESPACE = uuid.UUID("6b7f2e4d-3c1a-5e9f-8d2b-1a4c6e8f0b3d")
_TIMING_CODES = frozenset({"DIAMOND_TIMING", "BREAKOUT_TIMING"})
_TRIGGER_STATES = frozenset(
    {
        PatternState.BREAKOUT_PENDING_CONFIRMATION,
        PatternState.CONFIRMED_UP,
        PatternState.CONFIRMED_DOWN,
    }
)
_CLOSING_STATES = frozenset({PatternState.FAILED_BREAKOUT, PatternState.INVALIDATED})


class InvalidHypothesisError(ValueError):
    """A hypothesis or evaluation that contradicts itself or the contract. It cannot exist."""


class HypothesisKind(enum.StrEnum):
    CONTINUATION = "CONTINUATION"
    REVERSAL = "REVERSAL"
    BREAKOUT = "BREAKOUT"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"


class HypothesisDirection(enum.StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    # Reserved for a future version that allows pre-breakout hypotheses (contract, section 2);
    # never produced by this module.
    BIDIRECTIONAL = "BIDIRECTIONAL"
    # Only ever produced when the source instance closes (FAILED_BREAKOUT/INVALIDATED).
    UNKNOWN = "UNKNOWN"


class TargetScope(enum.StrEnum):
    # The only value this module ever produces (contract, section 3.2): no StrategySpec exists
    # yet to ask for a narrower horizon.
    MARKET_DIRECTION = "MARKET_DIRECTION"
    NEXT_CANDLE = "NEXT_CANDLE"
    MULTI_CANDLE_MOVE = "MULTI_CANDLE_MOVE"


class Operability(enum.StrEnum):
    OPERABLE = "OPERABLE"
    RETROSPECTIVE = "RETROSPECTIVE"
    UNPROVEN = "UNPROVEN"


@dataclass(frozen=True, slots=True)
class RelatedPattern:
    """Another figure's own directional read, as evidence for or against a hypothesis, with its
    own provenance kept apart (it never changes the hypothesis's own operability, section 5)."""

    pattern_instance_id: uuid.UUID
    pattern_type: str
    direction: BreakoutDirection
    provenance: str

    def __post_init__(self) -> None:
        if self.provenance not in (LIVE, AFTER_MARKET_FORMATION, RETROSPECTIVE, UNPROVEN):
            raise InvalidHypothesisError(f"unknown provenance {self.provenance!r}")


@dataclass(frozen=True, slots=True)
class HypothesisEvaluation:
    """What the hypothesis said at one instant. Autosufficient: it names the source's own state
    (``HYPOTHESIS_SOURCE`` evidence) and every supporting/conflicting figure, so nothing has to be
    looked up later to understand it."""

    evaluated_at: datetime
    as_of: datetime | None
    hypothesis_kind: HypothesisKind
    hypothesis_direction: HypothesisDirection
    target_scope: TargetScope
    context_compatible: bool
    supporting_patterns: tuple[RelatedPattern, ...]
    conflicting_patterns: tuple[RelatedPattern, ...]
    evidence: tuple[PatternEvidence, ...]
    operability: Operability
    definition_version: str = HYPOTHESIS_MODEL_VERSION

    def __post_init__(self) -> None:
        if self.evaluated_at.utcoffset() != timedelta(0):
            raise InvalidHypothesisError("evaluated_at must be a timezone-aware UTC datetime")
        if self.as_of is not None:
            if self.as_of.utcoffset() != timedelta(0):
                raise InvalidHypothesisError("as_of must be a timezone-aware UTC datetime")
            if self.as_of > self.evaluated_at:
                raise InvalidHypothesisError("a candle that closes after the evaluation was read")
        if self.target_scope is not TargetScope.MARKET_DIRECTION:
            raise InvalidHypothesisError(
                "target_scope is always MARKET_DIRECTION until a StrategySpec asks otherwise"
            )
        if self.hypothesis_direction is HypothesisDirection.BIDIRECTIONAL:
            raise InvalidHypothesisError("BIDIRECTIONAL is reserved, unused in v1")
        source_provenance = self._source_provenance()
        if (
            self.operability is Operability.OPERABLE
            and source_provenance is not None
            and source_provenance != LIVE
        ):
            # `None` means this evaluation carried operability forward from a previous one
            # (closing with no fresh breakout, see `_build`): nothing new to check against here.
            raise InvalidHypothesisError("OPERABLE requires the source's own provenance to be LIVE")
        if not any(item.code == "HYPOTHESIS_SOURCE" for item in self.evidence):
            raise InvalidHypothesisError("a hypothesis evaluation names its source's own state")
        for group in (self.supporting_patterns, self.conflicting_patterns):
            ids = [related.pattern_instance_id for related in group]
            if len(set(ids)) != len(ids):
                raise InvalidHypothesisError("a related pattern is listed at most once per side")

    def _source_provenance(self) -> str | None:
        for item in self.evidence:
            if item.code == "HYPOTHESIS_SOURCE":
                facts = dict(item.facts)
                value = facts.get("source_provenance")
                return None if value is None else str(value)
        return None


def derive_pattern_hypothesis_id(
    source_pattern_instance_id: uuid.UUID, definition_version: str = HYPOTHESIS_MODEL_VERSION
) -> uuid.UUID:
    """The identity of a hypothesis: its origin and the version that derived it. The same origin
    always produces the same hypothesis, evolving without ever changing identity."""
    return uuid.uuid5(_NAMESPACE, f"{definition_version}|{source_pattern_instance_id}")


@dataclass(frozen=True, slots=True)
class PatternHypothesis:
    """One hypothesis and its append-only history of evaluations."""

    source_pattern_instance_id: uuid.UUID
    evaluations: tuple[HypothesisEvaluation, ...]
    definition_version: str = HYPOTHESIS_MODEL_VERSION

    def __post_init__(self) -> None:
        if not self.evaluations:
            raise InvalidHypothesisError("a hypothesis is born from an evaluation")
        times = [e.evaluated_at for e in self.evaluations]
        if any(later <= earlier for earlier, later in pairwise(times)):
            raise InvalidHypothesisError("evaluations move strictly forward in time")
        for earlier in self.evaluations[:-1]:
            if earlier.hypothesis_direction is HypothesisDirection.UNKNOWN:
                raise InvalidHypothesisError("UNKNOWN closes a hypothesis: nothing follows it")

    @property
    def pattern_hypothesis_id(self) -> uuid.UUID:
        return derive_pattern_hypothesis_id(
            self.source_pattern_instance_id, self.definition_version
        )

    @property
    def latest(self) -> HypothesisEvaluation:
        return self.evaluations[-1]

    @property
    def is_terminal(self) -> bool:
        return self.latest.hypothesis_direction is HypothesisDirection.UNKNOWN

    def advance(self, evaluation: HypothesisEvaluation) -> "PatternHypothesis":
        """The same hypothesis one evaluation later. Earlier evaluations are untouched."""
        return PatternHypothesis(
            self.source_pattern_instance_id,
            (*self.evaluations, evaluation),
            self.definition_version,
        )


# -- deriving a hypothesis from a source instance and its coexisting pool -----------------------


def _timing_facts(evaluation: PatternEvaluation) -> dict[str, EvidenceValue] | None:
    for item in evaluation.evidence:
        if item.code in _TIMING_CODES:
            return dict(item.facts)
    return None


def _prior_trend_of(evaluation: PatternEvaluation) -> TrendState:
    for item in evaluation.evidence:
        if item.code == "PRIOR_TREND":
            return TrendState(str(dict(item.facts)["state"]))
    return TrendState.INSUFFICIENT_DATA  # never equals UPTREND/DOWNTREND: matches nothing


def evidence_provenance(evaluation: PatternEvaluation) -> str:
    """`LIVE`/`AFTER_MARKET_FORMATION`/`RETROSPECTIVE` only when the source detector actually
    proved `known_at` for this evaluation's breakout; `UNPROVEN` otherwise — never trusts a
    detector's own `provenance` fact without first checking `known_at` is present (contract,
    section 4.3): a fail-closed check independent of what the detector chose to call it."""
    facts = _timing_facts(evaluation)
    if facts is None or "known_at" not in facts or "provenance" not in facts:
        return UNPROVEN
    return str(facts["provenance"])


def _operability_of(provenance: str) -> Operability:
    if provenance == LIVE:
        return Operability.OPERABLE
    if provenance in (AFTER_MARKET_FORMATION, RETROSPECTIVE):
        return Operability.RETROSPECTIVE
    return Operability.UNPROVEN


def _kind_and_compatibility(
    roles: frozenset[PatternRole], prior_trend: TrendState, direction: BreakoutDirection
) -> tuple[HypothesisKind, bool]:
    """Contract, section 3.1: derived from roles, prior trend and the *real* breakout direction —
    never from `traditional_bias`. `EXPANSION` wins the `hypothesis_kind` regardless, but
    `context_compatible` is always the same underlying check (priority 1 does not fix it)."""
    trend_equivalent = (
        TrendState.UPTREND if direction is BreakoutDirection.UP else TrendState.DOWNTREND
    )
    opposite = TrendState.DOWNTREND if direction is BreakoutDirection.UP else TrendState.UPTREND
    reversal_match = PatternRole.REVERSAL in roles and prior_trend is opposite
    continuation_match = PatternRole.CONTINUATION in roles and prior_trend is trend_equivalent
    compatible = reversal_match or continuation_match
    if PatternRole.EXPANSION in roles:
        return HypothesisKind.VOLATILITY_EXPANSION, compatible
    if reversal_match:
        return HypothesisKind.REVERSAL, True
    if continuation_match:
        return HypothesisKind.CONTINUATION, True
    return HypothesisKind.BREAKOUT, False


def _directional_read(evaluation: PatternEvaluation) -> BreakoutDirection | None:
    """Another figure's own directional read at one of its evaluations, or `None` if it has none
    yet (still forming, paused, or its breakout failed/was invalidated): a neutral figure never
    supports nor contradicts (contract, section 3.3)."""
    if evaluation.state is PatternState.CONFIRMED_UP:
        return BreakoutDirection.UP
    if evaluation.state is PatternState.CONFIRMED_DOWN:
        return BreakoutDirection.DOWN
    if evaluation.state is PatternState.BREAKOUT_PENDING_CONFIRMATION and evaluation.breakout:
        return evaluation.breakout.direction
    return None


def _is_covered(evaluation: PatternEvaluation) -> bool:
    """Whether this evaluation was, at its own instant, held back by an overlap policy (only the
    diamond has this: `held_by_overlap` in `DIAMOND_TIMING`, contract section 3.3)."""
    for item in evaluation.evidence:
        if item.code == "DIAMOND_TIMING":
            return bool(dict(item.facts).get("held_by_overlap", False))
    return False


def _as_of(instance: PatternInstance, at: datetime) -> PatternEvaluation | None:
    """The instance's own latest evaluation known at or before `at`, or `None` if it did not yet
    exist: never a future one (no look-ahead)."""
    known = [e for e in instance.evaluations if e.evaluated_at <= at]
    return known[-1] if known else None


def _related_patterns(
    source_direction: BreakoutDirection, at: datetime, pool: Sequence[PatternInstance]
) -> tuple[tuple[RelatedPattern, ...], tuple[RelatedPattern, ...]]:
    supporting: list[RelatedPattern] = []
    conflicting: list[RelatedPattern] = []
    for other in sorted(pool, key=lambda i: str(i.pattern_instance_id)):
        seen = _as_of(other, at)
        if seen is None or _is_covered(seen):
            continue
        direction = _directional_read(seen)
        if direction is None:
            continue
        related = RelatedPattern(
            other.pattern_instance_id,
            other.pattern_type.value,
            direction,
            evidence_provenance(seen),
        )
        (supporting if direction is source_direction else conflicting).append(related)
    return tuple(supporting), tuple(conflicting)


def _source_evidence(evaluation: PatternEvaluation, provenance: str | None) -> PatternEvidence:
    facts: dict[str, EvidenceValue] = {"source_state": evaluation.state.value}
    if evaluation.breakout is not None:
        facts["breakout_direction"] = evaluation.breakout.direction.value
        facts["breakout_confirmed"] = evaluation.breakout.confirmed
        facts["breakout_close_time"] = evaluation.breakout.candle_close_time.isoformat()
    if provenance is not None:
        facts["source_provenance"] = provenance
    return evidence(
        "HYPOTHESIS_SOURCE",
        "state, breakout and procedence of the source instance at this evaluation",
        **facts,
    )


def _same_content(before: HypothesisEvaluation, after: HypothesisEvaluation) -> bool:
    return (
        before.hypothesis_kind is after.hypothesis_kind
        and before.hypothesis_direction is after.hypothesis_direction
        and before.context_compatible == after.context_compatible
        and before.supporting_patterns == after.supporting_patterns
        and before.conflicting_patterns == after.conflicting_patterns
        and before.operability is after.operability
        # The source's own state (pending vs confirmed, say) is news even when none of the above
        # changed: `HYPOTHESIS_SOURCE` carries it, so comparing the whole evidence catches it.
        and before.evidence == after.evidence
    )


def _build(
    source: PatternInstance,
    current: PatternEvaluation,
    pool: Sequence[PatternInstance],
    previous: HypothesisEvaluation | None,
) -> HypothesisEvaluation:
    if current.state in _CLOSING_STATES:
        direction = HypothesisDirection.UNKNOWN
        if current.breakout is not None:
            # FAILED_BREAKOUT: a real breakout, with its own fresh provenance.
            prior_trend = _prior_trend_of(current)
            kind, compatible = _kind_and_compatibility(
                source.traditional_roles, prior_trend, current.breakout.direction
            )
            confirmed_provenance = evidence_provenance(current)
            provenance: str | None = confirmed_provenance
            operability = _operability_of(confirmed_provenance)
        elif previous is not None:
            # INVALIDATED with no breakout of its own (SUPERSEDED/GEOMETRY_BROKEN): carry the
            # last known reading forward, only the direction closes.
            kind, compatible, provenance = (
                previous.hypothesis_kind,
                previous.context_compatible,
                None,
            )
            operability = previous.operability
        else:
            # Unreachable via `hypothesis_for` (the first evaluation processed is always a
            # trigger state, never a closing one), kept only so this function stays total.
            kind, compatible, provenance, operability = (
                HypothesisKind.BREAKOUT,
                False,
                None,
                Operability.UNPROVEN,
            )
        supporting, conflicting = (
            (previous.supporting_patterns, previous.conflicting_patterns)
            if previous is not None
            else ((), ())
        )
    else:
        assert current.breakout is not None  # BREAKOUT_PENDING_CONFIRMATION/CONFIRMED_* need one
        direction = (
            HypothesisDirection.UP
            if current.breakout.direction is BreakoutDirection.UP
            else HypothesisDirection.DOWN
        )
        prior_trend = _prior_trend_of(current)
        kind, compatible = _kind_and_compatibility(
            source.traditional_roles, prior_trend, current.breakout.direction
        )
        provenance = evidence_provenance(current)
        operability = _operability_of(provenance)
        supporting, conflicting = _related_patterns(
            current.breakout.direction, current.evaluated_at, pool
        )
    return HypothesisEvaluation(
        evaluated_at=current.evaluated_at,
        as_of=current.as_of,
        hypothesis_kind=kind,
        hypothesis_direction=direction,
        target_scope=TargetScope.MARKET_DIRECTION,
        context_compatible=compatible,
        supporting_patterns=supporting,
        conflicting_patterns=conflicting,
        evidence=(_source_evidence(current, provenance),),
        operability=operability,
    )


def hypothesis_for(
    source: PatternInstance, pool: Sequence[PatternInstance] = ()
) -> PatternHypothesis | None:
    """The hypothesis `source` produces, evolving through every instant its own evaluations
    reach a real breakout (contract, section 2). `pool` is every other instance of the *same*
    series (instrument, source, timeframe); it is filtered here, so passing every instance Freyja
    knows about, for every series, is safe and simplest for a caller.

    `None` if `source` never reaches a breakout state: an instance that stays `FORMING`,
    `GEOMETRICALLY_VALID` or is invalidated before ever breaking out never had a hypothesis to
    give (section 2)."""
    same_series = [
        other
        for other in pool
        if other.pattern_instance_id != source.pattern_instance_id
        and other.instrument_id == source.instrument_id
        and other.data_source == source.data_source
        and other.timeframe == source.timeframe
    ]
    first = next((i for i, e in enumerate(source.evaluations) if e.state in _TRIGGER_STATES), None)
    if first is None:
        return None

    evaluations: list[HypothesisEvaluation] = []
    previous: HypothesisEvaluation | None = None
    for current in source.evaluations[first:]:
        if current.state not in _TRIGGER_STATES and current.state not in _CLOSING_STATES:
            continue  # INSUFFICIENT_DATA or another pause: not a new reading, skip silently
        built = _build(source, current, same_series, previous)
        if previous is None or not _same_content(previous, built):
            evaluations.append(built)
            previous = built
        if built.hypothesis_direction is HypothesisDirection.UNKNOWN:
            break  # closed: nothing follows
    if not evaluations:
        return None
    return PatternHypothesis(source.pattern_instance_id, tuple(evaluations))
