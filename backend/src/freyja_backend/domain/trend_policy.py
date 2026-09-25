"""Trend requirements of a strategy (POINT2-POLICY-001).

The contract lives in ``docs/domain/politica-de-tendencia.md`` (and, above it,
``docs/domain/contexto-y-tendencia.md``, sections 3 to 5). A `TrendPolicy` is the part of a
future strategy version that says *which trend context its hypothesis needs*; this module
also decides, from the trend classifications of both timeframes, whether a hypothesis fits it.

It is a *compatibility* check, never a signal: the answer is COMPATIBLE, INCOMPATIBLE or
INSUFFICIENT_CONTEXT, and nothing here holds a side, an entry, an order, a confidence or a
position. What a bullish or bearish hypothesis means for a product (contract section 5) is
not decided here: for spot crypto "bearish" is to stand aside or leave, never a short, and
this layer never turns an orientation into a position.

Pure and free of I/O. Policies are immutable values: publishing a new version never touches
an older one, and every evaluation records the version it was made with, so history cannot
change when a policy does.
"""

import enum
from dataclasses import dataclass
from typing import Self

from freyja_backend.domain.market_data import Timeframe
from freyja_backend.domain.market_trend import (
    TrendClassification,
    TrendPair,
    TrendState,
    TrendTimeframes,
)

# Bump on ANY change to how a policy is judged, so an evaluation can always be traced to the
# exact rules that produced it.
POLICY_EVALUATION_VERSION = "trend-policy-v1"


class InvalidTrendPolicyError(ValueError):
    """A policy that contradicts itself or leaves something implicit. It cannot exist."""


class Orientation(enum.StrEnum):
    """The sense of a hypothesis. What it means in each product is the product's (contract
    section 5); this module only compares it with a trend."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


class TrendRelationship(enum.StrEnum):
    """How a hypothesis relates to the context trend. Always declared, never assumed:
    there is no default, and `ANY` in particular is never a fallback."""

    WITH_TREND = "WITH_TREND"
    COUNTER_TREND = "COUNTER_TREND"
    RANGE_ONLY = "RANGE_ONLY"
    TRANSITION_ONLY = "TRANSITION_ONLY"
    ANY = "ANY"


class ConflictRule(enum.StrEnum):
    """What to do when the signal timeframe and the context timeframe are both in a trend
    and the trends are opposite. Always declared: there is no default."""

    REJECT_ON_CONFLICT = "REJECT_ON_CONFLICT"
    ALLOW_CONFLICT = "ALLOW_CONFLICT"


class PolicyOutcome(enum.StrEnum):
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    # There is not enough (or not the right) context to say: never a soft yes.
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


class PolicyReason(enum.StrEnum):
    # -> INSUFFICIENT_CONTEXT
    POLICY_MISSING = "POLICY_MISSING"
    TIMEFRAME_MISMATCH = "TIMEFRAME_MISMATCH"
    SIGNAL_TREND_INSUFFICIENT = "SIGNAL_TREND_INSUFFICIENT"
    CONTEXT_TREND_INSUFFICIENT = "CONTEXT_TREND_INSUFFICIENT"
    TREND_DEFINITION_MISMATCH = "TREND_DEFINITION_MISMATCH"
    MINIMUM_HISTORY_NOT_MET = "MINIMUM_HISTORY_NOT_MET"
    # -> INCOMPATIBLE
    SIGNAL_STATE_NOT_ADMITTED = "SIGNAL_STATE_NOT_ADMITTED"
    CONTEXT_STATE_NOT_ADMITTED = "CONTEXT_STATE_NOT_ADMITTED"
    RELATIONSHIP_NOT_SATISFIED = "RELATIONSHIP_NOT_SATISFIED"
    MULTITIMEFRAME_CONFLICT = "MULTITIMEFRAME_CONFLICT"


_INSUFFICIENT_REASONS = frozenset(
    {
        PolicyReason.POLICY_MISSING,
        PolicyReason.TIMEFRAME_MISMATCH,
        PolicyReason.SIGNAL_TREND_INSUFFICIENT,
        PolicyReason.CONTEXT_TREND_INSUFFICIENT,
        PolicyReason.TREND_DEFINITION_MISMATCH,
        PolicyReason.MINIMUM_HISTORY_NOT_MET,
    }
)

_DIRECTIONAL = frozenset({TrendState.UPTREND, TrendState.DOWNTREND})
_CLASSIFIABLE = frozenset(
    {TrendState.UPTREND, TrendState.DOWNTREND, TrendState.RANGE, TrendState.TRANSITION}
)

# The context states each relationship can ever be satisfied by (contract section 4). A
# policy admitting a context state its own relationship can never accept contradicts itself.
_STATES_A_RELATIONSHIP_CAN_MEET: dict[TrendRelationship, frozenset[TrendState]] = {
    TrendRelationship.WITH_TREND: _DIRECTIONAL,
    TrendRelationship.COUNTER_TREND: _DIRECTIONAL,
    TrendRelationship.RANGE_ONLY: frozenset({TrendState.RANGE}),
    TrendRelationship.TRANSITION_ONLY: frozenset({TrendState.TRANSITION}),
    TrendRelationship.ANY: _CLASSIFIABLE,
}


@dataclass(frozen=True, slots=True)
class TrendPolicy:
    """What a strategy version needs from the trend context. Every field is required and
    explicit; nothing has a default that could turn a forgotten line into permission."""

    # Identifies the policy version. Versions are immutable: a change is a new version.
    version: str
    signal_timeframe: Timeframe
    context_timeframe: Timeframe
    relationship: TrendRelationship
    # Trend states of each timeframe the strategy accepts. INSUFFICIENT_DATA is never one.
    signal_states: frozenset[TrendState]
    context_states: frozenset[TrendState]
    conflict_rule: ConflictRule
    # Closed candles each classification must have read at least.
    minimum_history: int
    # The definition of trend the policy was written against; another one is not assumed
    # to mean the same thing.
    trend_definition_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise InvalidTrendPolicyError("a policy must carry its version")
        if not isinstance(self.trend_definition_version, str) or not (
            self.trend_definition_version.strip()
        ):
            raise InvalidTrendPolicyError("a policy must name the trend definition it uses")
        for name, value, kind in (
            ("signal_timeframe", self.signal_timeframe, Timeframe),
            ("context_timeframe", self.context_timeframe, Timeframe),
            ("relationship", self.relationship, TrendRelationship),
            ("conflict_rule", self.conflict_rule, ConflictRule),
        ):
            if not isinstance(value, kind):
                raise InvalidTrendPolicyError(f"{name} must be a {kind.__name__}, declared")
        if self.context_timeframe.duration < self.signal_timeframe.duration:
            raise InvalidTrendPolicyError(
                "the context timeframe must not be finer than the signal timeframe"
            )
        if (
            isinstance(self.minimum_history, bool)
            or not isinstance(self.minimum_history, int)
            or self.minimum_history < 1
        ):
            raise InvalidTrendPolicyError("minimum_history must be an integer of at least 1")
        self._check_states("signal_states", self.signal_states, _CLASSIFIABLE)
        self._check_states(
            "context_states",
            self.context_states,
            _STATES_A_RELATIONSHIP_CAN_MEET[self.relationship],
        )

    @staticmethod
    def _check_states(
        name: str, states: frozenset[TrendState], allowed: frozenset[TrendState]
    ) -> None:
        if not isinstance(states, frozenset) or not all(isinstance(s, TrendState) for s in states):
            raise InvalidTrendPolicyError(f"{name} must be a frozenset of TrendState")
        if not states:
            raise InvalidTrendPolicyError(f"{name} must admit at least one state")
        if TrendState.INSUFFICIENT_DATA in states:
            raise InvalidTrendPolicyError(
                f"{name} cannot admit INSUFFICIENT_DATA: without context there is no valid signal"
            )
        unreachable = states - allowed
        if unreachable:
            listed = ", ".join(sorted(s.value for s in unreachable))
            raise InvalidTrendPolicyError(
                f"{name} admits {listed}, which the policy can never meet"
            )

    @property
    def timeframes(self) -> TrendTimeframes:
        """The pair of timeframes this policy declares, versioned with the policy."""
        return TrendTimeframes(self.signal_timeframe, self.context_timeframe, self.version)

    def as_new_version(self, version: str, **changes: object) -> Self:
        """A *new* policy that differs in `changes`. The one it came from is untouched."""
        if version == self.version:
            raise InvalidTrendPolicyError("a new version needs a new version identifier")
        values = {name: getattr(self, name) for name in self.__dataclass_fields__}
        values.update(changes)
        values["version"] = version
        return type(self)(**values)


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    """Whether a hypothesis fits the trend context its strategy requires. Immutable, and it
    carries what it was made with, so it stays true whatever happens to the policy later."""

    outcome: PolicyOutcome
    reasons: tuple[PolicyReason, ...]
    orientation: Orientation
    # None only when there was no policy to speak of.
    policy_version: str | None
    relationship: TrendRelationship | None
    signal_state: TrendState | None
    context_state: TrendState | None
    trend_definition_version: str | None
    evaluation_version: str = POLICY_EVALUATION_VERSION

    @property
    def is_compatible(self) -> bool:
        return self.outcome is PolicyOutcome.COMPATIBLE


def evaluate_trend_policy(
    policy: TrendPolicy | None,
    *,
    orientation: Orientation,
    pair: TrendPair,
) -> PolicyEvaluation:
    """Does a hypothesis of this `orientation` fit what `policy` requires of the trend?

    Fail-closed. Without a policy, with timeframes that are not the policy's, with a
    classification that is INSUFFICIENT_DATA, made under another trend definition or from
    less history than required, the answer is INSUFFICIENT_CONTEXT, whatever else is true.
    Only with all of that in order are the admitted states, the relationship and the conflict
    rule judged, and every one that fails is reported. Nothing is ever defaulted to
    COMPATIBLE.
    """
    if not isinstance(orientation, Orientation):
        raise InvalidTrendPolicyError("the orientation of the hypothesis must be declared")
    if policy is None:
        return _evaluation(
            PolicyOutcome.INSUFFICIENT_CONTEXT,
            (PolicyReason.POLICY_MISSING,),
            orientation,
            None,
            pair,
        )

    reasons: list[PolicyReason] = []
    signal, context = pair.signal, pair.context

    if (
        (pair.timeframes.signal, pair.timeframes.context)
        != (policy.signal_timeframe, policy.context_timeframe)
        or signal.timeframe is not policy.signal_timeframe
        or context.timeframe is not policy.context_timeframe
    ):
        # The trends were classified for another pair of timeframes than the policy names.
        reasons.append(PolicyReason.TIMEFRAME_MISMATCH)
    if not signal.is_sufficient:
        reasons.append(PolicyReason.SIGNAL_TREND_INSUFFICIENT)
    if not context.is_sufficient:
        reasons.append(PolicyReason.CONTEXT_TREND_INSUFFICIENT)
    if any(c.definition_version != policy.trend_definition_version for c in (signal, context)):
        reasons.append(PolicyReason.TREND_DEFINITION_MISMATCH)
    if any(
        c.is_sufficient and c.window_candles < policy.minimum_history for c in (signal, context)
    ):
        reasons.append(PolicyReason.MINIMUM_HISTORY_NOT_MET)

    if not reasons:
        reasons.extend(_incompatibilities(policy, orientation, signal, context))

    if any(reason in _INSUFFICIENT_REASONS for reason in reasons):
        outcome = PolicyOutcome.INSUFFICIENT_CONTEXT
    elif reasons:
        outcome = PolicyOutcome.INCOMPATIBLE
    else:
        outcome = PolicyOutcome.COMPATIBLE
    return _evaluation(outcome, tuple(reasons), orientation, policy, pair)


def _incompatibilities(
    policy: TrendPolicy,
    orientation: Orientation,
    signal: TrendClassification,
    context: TrendClassification,
) -> list[PolicyReason]:
    reasons: list[PolicyReason] = []
    if signal.state not in policy.signal_states:
        reasons.append(PolicyReason.SIGNAL_STATE_NOT_ADMITTED)
    if context.state not in policy.context_states:
        reasons.append(PolicyReason.CONTEXT_STATE_NOT_ADMITTED)
    if not _relationship_holds(policy.relationship, orientation, context.state):
        reasons.append(PolicyReason.RELATIONSHIP_NOT_SATISFIED)
    if (
        policy.conflict_rule is ConflictRule.REJECT_ON_CONFLICT
        and signal.state in _DIRECTIONAL
        and context.state in _DIRECTIONAL
        and signal.state is not context.state
    ):
        reasons.append(PolicyReason.MULTITIMEFRAME_CONFLICT)
    return reasons


def _relationship_holds(
    relationship: TrendRelationship, orientation: Orientation, context_state: TrendState
) -> bool:
    """The matrix of contract section 4, for a context that has already been classified."""
    if context_state is TrendState.INSUFFICIENT_DATA:
        return False  # incompatible with every relationship, `ANY` included
    if relationship is TrendRelationship.ANY:
        return True
    if relationship is TrendRelationship.RANGE_ONLY:
        return context_state is TrendState.RANGE
    if relationship is TrendRelationship.TRANSITION_ONLY:
        return context_state is TrendState.TRANSITION
    with_trend = (context_state is TrendState.UPTREND and orientation is Orientation.BULLISH) or (
        context_state is TrendState.DOWNTREND and orientation is Orientation.BEARISH
    )
    counter_trend = (
        context_state is TrendState.UPTREND and orientation is Orientation.BEARISH
    ) or (context_state is TrendState.DOWNTREND and orientation is Orientation.BULLISH)
    return with_trend if relationship is TrendRelationship.WITH_TREND else counter_trend


def _evaluation(
    outcome: PolicyOutcome,
    reasons: tuple[PolicyReason, ...],
    orientation: Orientation,
    policy: TrendPolicy | None,
    pair: TrendPair,
) -> PolicyEvaluation:
    return PolicyEvaluation(
        outcome=outcome,
        reasons=reasons,
        orientation=orientation,
        policy_version=None if policy is None else policy.version,
        relationship=None if policy is None else policy.relationship,
        signal_state=pair.signal.state,
        context_state=pair.context.state,
        trend_definition_version=None if policy is None else policy.trend_definition_version,
    )
