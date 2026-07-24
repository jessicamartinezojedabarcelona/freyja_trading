"""provider_mappings

Revision ID: 0010_provider_mappings
Revises: 0009_seed_integrity_guard
Create Date: 2026-07-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_provider_mappings"
down_revision: str | None = "0009_seed_integrity_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# POINT1-PROVIDER-001: models *where* a canonical Instrument
# (freyja2_instruments, POINT1-DB-001) can be traded (Venue) or
# priced/settled (DataSource), and the concrete provider-specific
# symbol/contract each uses — never the instrument's own identity. No
# credentials, no account, no DEMO/REAL, no activation/authorization state:
# those belong to a future ExecutionContext (POINT1-CAPABILITY-001). No
# CASCADE anywhere — deleting a referenced Instrument/Venue/DataSource
# fails closed via the plain FK.

_VENUE_TYPE_VALUES = ("EXCHANGE", "BROKER")
_DATA_SOURCE_TYPE_VALUES = ("EXCHANGE", "BROKER", "MARKET_DATA")
_DATA_SOURCE_INSTRUMENT_PURPOSE_VALUES = ("ANALYSIS", "SETTLEMENT")


def upgrade() -> None:
    # Create the native enum types explicitly (once), then reference them
    # with create_type=False on the columns below — otherwise SQLAlchemy's
    # postgresql.ENUM auto-creation (triggered a second time by attaching
    # the type to a table column) collides with the explicit create() and
    # fails with "type already exists".
    venue_type_create = postgresql.ENUM(*_VENUE_TYPE_VALUES, name="freyja2_venue_type")
    data_source_type_create = postgresql.ENUM(
        *_DATA_SOURCE_TYPE_VALUES, name="freyja2_data_source_type"
    )
    purpose_create = postgresql.ENUM(
        *_DATA_SOURCE_INSTRUMENT_PURPOSE_VALUES, name="freyja2_data_source_instrument_purpose"
    )
    venue_type_create.create(op.get_bind(), checkfirst=False)
    data_source_type_create.create(op.get_bind(), checkfirst=False)
    purpose_create.create(op.get_bind(), checkfirst=False)

    venue_type = postgresql.ENUM(*_VENUE_TYPE_VALUES, name="freyja2_venue_type", create_type=False)
    data_source_type = postgresql.ENUM(
        *_DATA_SOURCE_TYPE_VALUES, name="freyja2_data_source_type", create_type=False
    )
    purpose = postgresql.ENUM(
        *_DATA_SOURCE_INSTRUMENT_PURPOSE_VALUES,
        name="freyja2_data_source_instrument_purpose",
        create_type=False,
    )

    op.create_table(
        "freyja2_venues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("venue_type", venue_type, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("code", name="uq_freyja2_venues_code"),
        sa.CheckConstraint("char_length(btrim(code)) > 0", name="ck_freyja2_venues_code_not_blank"),
        sa.CheckConstraint("code = btrim(code)", name="ck_freyja2_venues_code_trimmed"),
        sa.CheckConstraint(
            "char_length(btrim(display_name)) > 0",
            name="ck_freyja2_venues_display_name_not_blank",
        ),
        sa.CheckConstraint(
            "display_name = btrim(display_name)", name="ck_freyja2_venues_display_name_trimmed"
        ),
    )

    op.create_table(
        "freyja2_data_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("source_type", data_source_type, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("code", name="uq_freyja2_data_sources_code"),
        sa.CheckConstraint(
            "char_length(btrim(code)) > 0", name="ck_freyja2_data_sources_code_not_blank"
        ),
        sa.CheckConstraint("code = btrim(code)", name="ck_freyja2_data_sources_code_trimmed"),
        sa.CheckConstraint(
            "char_length(btrim(display_name)) > 0",
            name="ck_freyja2_data_sources_display_name_not_blank",
        ),
        sa.CheckConstraint(
            "display_name = btrim(display_name)",
            name="ck_freyja2_data_sources_display_name_trimmed",
        ),
    )

    op.create_table(
        "freyja2_venue_instruments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("venue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_symbol", sa.String(length=64), nullable=False),
        sa.Column("provider_contract_id", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["venue_id"], ["freyja2_venues.id"], name="fk_freyja2_venue_instruments_venue_id"
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["freyja2_instruments.instrument_id"],
            name="fk_freyja2_venue_instruments_instrument_id",
        ),
        # Deliberately NOT unique on (venue_id, instrument_id): a venue may
        # expose several contracts/listings for the same canonical
        # instrument (e.g. different expiries) — see the two partial unique
        # indexes created below instead of a single UniqueConstraint here.
        sa.CheckConstraint(
            "char_length(btrim(provider_symbol)) > 0",
            name="ck_freyja2_venue_instruments_provider_symbol_not_blank",
        ),
        sa.CheckConstraint(
            "provider_symbol = btrim(provider_symbol)",
            name="ck_freyja2_venue_instruments_provider_symbol_trimmed",
        ),
        sa.CheckConstraint(
            "provider_contract_id IS NULL OR ("
            "char_length(btrim(provider_contract_id)) > 0 "
            "AND provider_contract_id = btrim(provider_contract_id)"
            ")",
            name="ck_freyja2_venue_instruments_provider_contract_id_shape",
        ),
    )
    op.create_index(
        "ix_freyja2_venue_instruments_venue_id", "freyja2_venue_instruments", ["venue_id"]
    )
    op.create_index(
        "ix_freyja2_venue_instruments_instrument_id",
        "freyja2_venue_instruments",
        ["instrument_id"],
    )
    # Two partial unique indexes instead of a single UNIQUE(venue_id,
    # provider_symbol): a venue can list the SAME provider_symbol more than
    # once as long as each listing carries a distinct provider_contract_id
    # (e.g. the same BTCUSDT ticker at two different binary-option
    # expiries). With no contract id at all, (venue_id, provider_symbol)
    # alone must still be unique — nothing else disambiguates the row.
    op.create_index(
        "uq_freyja2_venue_instruments_venue_symbol_no_contract",
        "freyja2_venue_instruments",
        ["venue_id", "provider_symbol"],
        unique=True,
        postgresql_where=sa.text("provider_contract_id IS NULL"),
    )
    op.create_index(
        "uq_freyja2_venue_instruments_venue_symbol_contract",
        "freyja2_venue_instruments",
        ["venue_id", "provider_symbol", "provider_contract_id"],
        unique=True,
        postgresql_where=sa.text("provider_contract_id IS NOT NULL"),
    )

    op.create_table(
        "freyja2_data_source_instruments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_symbol", sa.String(length=64), nullable=False),
        sa.Column("purpose", purpose, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["freyja2_data_sources.id"],
            name="fk_freyja2_data_source_instruments_data_source_id",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["freyja2_instruments.instrument_id"],
            name="fk_freyja2_data_source_instruments_instrument_id",
        ),
        sa.UniqueConstraint(
            "data_source_id",
            "provider_symbol",
            "purpose",
            name="uq_freyja2_data_source_instruments_source_symbol_purpose",
        ),
        sa.CheckConstraint(
            "char_length(btrim(provider_symbol)) > 0",
            name="ck_freyja2_data_source_instruments_provider_symbol_not_blank",
        ),
        sa.CheckConstraint(
            "provider_symbol = btrim(provider_symbol)",
            name="ck_freyja2_data_source_instruments_provider_symbol_trimmed",
        ),
    )
    op.create_index(
        "ix_freyja2_data_source_instruments_data_source_id",
        "freyja2_data_source_instruments",
        ["data_source_id"],
    )
    op.create_index(
        "ix_freyja2_data_source_instruments_instrument_id",
        "freyja2_data_source_instruments",
        ["instrument_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_freyja2_data_source_instruments_instrument_id",
        table_name="freyja2_data_source_instruments",
    )
    op.drop_index(
        "ix_freyja2_data_source_instruments_data_source_id",
        table_name="freyja2_data_source_instruments",
    )
    op.drop_table("freyja2_data_source_instruments")

    op.drop_index(
        "uq_freyja2_venue_instruments_venue_symbol_contract",
        table_name="freyja2_venue_instruments",
    )
    op.drop_index(
        "uq_freyja2_venue_instruments_venue_symbol_no_contract",
        table_name="freyja2_venue_instruments",
    )
    op.drop_index(
        "ix_freyja2_venue_instruments_instrument_id", table_name="freyja2_venue_instruments"
    )
    op.drop_index("ix_freyja2_venue_instruments_venue_id", table_name="freyja2_venue_instruments")
    op.drop_table("freyja2_venue_instruments")

    op.drop_table("freyja2_data_sources")
    op.drop_table("freyja2_venues")

    postgresql.ENUM(name="freyja2_data_source_instrument_purpose").drop(
        op.get_bind(), checkfirst=False
    )
    postgresql.ENUM(name="freyja2_data_source_type").drop(op.get_bind(), checkfirst=False)
    postgresql.ENUM(name="freyja2_venue_type").drop(op.get_bind(), checkfirst=False)
