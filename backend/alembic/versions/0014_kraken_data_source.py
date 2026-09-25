"""kraken_data_source

Revision ID: 0014_kraken_data_source
Revises: 0013_market_data_persistence
Create Date: 2026-09-25

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_kraken_data_source"
down_revision: str | None = "0013_market_data_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# MARKET-DATA-KRAKEN-REST-001 (ADR 0007). Data only, no schema change: adds the KRAKEN
# data source and the four CRYPTO x SPOT symbol mappings (purpose ANALYSIS) its adapter
# uses, exactly as 0013 did for BINANCE. Instruments are looked up by natural key; the
# migration aborts if any is missing, never guessing.
#
# Kraken calls Bitcoin XBT, so the provider symbol for BTC/USDT is XBTUSDT.
#
# downgrade() removes exactly the rows this migration seeded, and refuses to run while
# any candle or sync state for KRAKEN exists: deleting them would silently destroy
# stored market data (the same rule as 0012's guard).

_DATA_SOURCE_CODE = "KRAKEN"
_MAPPINGS: tuple[tuple[str, str], ...] = (
    ("BTC/USDT", "XBTUSDT"),
    ("ETH/USDT", "ETHUSDT"),
    ("SOL/USDT", "SOLUSDT"),
    ("XRP/USDT", "XRPUSDT"),
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
            "VALUES (:id, :code, 'Kraken', 'EXCHANGE', true)"
        ),
        {"id": _DATA_SOURCE_ID, "code": _DATA_SOURCE_CODE},
    )
    for canonical_symbol, provider_symbol in _MAPPINGS:
        instrument_ids = (
            bind.execute(
                sa.text(
                    "SELECT i.instrument_id FROM freyja2_instruments i "
                    "JOIN freyja2_underlying_markets m ON m.id = i.underlying_market_id "
                    "JOIN freyja2_product_types p ON p.id = i.product_type_id "
                    "WHERE m.code = 'CRYPTO' AND p.code = 'SPOT' "
                    "AND i.canonical_symbol = :symbol"
                ),
                {"symbol": canonical_symbol},
            )
            .scalars()
            .all()
        )
        if len(instrument_ids) != 1:
            raise RuntimeError(
                f"0014 aborted: expected exactly one CRYPTO/SPOT instrument {canonical_symbol!r}, "
                f"found {len(instrument_ids)}. Refusing to guess a provider mapping."
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


class KrakenDataPresentError(RuntimeError):
    """Downgrading would delete stored Kraken candles or sync state."""


def _fail_if_stored_kraken_data_would_be_lost() -> None:
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
        raise KrakenDataPresentError(
            "0014 downgrade refused: it would delete stored KRAKEN market data "
            f"({present}). Nothing was changed. Remove that data on purpose first, if intended."
        )


def downgrade() -> None:
    _fail_if_stored_kraken_data_would_be_lost()
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM freyja2_data_source_instruments WHERE data_source_id = :source"),
        {"source": _DATA_SOURCE_ID},
    )
    bind.execute(
        sa.text("DELETE FROM freyja2_data_sources WHERE id = :source"), {"source": _DATA_SOURCE_ID}
    )
