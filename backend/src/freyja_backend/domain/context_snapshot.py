"""Snapshot of the context a hypothesis was evaluated in (POINT2-SNAPSHOT-001).

The contract lives in ``docs/domain/instantanea-de-contexto.md`` (and, above it,
``docs/domain/contexto-y-tendencia.md`` section 7). A `ContextSnapshot` is the exact picture
Freyja had at one instant: the observable context and trend of both timeframes, and what a
trend policy made of them. It is a *record*: an immutable value that is built once, stored as
it is and read back as it is. Nothing here reads a database, the clock or a provider, and
reading a snapshot never recomputes anything: a later reclassification produces a new
snapshot and leaves this one alone.

Two sections are kept apart on purpose. What was *observed* (both timeframes, the session,
the data state) is what the market showed. What was *judged* (the policy, the relationship,
the outcome and the reasons) is what the policy made of it. Neither holds a side, an entry,
an order, a confidence or a position: the decision and its execution belong to later layers
and are never mixed into this record.

The snapshot is identified by its content: the same observation, judged by the same policy,
always has the same `content_hash` and `snapshot_id`; only `computed_at`, the wall-clock
moment it was made, is left out of it.
"""

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from freyja_backend.domain.market_calendar import MarketSchedule, MarketSession
from freyja_backend.domain.market_context import (
    DataFreshness,
    MissingDataReason,
    ObservableContext,
    build_observable_context,
)
from freyja_backend.domain.market_data import (
    DEFAULT_PUBLICATION_GRACE,
    Candle,
    DataQuality,
    InstrumentRef,
    Timeframe,
)
from freyja_backend.domain.market_structure import (
    DEFAULT_PIVOT_PARAMS,
    MIN_HISTORY_CANDLES,
    Pivot,
    PivotKind,
    PivotParams,
    PivotStatus,
)
from freyja_backend.domain.market_trend import (
    DEFAULT_TREND_PARAMS,
    EvidenceCode,
    InsufficientDataReason,
    TrendClassification,
    TrendEvidence,
    TrendParams,
    TrendState,
    TrendTimeframes,
    classify_trend_pair,
)
from freyja_backend.domain.trend_policy import (
    Orientation,
    PolicyEvaluation,
    PolicyOutcome,
    PolicyReason,
    TrendPolicy,
    TrendRelationship,
    evaluate_trend_policy,
)

# Bump on ANY change to what a snapshot contains or how it is written, so a stored one can
# always be traced to the exact format that produced it.
CONTEXT_SNAPSHOT_VERSION = "context-snapshot-v1"

_NAMESPACE = uuid.UUID("6f0e3a5c-1d6b-5c0e-9a55-2f2a0c4d7b10")


class InvalidContextSnapshotError(ValueError):
    """A snapshot that contradicts itself, or a document that is not one. It cannot exist."""


@dataclass(frozen=True, slots=True)
class SwingSnapshot:
    """A confirmed swing point the state rests on, exactly as it was read."""

    kind: PivotKind
    open_time: datetime
    price: Decimal
    confirmed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ObservedTimeframe:
    """What one timeframe's series showed at the instant of the observation."""

    timeframe: Timeframe
    trend: TrendState
    # Close of the newest closed candle that was read; None if there was none.
    as_of: datetime | None
    window_candles: int
    data_freshness: DataFreshness
    data_quality: DataQuality
    # Why the data was not fit, and why there is no classification. Both kept, so an
    # INSUFFICIENT_DATA is never just a label.
    missing_data_reasons: tuple[MissingDataReason, ...]
    insufficient_data_reasons: tuple[InsufficientDataReason, ...]
    swings: tuple[SwingSnapshot, ...]
    evidence: tuple[TrendEvidence, ...]
    # The parameters the swings were read with, so the state can be reproduced.
    window_swings: int
    significance: Decimal
    pivot_k: int


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    snapshot_version: str
    instrument_id: str
    data_source: str
    product_type: str
    # The instant the observation is about. Only candles closed at or before it were read.
    observed_at: datetime
    # The wall-clock moment the snapshot was made. Never part of the content hash.
    computed_at: datetime
    # -- observed ------------------------------------------------------------------
    signal: ObservedTimeframe
    context: ObservedTimeframe
    market_open: bool | None
    # Only Forex has named sessions; None is "not applicable", never a borrowed one.
    market_session: MarketSession | None
    weekday_utc: int
    hour_utc: int
    timezone: str
    calendar_version: str | None
    context_version: str
    structure_version: str
    trend_definition_version: str
    # -- judged --------------------------------------------------------------------
    # None only when the strategy had no policy to be judged by.
    policy_version: str | None
    required_relationship: TrendRelationship | None
    orientation: Orientation
    outcome: PolicyOutcome
    # Empty exactly when the outcome is COMPATIBLE: each reason says why it is not.
    reasons: tuple[PolicyReason, ...]
    evaluation_version: str
    # A person-readable account of the two sections, in the words of the codes above.
    explanation: str

    def __post_init__(self) -> None:
        for name in ("observed_at", "computed_at"):
            moment = getattr(self, name)
            if not isinstance(moment, datetime) or moment.utcoffset() != timedelta(0):
                raise InvalidContextSnapshotError(f"{name} must be a timezone-aware UTC datetime")
        if self.computed_at < self.observed_at:
            raise InvalidContextSnapshotError(
                "a snapshot cannot be computed before the instant it observes"
            )
        if self.context.timeframe.duration < self.signal.timeframe.duration:
            raise InvalidContextSnapshotError(
                "the context timeframe must not be finer than the signal timeframe"
            )
        if bool(self.reasons) != (self.outcome is not PolicyOutcome.COMPATIBLE):
            raise InvalidContextSnapshotError(
                "reasons must be empty exactly when the outcome is COMPATIBLE"
            )
        if (self.policy_version is None) != (self.required_relationship is None):
            raise InvalidContextSnapshotError(
                "the policy version and the required relationship come together or not at all"
            )
        if not self.explanation.strip():
            raise InvalidContextSnapshotError("a snapshot must carry its explanation")

    @property
    def context_compatible(self) -> bool | None:
        """True or False when the policy could judge; None when it lacked the context to."""
        if self.outcome is PolicyOutcome.INSUFFICIENT_CONTEXT:
            return None
        return self.outcome is PolicyOutcome.COMPATIBLE

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(_canonical(self.document(include_computed_at=False))).hexdigest()

    @property
    def snapshot_id(self) -> uuid.UUID:
        return uuid.uuid5(_NAMESPACE, self.content_hash)

    def document(self, *, include_computed_at: bool = True) -> dict[str, Any]:
        """The snapshot as plain JSON values. Prices are exact decimal text, times are UTC."""
        document: dict[str, Any] = {
            "snapshot_version": self.snapshot_version,
            "instrument_id": self.instrument_id,
            "data_source": self.data_source,
            "product_type": self.product_type,
            "observed_at": _instant(self.observed_at),
            "observed": {
                "signal": _observed_document(self.signal),
                "context": _observed_document(self.context),
                "market_open": self.market_open,
                "market_session": None
                if self.market_session is None
                else self.market_session.value,
                "weekday_utc": self.weekday_utc,
                "hour_utc": self.hour_utc,
                "timezone": self.timezone,
                "calendar_version": self.calendar_version,
                "context_version": self.context_version,
                "structure_version": self.structure_version,
                "trend_definition_version": self.trend_definition_version,
            },
            "judged": {
                "policy_version": self.policy_version,
                "required_relationship": (
                    None if self.required_relationship is None else self.required_relationship.value
                ),
                "orientation": self.orientation.value,
                "outcome": self.outcome.value,
                "context_compatible": self.context_compatible,
                "reasons": [reason.value for reason in self.reasons],
                "evaluation_version": self.evaluation_version,
            },
            "explanation": self.explanation,
        }
        if include_computed_at:
            document["computed_at"] = _instant(self.computed_at)
        return document


def snapshot_from_document(
    document: Mapping[str, Any], *, computed_at: datetime | None = None
) -> ContextSnapshot:
    """The inverse of `ContextSnapshot.document`: what was stored, exactly as it was stored.

    It reads, it never derives: no trend is recomputed and no default fills a missing field.
    A document that lacks a field or carries an unknown value raises
    `InvalidContextSnapshotError`. The document of a stored snapshot leaves `computed_at` out
    (it is not part of its content) and keeps it in a column: pass it as `computed_at`.
    """
    if computed_at is not None and "computed_at" in document:
        raise InvalidContextSnapshotError("computed_at is given twice: in the document and apart")
    try:
        observed = document["observed"]
        judged = document["judged"]
        relationship = judged["required_relationship"]
        session = observed["market_session"]
        snapshot = ContextSnapshot(
            snapshot_version=document["snapshot_version"],
            instrument_id=document["instrument_id"],
            data_source=document["data_source"],
            product_type=document["product_type"],
            observed_at=_parse_instant(document["observed_at"]),
            computed_at=(
                _parse_instant(document["computed_at"]) if computed_at is None else computed_at
            ),
            signal=_observed_from_document(observed["signal"]),
            context=_observed_from_document(observed["context"]),
            market_open=observed["market_open"],
            market_session=None if session is None else MarketSession(session),
            weekday_utc=observed["weekday_utc"],
            hour_utc=observed["hour_utc"],
            timezone=observed["timezone"],
            calendar_version=observed["calendar_version"],
            context_version=observed["context_version"],
            structure_version=observed["structure_version"],
            trend_definition_version=observed["trend_definition_version"],
            policy_version=judged["policy_version"],
            required_relationship=None if relationship is None else TrendRelationship(relationship),
            orientation=Orientation(judged["orientation"]),
            outcome=PolicyOutcome(judged["outcome"]),
            reasons=tuple(PolicyReason(reason) for reason in judged["reasons"]),
            evaluation_version=judged["evaluation_version"],
            explanation=document["explanation"],
        )
    except (KeyError, TypeError, ValueError, ArithmeticError) as error:
        if isinstance(error, InvalidContextSnapshotError):
            raise
        raise InvalidContextSnapshotError(f"not a context snapshot document: {error!r}") from error
    return snapshot


def capture_context_snapshot(
    *,
    timeframes: TrendTimeframes,
    policy: TrendPolicy | None,
    orientation: Orientation,
    signal_candles: Sequence[Candle],
    context_candles: Sequence[Candle],
    instrument_id: str,
    instrument: InstrumentRef,
    schedule: MarketSchedule,
    observed_at: datetime,
    computed_at: datetime,
    data_source: str,
    authorized_sources: frozenset[str],
    pivot_params: PivotParams = DEFAULT_PIVOT_PARAMS,
    params: TrendParams = DEFAULT_TREND_PARAMS,
    min_history: int = MIN_HISTORY_CANDLES,
    publication_grace: timedelta = DEFAULT_PUBLICATION_GRACE,
) -> ContextSnapshot:
    """Observe both timeframes at `observed_at`, let `policy` judge them, and record it all.

    Each timeframe is read from its own candles and only from candles closed at
    `observed_at`, so nothing that happened later can reach the snapshot. Bad data never
    raises: it is recorded as INSUFFICIENT_DATA with its reasons, and a missing policy as
    INSUFFICIENT_CONTEXT. Only a wrong request (a naive instant, impossible parameters)
    raises.
    """
    pair = classify_trend_pair(
        timeframes=timeframes,
        signal_candles=signal_candles,
        context_candles=context_candles,
        instrument_id=instrument_id,
        instrument=instrument,
        schedule=schedule,
        observed_at=observed_at,
        data_source=data_source,
        authorized_sources=authorized_sources,
        pivot_params=pivot_params,
        params=params,
        min_history=min_history,
        publication_grace=publication_grace,
    )
    evaluation = evaluate_trend_policy(policy, orientation=orientation, pair=pair)

    def observable(timeframe: Timeframe, candles: Sequence[Candle]) -> ObservableContext:
        # As in the classifier: a series is observed on its own, as signal and as context.
        return build_observable_context(
            instrument_id=instrument_id,
            instrument=instrument,
            schedule=schedule,
            signal_timeframe=timeframe,
            context_timeframe=timeframe,
            observed_at=observed_at,
            data_source=data_source,
            authorized_sources=authorized_sources,
            candles=candles,
            min_history=min_history,
            publication_grace=publication_grace,
        )

    signal_observable = observable(timeframes.signal, signal_candles)
    context_observable = observable(timeframes.context, context_candles)
    signal = _observe(pair.signal, signal_observable)
    context = _observe(pair.context, context_observable)
    return ContextSnapshot(
        snapshot_version=CONTEXT_SNAPSHOT_VERSION,
        instrument_id=instrument_id,
        data_source=data_source,
        product_type=context_observable.product_type,
        observed_at=observed_at,
        computed_at=computed_at,
        signal=signal,
        context=context,
        market_open=context_observable.market_open,
        market_session=context_observable.market_session,
        weekday_utc=context_observable.weekday_utc,
        hour_utc=context_observable.hour_utc,
        timezone=context_observable.timezone,
        calendar_version=context_observable.calendar_version,
        context_version=context_observable.context_version,
        structure_version=pair.context.structure_version,
        trend_definition_version=pair.context.definition_version,
        policy_version=evaluation.policy_version,
        required_relationship=evaluation.relationship,
        orientation=evaluation.orientation,
        outcome=evaluation.outcome,
        reasons=evaluation.reasons,
        evaluation_version=evaluation.evaluation_version,
        explanation=_explain(signal, context, evaluation),
    )


# -- observing ------------------------------------------------------------------------------


def _observe(
    classification: TrendClassification, observable: ObservableContext
) -> ObservedTimeframe:
    return ObservedTimeframe(
        timeframe=classification.timeframe,
        trend=classification.state,
        as_of=classification.as_of,
        window_candles=classification.window_candles,
        data_freshness=observable.data_freshness,
        data_quality=observable.data_quality_status,
        missing_data_reasons=observable.missing_data_reasons,
        insufficient_data_reasons=classification.insufficient_data_reasons,
        swings=tuple(_swing(pivot) for pivot in classification.confirmed_swings),
        evidence=classification.evidence,
        window_swings=classification.params.window_swings,
        significance=classification.params.significance,
        pivot_k=classification.pivot_params.k,
    )


def _swing(pivot: Pivot) -> SwingSnapshot:
    # The swings a state rests on are always confirmed; a provisional one is never evidence.
    if pivot.status is not PivotStatus.CONFIRMED:
        raise InvalidContextSnapshotError("a provisional swing cannot be recorded as evidence")
    return SwingSnapshot(pivot.kind, pivot.open_time, pivot.price, pivot.confirmed_at)


def _explain(
    signal: ObservedTimeframe, context: ObservedTimeframe, evaluation: PolicyEvaluation
) -> str:
    parts = [_describe("signal", signal), _describe("context", context)]
    if evaluation.policy_version is None:
        parts.append("no trend policy was declared, so the hypothesis cannot be judged")
    else:
        judged = (
            f"policy {evaluation.policy_version} ({_value(evaluation.relationship)}) judged a "
            f"{evaluation.orientation.value} hypothesis {evaluation.outcome.value}"
        )
        if evaluation.reasons:
            judged += ": " + ", ".join(reason.value for reason in evaluation.reasons)
        parts.append(judged)
    return "; ".join(parts) + "."


def _describe(role: str, observed: ObservedTimeframe) -> str:
    text = f"{role} {observed.timeframe.value} is {observed.trend.value}"
    reasons = [reason.value for reason in observed.insufficient_data_reasons]
    if reasons:
        text += " (" + ", ".join(reasons) + ")"
    return text


def _value(relationship: TrendRelationship | None) -> str:
    return "no relationship" if relationship is None else relationship.value


# -- the document ---------------------------------------------------------------------------


def _canonical(document: Mapping[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _instant(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_instant(text: str) -> datetime:
    moment = datetime.fromisoformat(text)
    if moment.utcoffset() != timedelta(0):
        raise InvalidContextSnapshotError(f"{text!r} is not a UTC instant")
    return moment.astimezone(UTC)


def _optional_instant(moment: datetime | None) -> str | None:
    return None if moment is None else _instant(moment)


def _observed_document(observed: ObservedTimeframe) -> dict[str, Any]:
    return {
        "timeframe": observed.timeframe.value,
        "trend": observed.trend.value,
        "as_of": _optional_instant(observed.as_of),
        "window_candles": observed.window_candles,
        "data_freshness": observed.data_freshness.value,
        "data_quality": observed.data_quality.value,
        "missing_data_reasons": [reason.value for reason in observed.missing_data_reasons],
        "insufficient_data_reasons": [r.value for r in observed.insufficient_data_reasons],
        "swings": [
            {
                "kind": swing.kind.value,
                "open_time": _instant(swing.open_time),
                "price": str(swing.price),
                "confirmed_at": _optional_instant(swing.confirmed_at),
            }
            for swing in observed.swings
        ],
        "evidence": [{"code": e.code.value, "detail": e.detail} for e in observed.evidence],
        "window_swings": observed.window_swings,
        "significance": str(observed.significance),
        "pivot_k": observed.pivot_k,
    }


def _observed_from_document(document: Mapping[str, Any]) -> ObservedTimeframe:
    as_of = document["as_of"]
    return ObservedTimeframe(
        timeframe=Timeframe(document["timeframe"]),
        trend=TrendState(document["trend"]),
        as_of=None if as_of is None else _parse_instant(as_of),
        window_candles=document["window_candles"],
        data_freshness=DataFreshness(document["data_freshness"]),
        data_quality=DataQuality(document["data_quality"]),
        missing_data_reasons=tuple(MissingDataReason(r) for r in document["missing_data_reasons"]),
        insufficient_data_reasons=tuple(
            InsufficientDataReason(r) for r in document["insufficient_data_reasons"]
        ),
        swings=tuple(
            SwingSnapshot(
                kind=PivotKind(swing["kind"]),
                open_time=_parse_instant(swing["open_time"]),
                price=Decimal(swing["price"]),
                confirmed_at=(
                    None if swing["confirmed_at"] is None else _parse_instant(swing["confirmed_at"])
                ),
            )
            for swing in document["swings"]
        ),
        evidence=tuple(
            TrendEvidence(EvidenceCode(e["code"]), e["detail"]) for e in document["evidence"]
        ),
        window_swings=document["window_swings"],
        significance=Decimal(document["significance"]),
        pivot_k=document["pivot_k"],
    )
