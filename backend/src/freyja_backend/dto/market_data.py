import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, PlainSerializer

from freyja_backend.domain.market_data import DataQuality, QualityIssueCode

# Read-only external contract for stored candles (MARKET-DATA-PERSISTENCE-001).
# Prices and volume travel as JSON *strings*, never numbers: a JSON number would
# be parsed as a binary float by most clients and lose exactness. The text is the
# plain decimal ("100.5", "0.00012"), without trailing zeros or exponents.


def _plain_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


ExactDecimal = Annotated[Decimal, PlainSerializer(_plain_decimal, return_type=str)]


class FreshnessStatus(enum.StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    NO_DATA = "NO_DATA"


class CandleOut(BaseModel):
    """One closed candle covering ``[open_time, close_time)`` (UTC)."""

    open_time: datetime
    close_time: datetime
    open: ExactDecimal
    high: ExactDecimal
    low: ExactDecimal
    close: ExactDecimal
    volume: ExactDecimal
    # Quality of the batch this candle arrived in.
    quality: DataQuality
    # When Freyja first received it.
    received_at: datetime


class QualityIssueOut(BaseModel):
    code: QualityIssueCode
    detail: str


class GapOut(BaseModel):
    """`missing` consecutive candles are absent after the one opened at `after`."""

    after_open_time: datetime
    missing: int


class FreshnessOut(BaseModel):
    """How current the stored series is, judged at `checked_at`. Independent of
    the requested window: it always refers to the newest stored candle."""

    status: FreshnessStatus
    checked_at: datetime
    latest_open_time: datetime | None
    latest_close_time: datetime | None
    latest_received_at: datetime | None


class ProviderStatusOut(BaseModel):
    """Outcome of the latest sync attempt for this series (null if never tried)."""

    last_attempt_at: datetime
    last_success_at: datetime | None
    last_status: DataQuality
    last_issue_codes: list[str]
    last_detail: str | None
    consecutive_failures: int


class CandleSeriesOut(BaseModel):
    instrument_id: uuid.UUID
    data_source_code: str
    timeframe_code: str
    # Oldest first. Empty does not mean "zero": read `quality` and `issues`.
    candles: list[CandleOut]
    # Anything but OK must be shown as degraded, never as a normal chart.
    quality: DataQuality
    issues: list[QualityIssueOut]
    gaps: list[GapOut]
    freshness: FreshnessOut
    provider: ProviderStatusOut | None
    # Only when reading forward from `start`: more candles follow at `next_start`.
    has_more: bool
    next_start: datetime | None
