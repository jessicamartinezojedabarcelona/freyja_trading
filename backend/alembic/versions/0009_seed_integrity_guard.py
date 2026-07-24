"""seed_integrity_guard

Revision ID: 0009_seed_integrity_guard
Revises: 0008_catalog_integrity
Create Date: 2026-07-24

"""

from collections.abc import Sequence

from alembic import op
from freyja_backend.db import catalog_seed_v1 as seed_spec

# revision identifiers, used by Alembic.
revision: str = "0009_seed_integrity_guard"
down_revision: str | None = "0008_catalog_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# POINT1-SEED-001 independent-audit correction (2026-07-24): 0007's
# insert-or-verify logic only re-verifies a row when 0007 itself runs
# again, which never happens for a database already migrated past it. This
# revision closes that gap: it certifies, on every already-migrated
# database that upgrades through it, that the v1 seed is still exactly
# what POINT1-DOMAIN-001 approved — same UUIDs, same natural keys, same
# stable content, all active, all 50 associations present and active.
#
# It creates no schema objects and writes no data — it only reads and
# raises. A row or association that is missing, renamed, retyped, rewired,
# or deactivated aborts this migration (and therefore the whole upgrade)
# instead of being silently reconstructed. Extra, non-canonical rows an
# operator or test added separately are never touched: verification only
# looks up the specific canonical natural keys defined in
# freyja_backend.db.catalog_seed_v1, never enumerates the tables.
#
# This migration does not trust that live module blindly either: the
# SHA-256 fingerprint below is this migration's own frozen anchor — the
# exact same v1 contract 0007_seed_catalog_v1 pins, duplicated here only as
# a short historical anchor, never as a second copy of the full catalog
# lists. Any accidental drift in catalog_seed_v1.py fails this migration
# closed before it verifies (or fails to verify) a single row.
_EXPECTED_V1_CONTRACT_SHA256 = "5237ca2d9870c80402e2738ffe4e58492061b8c63d11ee165a64aa6d9b089f08"


def upgrade() -> None:
    seed_spec.verify_contract_fingerprint(_EXPECTED_V1_CONTRACT_SHA256)
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
        seed_spec.require_association_present(connection, row.instrument_id, row.timeframe_id)


def downgrade() -> None:
    """No-op, deliberately: this revision creates no schema objects and
    writes no data — it only certifies that the existing catalog matches
    the v1 seed exactly. There is nothing here for a downgrade to reverse."""
