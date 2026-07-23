"""seed_catalog_v1

Revision ID: 0007_seed_catalog_v1
Revises: 0006_catalog_display_names
Create Date: 2026-07-23

"""

import urllib.parse
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_seed_catalog_v1"
down_revision: str | None = "0006_catalog_display_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --- Deterministic identity -------------------------------------------------
#
# UUIDv5 over uuid.NAMESPACE_URL, so the same seed produces the same ID in
# every environment (local, CI, staging, production) without ever using
# uuid4/random defaults. Each path component is taken verbatim from the
# stored canonical value (case preserved, no lower()/casefold()/trim/alias)
# and percent-encoded on its own — never lower-cased, never aliased.


def _entity_uuid(kind: str, *raw_components: str) -> uuid.UUID:
    encoded = "/".join(urllib.parse.quote(component, safe="") for component in raw_components)
    url = f"https://freyja.app/freyja2/catalog/v1/{kind}/{encoded}"
    return uuid.uuid5(uuid.NAMESPACE_URL, url)


def _market_id(code: str) -> uuid.UUID:
    return _entity_uuid("underlying-market", code)


def _product_id(code: str) -> uuid.UUID:
    return _entity_uuid("product-type", code)


def _asset_id(code: str) -> uuid.UUID:
    return _entity_uuid("asset", code)


def _timeframe_id(code: str) -> uuid.UUID:
    return _entity_uuid("timeframe", code)


def _instrument_id(market_code: str, product_code: str, canonical_symbol: str) -> uuid.UUID:
    return _entity_uuid("instrument", market_code, product_code, canonical_symbol)


def _instrument_id_from_spec(spec: dict[str, object]) -> uuid.UUID:
    return _instrument_id(str(spec["market"]), str(spec["product"]), str(spec["symbol"]))


# --- Exact v1 scope approved in POINT1-DOMAIN-001 ---------------------------

_MARKETS: list[tuple[str, str]] = [
    ("CRYPTO", "Crypto"),
    ("FOREX", "Forex"),
]

_PRODUCTS: list[tuple[str, str]] = [
    ("SPOT", "Spot"),
    ("BINARY_OPTION", "Binary option"),
]

_ASSETS: list[tuple[str, str]] = [
    ("BTC", "Bitcoin"),
    ("ETH", "Ethereum"),
    ("SOL", "Solana"),
    ("XRP", "XRP"),
    ("USDT", "Tether USD"),
    ("EUR", "Euro"),
    ("USD", "US dollar"),
]

_TIMEFRAMES: list[tuple[str, int, str]] = [
    ("1m", 60, "1 minute"),
    ("5m", 300, "5 minutes"),
    ("15m", 900, "15 minutes"),
    ("1h", 3600, "1 hour"),
    ("4h", 14400, "4 hours"),
]

# 5 PAIR + 4 ASSET_UNDERLYING + 1 INSTRUMENT_UNDERLYING = 10 instruments.
# The broker contract symbol of a binary belongs to POINT1-PROVIDER-001; not
# seeded here.
_INSTRUMENTS: list[dict[str, object]] = [
    {"market": "CRYPTO", "product": "SPOT", "symbol": "BTC/USDT", "base": "BTC", "quote": "USDT"},
    {"market": "CRYPTO", "product": "SPOT", "symbol": "ETH/USDT", "base": "ETH", "quote": "USDT"},
    {"market": "CRYPTO", "product": "SPOT", "symbol": "SOL/USDT", "base": "SOL", "quote": "USDT"},
    {"market": "CRYPTO", "product": "SPOT", "symbol": "XRP/USDT", "base": "XRP", "quote": "USDT"},
    {"market": "FOREX", "product": "SPOT", "symbol": "EUR/USD", "base": "EUR", "quote": "USD"},
    {"market": "CRYPTO", "product": "BINARY_OPTION", "symbol": "BTC", "underlying_asset": "BTC"},
    {"market": "CRYPTO", "product": "BINARY_OPTION", "symbol": "ETH", "underlying_asset": "ETH"},
    {"market": "CRYPTO", "product": "BINARY_OPTION", "symbol": "SOL", "underlying_asset": "SOL"},
    {"market": "CRYPTO", "product": "BINARY_OPTION", "symbol": "XRP", "underlying_asset": "XRP"},
    {
        "market": "FOREX",
        "product": "BINARY_OPTION",
        "symbol": "EUR/USD",
        "underlying_instrument": {"market": "FOREX", "product": "SPOT", "symbol": "EUR/USD"},
    },
]

# --- Table handles for DML (column-name-only, the standard Alembic data-
# migration pattern — never imports the live ORM models, which could change
# independently of this historical migration) --------------------------------

_markets_t = sa.table(
    "freyja2_underlying_markets",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("code", sa.String),
    sa.column("display_name", sa.String),
)
_products_t = sa.table(
    "freyja2_product_types",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("code", sa.String),
    sa.column("display_name", sa.String),
)
_assets_t = sa.table(
    "freyja2_assets",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("code", sa.String),
    sa.column("display_name", sa.String),
)
_timeframes_t = sa.table(
    "freyja2_timeframes",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("code", sa.String),
    sa.column("duration_seconds", sa.Integer),
    sa.column("display_name", sa.String),
)
_instruments_t = sa.table(
    "freyja2_instruments",
    sa.column("instrument_id", postgresql.UUID(as_uuid=True)),
    sa.column("underlying_market_id", postgresql.UUID(as_uuid=True)),
    sa.column("product_type_id", postgresql.UUID(as_uuid=True)),
    sa.column("canonical_symbol", sa.String),
    sa.column("base_asset_id", postgresql.UUID(as_uuid=True)),
    sa.column("quote_asset_id", postgresql.UUID(as_uuid=True)),
    sa.column("underlying_asset_id", postgresql.UUID(as_uuid=True)),
    sa.column("underlying_instrument_id", postgresql.UUID(as_uuid=True)),
)
_instrument_timeframes_t = sa.table(
    "freyja2_instrument_timeframes",
    sa.column("instrument_id", postgresql.UUID(as_uuid=True)),
    sa.column("timeframe_id", postgresql.UUID(as_uuid=True)),
)


def _seed_rows(
    connection: Connection,
    table: sa.TableClause,
    id_column: str,
    rows: list[dict[str, object]],
    compare_columns: tuple[str, ...],
) -> None:
    """Idempotent, fail-closed seed: inserts a row that doesn't exist yet;
    for a row that already exists, verifies every compare_columns value
    matches exactly and raises (aborting the whole migration transaction)
    on any divergence — never overwrites, repairs, renames, or silently
    completes a changed seed."""
    id_col = table.c[id_column]
    for row in rows:
        existing = (
            connection.execute(
                sa.select(*[table.c[name] for name in compare_columns]).where(
                    id_col == row[id_column]
                )
            )
            .mappings()
            .first()
        )
        if existing is None:
            connection.execute(sa.insert(table).values(**row))
            continue
        for name in compare_columns:
            if existing[name] != row[name]:
                raise RuntimeError(
                    f"POINT1-SEED-001: divergencia detectada en {table.name} "
                    f"{id_column}={row[id_column]!r}: columna {name!r} "
                    f"existente={existing[name]!r} esperado={row[name]!r}"
                )


def _seed_instrument_timeframes(connection: Connection, rows: list[dict[str, object]]) -> None:
    for row in rows:
        existing = connection.execute(
            sa.select(_instrument_timeframes_t.c.instrument_id).where(
                _instrument_timeframes_t.c.instrument_id == row["instrument_id"],
                _instrument_timeframes_t.c.timeframe_id == row["timeframe_id"],
            )
        ).first()
        if existing is None:
            connection.execute(sa.insert(_instrument_timeframes_t).values(**row))


def upgrade() -> None:
    connection = op.get_bind()

    market_rows: list[dict[str, object]] = [
        {"id": _market_id(code), "code": code, "display_name": name} for code, name in _MARKETS
    ]
    _seed_rows(connection, _markets_t, "id", market_rows, ("code", "display_name"))

    product_rows: list[dict[str, object]] = [
        {"id": _product_id(code), "code": code, "display_name": name} for code, name in _PRODUCTS
    ]
    _seed_rows(connection, _products_t, "id", product_rows, ("code", "display_name"))

    asset_rows: list[dict[str, object]] = [
        {"id": _asset_id(code), "code": code, "display_name": name} for code, name in _ASSETS
    ]
    _seed_rows(connection, _assets_t, "id", asset_rows, ("code", "display_name"))

    timeframe_rows: list[dict[str, object]] = [
        {
            "id": _timeframe_id(code),
            "code": code,
            "duration_seconds": duration,
            "display_name": name,
        }
        for code, duration, name in _TIMEFRAMES
    ]
    _seed_rows(
        connection,
        _timeframes_t,
        "id",
        timeframe_rows,
        ("code", "duration_seconds", "display_name"),
    )

    instrument_rows: list[dict[str, object]] = []
    for spec in _INSTRUMENTS:
        underlying_instrument = spec.get("underlying_instrument")
        instrument_rows.append(
            {
                "instrument_id": _instrument_id_from_spec(spec),
                "underlying_market_id": _market_id(str(spec["market"])),
                "product_type_id": _product_id(str(spec["product"])),
                "canonical_symbol": spec["symbol"],
                "base_asset_id": _asset_id(str(spec["base"])) if "base" in spec else None,
                "quote_asset_id": _asset_id(str(spec["quote"])) if "quote" in spec else None,
                "underlying_asset_id": (
                    _asset_id(str(spec["underlying_asset"])) if "underlying_asset" in spec else None
                ),
                "underlying_instrument_id": (
                    _instrument_id_from_spec(underlying_instrument)  # type: ignore[arg-type]
                    if underlying_instrument
                    else None
                ),
            }
        )
    _seed_rows(
        connection,
        _instruments_t,
        "instrument_id",
        instrument_rows,
        (
            "underlying_market_id",
            "product_type_id",
            "canonical_symbol",
            "base_asset_id",
            "quote_asset_id",
            "underlying_asset_id",
            "underlying_instrument_id",
        ),
    )

    instrument_timeframe_rows: list[dict[str, object]] = [
        {"instrument_id": instrument_row["instrument_id"], "timeframe_id": timeframe_row["id"]}
        for instrument_row in instrument_rows
        for timeframe_row in timeframe_rows
    ]
    _seed_instrument_timeframes(connection, instrument_timeframe_rows)


def downgrade() -> None:
    connection = op.get_bind()

    instrument_ids = [_instrument_id_from_spec(spec) for spec in _INSTRUMENTS]
    timeframe_ids = [_timeframe_id(code) for code, _, _ in _TIMEFRAMES]

    connection.execute(
        sa.delete(_instrument_timeframes_t).where(
            _instrument_timeframes_t.c.instrument_id.in_(instrument_ids),
            _instrument_timeframes_t.c.timeframe_id.in_(timeframe_ids),
        )
    )

    # Delete INSTRUMENT_UNDERLYING rows before the instruments they
    # reference (FK from underlying_instrument_id) — no CASCADE anywhere, so
    # a real reference this migration doesn't know about aborts the
    # downgrade instead of being silently swept away.
    referencing_first = [s for s in _INSTRUMENTS if "underlying_instrument" in s]
    referenced_after = [s for s in _INSTRUMENTS if "underlying_instrument" not in s]
    for spec in referencing_first + referenced_after:
        connection.execute(
            sa.delete(_instruments_t).where(
                _instruments_t.c.instrument_id == _instrument_id_from_spec(spec)
            )
        )

    connection.execute(
        sa.delete(_assets_t).where(_assets_t.c.id.in_([_asset_id(code) for code, _ in _ASSETS]))
    )
    connection.execute(sa.delete(_timeframes_t).where(_timeframes_t.c.id.in_(timeframe_ids)))
    connection.execute(
        sa.delete(_products_t).where(
            _products_t.c.id.in_([_product_id(code) for code, _ in _PRODUCTS])
        )
    )
    connection.execute(
        sa.delete(_markets_t).where(_markets_t.c.id.in_([_market_id(code) for code, _ in _MARKETS]))
    )
