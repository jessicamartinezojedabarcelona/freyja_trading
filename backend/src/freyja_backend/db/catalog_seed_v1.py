"""Canonical, immutable v1 catalog seed specification (POINT1-SEED-001).

Single source of truth for the exact v1 scope approved in
POINT1-DOMAIN-001: 2 underlying markets, 2 product types, 7 assets, 10
instruments, 5 timeframes, 50 instrument-timeframe associations. Reused
verbatim by the data migration that seeds it (`0007_seed_catalog_v1`), the
migration that certifies it is still intact (`0009_seed_integrity_guard`),
and the test suite — never duplicated into a second, independently
maintainable list that could drift.

This module contains only pure data and pure, deterministic functions of
that data (plus thin read-only verification helpers against a live
connection). It imports no application services, no legacy code, and no
live ORM models — table shapes are declared as plain `sa.table()` clauses,
the same column-name-only pattern the migrations themselves use, so this
spec never depends on (or is invalidated by) unrelated model changes.

Changing any canonical value here is changing the approved v1 scope itself
— out of bounds for POINT1-SEED-001's fail-closed integrity correction.
"""

import urllib.parse
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection

# --- Deterministic identity -------------------------------------------------
#
# UUIDv5 over uuid.NAMESPACE_URL, so the same seed produces the same ID in
# every environment (local, CI, staging, production) without ever using
# uuid4/random defaults. Each path component is taken verbatim from the
# stored canonical value (case preserved, no lower()/casefold()/trim/alias)
# and percent-encoded on its own — never lower-cased, never aliased.


def entity_uuid(kind: str, *raw_components: str) -> uuid.UUID:
    encoded = "/".join(urllib.parse.quote(component, safe="") for component in raw_components)
    url = f"https://freyja.app/freyja2/catalog/v1/{kind}/{encoded}"
    return uuid.uuid5(uuid.NAMESPACE_URL, url)


def market_id(code: str) -> uuid.UUID:
    return entity_uuid("underlying-market", code)


def product_id(code: str) -> uuid.UUID:
    return entity_uuid("product-type", code)


def asset_id(code: str) -> uuid.UUID:
    return entity_uuid("asset", code)


def timeframe_id(code: str) -> uuid.UUID:
    return entity_uuid("timeframe", code)


def instrument_id(market_code: str, product_code: str, canonical_symbol: str) -> uuid.UUID:
    return entity_uuid("instrument", market_code, product_code, canonical_symbol)


def instrument_id_from_spec(spec: dict[str, object]) -> uuid.UUID:
    return instrument_id(str(spec["market"]), str(spec["product"]), str(spec["symbol"]))


# --- Exact v1 scope approved in POINT1-DOMAIN-001 ---------------------------

MARKETS: tuple[tuple[str, str], ...] = (
    ("CRYPTO", "Crypto"),
    ("FOREX", "Forex"),
)

PRODUCTS: tuple[tuple[str, str], ...] = (
    ("SPOT", "Spot"),
    ("BINARY_OPTION", "Binary option"),
)

ASSETS: tuple[tuple[str, str], ...] = (
    ("BTC", "Bitcoin"),
    ("ETH", "Ethereum"),
    ("SOL", "Solana"),
    ("XRP", "XRP"),
    ("USDT", "Tether USD"),
    ("EUR", "Euro"),
    ("USD", "US dollar"),
)

TIMEFRAMES: tuple[tuple[str, int, str], ...] = (
    ("1m", 60, "1 minute"),
    ("5m", 300, "5 minutes"),
    ("15m", 900, "15 minutes"),
    ("1h", 3600, "1 hour"),
    ("4h", 14400, "4 hours"),
)

# 5 PAIR + 4 ASSET_UNDERLYING + 1 INSTRUMENT_UNDERLYING = 10 instruments.
# The broker contract symbol of a binary belongs to POINT1-PROVIDER-001; not
# seeded here.
INSTRUMENTS: tuple[dict[str, object], ...] = (
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
)

CANONICAL_COUNTS: dict[str, int] = {
    "freyja2_underlying_markets": len(MARKETS),
    "freyja2_product_types": len(PRODUCTS),
    "freyja2_assets": len(ASSETS),
    "freyja2_timeframes": len(TIMEFRAMES),
    "freyja2_instruments": len(INSTRUMENTS),
    "freyja2_instrument_timeframes": len(INSTRUMENTS) * len(TIMEFRAMES),
}

# --- Row payloads, computed once from the data above -------------------------
#
# is_active is always True and always explicit here — both inserted
# explicitly (never left to a server_default) and compared explicitly, so a
# canonical row deactivated out-of-band is a detectable divergence rather
# than a silently-ignored column.

MARKET_ROWS: tuple[dict[str, object], ...] = tuple(
    {"id": market_id(code), "code": code, "display_name": name, "is_active": True}
    for code, name in MARKETS
)

PRODUCT_ROWS: tuple[dict[str, object], ...] = tuple(
    {"id": product_id(code), "code": code, "display_name": name, "is_active": True}
    for code, name in PRODUCTS
)

ASSET_ROWS: tuple[dict[str, object], ...] = tuple(
    {"id": asset_id(code), "code": code, "display_name": name, "is_active": True}
    for code, name in ASSETS
)

TIMEFRAME_ROWS: tuple[dict[str, object], ...] = tuple(
    {
        "id": timeframe_id(code),
        "code": code,
        "duration_seconds": duration,
        "display_name": name,
        "is_active": True,
    }
    for code, duration, name in TIMEFRAMES
)

INSTRUMENT_ROWS: tuple[dict[str, object], ...] = tuple(
    {
        "instrument_id": instrument_id_from_spec(spec),
        "underlying_market_id": market_id(str(spec["market"])),
        "product_type_id": product_id(str(spec["product"])),
        "canonical_symbol": spec["symbol"],
        "base_asset_id": asset_id(str(spec["base"])) if "base" in spec else None,
        "quote_asset_id": asset_id(str(spec["quote"])) if "quote" in spec else None,
        "underlying_asset_id": (
            asset_id(str(spec["underlying_asset"])) if "underlying_asset" in spec else None
        ),
        "underlying_instrument_id": (
            instrument_id_from_spec(spec["underlying_instrument"])  # type: ignore[arg-type]
            if "underlying_instrument" in spec
            else None
        ),
        "is_active": True,
    }
    for spec in INSTRUMENTS
)

INSTRUMENT_TIMEFRAME_ROWS: tuple[dict[str, object], ...] = tuple(
    {
        "instrument_id": instrument_row["instrument_id"],
        "timeframe_id": timeframe_row["id"],
        "is_active": True,
    }
    for instrument_row in INSTRUMENT_ROWS
    for timeframe_row in TIMEFRAME_ROWS
)

# --- Table handles for DML (column-name-only, the standard Alembic data-
# migration pattern — never imports the live ORM models, which could change
# independently of this historical/verification data) ------------------------

MARKETS_TABLE = sa.table(
    "freyja2_underlying_markets",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("code", sa.String),
    sa.column("display_name", sa.String),
    sa.column("is_active", sa.Boolean),
)
PRODUCTS_TABLE = sa.table(
    "freyja2_product_types",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("code", sa.String),
    sa.column("display_name", sa.String),
    sa.column("is_active", sa.Boolean),
)
ASSETS_TABLE = sa.table(
    "freyja2_assets",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("code", sa.String),
    sa.column("display_name", sa.String),
    sa.column("is_active", sa.Boolean),
)
TIMEFRAMES_TABLE = sa.table(
    "freyja2_timeframes",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("code", sa.String),
    sa.column("duration_seconds", sa.Integer),
    sa.column("display_name", sa.String),
    sa.column("is_active", sa.Boolean),
)
INSTRUMENTS_TABLE = sa.table(
    "freyja2_instruments",
    sa.column("instrument_id", postgresql.UUID(as_uuid=True)),
    sa.column("underlying_market_id", postgresql.UUID(as_uuid=True)),
    sa.column("product_type_id", postgresql.UUID(as_uuid=True)),
    sa.column("canonical_symbol", sa.String),
    sa.column("base_asset_id", postgresql.UUID(as_uuid=True)),
    sa.column("quote_asset_id", postgresql.UUID(as_uuid=True)),
    sa.column("underlying_asset_id", postgresql.UUID(as_uuid=True)),
    sa.column("underlying_instrument_id", postgresql.UUID(as_uuid=True)),
    sa.column("is_active", sa.Boolean),
)
INSTRUMENT_TIMEFRAMES_TABLE = sa.table(
    "freyja2_instrument_timeframes",
    sa.column("instrument_id", postgresql.UUID(as_uuid=True)),
    sa.column("timeframe_id", postgresql.UUID(as_uuid=True)),
    sa.column("is_active", sa.Boolean),
)


@dataclass(frozen=True)
class SeedTableSpec:
    """Everything needed to seed-or-verify one canonical catalog table,
    generically, without repeating per-table plumbing in both
    0007_seed_catalog_v1 and 0009_seed_integrity_guard."""

    table: sa.TableClause
    id_column: str
    natural_key_columns: tuple[str, ...]
    compare_columns: tuple[str, ...]
    rows: tuple[dict[str, object], ...]


CATALOG_ROW_SPECS: tuple[SeedTableSpec, ...] = (
    SeedTableSpec(MARKETS_TABLE, "id", ("code",), ("display_name", "is_active"), MARKET_ROWS),
    SeedTableSpec(PRODUCTS_TABLE, "id", ("code",), ("display_name", "is_active"), PRODUCT_ROWS),
    SeedTableSpec(ASSETS_TABLE, "id", ("code",), ("display_name", "is_active"), ASSET_ROWS),
    SeedTableSpec(
        TIMEFRAMES_TABLE,
        "id",
        ("code",),
        ("duration_seconds", "display_name", "is_active"),
        TIMEFRAME_ROWS,
    ),
    SeedTableSpec(
        INSTRUMENTS_TABLE,
        "instrument_id",
        ("underlying_market_id", "product_type_id", "canonical_symbol"),
        (
            "base_asset_id",
            "quote_asset_id",
            "underlying_asset_id",
            "underlying_instrument_id",
            "is_active",
        ),
        INSTRUMENT_ROWS,
    ),
)


# --- Fail-closed verification -------------------------------------------------
#
# Never timestamps: created_at/updated_at are database-generated and are
# never part of any natural key, compare_columns, or association check
# below — comparing them would make every "unchanged" row look diverged.


class SeedIntegrityError(RuntimeError):
    """Base for any v1 seed-integrity failure. Always aborts the enclosing
    Alembic migration transaction — never caught to repair, rename, or
    silently continue."""


class SeedMissingError(SeedIntegrityError):
    """A canonical v1 row or association is absent. Raised only by
    verification-only call sites (0009's upgrade(), 0007's downgrade()
    pre-check) — 0007's own upgrade() instead inserts a missing row; it
    never raises this."""


class SeedDivergenceError(SeedIntegrityError):
    """An existing row/association found under a canonical natural key does
    not match the v1 seed exactly: its id, a compared column, or is_active
    differs. Never reports the actual differing values — only which table,
    natural key, and column diverged — since the stored content is
    arbitrary, out-of-band data this code does not control."""


def verify_row(
    connection: Connection,
    table: sa.TableClause,
    id_column: str,
    natural_key_columns: tuple[str, ...],
    row: dict[str, object],
    compare_columns: tuple[str, ...],
) -> bool:
    """Looks up `row` by its natural key. Returns True if a row is found and
    its id and every compare_columns value match exactly. Returns False if
    no row exists under that natural key (missing — caller decides whether
    to insert it or to raise). Raises SeedDivergenceError if a row exists
    under the natural key but its id or any compared column differs."""
    natural_key_filter = [table.c[name] == row[name] for name in natural_key_columns]
    existing = (
        connection.execute(
            sa.select(*[table.c[name] for name in (id_column, *compare_columns)]).where(
                *natural_key_filter
            )
        )
        .mappings()
        .first()
    )
    if existing is None:
        return False

    natural_key_value = tuple(row[name] for name in natural_key_columns)
    if existing[id_column] != row[id_column]:
        raise SeedDivergenceError(
            f"POINT1-SEED-001: {table.name} clave natural {natural_key_value!r} "
            "tiene un id distinto del esperado por el seed canonico v1."
        )
    for name in compare_columns:
        if existing[name] != row[name]:
            raise SeedDivergenceError(
                f"POINT1-SEED-001: {table.name} clave natural {natural_key_value!r} "
                f"diverge del seed canonico v1 en la columna {name!r}."
            )
    return True


def require_row_present(
    connection: Connection,
    table: sa.TableClause,
    id_column: str,
    natural_key_columns: tuple[str, ...],
    row: dict[str, object],
    compare_columns: tuple[str, ...],
) -> None:
    """Same checks as verify_row, but a missing row is itself a failure —
    for verification-only call sites that must never insert."""
    if not verify_row(connection, table, id_column, natural_key_columns, row, compare_columns):
        natural_key_value = tuple(row[name] for name in natural_key_columns)
        raise SeedMissingError(
            f"POINT1-SEED-001: falta la fila canonica v1 en {table.name} "
            f"(clave natural {natural_key_value!r})."
        )


def verify_association(
    connection: Connection, instrument_id_value: uuid.UUID, timeframe_id_value: uuid.UUID
) -> bool:
    """Same contract as verify_row, specialized for the instrument<->
    timeframe association's composite key: existence plus is_active."""
    existing = connection.execute(
        sa.select(INSTRUMENT_TIMEFRAMES_TABLE.c.is_active).where(
            INSTRUMENT_TIMEFRAMES_TABLE.c.instrument_id == instrument_id_value,
            INSTRUMENT_TIMEFRAMES_TABLE.c.timeframe_id == timeframe_id_value,
        )
    ).first()
    if existing is None:
        return False
    if not existing[0]:
        raise SeedDivergenceError(
            "POINT1-SEED-001: asociacion instrumento-timeframe canonica esta "
            "inactiva (is_active=false)."
        )
    return True


def require_association_present(
    connection: Connection, instrument_id_value: uuid.UUID, timeframe_id_value: uuid.UUID
) -> None:
    if not verify_association(connection, instrument_id_value, timeframe_id_value):
        raise SeedMissingError(
            "POINT1-SEED-001: falta una asociacion instrumento-timeframe canonica v1."
        )
