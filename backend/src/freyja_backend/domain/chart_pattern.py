"""Chart pattern instance model (POINT3-MODEL-001).

The contract lives in ``docs/domain/instancia-de-figura.md`` (and, above it,
``docs/domain/figuras-chartistas.md``, which defines the twenty patterns this module knows).
It represents *one concrete figure* found on the closed candles and confirmed pivots of one
series, and how it evolved. It is a **model, not a detector**: it decides nothing about
whether a geometry is really a head and shoulders; it makes sure that what a detector says
is complete, coherent, free of look-ahead and reconstructable.

A pattern instance is a *record*, like a context snapshot: immutable values that are built,
stored and read back. Its history is append-only. Each **evaluation** says what the detector
saw at one instant (state, anchors, boundaries, breakout, reasons, evidence); a new evaluation
of the same figure is added, the earlier ones are never rewritten. A substantial change (a
different starting point, or anchors that are not simply the previous ones plus new ones)
is **another instance** with its own identity.

Nothing here generates a signal, a decision or an order; it holds no side, entry, target,
confidence or probability. The traditional bias of a pattern is tradition, not evidence.

Pure and free of I/O: no database, no clock, no provider.
"""

import enum
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from types import MappingProxyType
from typing import Any, Self

from freyja_backend.domain.market_context import MissingDataReason
from freyja_backend.domain.market_data import Timeframe
from freyja_backend.domain.market_structure import Pivot, PivotKind, PivotStatus

# Bump on ANY change to what an instance contains, how it is written or how it may evolve.
PATTERN_MODEL_VERSION = "pattern-instance-v1"
# Version of the catalogue of patterns (docs/domain/figuras-chartistas.md, v1).
PATTERN_CATALOGUE_VERSION = "chart-patterns-v1"

_NAMESPACE = uuid.UUID("3b7c1f0e-9a44-5d2b-8e61-0c5a7d2f4b19")
_CODE = re.compile(r"[A-Z][A-Z0-9_]*")
_FACT_NAME = re.compile(r"[a-z][a-z0-9_]*")


class InvalidPatternError(ValueError):
    """A pattern instance, evaluation or document that contradicts itself. It cannot exist."""


# -- the catalogue --------------------------------------------------------------------------


class PatternGroup(enum.StrEnum):
    """How the approved catalogue is grouped. Only for presentation: it decides no meaning."""

    REVERSAL = "REVERSAL"
    CONTINUATION_CONSOLIDATION = "CONTINUATION_CONSOLIDATION"
    COMPRESSION_EXPANSION_CONTEXTUAL = "COMPRESSION_EXPANSION_CONTEXTUAL"


class PatternRole(enum.StrEnum):
    REVERSAL = "REVERSAL"
    CONTINUATION = "CONTINUATION"
    CONSOLIDATION = "CONSOLIDATION"
    COMPRESSION = "COMPRESSION"
    EXPANSION = "EXPANSION"


class PatternBias(enum.StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    BREAKOUT_DEPENDENT = "BREAKOUT_DEPENDENT"
    CONTEXT_DEPENDENT = "CONTEXT_DEPENDENT"


class PatternType(enum.StrEnum):
    HEAD_AND_SHOULDERS_TOP = "HEAD_AND_SHOULDERS_TOP"
    HEAD_AND_SHOULDERS_BOTTOM = "HEAD_AND_SHOULDERS_BOTTOM"
    DOUBLE_TOP = "DOUBLE_TOP"
    DOUBLE_BOTTOM = "DOUBLE_BOTTOM"
    TRIPLE_TOP = "TRIPLE_TOP"
    TRIPLE_BOTTOM = "TRIPLE_BOTTOM"
    ROUNDING_TOP = "ROUNDING_TOP"
    ROUNDING_BOTTOM = "ROUNDING_BOTTOM"
    BULL_FLAG = "BULL_FLAG"
    BEAR_FLAG = "BEAR_FLAG"
    BULL_PENNANT = "BULL_PENNANT"
    BEAR_PENNANT = "BEAR_PENNANT"
    ASCENDING_TRIANGLE = "ASCENDING_TRIANGLE"
    DESCENDING_TRIANGLE = "DESCENDING_TRIANGLE"
    SYMMETRICAL_TRIANGLE = "SYMMETRICAL_TRIANGLE"
    RECTANGLE = "RECTANGLE"
    RISING_WEDGE = "RISING_WEDGE"
    FALLING_WEDGE = "FALLING_WEDGE"
    BROADENING_FORMATION = "BROADENING_FORMATION"
    DIAMOND = "DIAMOND"


@dataclass(frozen=True, slots=True)
class PatternDefinition:
    """What the contract says a pattern is, as data. A detector may demand more anchors, never
    fewer: `min_anchor_pivots` is the number of distinct confirmed pivots its geometry needs."""

    pattern_type: PatternType
    group: PatternGroup
    traditional_roles: frozenset[PatternRole]
    traditional_bias: PatternBias
    min_anchor_pivots: int


_R, _C = PatternGroup.REVERSAL, PatternGroup.CONTINUATION_CONSOLIDATION
_E = PatternGroup.COMPRESSION_EXPANSION_CONTEXTUAL
_REV, _CONT = PatternRole.REVERSAL, PatternRole.CONTINUATION
_CONS, _COMP, _EXP = PatternRole.CONSOLIDATION, PatternRole.COMPRESSION, PatternRole.EXPANSION
_BULL, _BEAR = PatternBias.BULLISH, PatternBias.BEARISH
_BRK, _CTX = PatternBias.BREAKOUT_DEPENDENT, PatternBias.CONTEXT_DEPENDENT

_T = PatternType
_DEFINITIONS: tuple[PatternDefinition, ...] = tuple(
    PatternDefinition(t, g, frozenset(roles), bias, anchors)
    for t, g, roles, bias, anchors in (
        (_T.HEAD_AND_SHOULDERS_TOP, _R, {_REV}, _BEAR, 5),
        (_T.HEAD_AND_SHOULDERS_BOTTOM, _R, {_REV}, _BULL, 5),
        (_T.DOUBLE_TOP, _R, {_REV}, _BEAR, 3),
        (_T.DOUBLE_BOTTOM, _R, {_REV}, _BULL, 3),
        (_T.TRIPLE_TOP, _R, {_REV}, _BEAR, 5),
        (_T.TRIPLE_BOTTOM, _R, {_REV}, _BULL, 5),
        (_T.ROUNDING_TOP, _R, {_REV}, _BEAR, 3),
        (_T.ROUNDING_BOTTOM, _R, {_REV}, _BULL, 3),
        (_T.BULL_FLAG, _C, {_CONT}, _BULL, 5),
        (_T.BEAR_FLAG, _C, {_CONT}, _BEAR, 5),
        (_T.BULL_PENNANT, _C, {_CONT}, _BULL, 5),
        (_T.BEAR_PENNANT, _C, {_CONT}, _BEAR, 5),
        (_T.ASCENDING_TRIANGLE, _C, {_CONT, _REV}, _BULL, 4),
        (_T.DESCENDING_TRIANGLE, _C, {_CONT, _REV}, _BEAR, 4),
        (_T.SYMMETRICAL_TRIANGLE, _C, {_CONT, _REV, _COMP}, _BRK, 4),
        (_T.RECTANGLE, _C, {_CONS, _CONT, _REV}, _BRK, 4),
        (_T.RISING_WEDGE, _E, {_REV, _CONT, _COMP}, _BEAR, 4),
        (_T.FALLING_WEDGE, _E, {_REV, _CONT, _COMP}, _BULL, 4),
        (_T.BROADENING_FORMATION, _E, {_REV, _EXP}, _CTX, 5),
        (_T.DIAMOND, _E, {_REV, _EXP, _COMP}, _CTX, 6),
    )
)

# The twenty approved patterns, and only those. Read-only.
PATTERN_CATALOGUE: Mapping[PatternType, PatternDefinition] = MappingProxyType(
    {definition.pattern_type: definition for definition in _DEFINITIONS}
)


# -- lifecycle ------------------------------------------------------------------------------


class PatternState(enum.StrEnum):
    FORMING = "FORMING"
    GEOMETRICALLY_VALID = "GEOMETRICALLY_VALID"
    BREAKOUT_PENDING_CONFIRMATION = "BREAKOUT_PENDING_CONFIRMATION"
    CONFIRMED_UP = "CONFIRMED_UP"
    CONFIRMED_DOWN = "CONFIRMED_DOWN"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"
    INVALIDATED = "INVALIDATED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


_S = PatternState
TERMINAL_STATES = frozenset({_S.FAILED_BREAKOUT, _S.INVALIDATED})

# From each state, the states an evaluation may move to (staying is always allowed unless the
# state is terminal). INSUFFICIENT_DATA is handled apart: see `_check_step`.
_NEXT: Mapping[PatternState, frozenset[PatternState]] = MappingProxyType(
    {
        _S.FORMING: frozenset({_S.GEOMETRICALLY_VALID, _S.INVALIDATED}),
        _S.GEOMETRICALLY_VALID: frozenset({_S.BREAKOUT_PENDING_CONFIRMATION, _S.INVALIDATED}),
        _S.BREAKOUT_PENDING_CONFIRMATION: frozenset(
            {_S.CONFIRMED_UP, _S.CONFIRMED_DOWN, _S.FAILED_BREAKOUT, _S.INVALIDATED}
        ),
        _S.CONFIRMED_UP: frozenset({_S.FAILED_BREAKOUT, _S.INVALIDATED}),
        _S.CONFIRMED_DOWN: frozenset({_S.FAILED_BREAKOUT, _S.INVALIDATED}),
        _S.FAILED_BREAKOUT: frozenset(),
        _S.INVALIDATED: frozenset(),
    }
)


class InvalidationReason(enum.StrEnum):
    """Why a figure stopped being one. Recorded, never inferred later."""

    GEOMETRY_BROKEN = "GEOMETRY_BROKEN"
    ANCHOR_EXCEEDED = "ANCHOR_EXCEEDED"
    CLOSED_THROUGH_AGAINST_BIAS = "CLOSED_THROUGH_AGAINST_BIAS"
    TOO_LONG = "TOO_LONG"
    SUPERSEDED = "SUPERSEDED"


class BoundaryRole(enum.StrEnum):
    UPPER = "UPPER"
    LOWER = "LOWER"
    NECKLINE = "NECKLINE"
    BASE = "BASE"
    ARC = "ARC"


class BreakoutDirection(enum.StrEnum):
    UP = "UP"
    DOWN = "DOWN"


# -- what an evaluation is made of ----------------------------------------------------------


def _require_utc(moment: object, name: str) -> datetime:
    if not isinstance(moment, datetime) or moment.utcoffset() != timedelta(0):
        raise InvalidPatternError(f"{name} must be a timezone-aware UTC datetime")
    return moment


def _require_price(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise InvalidPatternError(f"{name} must be a positive exact Decimal, never a float")
    return value


@dataclass(frozen=True, slots=True)
class AnchorPivot:
    """A confirmed pivot the figure rests on, with the part it plays (e.g. `HEAD`)."""

    kind: PivotKind
    open_time: datetime
    price: Decimal
    confirmed_at: datetime
    label: str

    def __post_init__(self) -> None:
        _require_utc(self.open_time, "anchor open_time")
        _require_utc(self.confirmed_at, "anchor confirmed_at")
        _require_price(self.price, "anchor price")
        if self.confirmed_at <= self.open_time:
            raise InvalidPatternError("a pivot cannot be confirmed before its candle has closed")
        if not _CODE.fullmatch(self.label):
            raise InvalidPatternError("an anchor label is an UPPER_SNAKE_CASE code")

    @classmethod
    def from_pivot(cls, pivot: Pivot, label: str) -> Self:
        """Only a confirmed pivot can be an anchor: a provisional one may still vanish."""
        if pivot.status is not PivotStatus.CONFIRMED or pivot.confirmed_at is None:
            raise InvalidPatternError("a provisional pivot cannot anchor a figure")
        return cls(pivot.kind, pivot.open_time, pivot.price, pivot.confirmed_at, label)


@dataclass(frozen=True, slots=True)
class BoundaryPoint:
    time: datetime
    price: Decimal

    def __post_init__(self) -> None:
        _require_utc(self.time, "boundary point time")
        _require_price(self.price, "boundary point price")


@dataclass(frozen=True, slots=True)
class Boundary:
    """A line (two points) or an arc (three or more) that contains part of the figure, with the
    anchors that touch it (`contacts`, by the open time of each)."""

    role: BoundaryRole
    points: tuple[BoundaryPoint, ...]
    contacts: tuple[datetime, ...]

    def __post_init__(self) -> None:
        minimum = 3 if self.role is BoundaryRole.ARC else 2
        if len(self.points) < minimum:
            raise InvalidPatternError(f"a {self.role.value} boundary needs {minimum} points")
        times = [point.time for point in self.points]
        if any(later < earlier for earlier, later in pairwise(times)):
            raise InvalidPatternError("boundary points must be in chronological order")
        for contact in self.contacts:
            _require_utc(contact, "boundary contact")
        if len(set(self.contacts)) != len(self.contacts):
            raise InvalidPatternError("a contact is listed once per boundary")


@dataclass(frozen=True, slots=True)
class Breakout:
    """A closed candle beyond a boundary. `confirmed` is the detector's verdict, not the
    model's: this record only says which candle, where it closed and in which direction."""

    direction: BreakoutDirection
    boundary: BoundaryRole
    candle_open_time: datetime
    candle_close_time: datetime
    close_price: Decimal
    confirmed: bool

    def __post_init__(self) -> None:
        _require_utc(self.candle_open_time, "breakout candle open_time")
        _require_utc(self.candle_close_time, "breakout candle close_time")
        _require_price(self.close_price, "breakout close_price")
        if self.candle_close_time <= self.candle_open_time:
            raise InvalidPatternError("a breakout candle closes after it opens")


EvidenceValue = str | int | bool | Decimal


@dataclass(frozen=True, slots=True)
class PatternEvidence:
    """One fact a detector reports, readable by a person and stable for a machine. The `code`
    names the kind (`FLAGPOLE`, `HEAD_AND_SHOULDERS`, `ROUNDING_ARC`, `EXPANSION_RANGE`,
    `DIAMOND_PHASES`…): a new figure brings new codes, never new fields."""

    code: str
    detail: str
    # Sorted (name, value) pairs; prices and other decimals stay exact `Decimal`.
    facts: tuple[tuple[str, EvidenceValue], ...] = ()

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.code):
            raise InvalidPatternError("an evidence code is an UPPER_SNAKE_CASE code")
        if not self.detail.strip():
            raise InvalidPatternError("evidence must carry its human-readable detail")
        names = [name for name, _ in self.facts]
        if names != sorted(set(names)):
            raise InvalidPatternError("evidence facts are unique and sorted by name")
        for name, value in self.facts:
            if not _FACT_NAME.fullmatch(name):
                raise InvalidPatternError("a fact name is a lower_snake_case identifier")
            if isinstance(value, float) or not isinstance(value, str | int | bool | Decimal):
                raise InvalidPatternError(f"fact {name!r} must be text, int, bool or Decimal")
            if isinstance(value, Decimal) and not value.is_finite():
                raise InvalidPatternError(f"fact {name!r} must be a finite Decimal")


def evidence(code: str, detail: str, **facts: EvidenceValue) -> PatternEvidence:
    return PatternEvidence(code, detail, tuple(sorted(facts.items())))


@dataclass(frozen=True, slots=True)
class PatternEvaluation:
    """What the detector saw at one instant. Complete on its own: it names every anchor and
    boundary it used, so nothing has to be looked up later to understand it."""

    # The instant of the evaluation: only what was knowable by then was read.
    evaluated_at: datetime
    # Close of the newest closed candle read; None only if there was none.
    as_of: datetime | None
    candle_count: int
    state: PatternState
    anchors: tuple[AnchorPivot, ...]
    boundaries: tuple[Boundary, ...] = ()
    breakout: Breakout | None = None
    invalidation_reasons: tuple[InvalidationReason, ...] = ()
    insufficient_data_reasons: tuple[MissingDataReason, ...] = ()
    evidence: tuple[PatternEvidence, ...] = ()

    def __post_init__(self) -> None:
        _require_utc(self.evaluated_at, "evaluated_at")
        if self.as_of is not None:
            _require_utc(self.as_of, "as_of")
            if self.as_of > self.evaluated_at:
                raise InvalidPatternError("a candle that closes after the evaluation was read")
        if isinstance(self.candle_count, bool) or self.candle_count < 0:
            raise InvalidPatternError("candle_count must be a non-negative integer")
        if not self.anchors:
            raise InvalidPatternError("a figure has at least one anchor: without one there is none")
        opens = [anchor.open_time for anchor in self.anchors]
        if any(later <= earlier for earlier, later in pairwise(opens)):
            raise InvalidPatternError("anchors are in strict chronological order")
        for anchor in self.anchors:
            if anchor.confirmed_at > self.evaluated_at:
                raise InvalidPatternError("an anchor that was not yet confirmed was used")
        anchor_times = set(opens)
        for boundary in self.boundaries:
            if any(point.time > self.evaluated_at for point in boundary.points):
                raise InvalidPatternError("a boundary point lies after the evaluation")
            if not set(boundary.contacts) <= anchor_times:
                raise InvalidPatternError("a boundary contact is not one of the anchors")
        if self.breakout is not None and self.breakout.candle_close_time > self.evaluated_at:
            raise InvalidPatternError("a breakout candle that had not closed was used")
        self._check_content()

    def _check_content(self) -> None:
        state = self.state
        if len(set(self.invalidation_reasons)) != len(self.invalidation_reasons):
            raise InvalidPatternError("an invalidation reason is listed once")
        if bool(self.invalidation_reasons) != (state is PatternState.INVALIDATED):
            raise InvalidPatternError("invalidation reasons exist exactly when INVALIDATED")
        if bool(self.insufficient_data_reasons) != (state is PatternState.INSUFFICIENT_DATA):
            raise InvalidPatternError("insufficient-data reasons exist exactly when it is")
        if state in (PatternState.FORMING, PatternState.GEOMETRICALLY_VALID) and self.breakout:
            raise InvalidPatternError(f"{state.value} cannot carry a breakout")
        if state is PatternState.INSUFFICIENT_DATA and self.breakout is not None:
            raise InvalidPatternError("without enough data nothing is claimed about a breakout")
        needs_breakout = {
            PatternState.BREAKOUT_PENDING_CONFIRMATION,
            PatternState.CONFIRMED_UP,
            PatternState.CONFIRMED_DOWN,
            PatternState.FAILED_BREAKOUT,
        }
        if state in needs_breakout and self.breakout is None:
            raise InvalidPatternError(f"{state.value} is defined by a breakout: none was given")
        if self.breakout is not None:
            if state is PatternState.BREAKOUT_PENDING_CONFIRMATION and self.breakout.confirmed:
                raise InvalidPatternError("a pending breakout is not yet confirmed")
            if state in (PatternState.CONFIRMED_UP, PatternState.CONFIRMED_DOWN):
                wanted = (
                    BreakoutDirection.UP
                    if state is PatternState.CONFIRMED_UP
                    else (BreakoutDirection.DOWN)
                )
                if not self.breakout.confirmed or self.breakout.direction is not wanted:
                    raise InvalidPatternError(
                        f"{state.value} needs its breakout confirmed {wanted}"
                    )
        if state is PatternState.INSUFFICIENT_DATA:
            return
        if state not in (PatternState.FORMING, PatternState.INVALIDATED):
            if not self.boundaries:
                raise InvalidPatternError(f"{state.value} needs the boundaries it is judged on")
            if self.breakout is not None and self.breakout.boundary not in {
                boundary.role for boundary in self.boundaries
            }:
                raise InvalidPatternError("the breakout is through a boundary the figure lacks")


# -- the instance ---------------------------------------------------------------------------


def _effective_state(evaluations: Sequence[PatternEvaluation]) -> PatternState:
    """The last state that said something about the figure: INSUFFICIENT_DATA says only that the
    figure could not be judged, so the state it interrupted is what continues afterwards."""
    for evaluation in reversed(evaluations):
        if evaluation.state is not PatternState.INSUFFICIENT_DATA:
            return evaluation.state
    return PatternState.FORMING


def _check_step(before: Sequence[PatternEvaluation], current: PatternEvaluation) -> None:
    previous = before[-1]
    if previous.state in TERMINAL_STATES:
        raise InvalidPatternError(f"{previous.state.value} is final: nothing follows it")
    if current.evaluated_at <= previous.evaluated_at:
        raise InvalidPatternError("evaluations move strictly forward in time")
    if previous.as_of is not None and (current.as_of is None or current.as_of < previous.as_of):
        raise InvalidPatternError("a later evaluation cannot have read fewer candles")
    if current.candle_count < previous.candle_count:
        raise InvalidPatternError("the candle count cannot go down")
    if current.anchors[: len(previous.anchors)] != previous.anchors:
        raise InvalidPatternError(
            "anchors may only be added: any other change is another figure, another instance"
        )
    if current.state is PatternState.INSUFFICIENT_DATA:
        return
    effective = _effective_state(before)
    if current.state is not effective and current.state not in _NEXT[effective]:
        raise InvalidPatternError(f"{effective.value} cannot go to {current.state.value}")


def derive_pattern_instance_id(
    *,
    pattern_type: PatternType,
    instrument_id: str,
    data_source: str,
    timeframe: Timeframe,
    started_at: datetime,
    first_anchor_kind: PivotKind,
    detector_version: str,
    parameter_version: str,
    model_version: str = PATTERN_MODEL_VERSION,
) -> uuid.UUID:
    """The identity of a figure: what it is, where it starts and who found it. The same figure,
    found again by the same detector with the same parameters, is the same instance; a different
    starting point, detector or parameter version is another."""
    key = "|".join(
        (
            model_version,
            pattern_type.value,
            instrument_id,
            data_source,
            timeframe.value,
            _instant(started_at),
            first_anchor_kind.value,
            detector_version,
            parameter_version,
        )
    )
    return uuid.uuid5(_NAMESPACE, key)


@dataclass(frozen=True, slots=True)
class PatternInstance:
    """A concrete figure and its append-only history of evaluations."""

    pattern_type: PatternType
    instrument_id: str
    data_source: str
    timeframe: Timeframe
    detector_version: str
    parameter_version: str
    evaluations: tuple[PatternEvaluation, ...]
    model_version: str = PATTERN_MODEL_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.pattern_type, PatternType):
            raise InvalidPatternError("the pattern type must be one of the catalogue")
        for name in ("instrument_id", "data_source", "detector_version", "parameter_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidPatternError(f"{name} must be declared")
        if not self.evaluations:
            raise InvalidPatternError("an instance is born from an evaluation")
        for index, evaluation in enumerate(self.evaluations):
            if index:
                _check_step(self.evaluations[:index], evaluation)
        needed = self.definition.min_anchor_pivots
        for evaluation in self.evaluations:
            geometric = {
                PatternState.GEOMETRICALLY_VALID,
                PatternState.BREAKOUT_PENDING_CONFIRMATION,
                PatternState.CONFIRMED_UP,
                PatternState.CONFIRMED_DOWN,
                PatternState.FAILED_BREAKOUT,
            }
            if evaluation.state in geometric and len(evaluation.anchors) < needed:
                raise InvalidPatternError(
                    f"{self.pattern_type.value} needs {needed} anchors to be "
                    f"{evaluation.state.value}, it has {len(evaluation.anchors)}"
                )

    @property
    def definition(self) -> PatternDefinition:
        return PATTERN_CATALOGUE[self.pattern_type]

    @property
    def traditional_roles(self) -> frozenset[PatternRole]:
        return self.definition.traditional_roles

    @property
    def traditional_bias(self) -> PatternBias:
        return self.definition.traditional_bias

    @property
    def started_at(self) -> datetime:
        return self.evaluations[0].anchors[0].open_time

    @property
    def observed_at(self) -> datetime:
        """When the figure was first seen: the instant of its first evaluation."""
        return self.evaluations[0].evaluated_at

    @property
    def last_evaluated_at(self) -> datetime:
        return self.evaluations[-1].evaluated_at

    @property
    def latest(self) -> PatternEvaluation:
        return self.evaluations[-1]

    @property
    def state(self) -> PatternState:
        return self.latest.state

    @property
    def pattern_instance_id(self) -> uuid.UUID:
        return derive_pattern_instance_id(
            pattern_type=self.pattern_type,
            instrument_id=self.instrument_id,
            data_source=self.data_source,
            timeframe=self.timeframe,
            started_at=self.started_at,
            first_anchor_kind=self.evaluations[0].anchors[0].kind,
            detector_version=self.detector_version,
            parameter_version=self.parameter_version,
            model_version=self.model_version,
        )

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def resolved_with_tradition(self) -> bool | None:
        """Whether a confirmed breakout went the way tradition expects. None when there is no
        confirmed breakout or tradition does not say (breakout- or context-dependent)."""
        if self.state not in (PatternState.CONFIRMED_UP, PatternState.CONFIRMED_DOWN):
            return None
        bias = self.traditional_bias
        if bias is PatternBias.BULLISH:
            return self.state is PatternState.CONFIRMED_UP
        if bias is PatternBias.BEARISH:
            return self.state is PatternState.CONFIRMED_DOWN
        return None

    def advance(self, evaluation: PatternEvaluation) -> "PatternInstance":
        """The same figure one evaluation later. The earlier evaluations are untouched, and a
        change that is not a simple continuation raises: it is another instance."""
        return PatternInstance(
            self.pattern_type,
            self.instrument_id,
            self.data_source,
            self.timeframe,
            self.detector_version,
            self.parameter_version,
            (*self.evaluations, evaluation),
            self.model_version,
        )

    def document(self) -> dict[str, Any]:
        """The instance as plain JSON values: exact decimal text, UTC instants, no floats."""
        return {
            "model_version": self.model_version,
            "catalogue_version": PATTERN_CATALOGUE_VERSION,
            "pattern_instance_id": str(self.pattern_instance_id),
            "pattern_type": self.pattern_type.value,
            "traditional_roles": sorted(role.value for role in self.traditional_roles),
            "traditional_bias": self.traditional_bias.value,
            "instrument_id": self.instrument_id,
            "data_source": self.data_source,
            "timeframe": self.timeframe.value,
            "observed_at": _instant(self.observed_at),
            "started_at": _instant(self.started_at),
            "last_evaluated_at": _instant(self.last_evaluated_at),
            "state": self.state.value,
            "detector_version": self.detector_version,
            "parameter_version": self.parameter_version,
            "evaluations": [_evaluation_document(evaluation) for evaluation in self.evaluations],
        }


def start_pattern_instance(
    *,
    pattern_type: PatternType,
    instrument_id: str,
    data_source: str,
    timeframe: Timeframe,
    detector_version: str,
    parameter_version: str,
    first_evaluation: PatternEvaluation,
) -> PatternInstance:
    return PatternInstance(
        pattern_type,
        instrument_id,
        data_source,
        timeframe,
        detector_version,
        parameter_version,
        (first_evaluation,),
    )


# -- the document ---------------------------------------------------------------------------


def _instant(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _optional_instant(moment: datetime | None) -> str | None:
    return None if moment is None else _instant(moment)


def _parse_instant(text: str) -> datetime:
    moment = datetime.fromisoformat(text)
    if moment.utcoffset() != timedelta(0):
        raise InvalidPatternError(f"{text!r} is not a UTC instant")
    return moment.astimezone(UTC)


def _fact_value(value: EvidenceValue) -> dict[str, Any]:
    # The type travels with the value so a Decimal is never read back as text or a float.
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": value}
    if isinstance(value, Decimal):
        return {"type": "decimal", "value": str(value)}
    return {"type": "text", "value": value}


def _read_fact(document: Mapping[str, Any]) -> EvidenceValue:
    kind, value = document["type"], document["value"]
    if kind == "bool" and isinstance(value, bool):
        return value
    if kind == "int" and isinstance(value, int) and not isinstance(value, bool):
        return value
    if kind == "decimal" and isinstance(value, str):
        return Decimal(value)
    if kind == "text" and isinstance(value, str):
        return value
    raise InvalidPatternError(f"unreadable evidence fact: {document!r}")


def _evaluation_document(evaluation: PatternEvaluation) -> dict[str, Any]:
    breakout = evaluation.breakout
    return {
        "evaluated_at": _instant(evaluation.evaluated_at),
        "as_of": _optional_instant(evaluation.as_of),
        "candle_count": evaluation.candle_count,
        "state": evaluation.state.value,
        "anchors": [
            {
                "kind": anchor.kind.value,
                "open_time": _instant(anchor.open_time),
                "price": str(anchor.price),
                "confirmed_at": _instant(anchor.confirmed_at),
                "label": anchor.label,
            }
            for anchor in evaluation.anchors
        ],
        "boundaries": [
            {
                "role": boundary.role.value,
                "points": [
                    {"time": _instant(point.time), "price": str(point.price)}
                    for point in boundary.points
                ],
                "contacts": [_instant(contact) for contact in boundary.contacts],
            }
            for boundary in evaluation.boundaries
        ],
        "breakout": None
        if breakout is None
        else {
            "direction": breakout.direction.value,
            "boundary": breakout.boundary.value,
            "candle_open_time": _instant(breakout.candle_open_time),
            "candle_close_time": _instant(breakout.candle_close_time),
            "close_price": str(breakout.close_price),
            "confirmed": breakout.confirmed,
        },
        "invalidation_reasons": [reason.value for reason in evaluation.invalidation_reasons],
        "insufficient_data_reasons": [r.value for r in evaluation.insufficient_data_reasons],
        "evidence": [
            {
                "code": item.code,
                "detail": item.detail,
                "facts": {name: _fact_value(value) for name, value in item.facts},
            }
            for item in evaluation.evidence
        ],
    }


def _evaluation_from_document(document: Mapping[str, Any]) -> PatternEvaluation:
    breakout = document["breakout"]
    as_of = document["as_of"]
    return PatternEvaluation(
        evaluated_at=_parse_instant(document["evaluated_at"]),
        as_of=None if as_of is None else _parse_instant(as_of),
        candle_count=document["candle_count"],
        state=PatternState(document["state"]),
        anchors=tuple(
            AnchorPivot(
                kind=PivotKind(a["kind"]),
                open_time=_parse_instant(a["open_time"]),
                price=Decimal(a["price"]),
                confirmed_at=_parse_instant(a["confirmed_at"]),
                label=a["label"],
            )
            for a in document["anchors"]
        ),
        boundaries=tuple(
            Boundary(
                role=BoundaryRole(b["role"]),
                points=tuple(
                    BoundaryPoint(_parse_instant(p["time"]), Decimal(p["price"]))
                    for p in b["points"]
                ),
                contacts=tuple(_parse_instant(c) for c in b["contacts"]),
            )
            for b in document["boundaries"]
        ),
        breakout=None
        if breakout is None
        else Breakout(
            direction=BreakoutDirection(breakout["direction"]),
            boundary=BoundaryRole(breakout["boundary"]),
            candle_open_time=_parse_instant(breakout["candle_open_time"]),
            candle_close_time=_parse_instant(breakout["candle_close_time"]),
            close_price=Decimal(breakout["close_price"]),
            confirmed=breakout["confirmed"],
        ),
        invalidation_reasons=tuple(InvalidationReason(r) for r in document["invalidation_reasons"]),
        insufficient_data_reasons=tuple(
            MissingDataReason(r) for r in document["insufficient_data_reasons"]
        ),
        evidence=tuple(
            PatternEvidence(
                code=e["code"],
                detail=e["detail"],
                facts=tuple(sorted((name, _read_fact(v)) for name, v in e["facts"].items())),
            )
            for e in document["evidence"]
        ),
    )


def pattern_instance_from_document(document: Mapping[str, Any]) -> PatternInstance:
    """The inverse of `PatternInstance.document`: what was stored, exactly as it was stored.

    It reads and validates; it never derives or repairs. The identity written in the document
    must be the one the content gives, so a document cannot claim to be another figure.
    """
    try:
        if document["model_version"] != PATTERN_MODEL_VERSION:
            raise InvalidPatternError(f"unsupported model version {document['model_version']!r}")
        instance = PatternInstance(
            pattern_type=PatternType(document["pattern_type"]),
            instrument_id=document["instrument_id"],
            data_source=document["data_source"],
            timeframe=Timeframe(document["timeframe"]),
            detector_version=document["detector_version"],
            parameter_version=document["parameter_version"],
            evaluations=tuple(_evaluation_from_document(e) for e in document["evaluations"]),
            model_version=document["model_version"],
        )
        claimed = document["pattern_instance_id"]
    except (KeyError, TypeError, ValueError, ArithmeticError) as error:
        if isinstance(error, InvalidPatternError):
            raise
        raise InvalidPatternError(f"not a pattern instance document: {error!r}") from error
    if claimed != str(instance.pattern_instance_id):
        raise InvalidPatternError("the identity in the document is not the one its content gives")
    return instance
