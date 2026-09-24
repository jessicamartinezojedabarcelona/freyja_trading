import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from freyja_backend.db.base import Base
from freyja_backend.domain.market_data import DataQuality

# Market-data persistence (MARKET-DATA-PERSISTENCE-001, ADR 0003).
#
# Market data is common to every account: nothing here is owned by a user.
#
# A stored candle is *closed* and *immutable*: the natural key below prevents
# duplicates, and a database trigger (migration 0013) rejects any UPDATE, so
# neither an upsert nor a bug can silently rewrite a confirmed candle. A
# provider that later reports different values for the same key is surfaced
# as a revision by the sync service, never applied over the stored row.

# Wide enough for any provider quote (8 decimals are typical) without ever
# rounding; NUMERIC is exact, never float.
_PRICE = Numeric(38, 12)


class Candle(Base):
    __tablename__ = "freyja2_candles"
    __table_args__ = (
        CheckConstraint("close_time > open_time", name="ck_freyja2_candles_close_after_open"),
        CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0",
            name="ck_freyja2_candles_prices_positive",
        ),
        CheckConstraint("volume >= 0", name="ck_freyja2_candles_volume_non_negative"),
        CheckConstraint(
            "high >= low AND high >= open AND high >= close AND low <= open AND low <= close",
            name="ck_freyja2_candles_ohlc_consistent",
        ),
        CheckConstraint("quality <> 'UNAVAILABLE'", name="ck_freyja2_candles_quality_has_data"),
    )

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_data_sources.id"), primary_key=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_instruments.instrument_id"), primary_key=True
    )
    timeframe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_timeframes.id"), primary_key=True
    )
    # Candle covers [open_time, close_time); both timezone-aware UTC.
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    close_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    high: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    low: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    close: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    volume: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    # Quality of the batch this candle arrived in (never UNAVAILABLE: a failed
    # fetch stores no candle).
    quality: Mapped[DataQuality] = mapped_column(
        Enum(DataQuality, name="freyja2_data_quality", native_enum=True), nullable=False
    )
    # When Freyja first received it — the provider's clock is never trusted
    # for this, and the value is never rewritten.
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return (
            f"Candle(instrument_id={self.instrument_id!r}, "
            f"timeframe_id={self.timeframe_id!r}, open_time={self.open_time!r})"
        )


class MarketDataSyncState(Base):
    """Outcome of the latest sync attempt per (source, instrument, timeframe):
    the only way the API can tell "the provider is failing" apart from "there
    is simply nothing new". Unlike candles, this row is meant to be updated."""

    __tablename__ = "freyja2_market_data_sync_state"
    __table_args__ = (
        CheckConstraint(
            "consecutive_failures >= 0", name="ck_freyja2_sync_state_failures_non_negative"
        ),
    )

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_data_sources.id"), primary_key=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_instruments.instrument_id"), primary_key=True
    )
    timeframe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_timeframes.id"), primary_key=True
    )
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Last time the provider actually delivered data (status OK or DEGRADED).
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[DataQuality] = mapped_column(
        Enum(DataQuality, name="freyja2_data_quality", native_enum=True, create_type=False),
        nullable=False,
    )
    last_issue_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), nullable=False, default=list
    )
    last_detail: Mapped[str | None] = mapped_column(String(300))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return (
            f"MarketDataSyncState(instrument_id={self.instrument_id!r}, "
            f"timeframe_id={self.timeframe_id!r}, last_status={self.last_status!r})"
        )
