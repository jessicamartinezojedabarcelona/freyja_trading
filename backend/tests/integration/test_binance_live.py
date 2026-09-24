"""Opt-in live check of the Binance public market-data endpoints.

Skipped unless `FREYJA_LIVE_MARKET_DATA=1`, so CI never depends on Binance or
the internet being up. It only reads public data: no credentials, no account,
no orders. Run it by hand to confirm the adapter still matches the real API:

    FREYJA_LIVE_MARKET_DATA=1 uv run pytest tests/integration/test_binance_live.py -v
"""

import os
from datetime import UTC, datetime

import pytest

from freyja_backend.domain.market_data import DataQuality, InstrumentRef, Timeframe
from freyja_backend.infrastructure.market_data.binance_spot_rest import (
    PROVIDER_SYMBOLS,
    BinanceSpotRestClient,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("FREYJA_LIVE_MARKET_DATA") != "1",
    reason="live Binance check is opt-in: set FREYJA_LIVE_MARKET_DATA=1",
)


@pytest.mark.parametrize("symbol", sorted(PROVIDER_SYMBOLS))
def test_live_metadata_matches_the_catalog(symbol: str) -> None:
    with BinanceSpotRestClient() as client:
        result = client.get_instrument_metadata(InstrumentRef("CRYPTO", "SPOT", symbol))
    assert result.quality is DataQuality.OK, result.issues
    assert result.metadata is not None
    assert result.metadata.trading is True


@pytest.mark.parametrize("timeframe", list(Timeframe))
def test_live_recent_candles_are_closed_utc_and_fresh(timeframe: Timeframe) -> None:
    with BinanceSpotRestClient() as client:
        batch = client.get_closed_candles(
            InstrumentRef("CRYPTO", "SPOT", "BTC/USDT"), timeframe, limit=20
        )
    assert batch.quality is DataQuality.OK, batch.issues
    assert len(batch.candles) >= 19  # the 20th may be the one still in progress
    now = datetime.now(UTC)
    assert all(candle.close_time <= now for candle in batch.candles)
    assert all(candle.open_time.utcoffset() is not None for candle in batch.candles)
    assert batch.candles[-1].close_time > now - 2 * timeframe.duration
