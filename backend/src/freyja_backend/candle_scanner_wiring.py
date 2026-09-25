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
from freyja_backend.infrastructure.market_data import binance_spot_rest, kraken_spot_rest


class _SourceClient(CandleProvider, Protocol):
    """A provider client the scanner owns, so it must be able to release its connections."""

    def close(self) -> None: ...


# Every source the scanner can read: how to build its client and which canonical CRYPTO x
# SPOT symbols it publishes. A test keeps the keys in step with `SCANNER_SOURCES`.
_SOURCES: Mapping[str, tuple[Callable[[], _SourceClient], tuple[str, ...]]] = {
    binance_spot_rest.SOURCE_CODE: (
        binance_spot_rest.BinanceSpotRestClient,
        tuple(binance_spot_rest.PROVIDER_SYMBOLS),
    ),
    kraken_spot_rest.SOURCE_CODE: (
        kraken_spot_rest.KrakenSpotRestClient,
        tuple(kraken_spot_rest.PROVIDER_SYMBOLS),
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
        build_client, symbols = _SOURCES[code]
        client = build_client()
        providers[code] = client
        closers.append(client.close)
        targets.extend(
            ScanTarget(code, InstrumentRef("CRYPTO", "SPOT", symbol), timeframe)
            for symbol in symbols
            for timeframe in Timeframe
        )
    scanner = CandleScanner(create_session_factory(engine), providers, targets)
    return CandleScannerService(
        scanner,
        interval_seconds=settings.candle_scanner_interval_seconds,
        on_close=closers,
    )
