"""POINT5-REGISTRY-001: the shape of the six indicator-registry entities.

No formula, no runtime wiring, no database — this only proves the shapes and their invariants
(indicadores.md's rules and registro-de-indicadores.md's "Contrato de versión"), the same way
candlestick_pattern.py's own tests prove the pattern model without detecting anything.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from freyja_backend.domain.indicator_registry import (
    INDICATOR_CATALOGUE,
    IncompleteDataPolicy,
    IndicatorDefinition,
    IndicatorFamily,
    IndicatorFunction,
    IndicatorMarketCapability,
    IndicatorName,
    IndicatorObservation,
    IndicatorParameterSchema,
    IndicatorStatus,
    IndicatorVersion,
    InitializationPolicy,
    InvalidIndicatorDefinitionError,
    ObservationAvailability,
    ParameterConstraint,
    ParameterType,
    StrategyIndicatorUsage,
)
from freyja_backend.domain.market_data import InvalidMarketDataError

N = IndicatorName
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


# -- catalogue ------------------------------------------------------------------------------


def test_the_catalogue_has_exactly_the_eight_named_indicators() -> None:
    assert set(INDICATOR_CATALOGUE) == {
        N.EMA,
        N.RSI,
        N.MACD,
        N.BOLLINGER_BANDS,
        N.ATR,
        N.VOLUME,
        N.TICK_VOLUME,
        N.FIBONACCI,
    }


def test_every_catalogued_indicator_is_family_ohlcv() -> None:
    assert all(d.family is IndicatorFamily.OHLCV for d in INDICATOR_CATALOGUE.values())


def test_volume_and_tick_volume_are_separate_catalogue_entries() -> None:
    """indicadores.md section 5: never the same indicator with two meanings."""
    assert N.VOLUME in INDICATOR_CATALOGUE
    assert N.TICK_VOLUME in INDICATOR_CATALOGUE
    assert INDICATOR_CATALOGUE[N.VOLUME] != INDICATOR_CATALOGUE[N.TICK_VOLUME]


def test_only_one_family_exists_today() -> None:
    """indicadores.md section 2: ORDER_FLOW/DOM/FOOTPRINT/SMC need their own contract before they
    exist here — a deliberate single-member enum, not an oversight."""
    assert set(IndicatorFamily) == {IndicatorFamily.OHLCV}


def test_an_indicator_definition_needs_a_description() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError):
        IndicatorDefinition(N.EMA, IndicatorFamily.OHLCV, "  ")


# -- parameters -------------------------------------------------------------------------------


def test_an_enum_parameter_needs_allowed_values() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError, match="allowed_values"):
        ParameterConstraint("smoothing", ParameterType.ENUM)


def test_a_non_enum_parameter_rejects_allowed_values() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError, match="ENUM"):
        ParameterConstraint("period", ParameterType.INTEGER, allowed_values=("a",))


def test_a_parameter_needs_a_name() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError):
        ParameterConstraint("  ", ParameterType.INTEGER)


def test_minimum_must_not_exceed_maximum() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError, match="minimum"):
        ParameterConstraint(
            "period", ParameterType.INTEGER, minimum=Decimal(10), maximum=Decimal(5)
        )


def test_a_parameter_schema_needs_a_version() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError):
        IndicatorParameterSchema(" ")


def test_a_parameter_schema_rejects_duplicate_parameter_names() -> None:
    period = ParameterConstraint("period", ParameterType.INTEGER)
    with pytest.raises(InvalidIndicatorDefinitionError, match="unique"):
        IndicatorParameterSchema("ema-params-v1", (period, period))


# -- indicator version --------------------------------------------------------------------------


def _schema() -> IndicatorParameterSchema:
    return IndicatorParameterSchema(
        "ema-params-v1",
        (ParameterConstraint("period", ParameterType.INTEGER, minimum=Decimal(1)),),
    )


def _version(**overrides: object) -> IndicatorVersion:
    defaults: dict[str, object] = {
        "indicator": N.EMA,
        "version": "ema-v1",
        "parameter_schema": _schema(),
        "inputs": ("close",),
        "outputs": ("value",),
        "initialization": InitializationPolicy.REQUIRES_FULL_WARMUP_WINDOW,
        "warmup_candles": 200,
        "precision": 8,
    }
    return IndicatorVersion(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_a_well_formed_indicator_version_is_accepted() -> None:
    version = _version()
    assert version.status is IndicatorStatus.ACTIVE
    assert version.incomplete_data_policy is IncompleteDataPolicy.FAIL_CLOSED_NO_VALUE


def test_an_indicator_version_needs_its_version_string() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError, match="version"):
        _version(version=" ")


def test_an_indicator_version_must_reference_a_catalogued_indicator() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError, match="INDICATOR_CATALOGUE"):
        _version(indicator="NOT_A_REAL_INDICATOR")


def test_an_indicator_version_needs_at_least_one_input_and_output() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError, match="inputs"):
        _version(inputs=())
    with pytest.raises(InvalidIndicatorDefinitionError, match="outputs"):
        _version(outputs=())


@pytest.mark.parametrize("warmup", [-1, True])
def test_warmup_candles_must_be_a_non_negative_integer(warmup: int) -> None:
    with pytest.raises(InvalidIndicatorDefinitionError, match="warmup_candles"):
        _version(warmup_candles=warmup)


@pytest.mark.parametrize("precision", [-1, True])
def test_precision_must_be_a_non_negative_integer(precision: int) -> None:
    with pytest.raises(InvalidIndicatorDefinitionError, match="precision"):
        _version(precision=precision)


def test_fibonacci_may_declare_no_warmup_at_all() -> None:
    """It is a pure function of an already-confirmed swing (fibonacci-retroceso.md) — no
    warmup window is needed, unlike a moving average."""
    version = _version(
        indicator=N.FIBONACCI,
        version="fibonacci-v1",
        parameter_schema=IndicatorParameterSchema("fibonacci-params-v1"),
        inputs=("swing",),
        outputs=("level_0_5", "level_0_618"),
        initialization=InitializationPolicy.NONE,
        warmup_candles=0,
    )
    assert version.initialization is InitializationPolicy.NONE
    assert version.warmup_candles == 0


# -- market capability --------------------------------------------------------------------------


def test_a_supported_capability_carries_no_reason() -> None:
    capability = IndicatorMarketCapability(N.EMA, "ema-v1", "FOREX", "SPOT", supported=True)
    assert capability.reason == ""


def test_an_unsupported_capability_requires_a_reason() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError, match="reason"):
        IndicatorMarketCapability(N.VOLUME, "volume-v1", "FOREX", "SPOT", supported=False)


def test_a_supported_capability_rejects_a_reason() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError, match="reason"):
        IndicatorMarketCapability(
            N.EMA, "ema-v1", "FOREX", "SPOT", supported=True, reason="should not be here"
        )


def test_a_capability_must_reference_a_catalogued_indicator() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError, match="INDICATOR_CATALOGUE"):
        IndicatorMarketCapability(
            "NOT_A_REAL_INDICATOR",  # type: ignore[arg-type]
            "v1",
            "FOREX",
            "SPOT",
            supported=True,
        )


def test_the_forex_metals_volume_limit_is_expressible_as_a_capability() -> None:
    """indicadores.md section 5: VOLUME is unsupported for FOREX/METALS, never AVAILABLE with a
    stored zero standing in for a real observation."""
    for market in ("FOREX", "METALS"):
        capability = IndicatorMarketCapability(
            N.VOLUME,
            "volume-v1",
            market,
            "SPOT",
            supported=False,
            reason="no existe un volumen spot global real",
        )
        assert capability.supported is False


# -- strategy usage -----------------------------------------------------------------------------


def test_a_strategy_usage_needs_a_non_blank_strategy_id() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError):
        StrategyIndicatorUsage(" ", N.EMA, "ema-v1", IndicatorFunction.CONTEXT)


def test_the_same_version_may_carry_different_functions_in_different_usages() -> None:
    context_use = StrategyIndicatorUsage("strategy-1", N.EMA, "ema-v1", IndicatorFunction.CONTEXT)
    informational_use = StrategyIndicatorUsage(
        "strategy-2", N.EMA, "ema-v1", IndicatorFunction.INFORMATIONAL
    )
    assert context_use.function is not informational_use.function
    assert context_use.indicator_version == informational_use.indicator_version


# -- observation --------------------------------------------------------------------------------


def test_an_available_observation_needs_at_least_one_value() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError, match="AVAILABLE"):
        IndicatorObservation(
            N.EMA,
            "ema-v1",
            "instrument-1",
            "BINANCE",
            "1m",
            observed_at=NOW,
            as_of=NOW,
            availability=ObservationAvailability.AVAILABLE,
        )


def test_an_unavailable_observation_must_carry_no_values() -> None:
    with pytest.raises(InvalidIndicatorDefinitionError, match="UNAVAILABLE"):
        IndicatorObservation(
            N.EMA,
            "ema-v1",
            "instrument-1",
            "BINANCE",
            "1m",
            observed_at=NOW,
            as_of=None,
            availability=ObservationAvailability.UNAVAILABLE,
            values={"value": Decimal("100")},
        )


def test_a_well_formed_available_observation_is_accepted() -> None:
    observation = IndicatorObservation(
        N.EMA,
        "ema-v1",
        "instrument-1",
        "BINANCE",
        "1m",
        observed_at=NOW,
        as_of=NOW,
        availability=ObservationAvailability.AVAILABLE,
        values={"value": Decimal("100.12345678")},
    )
    assert observation.values["value"] == Decimal("100.12345678")


def test_a_naive_observed_at_is_rejected() -> None:
    with pytest.raises(InvalidMarketDataError):
        IndicatorObservation(
            N.EMA,
            "ema-v1",
            "instrument-1",
            "BINANCE",
            "1m",
            observed_at=datetime(2026, 9, 30, 12, 0),  # naive
            as_of=None,
            availability=ObservationAvailability.UNAVAILABLE,
        )


def test_an_unavailable_observation_needs_no_as_of() -> None:
    observation = IndicatorObservation(
        N.EMA,
        "ema-v1",
        "instrument-1",
        "BINANCE",
        "1m",
        observed_at=NOW,
        as_of=None,
        availability=ObservationAvailability.UNAVAILABLE,
    )
    assert observation.as_of is None
    assert observation.values == {}
