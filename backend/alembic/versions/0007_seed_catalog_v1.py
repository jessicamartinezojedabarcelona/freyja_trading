"""seed_catalog_v1

Revision ID: 0007_seed_catalog_v1
Revises: 0006_catalog_display_names
Create Date: 2026-07-23

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from freyja_backend.db import catalog_seed_v1 as seed_spec

# revision identifiers, used by Alembic.
revision: str = "0007_seed_catalog_v1"
down_revision: str | None = "0006_catalog_display_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The exact v1 scope (markets, products, assets, timeframes, instruments,
# and their deterministic UUIDv5 identity) lives entirely in
# freyja_backend.db.catalog_seed_v1 — the single source of truth also used
# by 0009_seed_integrity_guard and the test suite, so it can never drift
# into two independently-maintained catalog definitions.


def upgrade() -> None:
    """Transactional, idempotent, fail-closed: inserts any canonical row or
    association that doesn't exist yet. For one that already exists,
    verifies every stable field (id, natural key, display_name,
    canonical_symbol, duration_seconds, FKs/shape, is_active) matches
    exactly and raises (aborting the whole migration transaction) on any
    divergence — never overwrites, repairs, renames, or silently completes
    a changed seed. Never compares created_at/updated_at."""
    connection = op.get_bind()

    for table_spec in seed_spec.CATALOG_ROW_SPECS:
        for row in table_spec.rows:
            already_present = seed_spec.verify_row(
                connection,
                table_spec.table,
                table_spec.id_column,
                table_spec.natural_key_columns,
                row,
                table_spec.compare_columns,
            )
            if not already_present:
                connection.execute(sa.insert(table_spec.table).values(**row))

    for row in seed_spec.INSTRUMENT_TIMEFRAME_ROWS:
        already_present = seed_spec.verify_association(
            connection, row["instrument_id"], row["timeframe_id"]
        )
        if not already_present:
            connection.execute(sa.insert(seed_spec.INSTRUMENT_TIMEFRAMES_TABLE).values(**row))


def downgrade() -> None:
    """Fail-closed: before deleting anything, verifies every canonical row
    and association this downgrade is about to remove still matches the v1
    seed exactly (id, natural key, every stable column, is_active). Any
    missing or diverged row aborts the whole downgrade untouched — nothing
    is deleted unless every single canonical row/association first passes
    verification.

    Once verified, deletes exclusively the exact rows/associations
    identified by deterministic UUID/natural key — any custom row a test or
    operator added separately is left untouched. No CASCADE anywhere: a
    real external reference this migration doesn't know about aborts the
    downgrade (FK violation) instead of being silently swept away."""
    connection = op.get_bind()

    for table_spec in seed_spec.CATALOG_ROW_SPECS:
        for row in table_spec.rows:
            seed_spec.require_row_present(
                connection,
                table_spec.table,
                table_spec.id_column,
                table_spec.natural_key_columns,
                row,
                table_spec.compare_columns,
            )
    for row in seed_spec.INSTRUMENT_TIMEFRAME_ROWS:
        seed_spec.require_association_present(connection, row["instrument_id"], row["timeframe_id"])

    instrument_ids = [row["instrument_id"] for row in seed_spec.INSTRUMENT_ROWS]
    timeframe_ids = [row["id"] for row in seed_spec.TIMEFRAME_ROWS]

    connection.execute(
        sa.delete(seed_spec.INSTRUMENT_TIMEFRAMES_TABLE).where(
            seed_spec.INSTRUMENT_TIMEFRAMES_TABLE.c.instrument_id.in_(instrument_ids),
            seed_spec.INSTRUMENT_TIMEFRAMES_TABLE.c.timeframe_id.in_(timeframe_ids),
        )
    )

    # Delete INSTRUMENT_UNDERLYING rows before the instruments they
    # reference (FK from underlying_instrument_id) — no CASCADE anywhere, so
    # a real reference this migration doesn't know about aborts the
    # downgrade instead of being silently swept away.
    referencing_first = [s for s in seed_spec.INSTRUMENTS if "underlying_instrument" in s]
    referenced_after = [s for s in seed_spec.INSTRUMENTS if "underlying_instrument" not in s]
    for spec in referencing_first + referenced_after:
        connection.execute(
            sa.delete(seed_spec.INSTRUMENTS_TABLE).where(
                seed_spec.INSTRUMENTS_TABLE.c.instrument_id
                == seed_spec.instrument_id_from_spec(spec)
            )
        )

    connection.execute(
        sa.delete(seed_spec.ASSETS_TABLE).where(
            seed_spec.ASSETS_TABLE.c.id.in_([row["id"] for row in seed_spec.ASSET_ROWS])
        )
    )
    connection.execute(
        sa.delete(seed_spec.TIMEFRAMES_TABLE).where(
            seed_spec.TIMEFRAMES_TABLE.c.id.in_(timeframe_ids)
        )
    )
    connection.execute(
        sa.delete(seed_spec.PRODUCTS_TABLE).where(
            seed_spec.PRODUCTS_TABLE.c.id.in_([row["id"] for row in seed_spec.PRODUCT_ROWS])
        )
    )
    connection.execute(
        sa.delete(seed_spec.MARKETS_TABLE).where(
            seed_spec.MARKETS_TABLE.c.id.in_([row["id"] for row in seed_spec.MARKET_ROWS])
        )
    )
