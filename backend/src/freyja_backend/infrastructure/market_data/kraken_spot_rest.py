"""Kraken Spot public REST adapter (MARKET-DATA-KRAKEN-REST-001, ADR 0007).

The only place that knows Kraken's wire format. It turns the two public,
unauthenticated, read-only market-data endpoints below into the
provider-agnostic contracts of `domain.market_data`:

* ``GET /0/public/OHLC``       — candles
* ``GET /0/public/AssetPairs`` — pair metadata

Hard boundaries, enforced in code and by tests (the same as the Binance adapter):

* Public market-data host only, over HTTPS, no redirects. Nothing here
  authenticates or reaches an account or order endpoint — the path allowlist
  below is the whole surface, and REAL execution stays out of reach.
* Only allowlisted CRYPTO x SPOT instruments and catalog timeframes.
* Every failure mode ends as an explicit UNAVAILABLE / DEGRADED result with
  the reason; a candle is never delivered unless it is closed and valid.

What is specific to Kraken (all verified against the live API on 2026-09-25):

* Errors arrive with HTTP 200 and a non-empty ``error`` list, never as a status code.
  Rate limiting is one of them (``EGeneral:Too many requests``): a burst of about nine
  requests trips it. The client therefore spaces its requests out and treats it as
  RATE_LIMITED.
* ``OHLC`` always answers with the 720 most recent candles **plus the one still in
  progress**, and takes no limit or end. ``since`` older than that horizon still returns
  the latest 720, so a window is selected here, on the client side. `limits` tells the
  scanner about both the page size and the horizon.
* Numbers arrive as strings (exact), times as whole seconds since the epoch.
* Kraken calls Bitcoin ``XBT``; the catalog says ``BTC``. `PROVIDER_SYMBOLS` and
  `_ASSET_ALIASES` are the only translation.

Retries are bounded and deterministic (exponential backoff without jitter,
injectable `sleep`); a `Retry-After` longer than the configured cap is not
waited for — the call fails fast as RATE_LIMITED so the caller decides.
The client is not thread-safe: one caller at a time, as the scanner does.
"""

import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
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

SOURCE_CODE = "KRAKEN"
DEFAULT_BASE_URL = "https://api.kraken.com"

OHLC_PATH = "/0/public/OHLC"
ASSET_PAIRS_PATH = "/0/public/AssetPairs"

_ALLOWED_HOSTS = frozenset({"api.kraken.com"})
_ALLOWED_PATHS = frozenset({OHLC_PATH, ASSET_PAIRS_PATH})

# Closed candles Kraken keeps per interval (it answers with these plus the open one).
HISTORY_CANDLES = 720

# Canonical catalog symbol -> provider pair. Immutable and explicit: nothing outside this
# table is ever requested. It is a subset of catalog v1's CRYPTO x SPOT instruments (a
# test keeps it from drifting).
PROVIDER_SYMBOLS: Mapping[str, str] = MappingProxyType(
    {
        "BTC/USDT": "XBTUSDT",
        "ETH/USDT": "ETHUSDT",
        "SOL/USDT": "SOLUSDT",
        "XRP/USDT": "XRPUSDT",
    }
)

# Kraken's asset codes that differ from the catalog's.
_ASSET_ALIASES: Mapping[str, str] = MappingProxyType({"XBT": "BTC"})

# Interval in minutes, as Kraken names them.
_INTERVALS: Mapping[Timeframe, int] = MappingProxyType(
    {
        Timeframe.M1: 1,
        Timeframe.M5: 5,
        Timeframe.M15: 15,
        Timeframe.H1: 60,
        Timeframe.H4: 240,
    }
)

_OHLC_FIELDS = 8  # time, open, high, low, close, vwap, volume, trade count
_MAX_EPOCH_S = 4_102_444_800  # 2100-01-01: anything later is not a real timestamp
# Kraken's error codes are short fixed strings; anything else is not echoed back.
_ERROR_CODE = re.compile(r"^[EW][A-Za-z]{1,20}:[A-Za-z0-9 _.:-]{1,60}$")


@dataclass(frozen=True, slots=True)
class KrakenRestConfig:
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 5.0
    max_attempts: int = 3
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 8.0
    # Longest `Retry-After` we are willing to sit through inside one call.
    max_retry_after_seconds: float = 10.0
    # Minimum pause between two requests. Kraken's public limit trips after a burst of
    # about nine; this keeps a full scanner pass (20 series) far below it.
    min_request_interval_seconds: float = 1.0
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
        if self.min_request_interval_seconds < 0:
            raise ValueError("min_request_interval_seconds must not be negative")


@dataclass(frozen=True, slots=True)
class _Fetched:
    payload: object | None
    failure: QualityIssue | None
    attempts: int


class KrakenSpotRestClient:
    """Sync client; owns one HTTP connection pool, so `close()` it (or use `with`)."""

    limits = ProviderLimits(
        max_candles_per_request=HISTORY_CANDLES, history_candles=HISTORY_CANDLES
    )

    def __init__(
        self,
        config: KrakenRestConfig | None = None,
        *,
        transport: httpx2.BaseTransport | None = None,
        clock: Clock = utc_now,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config or KrakenRestConfig()
        self._clock = clock
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None
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
        """Closed candles, oldest first. `[start, end)` is a historical window (at most
        `limit` candles, from `start`); with neither, the most recent `limit` candles
        (freshness is then checked). Only what Kraken still serves can be returned: a
        window older than its horizon comes back incomplete, never invented."""
        provider_symbol = _resolve_symbol(instrument)
        interval = _resolve_interval(timeframe)
        _validate_request(limit, start, end)

        requested_at = self._clock()
        params: dict[str, str | int] = {"pair": provider_symbol, "interval": interval}
        if start is not None:
            # One second early: whether `since` is inclusive or exclusive at the exact
            # candle open, `start` is still returned. The window is enforced below.
            params["since"] = _to_s(start) - 1
        fetched = self._get_json(OHLC_PATH, params)
        received_at = self._clock()
        provenance = Provenance(
            source=SOURCE_CODE,
            endpoint=OHLC_PATH,
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
            rows = _parse_ohlc(fetched.payload, provider_symbol, timeframe)
            selected = _select_window(rows, now=received_at, limit=limit, start=start, end=end)
            assessment = assess_candles(
                selected,
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
        fetched = self._get_json(ASSET_PAIRS_PATH, {"pair": provider_symbol})
        provenance = Provenance(
            source=SOURCE_CODE,
            endpoint=ASSET_PAIRS_PATH,
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
            base, quote, trading = _parse_pair_info(fetched.payload, provider_symbol)
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
                    f"{provider_symbol} is not currently open for trading",
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
                    failure = _reported_error(payload)
                    if failure is None:
                        return _Fetched(payload, None, attempt)
                    if failure.code is QualityIssueCode.INVALID_RESPONSE:
                        return _Fetched(None, failure, attempt)  # a rejection: retrying is futile
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


def _resolve_interval(timeframe: Timeframe) -> int:
    if not isinstance(timeframe, Timeframe) or timeframe not in _INTERVALS:
        raise MarketDataRequestError(f"unsupported timeframe: {timeframe!r}")
    return _INTERVALS[timeframe]


def _validate_request(limit: int, start: datetime | None, end: datetime | None) -> None:
    if isinstance(limit, bool) or not 1 <= limit <= HISTORY_CANDLES:
        raise MarketDataRequestError(f"limit must be between 1 and {HISTORY_CANDLES}")
    for name, moment in (("start", start), ("end", end)):
        if moment is not None and (moment.tzinfo is None or moment.utcoffset() != timedelta(0)):
            raise MarketDataRequestError(f"{name} must be timezone-aware UTC")
    if start is not None and end is not None and start >= end:
        raise MarketDataRequestError("start must be before end")


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SECOND = timedelta(seconds=1)


def _to_s(moment: datetime) -> int:
    return (moment - _EPOCH) // _SECOND


def _from_s(seconds: int) -> datetime:
    return _EPOCH + timedelta(seconds=seconds)


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


def _reported_error(payload: object) -> QualityIssue | None:
    """Kraken reports failures inside a 200 response, in `error`. None means none."""
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), list):
        return QualityIssue(QualityIssueCode.INVALID_RESPONSE, "response has no error list")
    errors = [item for item in payload["error"] if isinstance(item, str)]
    if not errors and not payload["error"]:
        return None
    text = "; ".join(item if _ERROR_CODE.match(item) else "unrecognised error" for item in errors)
    lowered = text.lower()
    if "too many requests" in lowered or "rate limit" in lowered or "lockout" in lowered:
        return QualityIssue(QualityIssueCode.RATE_LIMITED, f"rate limited: {text}")
    if any(item.startswith("EService:") for item in errors) or "internal error" in lowered:
        return QualityIssue(QualityIssueCode.PROVIDER_ERROR, f"provider error: {text}")
    return QualityIssue(QualityIssueCode.INVALID_RESPONSE, f"provider rejected the request: {text}")


def _result_of(payload: object, what: str) -> dict[str, object]:
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
        raise InvalidMarketDataError(f"{what} payload has no result object")
    return payload["result"]  # type: ignore[no-any-return]


def _parse_ohlc(payload: object, provider_symbol: str, timeframe: Timeframe) -> list[Candle]:
    result = _result_of(payload, "OHLC")
    keys = [key for key in result if key != "last"]
    if keys != [provider_symbol]:
        raise InvalidMarketDataError("OHLC answered for a different pair than requested")
    if not isinstance(result.get("last"), int) or isinstance(result.get("last"), bool):
        raise InvalidMarketDataError("OHLC result has no valid 'last' marker")
    rows = result[provider_symbol]
    if not isinstance(rows, list):
        raise InvalidMarketDataError("OHLC rows are not a list")
    if len(rows) > HISTORY_CANDLES + 1:
        raise InvalidMarketDataError(f"provider returned {len(rows)} rows, more than it promises")
    step = int(timeframe.duration.total_seconds())
    candles: list[Candle] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < _OHLC_FIELDS:
            raise InvalidMarketDataError("incomplete OHLC row")
        opened = _as_epoch_s(row[0])
        candles.append(
            Candle(
                open_time=_from_s(opened),
                close_time=_from_s(opened + step),
                open=_as_decimal(row[1]),
                high=_as_decimal(row[2]),
                low=_as_decimal(row[3]),
                close=_as_decimal(row[4]),
                volume=_as_decimal(row[6]),
            )
        )
    return candles


def _select_window(
    candles: Sequence[Candle],
    *,
    now: datetime,
    limit: int,
    start: datetime | None,
    end: datetime | None,
) -> list[Candle]:
    """What the caller asked for out of the fixed answer Kraken gives.

    Kraken takes no limit or end, so they are applied here, on closed candles only: the
    most recent `limit` when no `start` was given, otherwise the first `limit` from
    `start`. The candle still in progress stays in the selection, so assessing it reports
    `OPEN_CANDLE_EXCLUDED`, except when candles were cut off between the window's start
    and it: appended after that cut, it would look like a gap that does not exist.
    """
    in_window = [
        candle
        for candle in candles
        if (start is None or candle.open_time >= start) and (end is None or candle.open_time < end)
    ]
    closed = [candle for candle in in_window if candle.close_time <= now]
    still_open = [candle for candle in in_window if candle.close_time > now]
    chosen = closed[-limit:] if start is None else closed[:limit]
    cut_from_the_start = start is not None and len(closed) > limit
    return chosen if cut_from_the_start else chosen + still_open


def _parse_pair_info(payload: object, provider_symbol: str) -> tuple[str, str, bool]:
    result = _result_of(payload, "AssetPairs")
    if len(result) != 1:
        raise InvalidMarketDataError("AssetPairs did not return exactly one pair")
    key, info = next(iter(result.items()))
    if key != provider_symbol or not isinstance(info, dict):
        raise InvalidMarketDataError("AssetPairs returned a different pair than requested")
    wsname, status = info.get("wsname"), info.get("status")
    if not isinstance(wsname, str) or wsname.count("/") != 1 or not isinstance(status, str):
        raise InvalidMarketDataError("AssetPairs entry is missing wsname/status")
    base, quote = (_ASSET_ALIASES.get(code, code) for code in wsname.split("/"))
    if not base or not quote:
        raise InvalidMarketDataError("AssetPairs wsname has an empty asset")
    return base, quote, status == "online"


def _as_epoch_s(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_EPOCH_S:
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
