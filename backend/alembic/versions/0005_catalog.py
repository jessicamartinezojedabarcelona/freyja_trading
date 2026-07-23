"""catalog

Revision ID: 0005_catalog
Revises: 0004_remove_email_verification
Create Date: 2026-07-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_catalog"
down_revision: str | None = "0004_remove_email_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "freyja2_underlying_markets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("code", name="uq_freyja2_underlying_markets_code"),
    )

    op.create_table(
        "freyja2_product_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("code", name="uq_freyja2_product_types_code"),
    )

    op.create_table(
        "freyja2_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("code", name="uq_freyja2_assets_code"),
    )

    op.create_table(
        "freyja2_timeframes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("code", name="uq_freyja2_timeframes_code"),
    )

    # Every row adopts exactly one of three mutually exclusive shapes
    # (PAIR / ASSET_UNDERLYING / INSTRUMENT_UNDERLYING) — enforced by
    # ck_freyja2_instruments_exactly_one_shape, never a redundant
    # structure_type column. See db/models/catalog.py::Instrument.
    op.create_table(
        "freyja2_instruments",
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("underlying_market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_symbol", sa.String(length=64), nullable=False),
        sa.Column("base_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quote_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("underlying_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("underlying_instrument_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["underlying_market_id"],
            ["freyja2_underlying_markets.id"],
            name="fk_freyja2_instruments_underlying_market_id",
        ),
        sa.ForeignKeyConstraint(
            ["product_type_id"],
            ["freyja2_product_types.id"],
            name="fk_freyja2_instruments_product_type_id",
        ),
        sa.ForeignKeyConstraint(
            ["base_asset_id"], ["freyja2_assets.id"], name="fk_freyja2_instruments_base_asset_id"
        ),
        sa.ForeignKeyConstraint(
            ["quote_asset_id"], ["freyja2_assets.id"], name="fk_freyja2_instruments_quote_asset_id"
        ),
        sa.ForeignKeyConstraint(
            ["underlying_asset_id"],
            ["freyja2_assets.id"],
            name="fk_freyja2_instruments_underlying_asset_id",
        ),
        sa.ForeignKeyConstraint(
            ["underlying_instrument_id"],
            ["freyja2_instruments.instrument_id"],
            name="fk_freyja2_instruments_underlying_instrument_id",
        ),
        sa.UniqueConstraint(
            "underlying_market_id",
            "product_type_id",
            "canonical_symbol",
            name="uq_freyja2_instruments_market_product_symbol",
        ),
        sa.CheckConstraint(
            "base_asset_id <> quote_asset_id", name="ck_freyja2_instruments_base_ne_quote"
        ),
        sa.CheckConstraint(
            "underlying_instrument_id <> instrument_id",
            name="ck_freyja2_instruments_underlying_ne_self",
        ),
        sa.CheckConstraint(
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
    )

    op.create_table(
        "freyja2_instrument_timeframes",
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timeframe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["freyja2_instruments.instrument_id"],
            name="fk_freyja2_instrument_timeframes_instrument_id",
        ),
        sa.ForeignKeyConstraint(
            ["timeframe_id"],
            ["freyja2_timeframes.id"],
            name="fk_freyja2_instrument_timeframes_timeframe_id",
        ),
        sa.PrimaryKeyConstraint(
            "instrument_id", "timeframe_id", name="pk_freyja2_instrument_timeframes"
        ),
    )


def downgrade() -> None:
    op.drop_table("freyja2_instrument_timeframes")
    op.drop_table("freyja2_instruments")
    op.drop_table("freyja2_timeframes")
    op.drop_table("freyja2_assets")
    op.drop_table("freyja2_product_types")
    op.drop_table("freyja2_underlying_markets")
