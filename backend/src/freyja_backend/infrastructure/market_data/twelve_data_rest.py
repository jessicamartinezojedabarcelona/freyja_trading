"""Twelve Data REST adapter (MARKET-DATA-TWELVEDATA-REST-001, ADR 0009).

The only place that knows Twelve Data's wire format. It turns the one endpoint below into
the provider-agnostic contracts of `domain.market_data`:

* ``GET /time_series`` — candles, and (via its ``meta`` object) symbol metadata.

Hard boundaries, enforced in code and by tests (the same as Binance's and Kraken's
adapters):

* Public market-data host only, over HTTPS, no redirects. The path allowlist below is the
  whole surface, and REAL execution stays out of reach.
* Only allowlisted FOREX/METALS x SPOT instruments and catalog timeframes.
* Every failure mode ends as an explicit UNAVAILABLE / DEGRADED result with the reason; a
  candle is never delivered unless it is closed and valid.

What is specific to Twelve Data:

* Unlike Binance and Kraken, this provider requires an API key (CLAUDE.md §5: never
  logged, never in the repo — it travels only in the `Authorization` request header to
  Twelve Data's own host, supplied by the caller via `TwelveDataRestConfig`).
* Twelve Data covers two catalog markets from one symbol table: FOREX (EUR/USD, GBP/USD,
  USD/JPY, USD/CHF) and METALS (XAU/USD) — `_resolve_symbol` checks both the symbol *and*
  its catalog market, unlike the single-market Binance/Kraken adapters.
* The free tier is capped at 800 requests/day and about 8/minute. `daily_quota` is a
  local, in-memory, per-process counter that resets by UTC calendar day (it does not
  survive a process restart — a documented limitation, consistent with the project's other
  "Render Free sleeps" caveats). `min_request_interval_seconds` spaces requests so a full
  scanner pass stays under the per-minute limit.
* Every request asks for ``timezone=UTC`` explicitly and ``order=ASC``, so candle opens
  never depend on the account's default timezone or the provider's default ordering.
* Numbers arrive as strings (exact); `volume` is absent or null for FX/metals pairs
  (there is no central exchange), which is treated as zero.
* There is no separate metadata endpoint: `get_instrument_metadata` reads the base/quote
  pair back from `time_series`' own `meta.symbol` (not `meta.currency_base`/
  `currency_quote`, which are free-text names, not catalog codes) with `outputsize=1`.

Left unverified without a live API key (flagged in the ADR, to be confirmed against the
real API before this adapter is used in production): whether Twelve Data ever answers an
error with HTTP 200 and a JSON `status: "error"` body (handled defensively here) in
addition to standard HTTP error status codes; whether the most recent candle in a
`time_series` answer can still be in progress (if so, `assess_candles`' close_time <= now
check already excludes it, the same as for Binance and Kraken).

Retries are bounded and deterministic (exponential backoff without jitter, injectable
`sleep`); a `Retry-After` longer than the configured cap is not waited for — the call
fails fast as RATE_LIMITED so the caller decides. The client is not thread-safe: one
caller at a time, as the scanner does.
"""

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
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
    ProviderLimits,
    QualityIssue,
    QualityIssueCode,
    Timeframe,
    UnsupportedInstrumentError,
    assess_candles,
    quality_from_issues,
    utc_now,
)

logger = logging.getLogger(__name__)

SOURCE_CODE = "TWELVEDATA"
DEFAULT_BASE_URL = "https://api.twelvedata.com"

TIME_SERIES_PATH = "/time_series"

_ALLOWED_HOSTS = frozenset({"api.twelvedata.com"})
_ALLOWED_PATHS = frozenset({TIME_SERIES_PATH})

# Twelve Data's documented maximum `outputsize` for one request.
MAX_CANDLE_LIMIT = 5000

# Canonical catalog symbol -> provider symbol. Immutable and explicit: nothing outside
# this table is ever requested. A test keeps it from drifting from the catalog rows added
# by MARKET-DATA-TWELVEDATA-CATALOG-001.
PROVIDER_SYMBOLS: Mapping[str, str] = MappingProxyType(
    {
        "EUR/USD": "EUR/USD",
        "GBP/USD": "GBP/USD",
        "USD/JPY": "USD/JPY",
        "USD/CHF": "USD/CHF",
        "XAU/USD": "XAU/USD",
    }
)

# The catalog market each symbol above belongs to (Jessica's decision, 2026-09-29: gold is
# not a currency pair, so it is catalogued under METALS, not FOREX).
SYMBOL_MARKETS: Mapping[str, str] = MappingProxyType(
    {
        "EUR/USD": "FOREX",
        "GBP/USD": "FOREX",
        "USD/JPY": "FOREX",
        "USD/CHF": "FOREX",
        "XAU/USD": "METALS",
    }
)

_INTERVALS: Mapping[Timeframe, str] = MappingProxyType(
    {
        Timeframe.M1: "1min",
        Timeframe.M5: "5min",
        Timeframe.M15: "15min",
        Timeframe.H1: "1h",
        Timeframe.H4: "4h",
    }
)

_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
_MIN_DATETIME = datetime(2000, 1, 1, tzinfo=UTC)
_MAX_DATETIME = datetime(2100, 1, 1, tzinfo=UTC)

DEFAULT_DAILY_QUOTA = 800


@dataclass(frozen=True, slots=True)
class TwelveDataRestConfig:
    # No default: unlike Binance/Kraken, this provider cannot be reached without one, so a
    # missing key must fail at construction, not surface as a confusing request error.
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 5.0
    max_attempts: int = 3
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 8.0
    # Longest `Retry-After` we are willing to sit through inside one call.
    max_retry_after_seconds: float = 10.0
    # Minimum pause between two requests: keeps a full scanner pass under the free tier's
    # ~8 requests/minute limit.
    min_request_interval_seconds: float = 8.0
    # The free tier's daily cap. Tracked locally, per process (see module docstring).
    daily_quota: int = DEFAULT_DAILY_QUOTA
    # A candle that closed less than this ago may legitimately not be published yet.
    publication_grace: timedelta = DEFAULT_PUBLICATION_GRACE

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("api_key must not be blank")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
            raise ValueError(
                f"base_url must be https on one of {sorted(_ALLOWED_HOSTS)}, got {self.base_url!r}"
            )
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.min_request_interval_seconds < 0:
            raise ValueError("min_request_interval_seconds must not be negative")
        if self.daily_quota < 1:
            raise ValueError("daily_quota must be at least 1")


@dataclass(frozen=True, slots=True)
class _Fetched:
    payload: object | None
    failure: QualityIssue | None
    attempts: int


@dataclass(slots=True)
class _Quota:
    """Per-process, resets by UTC calendar day. Does not survive a restart."""

    used_on: date | None = field(default=None)
    used: int = 0


class TwelveDataRestClient:
    """Sync client; owns one HTTP connection pool, so `close()` it (or use `with`)."""

    limits = ProviderLimits(max_candles_per_request=MAX_CANDLE_LIMIT)

    def __init__(
        self,
        config: TwelveDataRestConfig,
        *,
        transport: httpx2.BaseTransport | None = None,
        clock: Clock = utc_now,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._clock = clock
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None
        self._quota = _Quota()
        self._http = httpx2.Client(
            base_url=self._config.base_url,
            timeout=httpx2.Timeout(self._config.timeout_seconds),
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "Authorization": f"apikey {self._config.api_key}",
            },
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
            "timezone": "UTC",
            "order": "ASC",
            "outputsize": limit,
        }
        if start is not None:
            params["start_date"] = start.strftime(_DATETIME_FORMAT)
        if end is not None:
            # One second early: `[start, end)` is half-open, and end_date's exact
            # boundary semantics are unverified without a live key.
            params["end_date"] = (end - timedelta(seconds=1)).strftime(_DATETIME_FORMAT)
        fetched = self._get_json(TIME_SERIES_PATH, params)
        received_at = self._clock()
        provenance = Provenance(
            source=SOURCE_CODE,
            endpoint=TIME_SERIES_PATH,
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
            candles = _parse_time_series(fetched.payload, provider_symbol, timeframe)
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
        params: dict[str, str | int] = {
            "symbol": provider_symbol,
            "interval": _INTERVALS[Timeframe.M1],
            "timezone": "UTC",
            "order": "DESC",
            "outputsize": 1,
        }
        fetched = self._get_json(TIME_SERIES_PATH, params)
        provenance = Provenance(
            source=SOURCE_CODE,
            endpoint=TIME_SERIES_PATH,
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
            # `_parse_meta` already checks `meta.symbol == provider_symbol`, and
            # `PROVIDER_SYMBOLS` is an identity mapping, so base/quote (split from that same
            # echoed symbol) can never disagree with the catalog: unlike Kraken's
            # AssetPairs, Twelve Data's `meta` gives no independent ground truth to cross-
            # check against, so there is no SYMBOL_MISMATCH case to detect here.
            base, quote, has_values = _parse_meta(fetched.payload, provider_symbol)
        except InvalidMarketDataError as exc:
            return unavailable(QualityIssue(QualityIssueCode.INVALID_RESPONSE, str(exc)))

        issues: tuple[QualityIssue, ...] = ()
        if not has_values:
            issues = (
                QualityIssue(
                    QualityIssueCode.INSTRUMENT_NOT_TRADING,
                    f"{provider_symbol} returned no recent values",
                ),
            )
        return MetadataResult(
            metadata=InstrumentMetadata(
                instrument=instrument,
                provider_symbol=provider_symbol,
                base_asset=base,
                quote_asset=quote,
                trading=has_values,
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
            quota_issue = self._check_daily_quota()
            if quota_issue is not None:
                return _Fetched(None, quota_issue, attempt - 1)
            delay = self._backoff(attempt)
            self._respect_request_spacing()
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
                        payload = response.json()
                    except ValueError:
                        return _Fetched(
                            None,
                            QualityIssue(QualityIssueCode.INVALID_RESPONSE, "body is not JSON"),
                            attempt,
                        )
                    error, retryable = _reported_error(payload)
                    if error is None:
                        return _Fetched(payload, None, attempt)
                    if not retryable:
                        return _Fetched(None, error, attempt)
                    failure = error
                elif status == 429:
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
                elif status in (401, 403):
                    return _Fetched(
                        None,
                        QualityIssue(
                            QualityIssueCode.PROVIDER_ERROR,
                            f"rejected: HTTP {status} (check the configured API key)",
                        ),
                        attempt,
                    )
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

    def _check_daily_quota(self) -> QualityIssue | None:
        today = self._clock().date()
        if self._quota.used_on != today:
            self._quota.used_on = today
            self._quota.used = 0
        if self._quota.used >= self._config.daily_quota:
            return QualityIssue(
                QualityIssueCode.RATE_LIMITED,
                f"daily quota of {self._config.daily_quota} requests exhausted for "
                f"{today.isoformat()} UTC",
            )
        self._quota.used += 1
        return None

    def _respect_request_spacing(self) -> None:
        """Wait, if needed, so two requests are never closer than the configured spacing."""
        spacing = self._config.min_request_interval_seconds
        now = self._monotonic()
        if self._last_request_at is not None:
            wait = self._last_request_at + spacing - now
            if wait > 0:
                self._sleep(wait)
                now = self._monotonic()
        self._last_request_at = now

    def _backoff(self, attempt: int) -> float:
        return min(
            self._config.backoff_base_seconds * float(2 ** (attempt - 1)),
            self._config.backoff_max_seconds,
        )


# -- request validation and translation -----------------------------------------


def _resolve_symbol(instrument: InstrumentRef) -> str:
    if instrument.product != "SPOT":
        raise UnsupportedInstrumentError(
            f"only SPOT is supported, got {instrument.market} x {instrument.product}"
        )
    try:
        provider_symbol = PROVIDER_SYMBOLS[instrument.symbol]
    except KeyError:
        raise UnsupportedInstrumentError(
            f"{instrument.symbol} is not an allowlisted instrument"
        ) from None
    expected_market = SYMBOL_MARKETS[instrument.symbol]
    if instrument.market != expected_market:
        raise UnsupportedInstrumentError(
            f"{instrument.symbol} is catalogued under {expected_market}, got {instrument.market}"
        )
    return provider_symbol


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
            # Fixed, non-sensitive text; never the API key or a raw provider payload.
            "detail": issue.detail,
            "attempts": attempts,
        },
    )


# -- response parsing -------------------------------------------------------------


def _reported_error(payload: object) -> tuple[QualityIssue | None, bool]:
    """Twelve Data can report a failure inside an HTTP 200 body (unverified without a
    live key; handled defensively). Returns `(None, False)` when the answer is not an
    error, otherwise the issue and whether retrying the same request could help: a rate
    limit or a transient provider error may clear up, a rejected request (bad symbol, bad
    key) never will."""
    if not isinstance(payload, dict):
        return QualityIssue(QualityIssueCode.INVALID_RESPONSE, "body is not a JSON object"), False
    if payload.get("status") != "error":
        return None, False
    code = payload.get("code")
    message = payload.get("message")
    detail = (
        f"provider error {code}: {message}"
        if isinstance(message, str)
        else f"provider error {code}"
    )
    if code == 429:
        return QualityIssue(QualityIssueCode.RATE_LIMITED, detail), True
    if code in (401, 403):
        return QualityIssue(QualityIssueCode.PROVIDER_ERROR, detail), False
    if isinstance(code, int) and code >= 500:
        return QualityIssue(QualityIssueCode.PROVIDER_ERROR, detail), True
    return QualityIssue(QualityIssueCode.INVALID_RESPONSE, detail), False


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise InvalidMarketDataError(f"invalid datetime field: {value!r}")
    try:
        parsed = datetime.strptime(value, _DATETIME_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        raise InvalidMarketDataError(f"unrecognised datetime format: {value!r}") from None
    if not _MIN_DATETIME <= parsed < _MAX_DATETIME:
        raise InvalidMarketDataError(f"datetime out of plausible range: {value!r}")
    return parsed


def _parse_time_series(payload: object, provider_symbol: str, timeframe: Timeframe) -> list[Candle]:
    if not isinstance(payload, dict):
        raise InvalidMarketDataError("time_series payload is not an object")
    meta = payload.get("meta")
    if not isinstance(meta, dict) or meta.get("symbol") != provider_symbol:
        raise InvalidMarketDataError("time_series answered for a different symbol than requested")
    values = payload.get("values", [])
    if values is None:
        values = []
    if not isinstance(values, list):
        raise InvalidMarketDataError("time_series values is not a list")
    step = timeframe.duration
    candles: list[Candle] = []
    for entry in values:
        if not isinstance(entry, dict):
            raise InvalidMarketDataError("incomplete time_series row")
        open_time = _parse_datetime(entry.get("datetime"))
        raw_volume = entry.get("volume")
        volume = Decimal("0") if raw_volume in (None, "") else _as_decimal(raw_volume)
        candles.append(
            Candle(
                open_time=open_time,
                close_time=open_time + step,
                open=_as_decimal(entry.get("open")),
                high=_as_decimal(entry.get("high")),
                low=_as_decimal(entry.get("low")),
                close=_as_decimal(entry.get("close")),
                volume=volume,
            )
        )
    return candles


def _parse_meta(payload: object, provider_symbol: str) -> tuple[str, str, bool]:
    if not isinstance(payload, dict):
        raise InvalidMarketDataError("time_series payload is not an object")
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise InvalidMarketDataError("time_series payload has no meta object")
    symbol_field = meta.get("symbol")
    if (
        not isinstance(symbol_field, str)
        or symbol_field != provider_symbol
        or symbol_field.count("/") != 1
    ):
        raise InvalidMarketDataError("time_series meta symbol does not match the request")
    base, quote = symbol_field.split("/")
    if not base or not quote:
        raise InvalidMarketDataError("time_series meta symbol has an empty asset")
    values = payload.get("values")
    has_values = isinstance(values, list) and len(values) > 0
    return base, quote, has_values


def _as_decimal(value: object) -> Decimal:
    # The provider sends numbers as strings precisely so they stay exact; a JSON float
    # here would already have lost precision, so it is rejected.
    if not isinstance(value, str):
        raise InvalidMarketDataError(f"numeric field is not a string: {value!r}")
    try:
        return Decimal(value)
    except InvalidOperation:
        raise InvalidMarketDataError(f"numeric field is not a number: {value!r}") from None
