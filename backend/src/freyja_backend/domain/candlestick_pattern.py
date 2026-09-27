"""Candlestick pattern instance model (POINT4-MODEL-001).

The contract lives in ``docs/domain/instancia-de-patron-de-vela.md`` (and, above it,
``docs/domain/patrones-de-vela.md``, which defines the twenty-three patterns this module knows).
It represents *one concrete pattern* found on the closed candles of one series, and how it
evolved. It is a **model, not a detector**: it decides nothing about whether a candle is really a
hammer; it makes sure that what a detector says is complete, coherent, free of look-ahead and
reconstructable.

A candle pattern instance is a *record*, like a chart pattern instance
(``chart_pattern.py``): immutable values that are built, stored and read back. Its history is
append-only. Each **evaluation** says what the detector saw at one instant (state, anchors,
reasons, evidence); a new evaluation of the same pattern is added, the earlier ones are never
rewritten. A substantial change (a different starting candle, or anchors that are not simply the
previous ones plus new ones) is **another instance** with its own identity.

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

from freyja_backend.domain.chart_pattern import EvidenceValue, PatternEvidence
from freyja_backend.domain.market_context import MissingDataReason
from freyja_backend.domain.market_data import Candle, Timeframe

# Bump on ANY change to what an instance contains, how it is written or how it may evolve.
CANDLE_PATTERN_MODEL_VERSION = "candle-pattern-instance-v1"
# Version of the catalogue of patterns (docs/domain/patrones-de-vela.md, v1).
CANDLE_PATTERN_CATALOGUE_VERSION = "candle-patterns-v1"

_NAMESPACE = uuid.UUID("8e4a2c60-5f91-4b3d-9a7e-2d6c1f8b0e35")
_CODE = re.compile(r"[A-Z][A-Z0-9_]*")


class InvalidCandlePatternError(ValueError):
    """A candle pattern instance, evaluation or document that contradicts itself."""


# -- the catalogue --------------------------------------------------------------------------


class CandleBias(enum.StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    CONTEXT_DEPENDENT = "CONTEXT_DEPENDENT"
    NONE = "NONE"


class CandlePatternType(enum.StrEnum):
    DOJI = "DOJI"
    DRAGONFLY_DOJI = "DRAGONFLY_DOJI"
    GRAVESTONE_DOJI = "GRAVESTONE_DOJI"
    HAMMER = "HAMMER"
    HANGING_MAN = "HANGING_MAN"
    INVERTED_HAMMER = "INVERTED_HAMMER"
    SHOOTING_STAR = "SHOOTING_STAR"
    BULLISH_PIN_BAR = "BULLISH_PIN_BAR"
    BEARISH_PIN_BAR = "BEARISH_PIN_BAR"
    BULLISH_ENGULFING = "BULLISH_ENGULFING"
    BEARISH_ENGULFING = "BEARISH_ENGULFING"
    BULLISH_HARAMI = "BULLISH_HARAMI"
    BEARISH_HARAMI = "BEARISH_HARAMI"
    TWEEZER_BOTTOM = "TWEEZER_BOTTOM"
    TWEEZER_TOP = "TWEEZER_TOP"
    PIERCING_PATTERN = "PIERCING_PATTERN"
    DARK_CLOUD_COVER = "DARK_CLOUD_COVER"
    MORNING_STAR = "MORNING_STAR"
    EVENING_STAR = "EVENING_STAR"
    THREE_WHITE_SOLDIERS = "THREE_WHITE_SOLDIERS"
    THREE_BLACK_CROWS = "THREE_BLACK_CROWS"
    THREE_INSIDE_UP = "THREE_INSIDE_UP"
    THREE_INSIDE_DOWN = "THREE_INSIDE_DOWN"


@dataclass(frozen=True, slots=True)
class CandlePatternDefinition:
    """What the contract says a pattern is, as data. `candle_count` is exact, never a minimum: a
    candle pattern is, by definition, a geometry of that many concrete candles, not more."""

    pattern_type: CandlePatternType
    candle_count: int
    traditional_bias: CandleBias
    # Whether the catalogue's own last candle already plays the confirming role (patrones-de-vela.md
    # section 5, column "Confirmación"). True for every three-candle pattern in v1; False otherwise.
    requires_confirmation: bool


_BULL, _BEAR = CandleBias.BULLISH, CandleBias.BEARISH
_CTX, _NONE = CandleBias.CONTEXT_DEPENDENT, CandleBias.NONE
_T = CandlePatternType

_DEFINITIONS: tuple[CandlePatternDefinition, ...] = tuple(
    CandlePatternDefinition(t, count, bias, confirms)
    for t, count, bias, confirms in (
        (_T.DOJI, 1, _NONE, False),
        (_T.DRAGONFLY_DOJI, 1, _CTX, False),
        (_T.GRAVESTONE_DOJI, 1, _CTX, False),
        (_T.HAMMER, 1, _CTX, False),
        (_T.HANGING_MAN, 1, _CTX, False),
        (_T.INVERTED_HAMMER, 1, _CTX, False),
        (_T.SHOOTING_STAR, 1, _CTX, False),
        (_T.BULLISH_PIN_BAR, 1, _CTX, False),
        (_T.BEARISH_PIN_BAR, 1, _CTX, False),
        (_T.BULLISH_ENGULFING, 2, _BULL, False),
        (_T.BEARISH_ENGULFING, 2, _BEAR, False),
        (_T.BULLISH_HARAMI, 2, _CTX, False),
        (_T.BEARISH_HARAMI, 2, _CTX, False),
        (_T.TWEEZER_BOTTOM, 2, _CTX, False),
        (_T.TWEEZER_TOP, 2, _CTX, False),
        (_T.PIERCING_PATTERN, 2, _BULL, False),
        (_T.DARK_CLOUD_COVER, 2, _BEAR, False),
        (_T.MORNING_STAR, 3, _BULL, True),
        (_T.EVENING_STAR, 3, _BEAR, True),
        (_T.THREE_WHITE_SOLDIERS, 3, _BULL, True),
        (_T.THREE_BLACK_CROWS, 3, _BEAR, True),
        (_T.THREE_INSIDE_UP, 3, _BULL, True),
        (_T.THREE_INSIDE_DOWN, 3, _BEAR, True),
    )
)

# The twenty-three approved patterns, and only those. Read-only.
CANDLE_PATTERN_CATALOGUE: Mapping[CandlePatternType, CandlePatternDefinition] = MappingProxyType(
    {definition.pattern_type: definition for definition in _DEFINITIONS}
)


# -- lifecycle ------------------------------------------------------------------------------


class CandlePatternState(enum.StrEnum):
    FORMING = "FORMING"
    MORPHOLOGICALLY_VALID = "MORPHOLOGICALLY_VALID"
    CONTEXT_VALID = "CONTEXT_VALID"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    INVALIDATED = "INVALIDATED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


_S = CandlePatternState
TERMINAL_STATES = frozenset({_S.FAILED, _S.INVALIDATED})

# From each state, the states an evaluation may move to (staying is always allowed unless the
# state is terminal). Forward only, but not necessarily one step at a time: a pattern whose own
# last candle is already its confirmation (every pattern in the v1 catalogue) can go straight from
# CONTEXT_VALID to CONFIRMED without stopping at PENDING_CONFIRMATION (see the model doc, section
# 3). INSUFFICIENT_DATA is handled apart: see `_check_step`.
_RESOLVED = frozenset({_S.CONFIRMED, _S.FAILED})
_NEXT: Mapping[CandlePatternState, frozenset[CandlePatternState]] = MappingProxyType(
    {
        _S.FORMING: frozenset(
            {_S.MORPHOLOGICALLY_VALID, _S.CONTEXT_VALID, _S.PENDING_CONFIRMATION, _S.INVALIDATED}
            | _RESOLVED
        ),
        _S.MORPHOLOGICALLY_VALID: frozenset(
            {_S.CONTEXT_VALID, _S.PENDING_CONFIRMATION, _S.INVALIDATED} | _RESOLVED
        ),
        _S.CONTEXT_VALID: frozenset({_S.PENDING_CONFIRMATION, _S.INVALIDATED} | _RESOLVED),
        _S.PENDING_CONFIRMATION: frozenset({_S.INVALIDATED} | _RESOLVED),
        _S.CONFIRMED: frozenset({_S.INVALIDATED}),
        _S.FAILED: frozenset(),
        _S.INVALIDATED: frozenset(),
    }
)

# States at which the catalogue's exact candle_count must already be met (FORMING may have fewer;
# INVALIDATED and INSUFFICIENT_DATA are exempt, see CandlePatternInstance.__post_init__).
_GEOMETRIC_OR_LATER = frozenset(
    {_S.MORPHOLOGICALLY_VALID, _S.CONTEXT_VALID, _S.PENDING_CONFIRMATION, _S.CONFIRMED, _S.FAILED}
)


class InvalidationReason(enum.StrEnum):
    """Why a pattern stopped being one. Recorded, never inferred later."""

    GEOMETRY_BROKEN = "GEOMETRY_BROKEN"
    # Context resolved a shared-geometry pair (HAMMER/HANGING_MAN...) in favour of the other name.
    SUPERSEDED = "SUPERSEDED"


# -- what an evaluation is made of ----------------------------------------------------------


def _require_utc(moment: object, name: str) -> datetime:
    if not isinstance(moment, datetime) or moment.utcoffset() != timedelta(0):
        raise InvalidCandlePatternError(f"{name} must be a timezone-aware UTC datetime")
    return moment


def _require_price(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise InvalidCandlePatternError(f"{name} must be a positive exact Decimal, never a float")
    return value


@dataclass(frozen=True, slots=True)
class CandleAnchor:
    """One closed candle the pattern rests on, with the part it plays (e.g. `FIRST`). Body,
    range and wicks are derived, never stored, so they can never diverge from the OHLC."""

    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    label: str

    def __post_init__(self) -> None:
        _require_utc(self.open_time, "anchor open_time")
        _require_utc(self.close_time, "anchor close_time")
        if self.close_time <= self.open_time:
            raise InvalidCandlePatternError("an anchor candle closes after it opens")
        for name in ("open", "high", "low", "close"):
            _require_price(getattr(self, name), f"anchor {name}")
        if self.high < max(self.open, self.close, self.low) or self.low > min(
            self.open, self.close, self.high
        ):
            raise InvalidCandlePatternError("inconsistent OHLC: high/low do not bound open/close")
        if not _CODE.fullmatch(self.label):
            raise InvalidCandlePatternError("an anchor label is an UPPER_SNAKE_CASE code")

    @property
    def body(self) -> Decimal:
        return abs(self.close - self.open)

    @property
    def range(self) -> Decimal:
        return self.high - self.low

    @property
    def upper_wick(self) -> Decimal:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> Decimal:
        return min(self.open, self.close) - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @classmethod
    def from_candle(cls, candle: Candle, label: str) -> Self:
        return cls(
            candle.open_time,
            candle.close_time,
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            label,
        )


@dataclass(frozen=True, slots=True)
class CandlePatternEvaluation:
    """What the detector saw at one instant. Complete on its own: it names every anchor it used,
    so nothing has to be looked up later to understand it."""

    # The instant of the evaluation: only what was knowable by then was read.
    evaluated_at: datetime
    # Close of the newest closed candle read; None only if there was none.
    as_of: datetime | None
    state: CandlePatternState
    anchors: tuple[CandleAnchor, ...]
    invalidation_reasons: tuple[InvalidationReason, ...] = ()
    insufficient_data_reasons: tuple[MissingDataReason, ...] = ()
    evidence: tuple[PatternEvidence, ...] = ()

    def __post_init__(self) -> None:
        _require_utc(self.evaluated_at, "evaluated_at")
        if self.as_of is not None:
            _require_utc(self.as_of, "as_of")
            if self.as_of > self.evaluated_at:
                raise InvalidCandlePatternError(
                    "a candle that closes after the evaluation was read"
                )
        if not self.anchors:
            raise InvalidCandlePatternError(
                "a pattern has at least one anchor: without one there is none"
            )
        opens = [anchor.open_time for anchor in self.anchors]
        if any(later <= earlier for earlier, later in pairwise(opens)):
            raise InvalidCandlePatternError("anchors are in strict chronological order")
        for anchor in self.anchors:
            if anchor.close_time > self.evaluated_at:
                raise InvalidCandlePatternError("an anchor candle that had not closed was used")
        self._check_content()

    def _check_content(self) -> None:
        state = self.state
        if len(set(self.invalidation_reasons)) != len(self.invalidation_reasons):
            raise InvalidCandlePatternError("an invalidation reason is listed once")
        if bool(self.invalidation_reasons) != (state is CandlePatternState.INVALIDATED):
            raise InvalidCandlePatternError("invalidation reasons exist exactly when INVALIDATED")
        if bool(self.insufficient_data_reasons) != (state is CandlePatternState.INSUFFICIENT_DATA):
            raise InvalidCandlePatternError("insufficient-data reasons exist exactly when it is")
        needs_context = {
            CandlePatternState.CONTEXT_VALID,
            CandlePatternState.PENDING_CONFIRMATION,
            CandlePatternState.CONFIRMED,
            CandlePatternState.FAILED,
        }
        if state in needs_context and "CONTEXT" not in {item.code for item in self.evidence}:
            raise InvalidCandlePatternError(f"{state.value} needs its CONTEXT evidence recorded")


# -- the instance ---------------------------------------------------------------------------


def _effective_state(evaluations: Sequence[CandlePatternEvaluation]) -> CandlePatternState:
    """The last state that said something about the pattern: INSUFFICIENT_DATA says only that it
    could not be judged, so the state it interrupted is what continues afterwards."""
    for evaluation in reversed(evaluations):
        if evaluation.state is not CandlePatternState.INSUFFICIENT_DATA:
            return evaluation.state
    return CandlePatternState.FORMING


def _check_step(
    before: Sequence[CandlePatternEvaluation], current: CandlePatternEvaluation
) -> None:
    previous = before[-1]
    if previous.state in TERMINAL_STATES:
        raise InvalidCandlePatternError(f"{previous.state.value} is final: nothing follows it")
    if current.evaluated_at <= previous.evaluated_at:
        raise InvalidCandlePatternError("evaluations move strictly forward in time")
    if previous.as_of is not None and (current.as_of is None or current.as_of < previous.as_of):
        raise InvalidCandlePatternError("a later evaluation cannot have read fewer candles")
    if current.anchors[: len(previous.anchors)] != previous.anchors:
        raise InvalidCandlePatternError(
            "anchors may only be added: any other change is another pattern, another instance"
        )
    if current.state is CandlePatternState.INSUFFICIENT_DATA:
        return
    effective = _effective_state(before)
    if current.state is not effective and current.state not in _NEXT[effective]:
        raise InvalidCandlePatternError(f"{effective.value} cannot go to {current.state.value}")


def derive_candle_pattern_instance_id(
    *,
    pattern_type: CandlePatternType,
    instrument_id: str,
    data_source: str,
    timeframe: Timeframe,
    started_at: datetime,
    detector_version: str,
    parameter_version: str,
    model_version: str = CANDLE_PATTERN_MODEL_VERSION,
) -> uuid.UUID:
    """The identity of a pattern: what it is, where it starts and who found it. The same pattern,
    found again by the same detector with the same parameters, is the same instance; a different
    starting candle, detector or parameter version is another."""
    key = "|".join(
        (
            model_version,
            pattern_type.value,
            instrument_id,
            data_source,
            timeframe.value,
            _instant(started_at),
            detector_version,
            parameter_version,
        )
    )
    return uuid.uuid5(_NAMESPACE, key)


@dataclass(frozen=True, slots=True)
class CandlePatternInstance:
    """A concrete candle pattern and its append-only history of evaluations."""

    pattern_type: CandlePatternType
    instrument_id: str
    data_source: str
    timeframe: Timeframe
    detector_version: str
    parameter_version: str
    evaluations: tuple[CandlePatternEvaluation, ...]
    model_version: str = CANDLE_PATTERN_MODEL_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.pattern_type, CandlePatternType):
            raise InvalidCandlePatternError("the pattern type must be one of the catalogue")
        for name in ("instrument_id", "data_source", "detector_version", "parameter_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidCandlePatternError(f"{name} must be declared")
        if not self.evaluations:
            raise InvalidCandlePatternError("an instance is born from an evaluation")
        for index, evaluation in enumerate(self.evaluations):
            if index:
                _check_step(self.evaluations[:index], evaluation)
        needed = self.definition.candle_count
        for evaluation in self.evaluations:
            count = len(evaluation.anchors)
            if count > needed:
                raise InvalidCandlePatternError(
                    f"{self.pattern_type.value} is exactly {needed} candles: it cannot have more"
                )
            if evaluation.state in _GEOMETRIC_OR_LATER and count != needed:
                raise InvalidCandlePatternError(
                    f"{self.pattern_type.value} needs exactly {needed} anchors to be "
                    f"{evaluation.state.value}, it has {count}"
                )

    @property
    def definition(self) -> CandlePatternDefinition:
        return CANDLE_PATTERN_CATALOGUE[self.pattern_type]

    @property
    def traditional_bias(self) -> CandleBias:
        return self.definition.traditional_bias

    @property
    def requires_confirmation(self) -> bool:
        return self.definition.requires_confirmation

    @property
    def started_at(self) -> datetime:
        return self.evaluations[0].anchors[0].open_time

    @property
    def observed_at(self) -> datetime:
        """When the pattern was first seen: the instant of its first evaluation."""
        return self.evaluations[0].evaluated_at

    @property
    def last_evaluated_at(self) -> datetime:
        return self.evaluations[-1].evaluated_at

    @property
    def latest(self) -> CandlePatternEvaluation:
        return self.evaluations[-1]

    @property
    def state(self) -> CandlePatternState:
        return self.latest.state

    @property
    def candle_pattern_instance_id(self) -> uuid.UUID:
        return derive_candle_pattern_instance_id(
            pattern_type=self.pattern_type,
            instrument_id=self.instrument_id,
            data_source=self.data_source,
            timeframe=self.timeframe,
            started_at=self.started_at,
            detector_version=self.detector_version,
            parameter_version=self.parameter_version,
            model_version=self.model_version,
        )

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def advance(self, evaluation: CandlePatternEvaluation) -> "CandlePatternInstance":
        """The same pattern one evaluation later. The earlier evaluations are untouched, and a
        change that is not a simple continuation raises: it is another instance."""
        return CandlePatternInstance(
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
            "catalogue_version": CANDLE_PATTERN_CATALOGUE_VERSION,
            "candle_pattern_instance_id": str(self.candle_pattern_instance_id),
            "pattern_type": self.pattern_type.value,
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


def start_candle_pattern_instance(
    *,
    pattern_type: CandlePatternType,
    instrument_id: str,
    data_source: str,
    timeframe: Timeframe,
    detector_version: str,
    parameter_version: str,
    first_evaluation: CandlePatternEvaluation,
) -> CandlePatternInstance:
    return CandlePatternInstance(
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
        raise InvalidCandlePatternError(f"{text!r} is not a UTC instant")
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
    raise InvalidCandlePatternError(f"unreadable evidence fact: {document!r}")


def _anchor_document(anchor: CandleAnchor) -> dict[str, Any]:
    return {
        "open_time": _instant(anchor.open_time),
        "close_time": _instant(anchor.close_time),
        "open": str(anchor.open),
        "high": str(anchor.high),
        "low": str(anchor.low),
        "close": str(anchor.close),
        "label": anchor.label,
    }


def _evaluation_document(evaluation: CandlePatternEvaluation) -> dict[str, Any]:
    return {
        "evaluated_at": _instant(evaluation.evaluated_at),
        "as_of": _optional_instant(evaluation.as_of),
        "state": evaluation.state.value,
        "anchors": [_anchor_document(anchor) for anchor in evaluation.anchors],
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


def _anchor_from_document(document: Mapping[str, Any]) -> CandleAnchor:
    return CandleAnchor(
        open_time=_parse_instant(document["open_time"]),
        close_time=_parse_instant(document["close_time"]),
        open=Decimal(document["open"]),
        high=Decimal(document["high"]),
        low=Decimal(document["low"]),
        close=Decimal(document["close"]),
        label=document["label"],
    )


def _evaluation_from_document(document: Mapping[str, Any]) -> CandlePatternEvaluation:
    as_of = document["as_of"]
    return CandlePatternEvaluation(
        evaluated_at=_parse_instant(document["evaluated_at"]),
        as_of=None if as_of is None else _parse_instant(as_of),
        state=CandlePatternState(document["state"]),
        anchors=tuple(_anchor_from_document(a) for a in document["anchors"]),
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


def candle_pattern_instance_from_document(document: Mapping[str, Any]) -> CandlePatternInstance:
    """The inverse of `CandlePatternInstance.document`: what was stored, exactly as it was stored.

    It reads and validates; it never derives or repairs. The identity written in the document
    must be the one the content gives, so a document cannot claim to be another pattern.
    """
    try:
        if document["model_version"] != CANDLE_PATTERN_MODEL_VERSION:
            raise InvalidCandlePatternError(
                f"unsupported model version {document['model_version']!r}"
            )
        instance = CandlePatternInstance(
            pattern_type=CandlePatternType(document["pattern_type"]),
            instrument_id=document["instrument_id"],
            data_source=document["data_source"],
            timeframe=Timeframe(document["timeframe"]),
            detector_version=document["detector_version"],
            parameter_version=document["parameter_version"],
            evaluations=tuple(_evaluation_from_document(e) for e in document["evaluations"]),
            model_version=document["model_version"],
        )
        claimed = document["candle_pattern_instance_id"]
    except (KeyError, TypeError, ValueError, ArithmeticError) as error:
        if isinstance(error, InvalidCandlePatternError):
            raise
        raise InvalidCandlePatternError(
            f"not a candle pattern instance document: {error!r}"
        ) from error
    if claimed != str(instance.candle_pattern_instance_id):
        raise InvalidCandlePatternError(
            "the identity in the document is not the one its content gives"
        )
    return instance
