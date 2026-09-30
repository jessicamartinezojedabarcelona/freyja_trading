"""Real-time indicator availability (POINT5-DATA-001).

Contract: ``docs/domain/disponibilidad-de-indicadores.md``, built on
``docs/domain/indicadores.md`` (POINT5-DOMAIN-001) and
``docs/domain/registro-de-indicadores.md`` (POINT5-REGISTRY-001). Crosses an
``IndicatorMarketCapability`` (structural: is this indicator meaningful here at all) with one real
candle series' actual state (how much history, how fresh, how valid) to decide, right now, whether
POINT5-CORE-001 could compute a value — and if not, exactly why.

Pure and free of I/O, like every other module in this family: no database, no clock, no provider.
The caller supplies an already-fetched candle count and an already-assessed
``domain.market_data.DataQuality``/``QualityIssue`` sequence (from ``assess_candles``); this module
never re-derives them.

Nothing here infers a capability from a provider's or market's name (indicadores.md, section 5) —
every branch reads a value the caller already declared (an ``IndicatorMarketCapability``,
authorized sources, candle counts, quality), never a literal market or provider code string
compared inside the decision logic itself.
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass

from freyja_backend.domain.indicator_registry import (
    IndicatorMarketCapability,
    IndicatorVersion,
    InvalidIndicatorDefinitionError,
)
from freyja_backend.domain.market_data import DataQuality, QualityIssue, QualityIssueCode


class IndicatorAvailabilityState(enum.StrEnum):
    """POINT5-DATA-001's six states, in the exact priority order `assess_indicator_availability`
    applies them (disponibilidad-de-indicadores.md, section 2) — from the most structural reason
    (nothing can be known) to the most benign (only time is missing)."""

    SOURCE_UNSUPPORTED = "SOURCE_UNSUPPORTED"
    FIELD_UNAVAILABLE = "FIELD_UNAVAILABLE"
    QUALITY_FAILED = "QUALITY_FAILED"
    STALE_DATA = "STALE_DATA"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    AVAILABLE = "AVAILABLE"


# Every failure-causing issue (domain.market_data.FAILURE_ISSUES) means QUALITY_FAILED; STALE
# alone means STALE_DATA; any other DEGRADED-only issue (GAP, DUPLICATE_DROPPED, OUT_OF_ORDER,
# INCOMPLETE_RANGE, REVISED_CANDLE, PROVIDER_FAILING, INSTRUMENT_NOT_TRADING) also means
# QUALITY_FAILED — an indicator never computes on a series it knows disagrees with itself.
_NON_STALE_DEGRADED_ISSUES = frozenset(
    {
        QualityIssueCode.GAP,
        QualityIssueCode.DUPLICATE_DROPPED,
        QualityIssueCode.OUT_OF_ORDER,
        QualityIssueCode.INCOMPLETE_RANGE,
        QualityIssueCode.REVISED_CANDLE,
        QualityIssueCode.PROVIDER_FAILING,
        QualityIssueCode.INSTRUMENT_NOT_TRADING,
    }
)


@dataclass(frozen=True, slots=True)
class IndicatorAvailabilityResult:
    """Exactly one of the six states, always with a human-readable reason — an indicator never
    produces a value halfway (indicadores.md, section 4)."""

    state: IndicatorAvailabilityState
    detail: str


def assess_indicator_availability(
    version: IndicatorVersion,
    capability: IndicatorMarketCapability,
    *,
    data_source: str,
    authorized_sources: frozenset[str],
    closed_candle_count: int,
    batch_quality: DataQuality,
    batch_issues: Sequence[QualityIssue] = (),
) -> IndicatorAvailabilityResult:
    """The one state POINT5-CORE-001 must respect for this version, on this series, right now.

    `capability` must be the `IndicatorMarketCapability` for this exact `(version.indicator,
    version.version)` pair — a mismatch is a caller error (`InvalidIndicatorDefinitionError`), not
    a data condition; this function never guesses which capability applies.
    """
    if capability.indicator != version.indicator or capability.indicator_version != version.version:
        raise InvalidIndicatorDefinitionError("capability does not describe this indicator version")
    if isinstance(closed_candle_count, bool) or closed_candle_count < 0:
        raise InvalidIndicatorDefinitionError("closed_candle_count must be a non-negative integer")

    if data_source not in authorized_sources:
        return IndicatorAvailabilityResult(
            IndicatorAvailabilityState.SOURCE_UNSUPPORTED,
            f"{data_source!r} is not an authorized source for {version.indicator.value}",
        )

    if not capability.supported:
        return IndicatorAvailabilityResult(
            IndicatorAvailabilityState.FIELD_UNAVAILABLE, capability.reason
        )

    issue_codes = {issue.code for issue in batch_issues}
    if batch_quality is DataQuality.UNAVAILABLE:
        return IndicatorAvailabilityResult(
            IndicatorAvailabilityState.QUALITY_FAILED,
            f"the candle series is unavailable: {sorted(code.value for code in issue_codes)}",
        )
    if batch_quality is DataQuality.DEGRADED and (issue_codes & _NON_STALE_DEGRADED_ISSUES):
        return IndicatorAvailabilityResult(
            IndicatorAvailabilityState.QUALITY_FAILED,
            f"the candle series is degraded: {sorted(code.value for code in issue_codes)}",
        )
    if QualityIssueCode.STALE in issue_codes:
        return IndicatorAvailabilityResult(
            IndicatorAvailabilityState.STALE_DATA,
            "the newest closed candle is older than this timeframe's publication grace allows",
        )

    if closed_candle_count < version.warmup_candles:
        return IndicatorAvailabilityResult(
            IndicatorAvailabilityState.INSUFFICIENT_HISTORY,
            f"{closed_candle_count} closed candles available, {version.warmup_candles} required",
        )

    return IndicatorAvailabilityResult(IndicatorAvailabilityState.AVAILABLE, "")
