"""forex_metals_catalog

Revision ID: 0016_forex_metals_catalog
Revises: 0015_context_snapshots
Create Date: 2026-09-29

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from freyja_backend.db.catalog_seed_v1 import asset_id, instrument_id, market_id, product_id

# revision identifiers, used by Alembic.
revision: str = "0016_forex_metals_catalog"
down_revision: str | None = "0015_context_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# MARKET-DATA-TWELVEDATA-CATALOG-001. Data only, no schema change: extends the catalog
# beyond the frozen POINT1-DOMAIN-001 v1 scope. catalog_seed_v1.py is never edited — its
# SHA-256 contract fingerprint is pinned by 0007/0009 and must stay exactly as approved.
# This migration is a separate, additive extension: a new market (METALS), four new
# assets (GBP, JPY, CHF, XAU) and four new instruments (GBP/USD, USD/JPY, USD/CHF under
# FOREX x SPOT; XAU/USD under METALS x SPOT), plus their timeframe associations against
# the five existing timeframes. EUR/USD and the FOREX market already exist from v1 and
# are not re-inserted here.
#
# Decision (Jessica, 29-09-2026): gold (XAU/USD) is not a currency pair and is not
# catalogued as FOREX. It gets its own market, METALS — the minimum needed for XAU/USD,
# not broad commodity coverage.
#
# IDs reuse catalog_seed_v1's own entity_uuid()-based helpers (market_id/asset_id/
# instrument_id/product_id) for the same deterministic-UUID scheme as every other
# catalog row. This only calls those pure functions with new inputs — it never reads,
# mutates, or re-derives catalog_seed_v1's frozen MARKET_ROWS/... constants, so the
# contract fingerprint 0007/0009 verify is unaffected.
#
# No provider/data-source mapping here: TWELVE_DATA and its symbol mappings belong to
# MARKET-DATA-TWELVEDATA-REST-001 — mirrors how 0014 added KRAKEN separately from the
# instruments it already traded, rather than mixing catalog and provider concerns.

_NEW_MARKET_CODE = "METALS"
_NEW_MARKET_NAME = "Metals"

_NEW_ASSETS: tuple[tuple[str, str], ...] = (
    ("GBP", "British pound"),
    ("JPY", "Japanese yen"),
    ("CHF", "Swiss franc"),
    ("XAU", "Gold"),
)

# (market, symbol, base, quote) — product is always SPOT for this batch.
_NEW_INSTRUMENTS: tuple[tuple[str, str, str, str], ...] = (
    ("FOREX", "GBP/USD", "GBP", "USD"),
    ("FOREX", "USD/JPY", "USD", "JPY"),
    ("FOREX", "USD/CHF", "USD", "CHF"),
    (_NEW_MARKET_CODE, "XAU/USD", "XAU", "USD"),
)

_TIMEFRAME_CODES = ("1m", "5m", "15m", "1h", "4h")

_DEPENDENT_TABLES = (
    "freyja2_data_source_instruments",
    "freyja2_venue_instruments",
    "freyja2_candles",
    "freyja2_market_data_sync_state",
)


def _new_instrument_ids() -> list[uuid.UUID]:
    return [
        instrument_id(market, "SPOT", symbol) for market, symbol, _base, _quote in _NEW_INSTRUMENTS
    ]


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text(
            "INSERT INTO freyja2_underlying_markets (id, code, display_name, is_active) "
            "VALUES (:id, :code, :name, true)"
        ),
        {"id": market_id(_NEW_MARKET_CODE), "code": _NEW_MARKET_CODE, "name": _NEW_MARKET_NAME},
    )

    for code, name in _NEW_ASSETS:
        bind.execute(
            sa.text(
                "INSERT INTO freyja2_assets (id, code, display_name, is_active) "
                "VALUES (:id, :code, :name, true)"
            ),
            {"id": asset_id(code), "code": code, "name": name},
        )

    spot_id = product_id("SPOT")
    for market, symbol, base, quote in _NEW_INSTRUMENTS:
        i_id = instrument_id(market, "SPOT", symbol)
        bind.execute(
            sa.text(
                "INSERT INTO freyja2_instruments "
                "(instrument_id, underlying_market_id, product_type_id, canonical_symbol, "
                "base_asset_id, quote_asset_id, underlying_asset_id, underlying_instrument_id, "
                "is_active) "
                "VALUES (:instrument_id, :market_id, :product_id, :symbol, "
                ":base_asset_id, :quote_asset_id, NULL, NULL, true)"
            ),
            {
                "instrument_id": i_id,
                "market_id": market_id(market),
                "product_id": spot_id,
                "symbol": symbol,
                "base_asset_id": asset_id(base),
                "quote_asset_id": asset_id(quote),
            },
        )
        for tf_code in _TIMEFRAME_CODES:
            bind.execute(
                sa.text(
                    "INSERT INTO freyja2_instrument_timeframes "
                    "(instrument_id, timeframe_id, is_active) "
                    "SELECT :instrument_id, t.id, true FROM freyja2_timeframes t "
                    "WHERE t.code = :tf_code"
                ),
                {"instrument_id": i_id, "tf_code": tf_code},
            )


class CatalogExtensionDataPresentError(RuntimeError):
    """Downgrading would delete catalog rows that later data (provider mappings,
    candles, sync state) still depends on."""


def _fail_if_dependent_data_would_be_lost() -> None:
    bind = op.get_bind()
    present: dict[str, int] = {}
    for instrument_id_value in _new_instrument_ids():
        for table in _DEPENDENT_TABLES:
            count = bind.execute(
                sa.text(f"SELECT count(*) FROM {table} WHERE instrument_id = :instrument_id"),
                {"instrument_id": instrument_id_value},
            ).scalar_one()
            if count:
                present[table] = present.get(table, 0) + count
    if present:
        raise CatalogExtensionDataPresentError(
            "0016 downgrade refused: dependent data still references these instruments "
            f"({present}). Remove that data on purpose first, if intended."
        )


def downgrade() -> None:
    _fail_if_dependent_data_would_be_lost()
    bind = op.get_bind()
    for instrument_id_value in _new_instrument_ids():
        bind.execute(
            sa.text(
                "DELETE FROM freyja2_instrument_timeframes WHERE instrument_id = :instrument_id"
            ),
            {"instrument_id": instrument_id_value},
        )
        bind.execute(
            sa.text("DELETE FROM freyja2_instruments WHERE instrument_id = :instrument_id"),
            {"instrument_id": instrument_id_value},
        )
    for code, _name in _NEW_ASSETS:
        bind.execute(sa.text("DELETE FROM freyja2_assets WHERE id = :id"), {"id": asset_id(code)})
    bind.execute(
        sa.text("DELETE FROM freyja2_underlying_markets WHERE id = :id"),
        {"id": market_id(_NEW_MARKET_CODE)},
    )
