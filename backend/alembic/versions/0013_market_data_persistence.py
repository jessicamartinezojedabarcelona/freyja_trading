"""market_data_persistence

Revision ID: 0013_market_data_persistence
Revises: 0012_remove_regulatory_engine
Create Date: 2026-09-24

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_market_data_persistence"
down_revision: str | None = "0012_remove_regulatory_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# MARKET-DATA-PERSISTENCE-001 (ADR 0003). Adds:
#
#   - freyja2_candles: closed, immutable candles with provenance and quality.
#     Natural primary key (data source, instrument, timeframe, open_time), so
#     the same candle can never be stored twice. A BEFORE UPDATE trigger
#     rejects every UPDATE: a confirmed candle can only be inserted, never
#     rewritten (DELETE stays allowed, for a future retention policy).
#   - freyja2_market_data_sync_state: latest sync outcome per key, the only
#     way to tell "provider failing" from "nothing new".
#   - The BINANCE data source and the four CRYPTO x SPOT symbol mappings
#     (purpose ANALYSIS) the first adapter uses. Instruments are looked up by
#     natural key; the migration aborts if any is missing, never guessing.
#
# Forward-only for data: downgrade() drops both tables (and any candles in
# them) and removes exactly the rows this migration seeded.

_DATA_SOURCE_CODE = "BINANCE"
_MAPPINGS: tuple[tuple[str, str], ...] = (
    ("BTC/USDT", "BTCUSDT"),
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
    data_quality = postgresql.ENUM("OK", "DEGRADED", "UNAVAILABLE", name="freyja2_data_quality")
    data_quality.create(op.get_bind(), checkfirst=False)
    quality_column = postgresql.ENUM(
        "OK", "DEGRADED", "UNAVAILABLE", name="freyja2_data_quality", create_type=False
    )
    price = sa.Numeric(38, 12)

    op.create_table(
        "freyja2_candles",
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timeframe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", price, nullable=False),
        sa.Column("high", price, nullable=False),
        sa.Column("low", price, nullable=False),
        sa.Column("close", price, nullable=False),
        sa.Column("volume", price, nullable=False),
        sa.Column("quality", quality_column, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "data_source_id",
            "instrument_id",
            "timeframe_id",
            "open_time",
            name="pk_freyja2_candles",
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"], ["freyja2_data_sources.id"], name="fk_freyja2_candles_data_source"
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["freyja2_instruments.instrument_id"],
            name="fk_freyja2_candles_instrument",
        ),
        sa.ForeignKeyConstraint(
            ["timeframe_id"], ["freyja2_timeframes.id"], name="fk_freyja2_candles_timeframe"
        ),
        sa.CheckConstraint("close_time > open_time", name="ck_freyja2_candles_close_after_open"),
        sa.CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0",
            name="ck_freyja2_candles_prices_positive",
        ),
        sa.CheckConstraint("volume >= 0", name="ck_freyja2_candles_volume_non_negative"),
        sa.CheckConstraint(
            "high >= low AND high >= open AND high >= close AND low <= open AND low <= close",
            name="ck_freyja2_candles_ohlc_consistent",
        ),
        sa.CheckConstraint("quality <> 'UNAVAILABLE'", name="ck_freyja2_candles_quality_has_data"),
    )

    op.execute(
        """
        CREATE FUNCTION freyja2_candles_reject_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'freyja2_candles rows are immutable: candles cannot be updated'
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_freyja2_candles_immutable
        BEFORE UPDATE ON freyja2_candles
        FOR EACH ROW EXECUTE FUNCTION freyja2_candles_reject_update()
        """
    )

    op.create_table(
        "freyja2_market_data_sync_state",
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timeframe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", quality_column, nullable=False),
        sa.Column(
            "last_issue_codes",
            postgresql.ARRAY(sa.String(length=32)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("last_detail", sa.String(length=300), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint(
            "data_source_id", "instrument_id", "timeframe_id", name="pk_freyja2_sync_state"
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["freyja2_data_sources.id"],
            name="fk_freyja2_sync_state_data_source",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["freyja2_instruments.instrument_id"],
            name="fk_freyja2_sync_state_instrument",
        ),
        sa.ForeignKeyConstraint(
            ["timeframe_id"], ["freyja2_timeframes.id"], name="fk_freyja2_sync_state_timeframe"
        ),
        sa.CheckConstraint(
            "consecutive_failures >= 0", name="ck_freyja2_sync_state_failures_non_negative"
        ),
    )

    _seed_binance_source()


def _seed_binance_source() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO freyja2_data_sources (id, code, display_name, source_type, is_active) "
            "VALUES (:id, :code, 'Binance', 'EXCHANGE', true)"
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
                f"0013 aborted: expected exactly one CRYPTO/SPOT instrument {canonical_symbol!r}, "
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


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("freyja2_market_data_sync_state")
    op.execute("DROP TRIGGER trg_freyja2_candles_immutable ON freyja2_candles")
    op.execute("DROP FUNCTION freyja2_candles_reject_update()")
    op.drop_table("freyja2_candles")
    bind.execute(
        sa.text("DELETE FROM freyja2_data_source_instruments WHERE data_source_id = :source"),
        {"source": _DATA_SOURCE_ID},
    )
    bind.execute(
        sa.text("DELETE FROM freyja2_data_sources WHERE id = :source"), {"source": _DATA_SOURCE_ID}
    )
    postgresql.ENUM(name="freyja2_data_quality").drop(bind, checkfirst=False)
