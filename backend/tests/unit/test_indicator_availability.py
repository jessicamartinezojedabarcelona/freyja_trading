"""POINT5-DATA-001: the six real-time availability states, and their exact priority.

No formula, no database, no provider — same discipline as test_indicator_registry.py. The three
market scenarios the task named explicitly (CRYPTO with real volume, FOREX/METALS without) are
covered with real IndicatorMarketCapability declarations, not hardcoded market-name branching.
"""

from decimal import Decimal

import pytest

from freyja_backend.domain.indicator_availability import (
    IndicatorAvailabilityResult,
    IndicatorAvailabilityState,
    assess_indicator_availability,
)
from freyja_backend.domain.indicator_registry import (
    IndicatorMarketCapability,
    IndicatorName,
    IndicatorParameterSchema,
    IndicatorVersion,
    InitializationPolicy,
    InvalidIndicatorDefinitionError,
    ParameterConstraint,
    ParameterType,
)
from freyja_backend.domain.market_data import DataQuality, QualityIssue, QualityIssueCode

N = IndicatorName
S = IndicatorAvailabilityState
SOURCE = "BINANCE"
AUTHORIZED = frozenset({SOURCE})


def _version(indicator: IndicatorName = N.EMA, warmup: int = 10) -> IndicatorVersion:
    schema = IndicatorParameterSchema(
        f"{indicator.value.lower()}-params-v1",
        (ParameterConstraint("period", ParameterType.INTEGER, minimum=Decimal(1)),),
    )
    return IndicatorVersion(
        indicator=indicator,
        version=f"{indicator.value.lower()}-v1",
        parameter_schema=schema,
        inputs=("close",) if indicator is not N.VOLUME else ("volume",),
        outputs=("value",),
        initialization=InitializationPolicy.REQUIRES_FULL_WARMUP_WINDOW,
        warmup_candles=warmup,
        precision=8,
    )


def _capability(
    version: IndicatorVersion, *, market: str = "CRYPTO", supported: bool = True, reason: str = ""
) -> IndicatorMarketCapability:
    return IndicatorMarketCapability(
        version.indicator, version.version, market, "SPOT", supported=supported, reason=reason
    )


def _assess(
    version: IndicatorVersion,
    capability: IndicatorMarketCapability,
    *,
    data_source: str = SOURCE,
    authorized_sources: frozenset[str] = AUTHORIZED,
    closed_candle_count: int = 500,
    batch_quality: DataQuality = DataQuality.OK,
    batch_issues: tuple[QualityIssue, ...] = (),
) -> IndicatorAvailabilityResult:
    return assess_indicator_availability(
        version,
        capability,
        data_source=data_source,
        authorized_sources=authorized_sources,
        closed_candle_count=closed_candle_count,
        batch_quality=batch_quality,
        batch_issues=batch_issues,
    )


# -- caller errors, not data conditions ----------------------------------------------------------


def test_a_capability_for_a_different_version_is_rejected() -> None:
    version = _version()
    mismatched = IndicatorMarketCapability(N.RSI, "rsi-v1", "CRYPTO", "SPOT", supported=True)
    with pytest.raises(InvalidIndicatorDefinitionError, match="does not describe"):
        _assess(version, mismatched)


@pytest.mark.parametrize("count", [-1, True])
def test_closed_candle_count_must_be_a_non_negative_integer(count: int) -> None:
    version = _version()
    with pytest.raises(InvalidIndicatorDefinitionError, match="closed_candle_count"):
        _assess(version, _capability(version), closed_candle_count=count)


# -- priority order: each condition wins over every weaker one below it --------------------------


def test_source_unsupported_wins_over_everything_else() -> None:
    """Even an unsupported capability, bad quality and no history don't matter if the source
    itself was never authorized — there is no series to evaluate at all."""
    version = _version()
    result = _assess(
        version,
        _capability(version, supported=False, reason="no matters"),
        data_source="UNKNOWN_SOURCE",
        closed_candle_count=0,
        batch_quality=DataQuality.UNAVAILABLE,
    )
    assert result.state is S.SOURCE_UNSUPPORTED


def test_field_unavailable_wins_over_quality_and_history() -> None:
    version = _version(indicator=N.VOLUME)
    result = _assess(
        version,
        _capability(
            version, market="FOREX", supported=False, reason="no existe volumen spot global"
        ),
        closed_candle_count=0,
        batch_quality=DataQuality.UNAVAILABLE,
    )
    assert result.state is S.FIELD_UNAVAILABLE
    assert result.detail == "no existe volumen spot global"


def test_quality_failed_wins_over_staleness_and_history() -> None:
    version = _version()
    result = _assess(
        version,
        _capability(version),
        closed_candle_count=0,
        batch_quality=DataQuality.UNAVAILABLE,
        batch_issues=(QualityIssue(QualityIssueCode.PROVIDER_ERROR, "500"),),
    )
    assert result.state is S.QUALITY_FAILED


def test_a_non_stale_degraded_issue_is_also_quality_failed() -> None:
    """A gap, duplicate, out-of-order or revised candle is a real problem with the series
    itself — an indicator never computes on data it knows disagrees with itself."""
    version = _version()
    result = _assess(
        version,
        _capability(version),
        batch_quality=DataQuality.DEGRADED,
        batch_issues=(QualityIssue(QualityIssueCode.GAP, "1 candle missing"),),
    )
    assert result.state is S.QUALITY_FAILED


def test_stale_data_wins_over_insufficient_history() -> None:
    version = _version(warmup=1000)
    result = _assess(
        version,
        _capability(version),
        closed_candle_count=5,  # also insufficient, but staleness wins
        batch_quality=DataQuality.DEGRADED,
        batch_issues=(QualityIssue(QualityIssueCode.STALE, "old"),),
    )
    assert result.state is S.STALE_DATA


def test_insufficient_history_when_nothing_else_is_wrong() -> None:
    version = _version(warmup=200)
    result = _assess(version, _capability(version), closed_candle_count=50)
    assert result.state is S.INSUFFICIENT_HISTORY
    assert "50" in result.detail and "200" in result.detail


def test_available_when_every_condition_is_met() -> None:
    version = _version(warmup=200)
    result = _assess(version, _capability(version), closed_candle_count=200)
    assert result.state is S.AVAILABLE
    assert result.detail == ""


# -- the three market scenarios the task named explicitly ----------------------------------------


def test_crypto_volume_is_available_with_real_exchange_volume() -> None:
    version = _version(indicator=N.VOLUME, warmup=1)
    capability = _capability(version, market="CRYPTO", supported=True)
    result = _assess(version, capability, closed_candle_count=1)
    assert result.state is S.AVAILABLE


@pytest.mark.parametrize("market", ["FOREX", "METALS"])
def test_forex_and_metals_volume_is_field_unavailable_never_available_with_a_stored_zero(
    market: str,
) -> None:
    """indicadores.md section 5: the Decimal("0") an adapter stores for these markets is absence
    of data, never a real zero-volume observation — this must never surface as AVAILABLE."""
    version = _version(indicator=N.VOLUME, warmup=1)
    capability = _capability(
        version,
        market=market,
        supported=False,
        reason="no existe un volumen spot global real",
    )
    result = _assess(version, capability, closed_candle_count=1)
    assert result.state is S.FIELD_UNAVAILABLE


def test_forex_and_metals_capabilities_are_declared_independently() -> None:
    """METALS never inherits FOREX's rule automatically — each is its own declaration, even
    though today both happen to be unsupported for VOLUME."""
    version = _version(indicator=N.VOLUME, warmup=1)
    forex = _capability(version, market="FOREX", supported=False, reason="sin volumen real")
    metals = _capability(version, market="METALS", supported=True)  # hypothetically different
    assert _assess(version, forex, closed_candle_count=1).state is S.FIELD_UNAVAILABLE
    assert _assess(version, metals, closed_candle_count=1).state is S.AVAILABLE


@pytest.mark.parametrize("market", ["CRYPTO", "FOREX", "METALS"])
def test_ohlc_only_indicators_are_supported_in_every_market(market: str) -> None:
    """EMA/RSI/MACD/BOLLINGER_BANDS/ATR only need price, available in all three markets — never
    blocked by the volume limit that is specific to VOLUME."""
    version = _version(indicator=N.EMA, warmup=1)
    capability = _capability(version, market=market, supported=True)
    result = _assess(version, capability, closed_candle_count=1)
    assert result.state is S.AVAILABLE


def test_a_binary_option_is_evaluated_like_its_underlying_spot() -> None:
    """Indicators are computed on the underlying instrument, never on the payout — the same
    capability declaration applies regardless of product (patrones-de-vela.md-style separation
    of concerns: the product does not invent a different data source)."""
    version = _version(indicator=N.EMA, warmup=1)
    spot_capability = IndicatorMarketCapability(
        version.indicator, version.version, "CRYPTO", "SPOT", supported=True
    )
    binary_capability = IndicatorMarketCapability(
        version.indicator, version.version, "CRYPTO", "BINARY_OPTION", supported=True
    )
    assert _assess(version, spot_capability, closed_candle_count=1).state is S.AVAILABLE
    assert _assess(version, binary_capability, closed_candle_count=1).state is S.AVAILABLE
