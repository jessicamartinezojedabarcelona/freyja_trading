"""Opt-in live check of the Twelve Data `/time_series` endpoint.

Skipped unless `FREYJA_LIVE_MARKET_DATA=1` *and* `FREYJA_TWELVE_DATA_API_KEY` is set, so CI
never depends on Twelve Data, the internet, or a real key being available. Run it by hand
to confirm the adapter still matches the real API — and to settle what this adapter's
module docstring flags as unverified (embedded-error shape, whether the newest candle can
still be forming):

    FREYJA_LIVE_MARKET_DATA=1 FREYJA_TWELVE_DATA_API_KEY=... \\
        uv run pytest tests/integration/test_twelve_data_live.py -v

Each parametrized case is one request: with the free tier's ~8/minute limit, this file's
own request count stays deliberately small.
"""

import os
from datetime import UTC, datetime

import pytest

from freyja_backend.domain.market_data import DataQuality, InstrumentRef, Timeframe
from freyja_backend.infrastructure.market_data.twelve_data_rest import (
    PROVIDER_SYMBOLS,
    SYMBOL_MARKETS,
    TwelveDataRestClient,
    TwelveDataRestConfig,
)

_API_KEY = os.environ.get("FREYJA_TWELVE_DATA_API_KEY")

pytestmark = pytest.mark.skipif(
    os.environ.get("FREYJA_LIVE_MARKET_DATA") != "1" or not _API_KEY,
    reason="live Twelve Data check is opt-in: set FREYJA_LIVE_MARKET_DATA=1 and "
    "FREYJA_TWELVE_DATA_API_KEY=...",
)


def _client() -> TwelveDataRestClient:
    assert _API_KEY is not None  # narrows the type; the skipif above already guarantees it
    return TwelveDataRestClient(TwelveDataRestConfig(api_key=_API_KEY))


@pytest.mark.parametrize("symbol", sorted(PROVIDER_SYMBOLS))
def test_live_metadata_matches_the_catalog(symbol: str) -> None:
    with _client() as client:
        instrument = InstrumentRef(SYMBOL_MARKETS[symbol], "SPOT", symbol)
        result = client.get_instrument_metadata(instrument)
    assert result.quality is DataQuality.OK, result.issues
    assert result.metadata is not None
    assert result.metadata.trading is True


def test_live_recent_candles_are_closed_utc_and_fresh() -> None:
    with _client() as client:
        batch = client.get_closed_candles(
            InstrumentRef("FOREX", "SPOT", "EUR/USD"), Timeframe.M1, limit=20
        )
    assert batch.quality is DataQuality.OK, batch.issues
    assert len(batch.candles) >= 19  # the 20th may be the one still in progress
    now = datetime.now(UTC)
    assert all(candle.close_time <= now for candle in batch.candles)
    assert all(candle.open_time.utcoffset() is not None for candle in batch.candles)
    assert batch.candles[-1].close_time > now - 2 * Timeframe.M1.duration
