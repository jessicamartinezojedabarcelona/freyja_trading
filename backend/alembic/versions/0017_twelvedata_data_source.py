"""twelvedata_data_source

Revision ID: 0017_twelvedata_data_source
Revises: 0016_forex_metals_catalog
Create Date: 2026-09-29

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017_twelvedata_data_source"
down_revision: str | None = "0016_forex_metals_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# MARKET-DATA-TWELVEDATA-REST-001 follow-up (ADR 0009). Data only, no schema change: adds
# the TWELVEDATA data source and the five symbol mappings (purpose ANALYSIS) its adapter
# uses, exactly as 0013/0014 did for BINANCE/KRAKEN. Unlike those two, Twelve Data is not
# an exchange (source_type MARKET_DATA, not EXCHANGE) and its instruments span two catalog
# markets (FOREX and METALS, added by 0016) rather than one, so each mapping carries its
# own market code instead of a single one shared by all. Instruments are looked up by
# natural key (market, SPOT, symbol); the migration aborts if any is missing, never
# guessing.
#
# Without this migration, `has_market_data` (backend/repositories/catalog_repository.py)
# stays false for all five instruments and they never appear on the Mercados page, even
# though 0016 already catalogued them and the REST-001 adapter can already read them.
#
# downgrade() removes exactly the rows this migration seeded, and refuses to run while any
# candle or sync state for TWELVEDATA exists: deleting them would silently destroy stored
# market data (the same rule as 0013/0014's guard).

_DATA_SOURCE_CODE = "TWELVEDATA"
_MAPPINGS: tuple[tuple[str, str, str], ...] = (
    ("FOREX", "EUR/USD", "EUR/USD"),
    ("FOREX", "GBP/USD", "GBP/USD"),
    ("FOREX", "USD/JPY", "USD/JPY"),
    ("FOREX", "USD/CHF", "USD/CHF"),
    ("METALS", "XAU/USD", "XAU/USD"),
)
_PURPOSE = "ANALYSIS"
_NAMESPACE = "https://freyja.app/freyja2/market-data/v1"


def _stable_id(kind: str, *parts: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "/".join([_NAMESPACE, kind, *parts]))


_DATA_SOURCE_ID = _stable_id("data-source", _DATA_SOURCE_CODE)


def _mapping_id(provider_symbol: str) -> uuid.UUID:
    return _stable_id("data-source-instrument", _DATA_SOURCE_CODE, provider_symbol, _PURPOSE)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO freyja2_data_sources (id, code, display_name, source_type, is_active) "
            "VALUES (:id, :code, 'Twelve Data', 'MARKET_DATA', true)"
        ),
        {"id": _DATA_SOURCE_ID, "code": _DATA_SOURCE_CODE},
    )
    for market_code, canonical_symbol, provider_symbol in _MAPPINGS:
        instrument_ids = (
            bind.execute(
                sa.text(
                    "SELECT i.instrument_id FROM freyja2_instruments i "
                    "JOIN freyja2_underlying_markets m ON m.id = i.underlying_market_id "
                    "JOIN freyja2_product_types p ON p.id = i.product_type_id "
                    "WHERE m.code = :market AND p.code = 'SPOT' "
                    "AND i.canonical_symbol = :symbol"
                ),
                {"market": market_code, "symbol": canonical_symbol},
            )
            .scalars()
            .all()
        )
        if len(instrument_ids) != 1:
            raise RuntimeError(
                f"0017 aborted: expected exactly one {market_code}/SPOT instrument "
                f"{canonical_symbol!r}, found {len(instrument_ids)}. Refusing to guess a "
                "provider mapping."
            )
        bind.execute(
            sa.text(
                "INSERT INTO freyja2_data_source_instruments "
                "(id, data_source_id, instrument_id, provider_symbol, purpose, is_active) "
                "VALUES (:id, :source, :instrument, :provider_symbol, "
                "CAST(:purpose AS freyja2_data_source_instrument_purpose), true)"
            ),
            {
                "id": _mapping_id(provider_symbol),
                "source": _DATA_SOURCE_ID,
                "instrument": instrument_ids[0],
                "provider_symbol": provider_symbol,
                "purpose": _PURPOSE,
            },
        )


class TwelveDataDataPresentError(RuntimeError):
    """Downgrading would delete stored TWELVEDATA candles or sync state."""


def _fail_if_stored_twelvedata_data_would_be_lost() -> None:
    bind = op.get_bind()
    counts = {
        table: bind.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE data_source_id = :source"),
            {"source": _DATA_SOURCE_ID},
        ).scalar_one()
        for table in ("freyja2_candles", "freyja2_market_data_sync_state")
    }
    present = {table: count for table, count in counts.items() if count}
    if present:
        raise TwelveDataDataPresentError(
            "0017 downgrade refused: it would delete stored TWELVEDATA market data "
            f"({present}). Nothing was changed. Remove that data on purpose first, if intended."
        )


def downgrade() -> None:
    _fail_if_stored_twelvedata_data_would_be_lost()
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM freyja2_data_source_instruments WHERE data_source_id = :source"),
        {"source": _DATA_SOURCE_ID},
    )
    bind.execute(
        sa.text("DELETE FROM freyja2_data_sources WHERE id = :source"), {"source": _DATA_SOURCE_ID}
    )
