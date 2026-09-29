"""Canonical, extensible indicator registry (POINT5-REGISTRY-001).

Contract: ``docs/domain/registro-de-indicadores.md``, built on ``docs/domain/indicadores.md``
(POINT5-DOMAIN-001). Fixes the exact shape of six entities so the catalogue can grow as data,
never as a schema change:

* ``IndicatorDefinition`` — an indicator's canonical identity, never its formula.
* ``IndicatorParameterSchema``/``ParameterConstraint`` — what parameters a version needs, generic
  enough that a new indicator's parameters never need a new column.
* ``IndicatorVersion`` — one immutable, versioned way of computing an indicator: inputs, outputs,
  initialization, warmup, precision and incomplete-data policy — never a formula either.
* ``IndicatorMarketCapability`` — that a version is, in principle, meaningful for one
  (market, product) pair. Structural only: whether it is actually available right now for one
  real series is POINT5-DATA-001, layered on top, never replacing this declaration.
* ``StrategyIndicatorUsage`` — how a (future) ``StrategySpec``, not contracted yet, would use one
  version. The function belongs to the usage, never to the indicator (indicadores.md, section 3).
* ``IndicatorObservation`` — one computed value for one series at one instant, with the same
  traceability discipline as ``Provenance`` (``domain/market_data.py``, ADR 0002).

Pure and free of I/O, like ``candlestick_pattern.py``: no database, no clock, no provider, no
formula, no runtime wiring (POINT5-REGISTRY-001, "Límites" — deliberate, not an oversight).
POINT5-CORE-001 fills in real ``IndicatorVersion`` records for the seven canonical tools;
POINT5-DATA-001 decides real-time availability; POINT5-POLICY-001/SNAPSHOT-001 use
``StrategyIndicatorUsage``/``IndicatorObservation`` once ``StrategySpec`` exists.
"""

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType

from freyja_backend.domain.market_data import _require_utc

INDICATOR_CATALOGUE_VERSION = "indicator-catalogue-v1"


class InvalidIndicatorDefinitionError(ValueError):
    """A wrong request to this registry — a programming error, not a runtime condition."""


class IndicatorFamily(enum.StrEnum):
    """indicadores.md, section 2: the only family Freyja supports today. Deliberately a single
    value — ORDER_FLOW/DOM/FOOTPRINT/SMC need their own contract before they exist here at all,
    never a silent extension of this enum."""

    OHLCV = "OHLCV"


class IndicatorFunction(enum.StrEnum):
    """indicadores.md, section 3. Declared by a `StrategyIndicatorUsage`, never fixed on an
    indicator or a version: the same version may be LOCATOR in one use and INFORMATIONAL in
    another."""

    LOCATOR = "LOCATOR"
    CONTEXT = "CONTEXT"
    TRIGGER = "TRIGGER"
    CONFIRMATION = "CONFIRMATION"
    FILTER = "FILTER"
    INVALIDATION = "INVALIDATION"
    RISK_INPUT = "RISK_INPUT"
    EXIT_INPUT = "EXIT_INPUT"
    SCORING_INPUT = "SCORING_INPUT"
    INFORMATIONAL = "INFORMATIONAL"


class IndicatorName(enum.StrEnum):
    """The seven-tool núcleo inicial (indicadores.md, section 3), plus TICK_VOLUME as its own,
    separate indicator — never VOLUME with a second, silently substituted meaning (indicadores.md,
    section 5)."""

    EMA = "EMA"
    RSI = "RSI"
    MACD = "MACD"
    BOLLINGER_BANDS = "BOLLINGER_BANDS"
    ATR = "ATR"
    VOLUME = "VOLUME"
    TICK_VOLUME = "TICK_VOLUME"
    FIBONACCI = "FIBONACCI"


@dataclass(frozen=True, slots=True)
class IndicatorDefinition:
    """What the contract says an indicator is, as data — never a formula."""

    name: IndicatorName
    family: IndicatorFamily
    description: str

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise InvalidIndicatorDefinitionError("an indicator definition needs a description")


_N = IndicatorName
_OHLCV = IndicatorFamily.OHLCV

_DEFINITIONS: tuple[IndicatorDefinition, ...] = (
    IndicatorDefinition(_N.EMA, _OHLCV, "Media móvil exponencial del precio de cierre."),
    IndicatorDefinition(_N.RSI, _OHLCV, "Momento (fuerza relativa) del precio de cierre."),
    IndicatorDefinition(_N.MACD, _OHLCV, "Convergencia/divergencia de dos medias móviles."),
    IndicatorDefinition(
        _N.BOLLINGER_BANDS, _OHLCV, "Volatilidad como banda alrededor de una media móvil."
    ),
    IndicatorDefinition(_N.ATR, _OHLCV, "Volatilidad como rango medio verdadero, sin dirección."),
    IndicatorDefinition(_N.VOLUME, _OHLCV, "Volumen negociado real, agregado por vela."),
    IndicatorDefinition(
        _N.TICK_VOLUME,
        _OHLCV,
        "Recuento de actualizaciones de precio por vela — nunca un sustituto silencioso de VOLUME.",
    ),
    IndicatorDefinition(
        _N.FIBONACCI,
        _OHLCV,
        "Niveles de retroceso de un impulso confirmado (contrato propio: fibonacci-retroceso.md).",
    ),
)

# The eight catalogued names, and only those. Read-only.
INDICATOR_CATALOGUE: Mapping[IndicatorName, IndicatorDefinition] = MappingProxyType(
    {definition.name: definition for definition in _DEFINITIONS}
)


# -- parameters: generic enough that a new indicator never needs a new column -------------------


class ParameterType(enum.StrEnum):
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"


@dataclass(frozen=True, slots=True)
class ParameterConstraint:
    """One parameter an `IndicatorVersion` needs, and the bounds it must satisfy."""

    name: str
    type: ParameterType
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    allowed_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvalidIndicatorDefinitionError("a parameter needs a name")
        if self.type is ParameterType.ENUM and not self.allowed_values:
            raise InvalidIndicatorDefinitionError("an ENUM parameter needs allowed_values")
        if self.type is not ParameterType.ENUM and self.allowed_values:
            raise InvalidIndicatorDefinitionError("allowed_values is only for ENUM parameters")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise InvalidIndicatorDefinitionError("minimum must not exceed maximum")


@dataclass(frozen=True, slots=True)
class IndicatorParameterSchema:
    """Every parameter one `IndicatorVersion` reads, and the version of the set — same principle
    as `SingleCandleParams`/`ThreeCandleParams` (candlestick_single.py/candlestick_multi.py)."""

    version: str
    parameters: tuple[ParameterConstraint, ...] = ()

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise InvalidIndicatorDefinitionError("a parameter schema must carry its version")
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise InvalidIndicatorDefinitionError("parameter names must be unique within a schema")


# -- one immutable, versioned way of computing an indicator --------------------------------------


class InitializationPolicy(enum.StrEnum):
    """How an `IndicatorVersion` is seeded before it produces its first real value."""

    SEEDED_FROM_FIRST_VALUE = "SEEDED_FROM_FIRST_VALUE"
    REQUIRES_FULL_WARMUP_WINDOW = "REQUIRES_FULL_WARMUP_WINDOW"
    # No warmup needed at all (e.g. FIBONACCI: a pure function of an already-confirmed swing).
    NONE = "NONE"


class IncompleteDataPolicy(enum.StrEnum):
    """indicadores.md, section 4: an indicator never invents a value for insufficient data."""

    FAIL_CLOSED_NO_VALUE = "FAIL_CLOSED_NO_VALUE"


class IndicatorStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


@dataclass(frozen=True, slots=True)
class IndicatorVersion:
    """One immutable, versioned way of computing an indicator. POINT5-CORE-001 fills in real ones
    for the seven canonical tools; this registry only fixes the shape every version must carry,
    never a formula or a threshold."""

    indicator: IndicatorName
    version: str
    parameter_schema: IndicatorParameterSchema
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    initialization: InitializationPolicy
    warmup_candles: int
    # Exact decimal places a value is rounded to — never float (CLAUDE.md §6).
    precision: int
    incomplete_data_policy: IncompleteDataPolicy = IncompleteDataPolicy.FAIL_CLOSED_NO_VALUE
    status: IndicatorStatus = IndicatorStatus.ACTIVE

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise InvalidIndicatorDefinitionError("an indicator version must carry its version")
        if self.indicator not in INDICATOR_CATALOGUE:
            raise InvalidIndicatorDefinitionError(
                f"{self.indicator!r} is not in INDICATOR_CATALOGUE"
            )
        if not self.inputs:
            raise InvalidIndicatorDefinitionError("an indicator version must declare its inputs")
        if not self.outputs:
            raise InvalidIndicatorDefinitionError("an indicator version must declare its outputs")
        if isinstance(self.warmup_candles, bool) or self.warmup_candles < 0:
            raise InvalidIndicatorDefinitionError("warmup_candles must be a non-negative integer")
        if isinstance(self.precision, bool) or self.precision < 0:
            raise InvalidIndicatorDefinitionError("precision must be a non-negative integer")


# -- where a version is, in principle, meaningful -------------------------------------------------


@dataclass(frozen=True, slots=True)
class IndicatorMarketCapability:
    """Declares that an `IndicatorVersion` is, in principle, meaningful for one (market, product)
    pair — never inferred from a provider's name (indicadores.md, section 5). Structural only:
    real-time availability for one actual series is POINT5-DATA-001, layered on top, never
    replacing this declaration."""

    indicator: IndicatorName
    indicator_version: str
    market: str
    product: str
    supported: bool
    reason: str = ""

    def __post_init__(self) -> None:
        if self.indicator not in INDICATOR_CATALOGUE:
            raise InvalidIndicatorDefinitionError(
                f"{self.indicator!r} is not in INDICATOR_CATALOGUE"
            )
        if not self.indicator_version.strip():
            raise InvalidIndicatorDefinitionError("indicator_version must not be blank")
        if not self.market.strip() or not self.product.strip():
            raise InvalidIndicatorDefinitionError("market and product must not be blank")
        if not self.supported and not self.reason.strip():
            raise InvalidIndicatorDefinitionError(
                "declaring a market/product unsupported needs a reason"
            )
        if self.supported and self.reason.strip():
            raise InvalidIndicatorDefinitionError(
                "a supported capability carries no rejection reason"
            )


# -- how a (future) StrategySpec would use a version ----------------------------------------------


@dataclass(frozen=True, slots=True)
class StrategyIndicatorUsage:
    """How a `StrategySpec` (point 6, not contracted yet) would use one indicator version.
    `strategy_id` is deliberately an opaque reference: no `StrategySpec` shape is assumed here."""

    strategy_id: str
    indicator: IndicatorName
    indicator_version: str
    function: IndicatorFunction

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise InvalidIndicatorDefinitionError("strategy_id must not be blank")
        if self.indicator not in INDICATOR_CATALOGUE:
            raise InvalidIndicatorDefinitionError(
                f"{self.indicator!r} is not in INDICATOR_CATALOGUE"
            )
        if not self.indicator_version.strip():
            raise InvalidIndicatorDefinitionError("indicator_version must not be blank")


# -- one computed value -----------------------------------------------------------------------


class ObservationAvailability(enum.StrEnum):
    """A marker only: the exact catalogue of reasons (and when each applies) is POINT5-DATA-001.
    This registry only fixes that every observation carries one, and that a missing value is
    never zero-filled (indicadores.md, section 4)."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class IndicatorObservation:
    """One computed value of one indicator version, for one series, at one instant — same
    traceability discipline as `Provenance` (domain/market_data.py, ADR 0002): always says which
    version, which series, and whether the value is real."""

    indicator: IndicatorName
    indicator_version: str
    instrument_id: str
    data_source: str
    timeframe: str
    observed_at: datetime
    as_of: datetime | None
    availability: ObservationAvailability
    values: Mapping[str, Decimal] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        _require_utc(self.observed_at, "observed_at")
        if self.as_of is not None:
            _require_utc(self.as_of, "as_of")
        if self.indicator not in INDICATOR_CATALOGUE:
            raise InvalidIndicatorDefinitionError(
                f"{self.indicator!r} is not in INDICATOR_CATALOGUE"
            )
        if not self.indicator_version.strip():
            raise InvalidIndicatorDefinitionError("indicator_version must not be blank")
        if not self.instrument_id.strip() or not self.data_source.strip():
            raise InvalidIndicatorDefinitionError("instrument_id and data_source must not be blank")
        if self.availability is ObservationAvailability.AVAILABLE and not self.values:
            raise InvalidIndicatorDefinitionError(
                "an AVAILABLE observation must carry at least one value"
            )
        if self.availability is ObservationAvailability.UNAVAILABLE and self.values:
            raise InvalidIndicatorDefinitionError("an UNAVAILABLE observation must carry no values")
