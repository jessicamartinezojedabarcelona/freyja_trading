"""Builds the candle scanner from settings (MARKET-DATA-SCANNER-001).

The only place that knows which provider adapters exist, so the scanner itself and the
rest of the application stay free of any provider name.
"""

from collections.abc import Callable, Mapping
from typing import Protocol

from freyja_backend.application.candle_scanner import CandleScanner, ScanTarget
from freyja_backend.application.candle_scanner_service import CandleScannerService
from freyja_backend.core.config import Settings
from freyja_backend.core.database import create_database_engine
from freyja_backend.db.session import create_session_factory
from freyja_backend.domain.market_data import CandleProvider, InstrumentRef, Timeframe
from freyja_backend.infrastructure.market_data import (
    binance_spot_rest,
    kraken_spot_rest,
    twelve_data_rest,
)


class _SourceClient(CandleProvider, Protocol):
    """A provider client the scanner owns, so it must be able to release its connections."""

    def close(self) -> None: ...


def _require_twelve_data_api_key(settings: Settings) -> str:
    key = settings.twelve_data_api_key
    if not key:  # unreachable while Settings validates this when TWELVEDATA is enabled
        raise ValueError("FREYJA_TWELVE_DATA_API_KEY must be set to enable the TWELVEDATA source")
    return key


# Every source the scanner can read: how to build its client (given settings, since Twelve
# Data needs an API key), which canonical instruments it publishes, and which timeframes it
# can actually serve for them (TWELVEDATA-4H-GRID-001: not every source supports every
# catalog timeframe — Twelve Data's forex/metals 4h candles don't align to Freyja's UTC
# grid, so its adapter never offers Timeframe.H4). A test keeps the keys in step with
# `SCANNER_SOURCES`.
_SOURCES: Mapping[
    str, tuple[Callable[[Settings], _SourceClient], tuple[InstrumentRef, ...], frozenset[Timeframe]]
] = {
    binance_spot_rest.SOURCE_CODE: (
        lambda _settings: binance_spot_rest.BinanceSpotRestClient(),
        tuple(
            InstrumentRef("CRYPTO", "SPOT", symbol) for symbol in binance_spot_rest.PROVIDER_SYMBOLS
        ),
        frozenset(Timeframe),
    ),
    kraken_spot_rest.SOURCE_CODE: (
        lambda _settings: kraken_spot_rest.KrakenSpotRestClient(),
        tuple(
            InstrumentRef("CRYPTO", "SPOT", symbol) for symbol in kraken_spot_rest.PROVIDER_SYMBOLS
        ),
        frozenset(Timeframe),
    ),
    twelve_data_rest.SOURCE_CODE: (
        lambda settings: twelve_data_rest.TwelveDataRestClient(
            twelve_data_rest.TwelveDataRestConfig(api_key=_require_twelve_data_api_key(settings))
        ),
        tuple(
            InstrumentRef(twelve_data_rest.SYMBOL_MARKETS[symbol], "SPOT", symbol)
            for symbol in twelve_data_rest.PROVIDER_SYMBOLS
        ),
        twelve_data_rest.SUPPORTED_TIMEFRAMES,
    ),
}


def build_candle_scanner_service(settings: Settings) -> CandleScannerService:
    """A ready-to-start service: its own database engine and provider clients, all of
    which it releases when it is stopped."""
    engine = create_database_engine()
    providers: dict[str, CandleProvider] = {}
    targets: list[ScanTarget] = []
    closers: list[Callable[[], None]] = [engine.dispose]
    for code in settings.candle_scanner_sources_list:
        if (
            code not in _SOURCES
        ):  # unreachable while Settings validates the list; never scan a guess
            raise ValueError(f"unknown scanner source {code!r}")
        build_client, instruments, timeframes = _SOURCES[code]
        client = build_client(settings)
        providers[code] = client
        closers.append(client.close)
        targets.extend(
            ScanTarget(code, instrument, timeframe)
            for instrument in instruments
            for timeframe in timeframes
        )
    scanner = CandleScanner(create_session_factory(engine), providers, targets)
    return CandleScannerService(
        scanner,
        interval_seconds=settings.candle_scanner_interval_seconds,
        on_close=closers,
    )
