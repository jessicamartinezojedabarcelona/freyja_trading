"""Which sources the scanner can be told to read, and what it builds for them
(MARKET-DATA-SCANNER-001, extended by MARKET-DATA-KRAKEN-REST-001 and
MARKET-DATA-TWELVEDATA-REST-001)."""

import asyncio
from typing import cast

import pytest

from freyja_backend import candle_scanner_wiring
from freyja_backend.application.candle_scanner import CandleScanner
from freyja_backend.core.config import SCANNER_SOURCES, Settings
from freyja_backend.db.catalog_seed_v1 import INSTRUMENTS
from freyja_backend.domain.market_data import Timeframe

TWELVE_DATA_KEY = "test-key-not-a-real-secret"


def settings(**values: object) -> Settings:
    return Settings(_env_file=None, environment="test", **values)  # type: ignore[arg-type]


def built_scanner(sources: str, **extra: object) -> tuple[CandleScanner, object]:
    service = candle_scanner_wiring.build_candle_scanner_service(
        settings(candle_scanner_enabled=True, candle_scanner_sources=sources, **extra)
    )
    return cast(CandleScanner, service._scanner), service


def release(service: object) -> None:
    asyncio.run(service.stop())  # type: ignore[attr-defined]  # closes the engine and clients


def test_the_sources_the_settings_accept_are_exactly_the_ones_that_can_be_built() -> None:
    assert set(candle_scanner_wiring._SOURCES) == SCANNER_SOURCES


def test_every_source_only_publishes_instruments_the_catalog_actually_has() -> None:
    # The frozen v1 seed (`catalog_seed_v1.INSTRUMENTS`) plus the four rows the separate,
    # additive migration 0016_forex_metals_catalog (MARKET-DATA-TWELVEDATA-CATALOG-001)
    # added — that migration never touches the frozen module, so its rows are not in it.
    catalog = {(spec.market, spec.product, spec.symbol) for spec in INSTRUMENTS} | {
        ("FOREX", "SPOT", "GBP/USD"),
        ("FOREX", "SPOT", "USD/JPY"),
        ("FOREX", "SPOT", "USD/CHF"),
        ("METALS", "SPOT", "XAU/USD"),
    }
    for code, (_build, instruments) in candle_scanner_wiring._SOURCES.items():
        assert {(i.market, i.product, i.symbol) for i in instruments} <= catalog, code


def test_binance_alone_builds_only_binance_series() -> None:
    scanner, service = built_scanner("BINANCE")
    try:
        assert {t.source_code for t in scanner.targets} == {"BINANCE"}
        assert len(scanner.targets) == 4 * len(Timeframe)
    finally:
        release(service)


def test_both_crypto_sources_build_a_separate_series_each_for_every_symbol_and_timeframe() -> None:
    scanner, service = built_scanner("BINANCE, kraken")
    try:
        assert len(scanner.targets) == 2 * 4 * len(Timeframe)
        per_source = {
            code: {
                (t.instrument.symbol, t.timeframe) for t in scanner.targets if t.source_code == code
            }
            for code in ("BINANCE", "KRAKEN")
        }
        # Same instruments and periods from each source, as separate targets.
        assert per_source["BINANCE"] == per_source["KRAKEN"]
        assert len(per_source["KRAKEN"]) == 4 * len(Timeframe)
    finally:
        release(service)


def test_an_unknown_source_is_never_guessed() -> None:
    with pytest.raises(ValueError, match="fuente conocida"):
        settings(candle_scanner_enabled=True, candle_scanner_sources="BINANCE,NOWHERE")


def test_twelve_data_alone_builds_series_for_both_forex_and_metals_symbols() -> None:
    scanner, service = built_scanner("TWELVEDATA", twelve_data_api_key=TWELVE_DATA_KEY)
    try:
        assert {t.source_code for t in scanner.targets} == {"TWELVEDATA"}
        markets = {t.instrument.market for t in scanner.targets}
        assert markets == {"FOREX", "METALS"}
        assert len(scanner.targets) == 5 * len(Timeframe)  # 4 FOREX + 1 METALS symbol
    finally:
        release(service)


def test_twelve_data_without_a_configured_key_fails_closed() -> None:
    with pytest.raises(ValueError, match="FREYJA_TWELVE_DATA_API_KEY"):
        settings(candle_scanner_enabled=True, candle_scanner_sources="TWELVEDATA")
