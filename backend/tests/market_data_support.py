"""Shared, deterministic test doubles for the market-data provider.

Only the *external provider* is simulated (an in-process HTTP transport that
speaks the public klines wire format). Everything on our side — the adapter,
the services and PostgreSQL — is the real thing.
"""

from collections.abc import Callable
from datetime import UTC, datetime

import httpx2

from freyja_backend.domain.market_data import InstrumentRef, Timeframe

# 12:07:30 UTC: the 12:05 five-minute candle and the 12:07 one-minute candle
# are still open; everything before them is closed.
NOW = datetime(2026, 9, 24, 12, 7, 30, tzinfo=UTC)
BTC = InstrumentRef("CRYPTO", "SPOT", "BTC/USDT")
ETH = InstrumentRef("CRYPTO", "SPOT", "ETH/USDT")
M1 = Timeframe.M1
M5 = Timeframe.M5
STEP_MS = 300_000

_INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}


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


Rows = list[list[object]]


class SyntheticExchange:
    """A deterministic public-klines endpoint.

    Every candle on the UTC grid exists up to `now` (including the one still in
    progress, like the real provider), and its prices are a pure function of its
    open time — so any two requests covering the same candle agree, exactly as a
    healthy provider would.

    `failing_calls` (1-based call numbers) answer with `fail_status` instead, and
    `mutate` can rewrite the rows of a response to inject gaps or revised values.
    """

    def __init__(
        self,
        *,
        now: datetime = NOW,
        failing_calls: frozenset[int] = frozenset(),
        fail_status: int = 503,
        mutate: Callable[[Rows], Rows] | None = None,
    ) -> None:
        self._now_ms = ms(now)
        self._failing = failing_calls
        self._fail_status = fail_status
        self._mutate = mutate
        self.requests: list[httpx2.Request] = []

    def set_now(self, now: datetime) -> None:
        """Let time pass: candles up to `now` exist from now on."""
        self._now_ms = ms(now)

    @staticmethod
    def price(open_ms: int, step_ms: int) -> int:
        return 100 + (open_ms // step_ms) % 50

    def candle(self, open_ms: int, step_ms: int) -> list[object]:
        base = self.price(open_ms, step_ms)
        return [
            open_ms,
            f"{base}.10000000",
            f"{base + 2}.00000000",
            f"{base - 1}.00000000",
            f"{base + 1}.00000000",
            "10.50000000",
            open_ms + step_ms - 1,
            "0",
            1,
            "0",
            "0",
            "0",
        ]

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if len(self.requests) in self._failing:
            return httpx2.Response(self._fail_status)
        params = request.url.params
        if request.url.path.endswith("/exchangeInfo"):
            symbol = params["symbol"]
            base = symbol.removesuffix("USDT")
            info = {"symbol": symbol, "status": "TRADING", "baseAsset": base, "quoteAsset": "USDT"}
            return ok({"symbols": [info]})
        step = _INTERVAL_MS[params["interval"]]
        limit = int(params["limit"])
        newest = min(int(params["endTime"]) if "endTime" in params else self._now_ms, self._now_ms)
        if "startTime" in params:
            first = -(-int(params["startTime"]) // step) * step  # ceil to the grid
            opens = list(range(first, newest + 1, step))[:limit]
        else:
            last = newest - newest % step
            opens = list(range(last - (limit - 1) * step, last + 1, step))
        rows = [self.candle(open_ms, step) for open_ms in opens if open_ms <= newest]
        return ok(self._mutate(rows) if self._mutate is not None else rows)


class SyntheticKraken:
    """A deterministic Kraken public endpoint, faithful to the real one.

    Behaviour reproduced from the live API (checked on 2026-09-25): OHLC always answers
    with the 720 most recent closed candles plus the one still in progress, takes no limit
    or end, and `since` only trims the front (an old `since` still returns the latest
    720). Failures arrive inside a 200 response, in `error`. Prices are a pure function of
    the open time, so any two requests covering the same candle agree.

    `errors_by_call` maps a 1-based call number to the `error` list that call answers
    with; `mutate` can rewrite the rows of a response to inject gaps or revised values.
    """

    HISTORY = 720

    def __init__(
        self,
        *,
        now: datetime = NOW,
        errors_by_call: dict[int, list[str]] | None = None,
        mutate: Callable[[Rows], Rows] | None = None,
    ) -> None:
        self._now_s = int(now.timestamp())
        self._errors = errors_by_call or {}
        self._mutate = mutate
        self.requests: list[httpx2.Request] = []

    def set_now(self, now: datetime) -> None:
        self._now_s = int(now.timestamp())

    @staticmethod
    def candle(open_s: int, step_s: int) -> list[object]:
        base = 100 + (open_s // step_s) % 50
        return [
            open_s,
            f"{base}.10000000",
            f"{base + 2}.00000000",
            f"{base - 1}.00000000",
            f"{base + 1}.00000000",
            f"{base}.50000000",
            "10.50000000",
            3,
        ]

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        errors = self._errors.get(len(self.requests))
        if errors is not None:
            return ok({"error": errors})
        params = request.url.params
        pair = params["pair"]
        if request.url.path.endswith("/AssetPairs"):
            base = pair.removesuffix("USDT")
            info = {
                "altname": pair,
                "wsname": f"{base}/USDT",
                "base": base,
                "quote": "USDT",
                "status": "online",
            }
            return ok({"error": [], "result": {pair: info}})
        step_s = int(params["interval"]) * 60
        open_now = self._now_s - self._now_s % step_s
        opens = [open_now - step_s * k for k in range(self.HISTORY, -1, -1)]
        if "since" in params:
            opens = [open_s for open_s in opens if open_s >= int(params["since"])]
        rows = [self.candle(open_s, step_s) for open_s in opens]
        if self._mutate is not None:
            rows = self._mutate(rows)
        return ok({"error": [], "result": {pair: rows, "last": open_now - step_s}})
