"""Candle pattern location (POINT4-CONTEXT-001).

The contract lives in ``docs/domain/localizacion-de-patron-de-vela.md``. Adds one new dimension to
a candle pattern already detected by ``candlestick_single.py``/``candlestick_multi.py``: whether it
sits near a price level Freyja could actually know about at the time — a confirmed pivot of the
point 2 structure, or the boundary of a chart figure of point 3. It never reinterprets the trend
those two modules already resolve, and it never combines several patterns' evidence
(POINT4-HYPOTHESIS-001's job): it is one fact about one pattern.

Append-only, like ``pattern_hypothesis.PatternHypothesis``: a later evaluation, made once more
structure has been confirmed or published, is added with its own instant, computed from the
structure's own ``known_at``/``published_at`` — never from when the code happened to run, and
never rewriting or backdating what an earlier evaluation could truthfully say (contract, sections
2-3).
"""

import enum
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise

from freyja_backend.domain.candlestick_pattern import CandlePatternInstance
from freyja_backend.domain.chart_pattern import (
    Boundary,
    BoundaryRole,
    PatternEvidence,
    PatternInstance,
    evidence,
)
from freyja_backend.domain.market_calendar import MarketSchedule
from freyja_backend.domain.market_context import MissingDataReason, build_observable_context
from freyja_backend.domain.market_data import (
    DEFAULT_PUBLICATION_GRACE,
    Candle,
    InstrumentRef,
    InvalidMarketDataError,
    Timeframe,
    _require_utc,
    assess_candles,
)
from freyja_backend.domain.market_structure import (
    DEFAULT_PIVOT_PARAMS,
    MIN_HISTORY_CANDLES,
    Pivot,
    PivotParams,
    PivotStatus,
    detect_pivots,
)
from freyja_backend.domain.pattern_detection import InvalidDetectionRequestError, line_through

LOCATION_MODEL_VERSION = "candle-location-v1"
# Bump on ANY change to a threshold or to how they are read. Its own version, independent of
# single-candle-params-v1/multi-candle-params-v1/three-candle-params-v1 (same reasoning as the
# split corrected in POINT4-MULTI-001 before its second delivery: a change here must never shift
# the identity of an already-detected candle pattern, and vice versa).
LOCATION_PARAMETER_VERSION = "candle-location-params-v1"

_NAMESPACE = uuid.UUID("2f6a8c14-9d3b-4e07-a1c5-6b8e0f2a4d76")


class LocationState(enum.StrEnum):
    NEAR_LEVEL = "NEAR_LEVEL"
    NOT_NEAR_LEVEL = "NOT_NEAR_LEVEL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class LevelKind(enum.StrEnum):
    PIVOT = "PIVOT"
    CHART_PATTERN_BOUNDARY = "CHART_PATTERN_BOUNDARY"


@dataclass(frozen=True, slots=True)
class LocationParams:
    """Every threshold the location evaluator reads, and the version of the set (part of every
    evaluation's identity). Provisional and unvalidated: see PARAMS-VALIDATION-001."""

    version: str = LOCATION_PARAMETER_VERSION
    # A level is "near" when its distance to the pattern is at most this fraction of the
    # pattern's own anchor range (its highest high to its lowest low).
    max_distance_fraction: Decimal = Decimal("0.25")
    pivot_params: PivotParams = DEFAULT_PIVOT_PARAMS
    min_history: int = MIN_HISTORY_CANDLES

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise InvalidDetectionRequestError("the parameters must carry their version")
        if not isinstance(self.max_distance_fraction, Decimal) or not (
            Decimal(0) < self.max_distance_fraction < Decimal(1)
        ):
            raise InvalidDetectionRequestError(
                "max_distance_fraction must be a Decimal between 0 and 1"
            )
        if (
            isinstance(self.min_history, bool)
            or not isinstance(self.min_history, int)
            or self.min_history < 1
        ):
            raise InvalidDetectionRequestError("min_history must be an integer of at least 1")


DEFAULT_LOCATION_PARAMS = LocationParams()


@dataclass(frozen=True, slots=True)
class LocationContext:
    """What the location evaluator needs to know about the series it reads, at one instant. Its
    own type, mirroring `SingleCandleContext`/`MultiCandleContext` for the same reason: this is
    its own task, with its own parameters."""

    instrument_id: str
    instrument: InstrumentRef
    schedule: MarketSchedule
    data_source: str
    authorized_sources: frozenset[str]
    timeframe: Timeframe
    observed_at: datetime
    params: LocationParams = DEFAULT_LOCATION_PARAMS
    publication_grace: timedelta = DEFAULT_PUBLICATION_GRACE


@dataclass(frozen=True, slots=True)
class LocationEvaluation:
    """What was knowable about a pattern's location at one instant. Complete on its own: its
    evidence names every level it used, so nothing has to be looked up later to understand it."""

    evaluated_at: datetime
    as_of: datetime | None
    state: LocationState
    insufficient_data_reasons: tuple[MissingDataReason, ...] = ()
    evidence: tuple[PatternEvidence, ...] = ()

    def __post_init__(self) -> None:
        _require_utc(self.evaluated_at, "evaluated_at")
        if self.as_of is not None:
            _require_utc(self.as_of, "as_of")
            if self.as_of > self.evaluated_at:
                raise InvalidDetectionRequestError(
                    "a candle that closes after the evaluation was read"
                )
        if bool(self.insufficient_data_reasons) != (self.state is LocationState.INSUFFICIENT_DATA):
            raise InvalidDetectionRequestError("insufficient-data reasons exist exactly when it is")
        codes = {item.code for item in self.evidence}
        if self.state is LocationState.NEAR_LEVEL and "LEVEL" not in codes:
            raise InvalidDetectionRequestError("NEAR_LEVEL needs at least one LEVEL evidence item")
        if self.state is LocationState.NOT_NEAR_LEVEL and "LEVELS_CHECKED" not in codes:
            raise InvalidDetectionRequestError(
                "NOT_NEAR_LEVEL needs a LEVELS_CHECKED evidence item"
            )


def derive_location_id(
    source_candle_pattern_instance_id: uuid.UUID,
    definition_version: str = LOCATION_MODEL_VERSION,
) -> uuid.UUID:
    key = f"{definition_version}|{source_candle_pattern_instance_id}"
    return uuid.uuid5(_NAMESPACE, key)


@dataclass(frozen=True, slots=True)
class PatternLocation:
    """One candle pattern's append-only history of location evaluations."""

    source_candle_pattern_instance_id: uuid.UUID
    evaluations: tuple[LocationEvaluation, ...]
    definition_version: str = LOCATION_MODEL_VERSION

    def __post_init__(self) -> None:
        if not self.evaluations:
            raise InvalidDetectionRequestError("a location is born from an evaluation")
        for earlier, later in pairwise(self.evaluations):
            if later.evaluated_at <= earlier.evaluated_at:
                raise InvalidDetectionRequestError("evaluations move strictly forward in time")

    @property
    def location_id(self) -> uuid.UUID:
        return derive_location_id(self.source_candle_pattern_instance_id, self.definition_version)

    @property
    def latest(self) -> LocationEvaluation:
        return self.evaluations[-1]

    def advance(self, evaluation: LocationEvaluation) -> "PatternLocation":
        """The same location one evaluation later. The earlier evaluations are untouched."""
        return PatternLocation(
            self.source_candle_pattern_instance_id,
            (*self.evaluations, evaluation),
            self.definition_version,
        )


# -- reading knowability from a chart figure, never recomputing it ------------------------------


def _parse_instant(text: str) -> datetime:
    moment = datetime.fromisoformat(text)
    if moment.utcoffset() != timedelta(0):
        raise InvalidDetectionRequestError(f"{text!r} is not a UTC instant")
    return moment.astimezone(UTC)


def _figure_knowability(
    figure: PatternInstance,
) -> tuple[datetime | None, datetime | None, str | None]:
    """(known_at, published_at, provenance), copied as-is from the figure's own timing evidence
    (`BREAKOUT_TIMING`/`DIAMOND_TIMING`) — never recomputed (contract, section 4: "la procedencia
    se lee, no se recalcula", same rule `hipotesis-de-figura.md` already applies)."""
    known_at: datetime | None = None
    published_at: datetime | None = None
    provenance: str | None = None
    for item in figure.latest.evidence:
        if item.code not in ("BREAKOUT_TIMING", "DIAMOND_TIMING"):
            continue
        facts = dict(item.facts)
        if "known_at" in facts:
            known_at = _parse_instant(str(facts["known_at"]))
        if "published_at" in facts:
            published_at = _parse_instant(str(facts["published_at"]))
        if "provenance" in facts:
            provenance = str(facts["provenance"])
    return known_at, published_at, provenance


# -- candidates: pivots and figure boundaries, filtered by knowability ---------------------------


@dataclass(frozen=True, slots=True)
class _Candidate:
    kind: LevelKind
    label: str
    price: Decimal
    known_at: datetime
    published_at: datetime | None
    provenance: str | None


def _pivot_candidates(pivots: Sequence[Pivot], *, knowability_cutoff: datetime) -> list[_Candidate]:
    out: list[_Candidate] = []
    for pivot in pivots:
        if pivot.status is not PivotStatus.CONFIRMED or pivot.confirmed_at is None:
            continue
        if pivot.confirmed_at > knowability_cutoff:
            continue
        out.append(
            _Candidate(
                LevelKind.PIVOT,
                f"{pivot.kind.value} pivot",
                pivot.price,
                pivot.confirmed_at,
                None,
                None,
            )
        )
    return out


def _boundary_price_at(boundary: Boundary, at: datetime) -> Decimal | None:
    """The boundary's price at `at`, as a straight line through its first and last point. `None`
    for an arc (rounding tops/bottoms): approximating it as a chord would misstate the level, and
    fitting the real parabola here would duplicate `pattern_rounding.py` (contract, decisions)."""
    if boundary.role is BoundaryRole.ARC:
        return None
    first, last = boundary.points[0], boundary.points[-1]
    if first.time == last.time:
        return None
    return line_through(first.time, first.price, last.time, last.price)(at)


def _figure_candidates(
    figures: Sequence[PatternInstance],
    *,
    pattern_at: datetime,
    knowability_cutoff: datetime,
    context: LocationContext,
) -> list[_Candidate]:
    out: list[_Candidate] = []
    for figure in figures:
        if (
            figure.instrument_id != context.instrument_id
            or figure.data_source != context.data_source
            or figure.timeframe != context.timeframe
        ):
            continue
        known_at, published_at, provenance = _figure_knowability(figure)
        if known_at is None or known_at > knowability_cutoff:
            continue
        if published_at is not None and published_at > knowability_cutoff:
            continue
        for boundary in figure.latest.boundaries:
            price = _boundary_price_at(boundary, pattern_at)
            if price is None:
                continue
            out.append(
                _Candidate(
                    LevelKind.CHART_PATTERN_BOUNDARY,
                    f"{figure.pattern_type.value} {boundary.role.value} boundary",
                    price,
                    known_at,
                    published_at,
                    provenance,
                )
            )
    return out


# -- building the evaluation ----------------------------------------------------------------


def _reference_price(source: CandlePatternInstance) -> Decimal:
    return source.latest.anchors[-1].close


def _reference_range(source: CandlePatternInstance) -> Decimal:
    anchors = source.latest.anchors
    span = max(a.high for a in anchors) - min(a.low for a in anchors)
    return span if span > 0 else anchors[-1].range


def _nearby_evidence(candidate: _Candidate, distance_fraction: Decimal) -> PatternEvidence:
    facts: dict[str, str | int | bool | Decimal] = {
        "kind": candidate.kind.value,
        "label": candidate.label,
        "price": candidate.price,
        "distance_fraction": distance_fraction,
        "source_known_at": candidate.known_at.isoformat(),
    }
    if candidate.published_at is not None:
        facts["source_published_at"] = candidate.published_at.isoformat()
    if candidate.provenance is not None:
        facts["source_provenance"] = candidate.provenance
    return evidence(
        "LEVEL",
        f"{candidate.label} at {candidate.price}, {distance_fraction} of the pattern's range away",
        **facts,
    )


def _checked_evidence(count: int, closest: Decimal | None) -> PatternEvidence:
    facts: dict[str, str | int | bool | Decimal] = {"levels_checked": count}
    if closest is not None:
        facts["closest_distance_fraction"] = closest
    return evidence("LEVELS_CHECKED", f"{count} level(s) checked, none within tolerance", **facts)


def _build_evaluation(
    context: LocationContext,
    source: CandlePatternInstance,
    *,
    pattern_at: datetime,
    knowability_cutoff: datetime,
    pivots: Sequence[Pivot],
    figures: Sequence[PatternInstance],
    as_of: datetime | None,
) -> LocationEvaluation:
    candidates = _pivot_candidates(
        pivots, knowability_cutoff=knowability_cutoff
    ) + _figure_candidates(
        figures, pattern_at=pattern_at, knowability_cutoff=knowability_cutoff, context=context
    )
    instants = [pattern_at, *(c.known_at for c in candidates)]
    instants.extend(c.published_at for c in candidates if c.published_at is not None)
    evaluated_at = max(instants)
    # `as_of` (la vela más nueva realmente leída) puede llegar aquí más tarde que
    # `evaluated_at` cuando el llamador vuelve a evaluar con más velas de las que esta
    # evaluación concreta puede reclamar conocer (p. ej. la primera evaluación, acotada al
    # instante propio del patrón). Se acota: esta evaluación nunca puede afirmar haber leído
    # una vela posterior a lo que ella misma puede saber.
    capped_as_of = as_of if as_of is None else min(as_of, evaluated_at)

    reference_price = _reference_price(source)
    reference_range = _reference_range(source)
    scored = sorted(
        ((c, abs(c.price - reference_price) / reference_range) for c in candidates),
        key=lambda pair: (pair[0].kind.value, pair[0].label, str(pair[0].price)),
    )
    params = context.params
    near = [(c, f) for c, f in scored if f <= params.max_distance_fraction]
    closest = min((f for _c, f in scored), default=None)

    if near:
        items = tuple(_nearby_evidence(c, f) for c, f in near)
        return LocationEvaluation(
            evaluated_at, capped_as_of, LocationState.NEAR_LEVEL, evidence=items
        )
    items = (_checked_evidence(len(candidates), closest),)
    return LocationEvaluation(
        evaluated_at, capped_as_of, LocationState.NOT_NEAR_LEVEL, evidence=items
    )


def _same_content(before: LocationEvaluation, after: LocationEvaluation) -> bool:
    return (
        before.state is after.state
        and before.insufficient_data_reasons == after.insufficient_data_reasons
        and before.evidence == after.evidence
    )


def _advance(
    previous: PatternLocation | None,
    source: CandlePatternInstance,
    evaluation: LocationEvaluation,
) -> PatternLocation:
    if previous is None:
        return PatternLocation(source.candle_pattern_instance_id, (evaluation,))
    if _same_content(previous.latest, evaluation):
        return previous
    return previous.advance(evaluation)


def evaluate_location(
    context: LocationContext,
    candles: Sequence[Candle],
    source: CandlePatternInstance,
    figures: Sequence[PatternInstance],
    previous: PatternLocation | None = None,
) -> PatternLocation:
    """Where `source` stands relative to price structure Freyja could know about, as evidence
    separate from the pattern itself (contract, section 1).

    The first evaluation (`previous is None`) uses only pivots/figures knowable at or before the
    pattern's own instant (`source.latest.evaluated_at`) — never later, however far in the future
    `context.observed_at` is. Every following evaluation uses everything knowable by
    `context.observed_at` instead (cumulative): a pivot or a held-back figure that becomes
    knowable later is added as a *new* evaluation, dated at when it actually became knowable
    (never at the pattern's own instant, never at whenever this function happened to run) — never
    rewriting what an earlier evaluation could truthfully say (contract, sections 2-3).
    """
    _require_utc(context.observed_at, "observed_at")
    pattern_at = source.latest.evaluated_at
    knowability_cutoff = pattern_at if previous is None else context.observed_at
    try:
        closed = assess_candles(
            candles,
            timeframe=context.timeframe,
            now=context.observed_at,
            publication_grace=context.publication_grace,
        ).candles
    except InvalidMarketDataError:
        evaluation = LocationEvaluation(
            knowability_cutoff,
            None,
            LocationState.INSUFFICIENT_DATA,
            insufficient_data_reasons=(MissingDataReason.INVALID_CANDLES,),
        )
        return _advance(previous, source, evaluation)
    as_of = closed[-1].close_time if closed else None
    observable = build_observable_context(
        instrument_id=context.instrument_id,
        instrument=context.instrument,
        schedule=context.schedule,
        signal_timeframe=context.timeframe,
        context_timeframe=context.timeframe,
        observed_at=context.observed_at,
        data_source=context.data_source,
        authorized_sources=context.authorized_sources,
        candles=candles,
        min_history=context.params.min_history,
        publication_grace=context.publication_grace,
    )
    if not observable.is_sufficient:
        capped_as_of = as_of if as_of is None else min(as_of, knowability_cutoff)
        evaluation = LocationEvaluation(
            knowability_cutoff,
            capped_as_of,
            LocationState.INSUFFICIENT_DATA,
            insufficient_data_reasons=observable.missing_data_reasons,
        )
        return _advance(previous, source, evaluation)
    pivots = detect_pivots(
        closed,
        timeframe=context.timeframe,
        observed_at=context.observed_at,
        params=context.params.pivot_params,
    ).confirmed
    evaluation = _build_evaluation(
        context,
        source,
        pattern_at=pattern_at,
        knowability_cutoff=knowability_cutoff,
        pivots=pivots,
        figures=figures,
        as_of=as_of,
    )
    return _advance(previous, source, evaluation)
