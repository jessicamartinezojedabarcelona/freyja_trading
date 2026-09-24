"""Binance Spot public REST adapter, driven by deterministic responses.

No test here touches the network: an in-process transport plays the provider,
the clock is fixed and `sleep` is recorded instead of waited for, so the suite
is fast and can never become flaky because Binance (or the internet) is down.
The one live check is opt-in, in tests/integration/test_binance_live.py.
"""

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx2
import pytest

from freyja_backend.db.catalog_seed_v1 import INSTRUMENTS, TIMEFRAMES
from freyja_backend.domain.market_data import (
    DataQuality,
    InstrumentRef,
    MarketDataRequestError,
    QualityIssueCode,
    Timeframe,
    UnsupportedInstrumentError,
)
from freyja_backend.infrastructure.market_data.binance_spot_rest import (
    EXCHANGE_INFO_PATH,
    KLINES_PATH,
    PROVIDER_SYMBOLS,
    BinanceRestConfig,
    BinanceSpotRestClient,
)

# 12:07:30 UTC: the 12:05 five-minute candle is still open, 12:00 is closed.
NOW = datetime(2026, 9, 24, 12, 7, 30, tzinfo=UTC)
BTC = InstrumentRef("CRYPTO", "SPOT", "BTC/USDT")
M5 = Timeframe.M5
STEP_MS = 300_000


def ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def at(hour: int, minute: int) -> datetime:
    return datetime(2026, 9, 24, hour, minute, tzinfo=UTC)


def row(
    open_time: datetime,
    *,
    step_ms: int = STEP_MS,
    open_: str = "100.10",
    high: str = "101.00",
    low: str = "99.50",
    close: str = "100.50",
    volume: str = "12.345",
) -> list[object]:
    """One kline row in the provider's 12-field wire format."""
    open_ms = ms(open_time)
    return [open_ms, open_, high, low, close, volume, open_ms + step_ms - 1, "0", 1, "0", "0", "0"]


def clean_rows() -> list[list[object]]:
    return [row(at(11, 55)), row(at(12, 0))]


class Provider:
    """Scripted stand-in for the provider: replays responses, records requests."""

    def __init__(self, *responses: httpx2.Response | Exception) -> None:
        self._responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        outcome = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def ok(payload: object) -> httpx2.Response:
    return httpx2.Response(200, json=payload)


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def make_client(sleeps: list[float]) -> Iterator[Callable[..., BinanceSpotRestClient]]:
    created: list[BinanceSpotRestClient] = []

    def build(provider: Provider, **config: object) -> BinanceSpotRestClient:
        client = BinanceSpotRestClient(
            BinanceRestConfig(**config),  # type: ignore[arg-type]
            transport=httpx2.MockTransport(provider),
            clock=lambda: NOW,
            sleep=sleeps.append,
        )
        created.append(client)
        return client

    yield build
    for client in created:
        client.close()


# -- happy path and what is sent ----------------------------------------------


def test_returns_closed_candles_with_exact_decimals_and_provenance(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(ok(clean_rows()))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)

    assert batch.quality is DataQuality.OK
    assert batch.issues == ()
    assert [c.open_time for c in batch.candles] == [at(11, 55), at(12, 0)]
    first = batch.candles[0]
    assert first.close_time == at(12, 0)  # exclusive end, not the provider's ms-1
    assert (first.open, first.high, first.low, first.close, first.volume) == (
        Decimal("100.10"),
        Decimal("101.00"),
        Decimal("99.50"),
        Decimal("100.50"),
        Decimal("12.345"),
    )
    assert all(isinstance(v, Decimal) for v in (first.open, first.volume))
    assert batch.candles[0].open_time.tzinfo is UTC
    assert batch.provenance.source == "BINANCE"
    assert batch.provenance.provider_symbol == "BTCUSDT"
    assert batch.provenance.endpoint == KLINES_PATH
    assert batch.provenance.received_at == NOW
    assert batch.provenance.attempts == 1
    assert batch.instrument == BTC
    assert batch.timeframe is M5


def test_request_is_public_read_only_and_minimal(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(ok(clean_rows()))
    make_client(provider).get_closed_candles(BTC, M5, limit=2)

    (request,) = provider.requests
    assert request.method == "GET"
    assert request.url.scheme == "https"
    assert request.url.host == "data-api.binance.vision"
    assert request.url.path == KLINES_PATH
    assert dict(request.url.params) == {"symbol": "BTCUSDT", "interval": "5m", "limit": "2"}
    forbidden = {"x-mbx-apikey", "authorization", "cookie"}
    assert forbidden.isdisjoint(name.lower() for name in request.headers)
    assert "signature" not in request.url.params


def test_window_is_sent_as_inclusive_provider_bounds(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(ok([row(at(9, 0)), row(at(9, 5)), row(at(9, 10))]))
    batch = make_client(provider).get_closed_candles(
        BTC, M5, limit=10, start=at(9, 0), end=at(9, 15)
    )
    params = provider.requests[0].url.params
    assert params["startTime"] == str(ms(at(9, 0)))
    assert params["endTime"] == str(ms(at(9, 15)) - 1)  # [start, end) -> inclusive end
    assert batch.quality is DataQuality.OK


@pytest.mark.parametrize(
    ("timeframe", "interval", "step_ms"),
    [
        (Timeframe.M1, "1m", 60_000),
        (Timeframe.M5, "5m", 300_000),
        (Timeframe.M15, "15m", 900_000),
        (Timeframe.H1, "1h", 3_600_000),
        (Timeframe.H4, "4h", 14_400_000),
    ],
)
def test_every_catalog_timeframe_is_translated(
    make_client: Callable[..., BinanceSpotRestClient],
    timeframe: Timeframe,
    interval: str,
    step_ms: int,
) -> None:
    last_open = timeframe.floor(NOW - timedelta(seconds=10)) - timeframe.duration
    provider = Provider(ok([row(last_open, step_ms=step_ms)]))
    batch = make_client(provider).get_closed_candles(BTC, timeframe, limit=1)
    assert provider.requests[0].url.params["interval"] == interval
    assert batch.quality is DataQuality.OK
    assert batch.candles[0].close_time - batch.candles[0].open_time == timeframe.duration


# -- allowlists and request validation -----------------------------------------


@pytest.mark.parametrize(
    "instrument",
    [
        InstrumentRef("FOREX", "SPOT", "EUR/USD"),
        InstrumentRef("CRYPTO", "BINARY_OPTION", "BTC"),
        InstrumentRef("CRYPTO", "SPOT", "DOGE/USDT"),
        InstrumentRef("CRYPTO", "SPOT", "BTCUSDT"),  # provider spelling is not canonical
        InstrumentRef("crypto", "spot", "BTC/USDT"),
    ],
)
def test_only_allowlisted_instruments_are_processed(
    make_client: Callable[..., BinanceSpotRestClient], instrument: InstrumentRef
) -> None:
    provider = Provider(ok([]))
    client = make_client(provider)
    with pytest.raises(UnsupportedInstrumentError):
        client.get_closed_candles(instrument, M5)
    with pytest.raises(UnsupportedInstrumentError):
        client.get_instrument_metadata(instrument)
    assert provider.requests == []  # rejected before anything left the process


def test_only_catalog_timeframes_are_accepted(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(ok([]))
    client = make_client(provider)
    for bogus in ("30s", "1d", "5m"):  # even the plain string "5m" is not a Timeframe
        with pytest.raises(MarketDataRequestError, match="unsupported timeframe"):
            client.get_closed_candles(BTC, bogus)  # type: ignore[arg-type]
    assert provider.requests == []


@pytest.mark.parametrize("limit", [0, -1, 1001, True])
def test_limit_must_be_within_the_provider_bounds(
    make_client: Callable[..., BinanceSpotRestClient], limit: int
) -> None:
    with pytest.raises(MarketDataRequestError, match="limit"):
        make_client(Provider(ok([]))).get_closed_candles(BTC, M5, limit=limit)


def test_start_and_end_must_be_utc_and_ordered(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    client = make_client(Provider(ok([])))
    with pytest.raises(MarketDataRequestError, match="start must be timezone-aware UTC"):
        client.get_closed_candles(BTC, M5, start=datetime(2026, 9, 24, 9, 0))
    with pytest.raises(MarketDataRequestError, match="end must be timezone-aware UTC"):
        client.get_closed_candles(BTC, M5, end=datetime(2026, 9, 24, 9, 0))
    with pytest.raises(MarketDataRequestError, match="start must be before end"):
        client.get_closed_candles(BTC, M5, start=at(9, 5), end=at(9, 5))


def test_provider_symbols_and_intervals_do_not_drift_from_the_catalog() -> None:
    catalog_pairs = {
        spec.symbol for spec in INSTRUMENTS if (spec.market, spec.product) == ("CRYPTO", "SPOT")
    }
    assert set(PROVIDER_SYMBOLS) == catalog_pairs
    for canonical, provider_symbol in PROVIDER_SYMBOLS.items():
        assert provider_symbol == canonical.replace("/", "")
    catalog_seconds = {code: seconds for code, seconds, _ in TIMEFRAMES}
    assert {tf.value: int(tf.duration.total_seconds()) for tf in Timeframe} == catalog_seconds


def test_config_only_accepts_the_public_market_data_host_over_https() -> None:
    for bad in (
        "http://data-api.binance.vision",
        "https://api.example.test",
        "https://data-api.binance.vision.evil.test",
    ):
        with pytest.raises(ValueError, match="base_url"):
            BinanceRestConfig(base_url=bad)
    with pytest.raises(ValueError, match="max_attempts"):
        BinanceRestConfig(max_attempts=0)
    with pytest.raises(ValueError, match="timeout_seconds"):
        BinanceRestConfig(timeout_seconds=0)


# -- open, duplicated, missing and old candles ---------------------------------


def test_candle_in_progress_is_dropped_never_returned_as_closed(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(ok([*clean_rows(), row(at(12, 5))]))  # provider includes the open candle
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=3)
    assert [c.open_time for c in batch.candles] == [at(11, 55), at(12, 0)]
    assert [i.code for i in batch.issues] == [QualityIssueCode.OPEN_CANDLE_EXCLUDED]
    assert batch.quality is DataQuality.OK


def test_duplicates_are_dropped_and_visible_as_degraded(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(ok([row(at(11, 55)), row(at(11, 55)), row(at(12, 0))]))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=3)
    assert len(batch.candles) == 2
    assert batch.quality is DataQuality.DEGRADED
    assert [i.code for i in batch.issues] == [QualityIssueCode.DUPLICATE_DROPPED]


def test_out_of_order_rows_are_sorted_and_visible_as_degraded(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(ok([row(at(12, 0)), row(at(11, 55))]))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert [c.open_time for c in batch.candles] == [at(11, 55), at(12, 0)]
    assert batch.quality is DataQuality.DEGRADED
    assert [i.code for i in batch.issues] == [QualityIssueCode.OUT_OF_ORDER]


def test_gap_is_visible_as_degraded_and_keeps_the_real_candles(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(ok([row(at(11, 45)), row(at(12, 0))]))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert batch.quality is DataQuality.DEGRADED
    assert [i.code for i in batch.issues] == [QualityIssueCode.GAP]
    assert len(batch.candles) == 2


def test_stale_data_is_visible_as_degraded(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(ok([row(at(9, 0)), row(at(9, 5))]))  # provider stopped publishing
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert batch.quality is DataQuality.DEGRADED
    assert [i.code for i in batch.issues] == [QualityIssueCode.STALE]


def test_truncated_historical_window_is_visible_as_degraded(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(ok([row(at(9, 0)), row(at(9, 5))]))  # limit cut the window short
    batch = make_client(provider).get_closed_candles(
        BTC, M5, limit=2, start=at(9, 0), end=at(9, 30)
    )
    assert batch.quality is DataQuality.DEGRADED
    assert [i.code for i in batch.issues] == [QualityIssueCode.INCOMPLETE_RANGE]


# -- invalid or incomplete responses -------------------------------------------


def _bad(index: int, value: object) -> list[list[object]]:
    broken = row(at(12, 0))
    broken[index] = value
    return [broken]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"code": -1121, "msg": "Invalid symbol."}, id="object-instead-of-list"),
        pytest.param("nope", id="string"),
        pytest.param([row(at(12, 0))[:6]], id="truncated-row"),
        pytest.param(["not-a-row"], id="row-not-a-list"),
        pytest.param(_bad(1, 100.1), id="float-price-not-string"),
        pytest.param(_bad(1, "abc"), id="price-not-a-number"),
        pytest.param(_bad(1, "NaN"), id="price-nan"),
        pytest.param(_bad(3, "0"), id="zero-low-price"),
        pytest.param(_bad(2, "50"), id="high-below-low"),
        pytest.param(_bad(5, "-1"), id="negative-volume"),
        pytest.param(_bad(0, "1"), id="timestamp-not-int"),
        pytest.param(_bad(0, True), id="timestamp-bool"),
        pytest.param(_bad(0, -5), id="timestamp-negative"),
        pytest.param(_bad(6, ms(at(12, 0)) + 5), id="close-time-wrong-span"),
        pytest.param([row(at(12, 1))], id="off-the-utc-grid"),
        pytest.param([row(at(12, 0)), row(at(12, 0), close="100.90")], id="conflicting-duplicates"),
        pytest.param([row(at(11, 50)), row(at(11, 55)), row(at(12, 0))], id="more-rows-than-limit"),
    ],
)
def test_invalid_response_is_unavailable_with_no_candles(
    make_client: Callable[..., BinanceSpotRestClient], payload: object
) -> None:
    provider = Provider(ok(payload))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert batch.quality is DataQuality.UNAVAILABLE
    assert batch.candles == ()
    assert [i.code for i in batch.issues] == [QualityIssueCode.INVALID_RESPONSE]
    assert len(provider.requests) == 1  # a bad answer is not retried


def test_body_that_is_not_json_is_unavailable(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(httpx2.Response(200, content=b"<html>gateway</html>"))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert batch.quality is DataQuality.UNAVAILABLE
    assert [i.code for i in batch.issues] == [QualityIssueCode.INVALID_RESPONSE]


# -- rate limits, timeouts and provider errors ----------------------------------


def test_429_waits_the_retry_after_then_recovers(
    make_client: Callable[..., BinanceSpotRestClient], sleeps: list[float]
) -> None:
    provider = Provider(httpx2.Response(429, headers={"Retry-After": "2"}), ok(clean_rows()))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert sleeps == [2.0]
    assert batch.quality is DataQuality.OK
    assert batch.provenance.attempts == 2
    assert len(provider.requests) == 2


def test_429_with_a_retry_after_beyond_the_cap_fails_fast_as_rate_limited(
    make_client: Callable[..., BinanceSpotRestClient], sleeps: list[float]
) -> None:
    provider = Provider(httpx2.Response(429, headers={"Retry-After": "60"}))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert sleeps == []
    assert len(provider.requests) == 1
    assert batch.quality is DataQuality.UNAVAILABLE
    assert batch.candles == ()
    assert [i.code for i in batch.issues] == [QualityIssueCode.RATE_LIMITED]
    assert "Retry-After 60s" in batch.issues[0].detail


def test_persistent_429_uses_bounded_backoff_then_gives_up(
    make_client: Callable[..., BinanceSpotRestClient], sleeps: list[float]
) -> None:
    provider = Provider(httpx2.Response(429))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert sleeps == [0.5, 1.0]  # no sleep after the last attempt
    assert len(provider.requests) == 3
    assert batch.provenance.attempts == 3
    assert batch.quality is DataQuality.UNAVAILABLE
    assert [i.code for i in batch.issues] == [QualityIssueCode.RATE_LIMITED]


def test_backoff_never_exceeds_its_cap(
    make_client: Callable[..., BinanceSpotRestClient], sleeps: list[float]
) -> None:
    provider = Provider(httpx2.Response(503))
    make_client(provider, max_attempts=6).get_closed_candles(BTC, M5, limit=2)
    assert sleeps == [0.5, 1.0, 2.0, 4.0, 4.0]


@pytest.mark.parametrize("junk", ["abc", "-3", "1.5", "Wed, 21 Oct 2026 07:28:00 GMT", ""])
def test_unusable_retry_after_falls_back_to_backoff(
    make_client: Callable[..., BinanceSpotRestClient], sleeps: list[float], junk: str
) -> None:
    provider = Provider(httpx2.Response(429, headers={"Retry-After": junk}), ok(clean_rows()))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert sleeps == [0.5]
    assert batch.quality is DataQuality.OK


def test_418_ip_ban_is_never_retried(
    make_client: Callable[..., BinanceSpotRestClient], sleeps: list[float]
) -> None:
    provider = Provider(httpx2.Response(418, headers={"Retry-After": "120"}))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert sleeps == []
    assert len(provider.requests) == 1
    assert [i.code for i in batch.issues] == [QualityIssueCode.RATE_LIMITED]
    assert batch.quality is DataQuality.UNAVAILABLE


def test_timeout_is_retried_then_reported_as_unavailable(
    make_client: Callable[..., BinanceSpotRestClient], sleeps: list[float]
) -> None:
    provider = Provider(httpx2.ReadTimeout("slow"))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert len(provider.requests) == 3
    assert sleeps == [0.5, 1.0]
    assert batch.quality is DataQuality.UNAVAILABLE
    assert batch.candles == ()
    assert [i.code for i in batch.issues] == [QualityIssueCode.TIMEOUT]


def test_timeout_then_success_is_ok(
    make_client: Callable[..., BinanceSpotRestClient], sleeps: list[float]
) -> None:
    provider = Provider(httpx2.ConnectTimeout("slow"), ok(clean_rows()))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert batch.quality is DataQuality.OK
    assert batch.provenance.attempts == 2
    assert sleeps == [0.5]


def test_network_error_is_reported_without_leaking_details(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(httpx2.ConnectError("dns failure for internal-host"))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert batch.quality is DataQuality.UNAVAILABLE
    assert [i.code for i in batch.issues] == [QualityIssueCode.PROVIDER_ERROR]
    assert batch.issues[0].detail == "network error: ConnectError"


def test_5xx_is_retried_and_can_recover(
    make_client: Callable[..., BinanceSpotRestClient], sleeps: list[float]
) -> None:
    provider = Provider(httpx2.Response(502), httpx2.Response(503), ok(clean_rows()))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert batch.quality is DataQuality.OK
    assert sleeps == [0.5, 1.0]
    assert batch.provenance.attempts == 3


@pytest.mark.parametrize("status", [400, 401, 403, 404, 451])
def test_client_errors_are_not_retried(
    make_client: Callable[..., BinanceSpotRestClient], sleeps: list[float], status: int
) -> None:
    provider = Provider(httpx2.Response(status, json={"code": -1121}))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert len(provider.requests) == 1
    assert sleeps == []
    assert batch.quality is DataQuality.UNAVAILABLE
    assert [i.code for i in batch.issues] == [QualityIssueCode.PROVIDER_ERROR]
    assert batch.issues[0].detail == f"rejected: HTTP {status}"


def test_redirects_are_not_followed(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(httpx2.Response(302, headers={"Location": "https://evil.example/x"}))
    batch = make_client(provider).get_closed_candles(BTC, M5, limit=2)
    assert len(provider.requests) == 1
    assert batch.quality is DataQuality.UNAVAILABLE


# -- instrument metadata ---------------------------------------------------------


def symbol_info(**overrides: object) -> dict[str, object]:
    info: dict[str, object] = {
        "symbol": "BTCUSDT",
        "status": "TRADING",
        "baseAsset": "BTC",
        "quoteAsset": "USDT",
        "isSpotTradingAllowed": True,
    }
    return {**info, **overrides}


def test_metadata_confirms_the_catalog_mapping(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(ok({"symbols": [symbol_info()]}))
    result = make_client(provider).get_instrument_metadata(BTC)
    assert result.quality is DataQuality.OK
    assert result.metadata is not None
    assert result.metadata.provider_symbol == "BTCUSDT"
    assert (result.metadata.base_asset, result.metadata.quote_asset) == ("BTC", "USDT")
    assert result.metadata.trading is True
    assert result.provenance.endpoint == EXCHANGE_INFO_PATH
    (request,) = provider.requests
    assert request.url.path == EXCHANGE_INFO_PATH
    assert dict(request.url.params) == {"symbol": "BTCUSDT"}


@pytest.mark.parametrize(
    "overrides",
    [{"status": "BREAK"}, {"isSpotTradingAllowed": False}],
)
def test_metadata_for_a_symbol_not_trading_is_degraded(
    make_client: Callable[..., BinanceSpotRestClient], overrides: dict[str, object]
) -> None:
    provider = Provider(ok({"symbols": [symbol_info(**overrides)]}))
    result = make_client(provider).get_instrument_metadata(BTC)
    assert result.quality is DataQuality.DEGRADED
    assert result.metadata is not None and result.metadata.trading is False
    assert [i.code for i in result.issues] == [QualityIssueCode.INSTRUMENT_NOT_TRADING]


def test_metadata_that_contradicts_the_catalog_is_unavailable(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(ok({"symbols": [symbol_info(baseAsset="WBTC")]}))
    result = make_client(provider).get_instrument_metadata(BTC)
    assert result.quality is DataQuality.UNAVAILABLE
    assert result.metadata is None
    assert [i.code for i in result.issues] == [QualityIssueCode.SYMBOL_MISMATCH]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param([], id="list"),
        pytest.param({"symbols": []}, id="no-symbols"),
        pytest.param({"symbols": [symbol_info(), symbol_info()]}, id="two-symbols"),
        pytest.param({"symbols": [symbol_info(symbol="ETHUSDT")]}, id="other-symbol"),
        pytest.param({"symbols": [symbol_info(status=None)]}, id="missing-status"),
        pytest.param({"symbols": [symbol_info(quoteAsset="")]}, id="empty-quote"),
        pytest.param({"symbols": [symbol_info(isSpotTradingAllowed="yes")]}, id="flag-not-bool"),
    ],
)
def test_invalid_metadata_response_is_unavailable(
    make_client: Callable[..., BinanceSpotRestClient], payload: object
) -> None:
    result = make_client(Provider(ok(payload))).get_instrument_metadata(BTC)
    assert result.quality is DataQuality.UNAVAILABLE
    assert result.metadata is None
    assert [i.code for i in result.issues] == [QualityIssueCode.INVALID_RESPONSE]


def test_metadata_failures_are_reported_like_candle_failures(
    make_client: Callable[..., BinanceSpotRestClient], sleeps: list[float]
) -> None:
    provider = Provider(httpx2.Response(429, headers={"Retry-After": "600"}))
    result = make_client(provider).get_instrument_metadata(BTC)
    assert result.quality is DataQuality.UNAVAILABLE
    assert [i.code for i in result.issues] == [QualityIssueCode.RATE_LIMITED]
    assert sleeps == []


# -- the whole surface, end to end ---------------------------------------------------


def test_only_the_two_public_endpoints_are_ever_called(
    make_client: Callable[..., BinanceSpotRestClient],
) -> None:
    provider = Provider(ok({"symbols": [symbol_info()]}), ok(clean_rows()))
    client = make_client(provider)
    client.get_instrument_metadata(BTC)
    client.get_closed_candles(BTC, M5, limit=2)
    assert {request.url.path for request in provider.requests} == {KLINES_PATH, EXCHANGE_INFO_PATH}
    assert {request.method for request in provider.requests} == {"GET"}


def test_failures_are_logged_without_secrets_or_payloads(
    make_client: Callable[..., BinanceSpotRestClient], caplog: pytest.LogCaptureFixture
) -> None:
    body = json.dumps({"msg": "internal detail that must not be logged"})
    provider = Provider(httpx2.Response(400, content=body))
    with caplog.at_level("WARNING"):
        make_client(provider).get_closed_candles(BTC, M5, limit=2)
    (record,) = caplog.records
    assert record.getMessage() == "market_data_unavailable"
    assert "internal detail" not in caplog.text
    assert record.__dict__["issue"] == "PROVIDER_ERROR"
