"""catalog_integrity

Revision ID: 0008_catalog_integrity
Revises: 0007_seed_catalog_v1
Create Date: 2026-07-24

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_catalog_integrity"
down_revision: str | None = "0007_seed_catalog_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# POINT1-DB-001 independent-audit correction (2026-07-24): adds the
# structural invariants PostgreSQL CAN prove without knowing any concrete
# code — non-blank/non-whitespace-padded text, positive and unique
# timeframe durations, and same-market underlying instruments. It does not
# and cannot make PostgreSQL deduce market/product/asset semantics from a
# symbol (e.g. that BTC is CRYPTO): that boundary is documented in
# db/models/catalog.py and proven by the canonical seed
# (0007_seed_catalog_v1), never by schema-level enums or symbol parsing.

_TEXT_NOT_BLANK: tuple[tuple[str, str, str], ...] = (
    ("freyja2_underlying_markets", "code", "ck_freyja2_underlying_markets_code"),
    ("freyja2_underlying_markets", "display_name", "ck_freyja2_underlying_markets_display_name"),
    ("freyja2_product_types", "code", "ck_freyja2_product_types_code"),
    ("freyja2_product_types", "display_name", "ck_freyja2_product_types_display_name"),
    ("freyja2_assets", "code", "ck_freyja2_assets_code"),
    ("freyja2_assets", "display_name", "ck_freyja2_assets_display_name"),
    ("freyja2_timeframes", "code", "ck_freyja2_timeframes_code"),
    ("freyja2_timeframes", "display_name", "ck_freyja2_timeframes_display_name"),
    ("freyja2_instruments", "canonical_symbol", "ck_freyja2_instruments_canonical_symbol"),
)


def upgrade() -> None:
    for table, column, prefix in _TEXT_NOT_BLANK:
        op.create_check_constraint(
            f"{prefix}_not_blank", table, f"char_length(btrim({column})) > 0"
        )
        op.create_check_constraint(f"{prefix}_trimmed", table, f"{column} = btrim({column})")

    op.create_check_constraint(
        "ck_freyja2_timeframes_duration_positive", "freyja2_timeframes", "duration_seconds > 0"
    )
    op.create_unique_constraint(
        "uq_freyja2_timeframes_duration_seconds", "freyja2_timeframes", ["duration_seconds"]
    )

    # Replace the single-column FK on underlying_instrument_id with a
    # composite, same-market FK: instrument_id alone already proves the
    # underlying instrument exists, but says nothing about which market it
    # belongs to. Widening the candidate key to (underlying_market_id,
    # instrument_id) — trivially unique since instrument_id already is —
    # lets the new FK require the underlying instrument's market to match
    # the referencer's, without parsing canonical_symbol.
    op.drop_constraint(
        "fk_freyja2_instruments_underlying_instrument_id",
        "freyja2_instruments",
        type_="foreignkey",
    )
    op.create_unique_constraint(
        "uq_freyja2_instruments_market_instrument",
        "freyja2_instruments",
        ["underlying_market_id", "instrument_id"],
    )
    op.create_foreign_key(
        "fk_freyja2_instruments_underlying_same_market",
        "freyja2_instruments",
        "freyja2_instruments",
        ["underlying_market_id", "underlying_instrument_id"],
        ["underlying_market_id", "instrument_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_freyja2_instruments_underlying_same_market",
        "freyja2_instruments",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_freyja2_instruments_market_instrument", "freyja2_instruments", type_="unique"
    )
    op.create_foreign_key(
        "fk_freyja2_instruments_underlying_instrument_id",
        "freyja2_instruments",
        "freyja2_instruments",
        ["underlying_instrument_id"],
        ["instrument_id"],
    )

    op.drop_constraint(
        "uq_freyja2_timeframes_duration_seconds", "freyja2_timeframes", type_="unique"
    )
    op.drop_constraint(
        "ck_freyja2_timeframes_duration_positive", "freyja2_timeframes", type_="check"
    )

    for table, _column, prefix in reversed(_TEXT_NOT_BLANK):
        op.drop_constraint(f"{prefix}_trimmed", table, type_="check")
        op.drop_constraint(f"{prefix}_not_blank", table, type_="check")
