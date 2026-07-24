import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from freyja_backend.db.base import Base

# Provider mapping tables (POINT1-PROVIDER-001). Model *where* a canonical
# Instrument (freyja2_instruments, POINT1-DB-001) can be traded (Venue) or
# priced/settled (DataSource), and the concrete provider-specific
# symbol/contract each uses — never the instrument's own identity.
#
# A row here is evidence of a provider mapping. It is never itself an
# enablement of trading, a selection made by a user, or a claim that an
# environment is supported/available. No credentials, no account, no
# DEMO/REAL, no activation or authorization state belong here — those
# belong to ExecutionContext, modeled later in POINT1-CAPABILITY-001.


class VenueType(enum.StrEnum):
    """A closed, structural taxonomy of execution venues — unlike market or
    asset codes, this is not an open/extensible catalog, so it uses a
    native Postgres enum rather than a data-driven code table."""

    EXCHANGE = "EXCHANGE"
    BROKER = "BROKER"


class DataSourceType(enum.StrEnum):
    EXCHANGE = "EXCHANGE"
    BROKER = "BROKER"
    MARKET_DATA = "MARKET_DATA"


class DataSourceInstrumentPurpose(enum.StrEnum):
    """ANALYSIS and SETTLEMENT are deliberately distinct relations, even for
    the same (data_source, instrument) pair: a binary option's resolution
    must use its contractual settlement mapping, never a different,
    merely-convenient analysis quote."""

    ANALYSIS = "ANALYSIS"
    SETTLEMENT = "SETTLEMENT"


class Venue(Base):
    """Stable identity of a broker, exchange, or execution platform — never
    an account, credentials, or activation state."""

    __tablename__ = "freyja2_venues"
    __table_args__ = (
        CheckConstraint("char_length(btrim(code)) > 0", name="ck_freyja2_venues_code_not_blank"),
        CheckConstraint("code = btrim(code)", name="ck_freyja2_venues_code_trimmed"),
        CheckConstraint(
            "char_length(btrim(display_name)) > 0",
            name="ck_freyja2_venues_display_name_not_blank",
        ),
        CheckConstraint(
            "display_name = btrim(display_name)", name="ck_freyja2_venues_display_name_trimmed"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    venue_type: Mapped[VenueType] = mapped_column(
        Enum(VenueType, name="freyja2_venue_type", native_enum=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"Venue(id={self.id!r}, code={self.code!r})"


class DataSource(Base):
    """Stable identity of a market-data/settlement provider — never an
    account, credentials, or activation state."""

    __tablename__ = "freyja2_data_sources"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(code)) > 0", name="ck_freyja2_data_sources_code_not_blank"
        ),
        CheckConstraint("code = btrim(code)", name="ck_freyja2_data_sources_code_trimmed"),
        CheckConstraint(
            "char_length(btrim(display_name)) > 0",
            name="ck_freyja2_data_sources_display_name_not_blank",
        ),
        CheckConstraint(
            "display_name = btrim(display_name)",
            name="ck_freyja2_data_sources_display_name_trimmed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[DataSourceType] = mapped_column(
        Enum(DataSourceType, name="freyja2_data_source_type", native_enum=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"DataSource(id={self.id!r}, code={self.code!r})"


class VenueInstrument(Base):
    """Mapping between a Venue and a canonical Instrument: the concrete,
    executable listing/contract a venue offers for that instrument — never
    the instrument's identity, never an account, credential, or activation
    state. A venue may expose several contracts/listings for the same
    instrument (e.g. different expiries), so (venue_id, instrument_id) is
    deliberately NOT unique. Uniqueness of the symbol itself instead
    follows two rules, enforced by the two partial unique indexes below:
    without a provider_contract_id, a row is unique per
    (venue_id, provider_symbol); with one, it's unique per
    (venue_id, provider_symbol, provider_contract_id) — so a venue can
    reuse the same provider_symbol across several contracts as long as
    each carries a distinct provider_contract_id (e.g. the same BTCUSDT
    ticker at two different binary-option expiries)."""

    __tablename__ = "freyja2_venue_instruments"
    __table_args__ = (
        # Two partial unique indexes replace a single UNIQUE(venue_id,
        # provider_symbol): a venue can list the SAME provider_symbol more
        # than once when each listing carries a distinct
        # provider_contract_id (e.g. the same BTCUSDT ticker at two
        # different binary-option expiries) — only the (venue, symbol,
        # contract) triple must be unique then. When no contract id is
        # given at all, (venue, symbol) alone must still be unique, since
        # nothing else disambiguates the row.
        Index(
            "uq_freyja2_venue_instruments_venue_symbol_no_contract",
            "venue_id",
            "provider_symbol",
            unique=True,
            postgresql_where=text("provider_contract_id IS NULL"),
        ),
        Index(
            "uq_freyja2_venue_instruments_venue_symbol_contract",
            "venue_id",
            "provider_symbol",
            "provider_contract_id",
            unique=True,
            postgresql_where=text("provider_contract_id IS NOT NULL"),
        ),
        CheckConstraint(
            "char_length(btrim(provider_symbol)) > 0",
            name="ck_freyja2_venue_instruments_provider_symbol_not_blank",
        ),
        CheckConstraint(
            "provider_symbol = btrim(provider_symbol)",
            name="ck_freyja2_venue_instruments_provider_symbol_trimmed",
        ),
        CheckConstraint(
            "provider_contract_id IS NULL OR ("
            "char_length(btrim(provider_contract_id)) > 0 "
            "AND provider_contract_id = btrim(provider_contract_id)"
            ")",
            name="ck_freyja2_venue_instruments_provider_contract_id_shape",
        ),
        Index("ix_freyja2_venue_instruments_venue_id", "venue_id"),
        Index("ix_freyja2_venue_instruments_instrument_id", "instrument_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_venues.id"), nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_instruments.instrument_id"), nullable=False
    )
    provider_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    # Nullable: only needed for contracts whose identifier differs from the
    # provider_symbol itself (e.g. a numeric/opaque contract id alongside a
    # human-readable ticker) — never invented when unknown.
    provider_contract_id: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"VenueInstrument(id={self.id!r}, venue_id={self.venue_id!r}, "
            f"provider_symbol={self.provider_symbol!r})"
        )


class DataSourceInstrument(Base):
    """Mapping between a DataSource and a canonical Instrument: the symbol a
    data source uses to publish candles/prices/settlement data for that
    instrument, for a specific purpose. ANALYSIS and SETTLEMENT are
    distinct rows even for the same (data_source, instrument) pair."""

    __tablename__ = "freyja2_data_source_instruments"
    __table_args__ = (
        UniqueConstraint(
            "data_source_id",
            "provider_symbol",
            "purpose",
            name="uq_freyja2_data_source_instruments_source_symbol_purpose",
        ),
        CheckConstraint(
            "char_length(btrim(provider_symbol)) > 0",
            name="ck_freyja2_data_source_instruments_provider_symbol_not_blank",
        ),
        CheckConstraint(
            "provider_symbol = btrim(provider_symbol)",
            name="ck_freyja2_data_source_instruments_provider_symbol_trimmed",
        ),
        Index("ix_freyja2_data_source_instruments_data_source_id", "data_source_id"),
        Index("ix_freyja2_data_source_instruments_instrument_id", "instrument_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_data_sources.id"), nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_instruments.instrument_id"), nullable=False
    )
    provider_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[DataSourceInstrumentPurpose] = mapped_column(
        Enum(
            DataSourceInstrumentPurpose,
            name="freyja2_data_source_instrument_purpose",
            native_enum=True,
        ),
        nullable=False,
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
            f"DataSourceInstrument(id={self.id!r}, data_source_id={self.data_source_id!r}, "
            f"provider_symbol={self.provider_symbol!r}, purpose={self.purpose!r})"
        )
