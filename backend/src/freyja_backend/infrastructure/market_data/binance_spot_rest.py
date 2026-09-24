"""Binance Spot public REST adapter (MARKET-DATA-BINANCE-REST-001, ADR 0002).

The only place that knows Binance's wire format. It turns the two public,
unauthenticated, read-only market-data endpoints below into the
provider-agnostic contracts of `domain.market_data`:

* ``GET /api/v3/klines``       — candles
* ``GET /api/v3/exchangeInfo`` — symbol metadata

Hard boundaries, enforced in code and by tests:

* Public market-data host only, over HTTPS, no redirects. Nothing here
  authenticates or reaches an account or order endpoint — the path allowlist
  below is the whole surface, and REAL execution stays out of reach. Trading
  adapters, with their own credentials handling, belong to later tasks.
* Only allowlisted CRYPTO x SPOT instruments and catalog timeframes.
* Every failure mode ends as an explicit UNAVAILABLE / DEGRADED result with
  the reason; a candle is never delivered unless it is closed and valid.

Retries are bounded and deterministic (exponential backoff without jitter,
injectable `sleep`); a `Retry-After` longer than the configured cap is not
waited for — the call fails fast as RATE_LIMITED so the caller decides.
"""

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from types import MappingProxyType, TracebackType
from typing import Self
from urllib.parse import urlparse

import httpx2

from freyja_backend.domain.market_data import (
    DEFAULT_PUBLICATION_GRACE,
    Candle,
    CandleBatch,
    Clock,
    DataQuality,
    InstrumentMetadata,
    InstrumentRef,
    InvalidMarketDataError,
    MarketDataRequestError,
    MetadataResult,
    Provenance,
    QualityIssue,
    QualityIssueCode,
    Timeframe,
    UnsupportedInstrumentError,
    assess_candles,
    quality_from_issues,
    utc_now,
)

logger = logging.getLogger(__name__)

SOURCE_CODE = "BINANCE"
DEFAULT_BASE_URL = "https://data-api.binance.vision"

KLINES_PATH = "/api/v3/klines"
EXCHANGE_INFO_PATH = "/api/v3/exchangeInfo"

_ALLOWED_HOSTS = frozenset({"data-api.binance.vision"})
_ALLOWED_PATHS = frozenset({KLINES_PATH, EXCHANGE_INFO_PATH})

MAX_CANDLE_LIMIT = 1000

# Canonical catalog symbol -> provider symbol. Immutable and explicit: nothing
# outside this table is ever requested. It is a subset of catalog v1's
# CRYPTO x SPOT instruments (a test keeps it from drifting).
PROVIDER_SYMBOLS: Mapping[str, str] = MappingProxyType(
    {
        "BTC/USDT": "BTCUSDT",
        "ETH/USDT": "ETHUSDT",
        "SOL/USDT": "SOLUSDT",
        "XRP/USDT": "XRPUSDT",
    }
)

_INTERVALS: Mapping[Timeframe, str] = MappingProxyType(
    {
        Timeframe.M1: "1m",
        Timeframe.M5: "5m",
        Timeframe.M15: "15m",
        Timeframe.H1: "1h",
        Timeframe.H4: "4h",
    }
)

_KLINE_FIELDS = 12
_MAX_EPOCH_MS = 4_102_444_800_000  # 2100-01-01: anything later is not a real timestamp


@dataclass(frozen=True, slots=True)
class BinanceRestConfig:
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 5.0
    max_attempts: int = 3
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 4.0
    # Longest `Retry-After` we are willing to sit through inside one call.
    max_retry_after_seconds: float = 10.0
    # A candle that closed less than this ago may legitimately not be published yet.
    publication_grace: timedelta = DEFAULT_PUBLICATION_GRACE

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
            raise ValueError(
                f"base_url must be https on one of {sorted(_ALLOWED_HOSTS)}, got {self.base_url!r}"
            )
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class _Fetched:
    payload: object | None
    failure: QualityIssue | None
    attempts: int


class BinanceSpotRestClient:
    """Sync client; owns one HTTP connection pool, so `close()` it (or use `with`)."""

    def __init__(
        self,
        config: BinanceRestConfig | None = None,
        *,
        transport: httpx2.BaseTransport | None = None,
        clock: Clock = utc_now,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config or BinanceRestConfig()
        self._clock = clock
        self._sleep = sleep
        self._http = httpx2.Client(
            base_url=self._config.base_url,
            timeout=httpx2.Timeout(self._config.timeout_seconds),
            follow_redirects=False,
            headers={"Accept": "application/json"},
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    # -- public API ---------------------------------------------------------

    def get_closed_candles(
        self,
        instrument: InstrumentRef,
        timeframe: Timeframe,
        *,
        limit: int = 500,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> CandleBatch:
        """Closed candles, oldest first. `[start, end)` is a historical window;
        with neither, the most recent candles (freshness is then checked)."""
        provider_symbol = _resolve_symbol(instrument)
        interval = _resolve_interval(timeframe)
        _validate_request(limit, start, end)

        requested_at = self._clock()
        params: dict[str, str | int] = {
            "symbol": provider_symbol,
            "interval": interval,
            "limit": limit,
        }
        if start is not None:
            params["startTime"] = _to_ms(start)
        if end is not None:
            params["endTime"] = _to_ms(end) - 1  # provider's endTime is inclusive
        fetched = self._get_json(KLINES_PATH, params)
        received_at = self._clock()
        provenance = Provenance(
            source=SOURCE_CODE,
            endpoint=KLINES_PATH,
            provider_symbol=provider_symbol,
            requested_at=requested_at,
            received_at=received_at,
            attempts=fetched.attempts,
        )

        def unavailable(issue: QualityIssue) -> CandleBatch:
            _log_failure(provider_symbol, issue, fetched.attempts)
            return CandleBatch(
                instrument=instrument,
                timeframe=timeframe,
                candles=(),
                quality=DataQuality.UNAVAILABLE,
                issues=(issue,),
                provenance=provenance,
            )

        if fetched.failure is not None:
            return unavailable(fetched.failure)
        try:
            candles = _parse_klines(fetched.payload, timeframe, limit)
            assessment = assess_candles(
                candles,
                timeframe=timeframe,
                now=received_at,
                start=start,
                end=end,
                publication_grace=self._config.publication_grace,
            )
        except InvalidMarketDataError as exc:
            return unavailable(QualityIssue(QualityIssueCode.INVALID_RESPONSE, str(exc)))
        return CandleBatch(
            instrument=instrument,
            timeframe=timeframe,
            candles=assessment.candles,
            quality=quality_from_issues(assessment.issues),
            issues=assessment.issues,
            provenance=provenance,
        )

    def get_instrument_metadata(self, instrument: InstrumentRef) -> MetadataResult:
        provider_symbol = _resolve_symbol(instrument)
        requested_at = self._clock()
        fetched = self._get_json(EXCHANGE_INFO_PATH, {"symbol": provider_symbol})
        provenance = Provenance(
            source=SOURCE_CODE,
            endpoint=EXCHANGE_INFO_PATH,
            provider_symbol=provider_symbol,
            requested_at=requested_at,
            received_at=self._clock(),
            attempts=fetched.attempts,
        )

        def unavailable(issue: QualityIssue) -> MetadataResult:
            _log_failure(provider_symbol, issue, fetched.attempts)
            return MetadataResult(None, DataQuality.UNAVAILABLE, (issue,), provenance)

        if fetched.failure is not None:
            return unavailable(fetched.failure)
        try:
            base, quote, trading = _parse_symbol_info(fetched.payload, provider_symbol)
        except InvalidMarketDataError as exc:
            return unavailable(QualityIssue(QualityIssueCode.INVALID_RESPONSE, str(exc)))

        expected_base, expected_quote = instrument.symbol.split("/")
        if (base, quote) != (expected_base, expected_quote):
            return unavailable(
                QualityIssue(
                    QualityIssueCode.SYMBOL_MISMATCH,
                    f"{provider_symbol} is {base}/{quote} at the provider, "
                    f"but the catalog says {instrument.symbol}",
                )
            )
        issues: tuple[QualityIssue, ...] = ()
        if not trading:
            issues = (
                QualityIssue(
                    QualityIssueCode.INSTRUMENT_NOT_TRADING,
                    f"{provider_symbol} is not currently open for spot trading",
                ),
            )
        return MetadataResult(
            metadata=InstrumentMetadata(
                instrument=instrument,
                provider_symbol=provider_symbol,
                base_asset=base,
                quote_asset=quote,
                trading=trading,
            ),
            quality=quality_from_issues(issues),
            issues=issues,
            provenance=provenance,
        )

    # -- transport with bounded retries --------------------------------------

    def _get_json(self, path: str, params: Mapping[str, str | int]) -> _Fetched:
        if path not in _ALLOWED_PATHS:
            raise MarketDataRequestError(f"path {path!r} is not an allowlisted public endpoint")
        attempts = self._config.max_attempts
        failure: QualityIssue | None = None
        for attempt in range(1, attempts + 1):
            delay = self._backoff(attempt)
            try:
                response = self._http.get(path, params=params)
            except httpx2.TimeoutException:
                failure = QualityIssue(QualityIssueCode.TIMEOUT, "no response within timeout")
            except httpx2.TransportError as exc:
                failure = QualityIssue(
                    QualityIssueCode.PROVIDER_ERROR, f"network error: {type(exc).__name__}"
                )
            else:
                status = response.status_code
                if status == 200:
                    try:
                        return _Fetched(response.json(), None, attempt)
                    except ValueError:
                        return _Fetched(
                            None,
                            QualityIssue(QualityIssueCode.INVALID_RESPONSE, "body is not JSON"),
                            attempt,
                        )
                if status == 418:
                    return _Fetched(
                        None,
                        QualityIssue(
                            QualityIssueCode.RATE_LIMITED, "provider banned this IP (418)"
                        ),
                        attempt,
                    )
                if status == 429:
                    retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                    failure = QualityIssue(
                        QualityIssueCode.RATE_LIMITED,
                        "rate limited (429)"
                        + (f", Retry-After {retry_after:g}s" if retry_after is not None else ""),
                    )
                    if retry_after is not None:
                        if retry_after > self._config.max_retry_after_seconds:
                            return _Fetched(None, failure, attempt)  # too long to wait here
                        delay = retry_after
                elif status >= 500:
                    failure = QualityIssue(
                        QualityIssueCode.PROVIDER_ERROR, f"provider error HTTP {status}"
                    )
                else:
                    return _Fetched(
                        None,
                        QualityIssue(QualityIssueCode.PROVIDER_ERROR, f"rejected: HTTP {status}"),
                        attempt,
                    )
            if attempt < attempts:
                self._sleep(delay)
        return _Fetched(None, failure, attempts)

    def _backoff(self, attempt: int) -> float:
        return min(
            self._config.backoff_base_seconds * float(2 ** (attempt - 1)),
            self._config.backoff_max_seconds,
        )


# -- request validation and translation -----------------------------------------


def _resolve_symbol(instrument: InstrumentRef) -> str:
    if instrument.market != "CRYPTO" or instrument.product != "SPOT":
        raise UnsupportedInstrumentError(
            f"only CRYPTO x SPOT is supported, got {instrument.market} x {instrument.product}"
        )
    try:
        return PROVIDER_SYMBOLS[instrument.symbol]
    except KeyError:
        raise UnsupportedInstrumentError(
            f"{instrument.symbol} is not an allowlisted instrument"
        ) from None


def _resolve_interval(timeframe: Timeframe) -> str:
    if not isinstance(timeframe, Timeframe) or timeframe not in _INTERVALS:
        raise MarketDataRequestError(f"unsupported timeframe: {timeframe!r}")
    return _INTERVALS[timeframe]


def _validate_request(limit: int, start: datetime | None, end: datetime | None) -> None:
    if isinstance(limit, bool) or not 1 <= limit <= MAX_CANDLE_LIMIT:
        raise MarketDataRequestError(f"limit must be between 1 and {MAX_CANDLE_LIMIT}")
    for name, moment in (("start", start), ("end", end)):
        if moment is not None and (moment.tzinfo is None or moment.utcoffset() != timedelta(0)):
            raise MarketDataRequestError(f"{name} must be timezone-aware UTC")
    if start is not None and end is not None and start >= end:
        raise MarketDataRequestError("start must be before end")


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MILLISECOND = timedelta(milliseconds=1)


def _to_ms(moment: datetime) -> int:
    return (moment - _EPOCH) // _MILLISECOND


def _from_ms(milliseconds: int) -> datetime:
    return _EPOCH + timedelta(milliseconds=milliseconds)


def _parse_retry_after(value: str | None) -> float | None:
    """Seconds form only; anything else (missing, date, negative, junk) is
    treated as absent so the bounded backoff applies instead."""
    if value is None:
        return None
    text = value.strip()
    return float(int(text)) if text.isascii() and text.isdigit() else None


def _log_failure(provider_symbol: str, issue: QualityIssue, attempts: int) -> None:
    logger.warning(
        "market_data_unavailable",
        extra={
            "source": SOURCE_CODE,
            "provider_symbol": provider_symbol,
            "issue": issue.code.value,
            "attempts": attempts,
        },
    )


# -- response parsing -------------------------------------------------------------


def _parse_klines(payload: object, timeframe: Timeframe, limit: int) -> list[Candle]:
    if not isinstance(payload, list):
        raise InvalidMarketDataError("klines payload is not a list")
    if len(payload) > limit:
        raise InvalidMarketDataError(f"provider returned {len(payload)} rows for limit {limit}")
    step_ms = int(timeframe.duration.total_seconds() * 1000)
    candles: list[Candle] = []
    for row in payload:
        if not isinstance(row, list) or len(row) < _KLINE_FIELDS:
            raise InvalidMarketDataError("incomplete kline row")
        open_ms = _as_epoch_ms(row[0])
        close_ms = _as_epoch_ms(row[6])
        if close_ms != open_ms + step_ms - 1:
            raise InvalidMarketDataError(
                f"kline {open_ms} does not span exactly one {timeframe.value}"
            )
        candles.append(
            Candle(
                open_time=_from_ms(open_ms),
                close_time=_from_ms(open_ms + step_ms),
                open=_as_decimal(row[1]),
                high=_as_decimal(row[2]),
                low=_as_decimal(row[3]),
                close=_as_decimal(row[4]),
                volume=_as_decimal(row[5]),
            )
        )
    return candles


def _parse_symbol_info(payload: object, provider_symbol: str) -> tuple[str, str, bool]:
    if not isinstance(payload, dict):
        raise InvalidMarketDataError("exchangeInfo payload is not an object")
    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or len(symbols) != 1 or not isinstance(symbols[0], dict):
        raise InvalidMarketDataError("exchangeInfo did not return exactly one symbol")
    info = symbols[0]
    if info.get("symbol") != provider_symbol:
        raise InvalidMarketDataError("exchangeInfo returned a different symbol than requested")
    base, quote, status = info.get("baseAsset"), info.get("quoteAsset"), info.get("status")
    if not all(isinstance(value, str) and value for value in (base, quote, status)):
        raise InvalidMarketDataError("exchangeInfo symbol is missing baseAsset/quoteAsset/status")
    spot_allowed = info.get("isSpotTradingAllowed", True)
    if not isinstance(spot_allowed, bool):
        raise InvalidMarketDataError("isSpotTradingAllowed is not a boolean")
    return str(base), str(quote), status == "TRADING" and spot_allowed


def _as_epoch_ms(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_EPOCH_MS:
        raise InvalidMarketDataError(f"invalid timestamp {value!r}")
    return value


def _as_decimal(value: object) -> Decimal:
    # The provider sends numbers as strings precisely so they stay exact; a
    # JSON float here would already have lost precision, so it is rejected.
    if not isinstance(value, str):
        raise InvalidMarketDataError(f"numeric field is not a string: {value!r}")
    try:
        return Decimal(value)
    except InvalidOperation:
        raise InvalidMarketDataError(f"numeric field is not a number: {value!r}") from None
