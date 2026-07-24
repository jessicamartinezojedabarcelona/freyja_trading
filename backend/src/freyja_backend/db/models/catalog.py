import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from freyja_backend.db.base import Base

# Catalog identity tables (POINT1-DB-001, integrity hardened in
# POINT1-DB-001 2026-07-24). Extensible catalogs — per MODELO EXISTENTE regla
# 8/10, adding a market/product/asset/timeframe is a data insertion, never a
# schema change, so none of these use a native Postgres enum: `code` is a
# unique natural key, the UUID `id` is the stable primary key. This module
# answers only *what* an instrument is — venue, data source, broker symbol,
# credentials, activation status, and regulatory permissions belong to
# POINT1-PROVIDER-001 / POINT1-CAPABILITY-001, not here.
#
# Semantic limits PostgreSQL cannot enforce physically (POINT1-DB-001
# 2026-07-24 correction): FKs prove a referenced row exists; CHECK
# constraints prove textual/numeric shape; the composite FK below proves an
# underlying instrument belongs to the same market as its referencer. None
# of that lets PostgreSQL deduce or validate market/product/asset semantics
# from a symbol — e.g. nothing here stops a row claiming BTC as the base
# asset of a FOREX instrument. Which market/product/asset/instrument
# combinations are authorized for v1 is proven exclusively by the canonical
# seed (`0007_seed_catalog_v1`) and its tests, never by parsing
# `canonical_symbol` or by schema-level enums. Any future write endpoint
# must validate catalog policy in the application layer before persisting;
# no such endpoint exists yet.


class UnderlyingMarket(Base):
    __tablename__ = "freyja2_underlying_markets"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(code)) > 0", name="ck_freyja2_underlying_markets_code_not_blank"
        ),
        CheckConstraint("code = btrim(code)", name="ck_freyja2_underlying_markets_code_trimmed"),
        CheckConstraint(
            "char_length(btrim(display_name)) > 0",
            name="ck_freyja2_underlying_markets_display_name_not_blank",
        ),
        CheckConstraint(
            "display_name = btrim(display_name)",
            name="ck_freyja2_underlying_markets_display_name_trimmed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"UnderlyingMarket(id={self.id!r}, code={self.code!r})"


class ProductType(Base):
    __tablename__ = "freyja2_product_types"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(code)) > 0", name="ck_freyja2_product_types_code_not_blank"
        ),
        CheckConstraint("code = btrim(code)", name="ck_freyja2_product_types_code_trimmed"),
        CheckConstraint(
            "char_length(btrim(display_name)) > 0",
            name="ck_freyja2_product_types_display_name_not_blank",
        ),
        CheckConstraint(
            "display_name = btrim(display_name)",
            name="ck_freyja2_product_types_display_name_trimmed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"ProductType(id={self.id!r}, code={self.code!r})"


class Asset(Base):
    __tablename__ = "freyja2_assets"
    __table_args__ = (
        CheckConstraint("char_length(btrim(code)) > 0", name="ck_freyja2_assets_code_not_blank"),
        CheckConstraint("code = btrim(code)", name="ck_freyja2_assets_code_trimmed"),
        CheckConstraint(
            "char_length(btrim(display_name)) > 0",
            name="ck_freyja2_assets_display_name_not_blank",
        ),
        CheckConstraint(
            "display_name = btrim(display_name)", name="ck_freyja2_assets_display_name_trimmed"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"Asset(id={self.id!r}, code={self.code!r})"


class Timeframe(Base):
    """A timeframe means candle duration only — never contract expiry,
    predicted horizon, entry window, time-in-force, max holding duration, or
    evaluation horizon. Those are separate clocks defined in later roadmap
    points (7-14), never here."""

    __tablename__ = "freyja2_timeframes"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(code)) > 0", name="ck_freyja2_timeframes_code_not_blank"
        ),
        CheckConstraint("code = btrim(code)", name="ck_freyja2_timeframes_code_trimmed"),
        CheckConstraint(
            "char_length(btrim(display_name)) > 0",
            name="ck_freyja2_timeframes_display_name_not_blank",
        ),
        CheckConstraint(
            "display_name = btrim(display_name)",
            name="ck_freyja2_timeframes_display_name_trimmed",
        ),
        CheckConstraint("duration_seconds > 0", name="ck_freyja2_timeframes_duration_positive"),
        UniqueConstraint("duration_seconds", name="uq_freyja2_timeframes_duration_seconds"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"Timeframe(id={self.id!r}, code={self.code!r})"


class Instrument(Base):
    """Canonical instrument identity — answers only *what* the instrument is,
    never where it trades, which account operates it, or whether that
    account is authorized (see POINT1-PROVIDER-001 / POINT1-CAPABILITY-001).

    Every row adopts exactly one of three mutually exclusive shapes, enforced
    below by `ck_freyja2_instruments_exactly_one_shape` (never a redundant
    `structure_type` column — the shape is determined by which FKs are set):
      PAIR                  — base_asset + quote_asset (e.g. BTC/USDT spot)
      ASSET_UNDERLYING      — a single underlying_asset (e.g. a BTC binary)
      INSTRUMENT_UNDERLYING — another Instrument as underlying (e.g. a
                              EUR/USD binary referencing the canonical
                              EUR/USD spot instrument by FK, never copying
                              or reinterpreting its symbol text)
    """

    __tablename__ = "freyja2_instruments"
    __table_args__ = (
        UniqueConstraint(
            "underlying_market_id",
            "product_type_id",
            "canonical_symbol",
            name="uq_freyja2_instruments_market_product_symbol",
        ),
        # Candidate key that lets the composite FK below prove an underlying
        # instrument belongs to the same market as its referencer — instrument_id
        # alone is already globally unique, so this widening is never violated
        # by existing rows, it only exists to be the target of that FK.
        UniqueConstraint(
            "underlying_market_id",
            "instrument_id",
            name="uq_freyja2_instruments_market_instrument",
        ),
        CheckConstraint(
            "base_asset_id <> quote_asset_id", name="ck_freyja2_instruments_base_ne_quote"
        ),
        CheckConstraint(
            "underlying_instrument_id <> instrument_id",
            name="ck_freyja2_instruments_underlying_ne_self",
        ),
        CheckConstraint(
            "("
            "base_asset_id IS NOT NULL AND quote_asset_id IS NOT NULL "
            "AND underlying_asset_id IS NULL AND underlying_instrument_id IS NULL"
            ") OR ("
            "underlying_asset_id IS NOT NULL "
            "AND base_asset_id IS NULL AND quote_asset_id IS NULL "
            "AND underlying_instrument_id IS NULL"
            ") OR ("
            "underlying_instrument_id IS NOT NULL "
            "AND base_asset_id IS NULL AND quote_asset_id IS NULL "
            "AND underlying_asset_id IS NULL"
            ")",
            name="ck_freyja2_instruments_exactly_one_shape",
        ),
        CheckConstraint(
            "char_length(btrim(canonical_symbol)) > 0",
            name="ck_freyja2_instruments_canonical_symbol_not_blank",
        ),
        CheckConstraint(
            "canonical_symbol = btrim(canonical_symbol)",
            name="ck_freyja2_instruments_canonical_symbol_trimmed",
        ),
        # Composite, self-referential FK: an underlying_instrument_id (when
        # set) must belong to the SAME underlying_market_id as the row that
        # references it — enforced physically via MATCH SIMPLE against
        # uq_freyja2_instruments_market_instrument above, without ever
        # parsing or inspecting canonical_symbol. Rows where
        # underlying_instrument_id IS NULL (PAIR, ASSET_UNDERLYING) are
        # unaffected: MATCH SIMPLE skips the check whenever any referencing
        # column is NULL. This replaces the single-column FK that POINT1-DB-001
        # originally declared inline on underlying_instrument_id (see
        # 0008_catalog_integrity) — keeping both would create two competing FK
        # paths between freyja2_instruments and itself, which is exactly the
        # foreign-key ambiguity this correction removes.
        ForeignKeyConstraint(
            ["underlying_market_id", "underlying_instrument_id"],
            ["freyja2_instruments.underlying_market_id", "freyja2_instruments.instrument_id"],
            name="fk_freyja2_instruments_underlying_same_market",
        ),
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    underlying_market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_underlying_markets.id"), nullable=False
    )
    product_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_product_types.id"), nullable=False
    )
    canonical_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    base_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_assets.id")
    )
    quote_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_assets.id")
    )
    underlying_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_assets.id")
    )
    # No inline ForeignKey here: the composite, same-market FK is declared
    # in __table_args__ (fk_freyja2_instruments_underlying_same_market) —
    # a single-column FK on this column alone would duplicate that path and
    # create ambiguous foreign keys between freyja2_instruments and itself.
    underlying_instrument_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"Instrument(instrument_id={self.instrument_id!r}, "
            f"canonical_symbol={self.canonical_symbol!r})"
        )


class InstrumentTimeframe(Base):
    """Explicit many-to-many: which timeframes (candle durations) an
    instrument supports."""

    __tablename__ = "freyja2_instrument_timeframes"

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_instruments.instrument_id"), primary_key=True
    )
    timeframe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_timeframes.id"), primary_key=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"InstrumentTimeframe(instrument_id={self.instrument_id!r}, "
            f"timeframe_id={self.timeframe_id!r})"
        )
