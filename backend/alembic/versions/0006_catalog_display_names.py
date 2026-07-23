"""catalog_display_names

Revision ID: 0006_catalog_display_names
Revises: 0005_catalog
Create Date: 2026-07-23

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_catalog_display_names"
down_revision: str | None = "0005_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# All four tables are empty at this point in history (POINT1-DB-001 shipped
# no seed data), so a NOT NULL column needs neither a server_default nor a
# backfill step.
_TABLES = (
    "freyja2_underlying_markets",
    "freyja2_product_types",
    "freyja2_assets",
    "freyja2_timeframes",
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("display_name", sa.String(length=64), nullable=False))


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_column(table, "display_name")
