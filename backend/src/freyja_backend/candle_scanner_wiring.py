"""Builds the candle scanner from settings (MARKET-DATA-SCANNER-001).

The only place that knows which provider adapters exist, so the scanner itself and the
rest of the application stay free of any provider name.
"""

from collections.abc import Callable

from freyja_backend.application.candle_scanner import CandleScanner, ScanTarget
from freyja_backend.application.candle_scanner_service import CandleScannerService
from freyja_backend.core.config import Settings
from freyja_backend.core.database import create_database_engine
from freyja_backend.db.session import create_session_factory
from freyja_backend.domain.market_data import CandleProvider, InstrumentRef, Timeframe
from freyja_backend.infrastructure.market_data import binance_spot_rest


def build_candle_scanner_service(settings: Settings) -> CandleScannerService:
    """A ready-to-start service: its own database engine and provider clients, all of
    which it releases when it is stopped."""
    engine = create_database_engine()
    providers: dict[str, CandleProvider] = {}
    targets: list[ScanTarget] = []
    closers: list[Callable[[], None]] = [engine.dispose]
    for code in settings.candle_scanner_sources_list:
        if code == binance_spot_rest.SOURCE_CODE:
            client = binance_spot_rest.BinanceSpotRestClient()
            providers[code] = client
            closers.append(client.close)
            targets.extend(
                ScanTarget(code, InstrumentRef("CRYPTO", "SPOT", symbol), timeframe)
                for symbol in binance_spot_rest.PROVIDER_SYMBOLS
                for timeframe in Timeframe
            )
        else:  # unreachable while Settings validates the list; never scan a guess
            raise ValueError(f"unknown scanner source {code!r}")
    scanner = CandleScanner(create_session_factory(engine), providers, targets)
    return CandleScannerService(
        scanner,
        interval_seconds=settings.candle_scanner_interval_seconds,
        on_close=closers,
    )
