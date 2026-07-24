"""Canonical, immutable v1 catalog seed specification (POINT1-SEED-001).

Single source of truth for the exact v1 scope approved in
POINT1-DOMAIN-001: 2 underlying markets, 2 product types, 7 assets, 10
instruments, 5 timeframes, 50 instrument-timeframe associations. Reused
verbatim by the data migration that seeds it (`0007_seed_catalog_v1`), the
migration that certifies it is still intact (`0009_seed_integrity_guard`),
and the test suite — never duplicated into a second, independently
maintained list that could drift.

Every canonical structure below is deeply immutable: frozen dataclasses and
tuples all the way down, never a public dict. A dict is only ever produced
as a brand-new copy at the exact persistence boundary (via
`dataclasses.asdict`, immediately before an INSERT) — it is never itself
the canonical source.

`0007_seed_catalog_v1` and `0009_seed_integrity_guard` do not trust this
module blindly: `contract_fingerprint()` computes a deterministic SHA-256
over a fixed, explicit serialization of the whole *final, stable payload*
of all six catalog tables — every deterministic UUID, natural key,
display_name, canonical_symbol, duration_seconds, FK/instrument shape, and
is_active, for every canonical row AND every one of the 50
instrument-timeframe associations. It is computed from the same
MARKET_ROWS/.../INSTRUMENT_TIMEFRAME_ROWS constants 0007/0009 actually
insert-or-verify, never from the pre-UUID conceptual data alone — so a
future change to entity_uuid()'s algorithm, to uuid.NAMESPACE_URL, to the
base URL, to any row's is_active default, or to an association's
identity/state changes the fingerprint too, not just the row content. Each
of 0007/0009 pins its own historical copy of the expected fingerprint and
calls `verify_contract_fingerprint()` as the very first thing it does,
before any insert, verification, or delete — any accidental drift in this
module (a typo, a merge mistake, a future task editing it for an unrelated
reason) fails closed immediately instead of silently seeding, verifying,
or deleting against altered data.

This module imports no application services, no legacy code, and no live
ORM models — table shapes are declared as plain `sa.table()` clauses, the
same column-name-only pattern the migrations themselves use.

Changing any canonical value here is changing the approved v1 scope itself
— out of bounds for POINT1-SEED-001's fail-closed integrity correction.
"""

import dataclasses
import hashlib
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


# --- Exact v1 scope approved in POINT1-DOMAIN-001 ---------------------------
#
# Markets, products, assets, and timeframes are already deeply immutable as
# plain tuples of (str, ...) primitives — no dict involved. Instruments need
# an explicit shape (optional base/quote/underlying fields), so they are a
# frozen dataclass instead of a dict.

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


@dataclass(frozen=True, slots=True)
class InstrumentKey:
    """Identifies another canonical instrument by its own natural key —
    never a nested dict, never a copy/reinterpretation of its symbol text."""

    market: str
    product: str
    symbol: str


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """One canonical v1 instrument. Exactly one of (base & quote),
    underlying_asset, or underlying_instrument is set — the same three
    mutually exclusive shapes POINT1-DB-001's schema enforces physically."""

    market: str
    product: str
    symbol: str
    base: str | None = None
    quote: str | None = None
    underlying_asset: str | None = None
    underlying_instrument: InstrumentKey | None = None


# 5 PAIR + 4 ASSET_UNDERLYING + 1 INSTRUMENT_UNDERLYING = 10 instruments.
# The broker contract symbol of a binary belongs to POINT1-PROVIDER-001; not
# seeded here.
INSTRUMENTS: tuple[InstrumentSpec, ...] = (
    InstrumentSpec("CRYPTO", "SPOT", "BTC/USDT", base="BTC", quote="USDT"),
    InstrumentSpec("CRYPTO", "SPOT", "ETH/USDT", base="ETH", quote="USDT"),
    InstrumentSpec("CRYPTO", "SPOT", "SOL/USDT", base="SOL", quote="USDT"),
    InstrumentSpec("CRYPTO", "SPOT", "XRP/USDT", base="XRP", quote="USDT"),
    InstrumentSpec("FOREX", "SPOT", "EUR/USD", base="EUR", quote="USD"),
    InstrumentSpec("CRYPTO", "BINARY_OPTION", "BTC", underlying_asset="BTC"),
    InstrumentSpec("CRYPTO", "BINARY_OPTION", "ETH", underlying_asset="ETH"),
    InstrumentSpec("CRYPTO", "BINARY_OPTION", "SOL", underlying_asset="SOL"),
    InstrumentSpec("CRYPTO", "BINARY_OPTION", "XRP", underlying_asset="XRP"),
    InstrumentSpec(
        "FOREX",
        "BINARY_OPTION",
        "EUR/USD",
        underlying_instrument=InstrumentKey("FOREX", "SPOT", "EUR/USD"),
    ),
)


def instrument_id_from_spec(spec: InstrumentSpec) -> uuid.UUID:
    return instrument_id(spec.market, spec.product, spec.symbol)


def instrument_id_from_key(key: InstrumentKey) -> uuid.UUID:
    return instrument_id(key.market, key.product, key.symbol)


# --- Row payloads, computed once from the data above -------------------------
#
# Each is a frozen dataclass, never a dict: the only dict ever produced from
# one of these is a brand-new copy from `dataclasses.asdict()`, generated
# immediately before an INSERT — never stored, never shared, never the
# canonical source itself.
#
# is_active is always True and always explicit here — both inserted
# explicitly (never left to a server_default) and compared explicitly, so a
# canonical row deactivated out-of-band is a detectable divergence rather
# than a silently-ignored column.


@dataclass(frozen=True, slots=True)
class MarketRow:
    id: uuid.UUID
    code: str
    display_name: str
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class ProductRow:
    id: uuid.UUID
    code: str
    display_name: str
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class AssetRow:
    id: uuid.UUID
    code: str
    display_name: str
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class TimeframeRow:
    id: uuid.UUID
    code: str
    duration_seconds: int
    display_name: str
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class InstrumentRow:
    instrument_id: uuid.UUID
    underlying_market_id: uuid.UUID
    product_type_id: uuid.UUID
    canonical_symbol: str
    base_asset_id: uuid.UUID | None
    quote_asset_id: uuid.UUID | None
    underlying_asset_id: uuid.UUID | None
    underlying_instrument_id: uuid.UUID | None
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class AssociationRow:
    instrument_id: uuid.UUID
    timeframe_id: uuid.UUID
    is_active: bool = True


MARKET_ROWS: tuple[MarketRow, ...] = tuple(
    MarketRow(id=market_id(code), code=code, display_name=name) for code, name in MARKETS
)

PRODUCT_ROWS: tuple[ProductRow, ...] = tuple(
    ProductRow(id=product_id(code), code=code, display_name=name) for code, name in PRODUCTS
)

ASSET_ROWS: tuple[AssetRow, ...] = tuple(
    AssetRow(id=asset_id(code), code=code, display_name=name) for code, name in ASSETS
)

TIMEFRAME_ROWS: tuple[TimeframeRow, ...] = tuple(
    TimeframeRow(id=timeframe_id(code), code=code, duration_seconds=duration, display_name=name)
    for code, duration, name in TIMEFRAMES
)

INSTRUMENT_ROWS: tuple[InstrumentRow, ...] = tuple(
    InstrumentRow(
        instrument_id=instrument_id_from_spec(spec),
        underlying_market_id=market_id(spec.market),
        product_type_id=product_id(spec.product),
        canonical_symbol=spec.symbol,
        base_asset_id=asset_id(spec.base) if spec.base is not None else None,
        quote_asset_id=asset_id(spec.quote) if spec.quote is not None else None,
        underlying_asset_id=(
            asset_id(spec.underlying_asset) if spec.underlying_asset is not None else None
        ),
        underlying_instrument_id=(
            instrument_id_from_key(spec.underlying_instrument)
            if spec.underlying_instrument is not None
            else None
        ),
    )
    for spec in INSTRUMENTS
)

INSTRUMENT_TIMEFRAME_ROWS: tuple[AssociationRow, ...] = tuple(
    AssociationRow(instrument_id=instrument_row.instrument_id, timeframe_id=timeframe_row.id)
    for instrument_row in INSTRUMENT_ROWS
    for timeframe_row in TIMEFRAME_ROWS
)


# --- Contract fingerprint ----------------------------------------------------
#
# A fixed, explicit, human-auditable serialization — never dict/JSON
# key-ordering — of the whole approved v1 contract's FINAL, STABLE PAYLOAD:
# every row's deterministic UUID, natural key, display_name/canonical_symbol,
# duration_seconds, FKs/instrument shape, and is_active — plus every one of
# the 50 associations' instrument_id, timeframe_id, and is_active. Built from
# the same *_ROWS constants 0007/0009 actually act on, so it also protects
# against silent drift in entity_uuid()'s algorithm, uuid.NAMESPACE_URL, the
# base URL, or any is_active default — not just the pre-UUID conceptual data.
# `0007_seed_catalog_v1` and `0009_seed_integrity_guard` each pin their own
# copy of the expected digest and verify it before doing anything else.


def _market_line(market: MarketRow) -> str:
    return f"market|{market.id}|{market.code}|{market.display_name}|{market.is_active}"


def _product_line(product: ProductRow) -> str:
    return f"product|{product.id}|{product.code}|{product.display_name}|{product.is_active}"


def _asset_line(asset: AssetRow) -> str:
    return f"asset|{asset.id}|{asset.code}|{asset.display_name}|{asset.is_active}"


def _timeframe_line(timeframe: TimeframeRow) -> str:
    return (
        f"timeframe|{timeframe.id}|{timeframe.code}|{timeframe.duration_seconds}|"
        f"{timeframe.display_name}|{timeframe.is_active}"
    )


def _instrument_line(instrument: InstrumentRow) -> str:
    return (
        "instrument|"
        f"{instrument.instrument_id}|{instrument.underlying_market_id}|"
        f"{instrument.product_type_id}|{instrument.canonical_symbol}|"
        f"base={instrument.base_asset_id or ''}|"
        f"quote={instrument.quote_asset_id or ''}|"
        f"underlying_asset={instrument.underlying_asset_id or ''}|"
        f"underlying_instrument={instrument.underlying_instrument_id or ''}|"
        f"is_active={instrument.is_active}"
    )


def _association_line(association: AssociationRow) -> str:
    return (
        f"association|{association.instrument_id}|{association.timeframe_id}|"
        f"{association.is_active}"
    )


def _canonical_lines() -> tuple[str, ...]:
    return (
        *(_market_line(market) for market in MARKET_ROWS),
        *(_product_line(product) for product in PRODUCT_ROWS),
        *(_asset_line(asset) for asset in ASSET_ROWS),
        *(_timeframe_line(timeframe) for timeframe in TIMEFRAME_ROWS),
        *(_instrument_line(instrument) for instrument in INSTRUMENT_ROWS),
        *(_association_line(association) for association in INSTRUMENT_TIMEFRAME_ROWS),
    )


def canonical_serialization() -> str:
    return "\n".join(_canonical_lines())


def contract_fingerprint() -> str:
    return hashlib.sha256(canonical_serialization().encode("utf-8")).hexdigest()


class SeedIntegrityError(RuntimeError):
    """Base for any v1 seed-integrity failure. Always aborts the enclosing
    Alembic migration transaction — never caught to repair, rename, or
    silently continue."""


class ContractFingerprintError(SeedIntegrityError):
    """The live v1 catalog specification's SHA-256 fingerprint does not
    match the historical anchor pinned inside the calling migration. Raised
    before any insert, verification, or delete ever runs — an accidental
    edit to this module (a typo, a merge mistake, an unrelated future
    change) fails closed instead of silently seeding, verifying, or
    deleting against altered data."""


def verify_contract_fingerprint(expected_sha256: str) -> None:
    actual = contract_fingerprint()
    if actual != expected_sha256:
        raise ContractFingerprintError(
            "POINT1-SEED-001: la huella SHA-256 del contrato v1 vigente no "
            "coincide con el ancla historica fijada en esta migracion; "
            "abortando antes de cualquier operacion sobre datos."
        )


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


@dataclass(frozen=True, slots=True)
class SeedTableSpec:
    """Everything needed to seed-or-verify one canonical catalog table,
    generically, without repeating per-table plumbing in both
    0007_seed_catalog_v1 and 0009_seed_integrity_guard."""

    table: sa.TableClause
    id_column: str
    natural_key_columns: tuple[str, ...]
    compare_columns: tuple[str, ...]
    rows: tuple[object, ...]


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


def verify_row(
    connection: Connection,
    table: sa.TableClause,
    id_column: str,
    natural_key_columns: tuple[str, ...],
    row: object,
    compare_columns: tuple[str, ...],
) -> bool:
    """Looks up `row` by its natural key. Returns True if a row is found and
    its id and every compare_columns value match exactly. Returns False if
    no row exists under that natural key (missing — caller decides whether
    to insert it or to raise). Raises SeedDivergenceError if a row exists
    under the natural key but its id or any compared column differs."""
    natural_key_filter = [table.c[name] == getattr(row, name) for name in natural_key_columns]
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

    natural_key_value = tuple(getattr(row, name) for name in natural_key_columns)
    if existing[id_column] != getattr(row, id_column):
        raise SeedDivergenceError(
            f"POINT1-SEED-001: {table.name} clave natural {natural_key_value!r} "
            "tiene un id distinto del esperado por el seed canonico v1."
        )
    for name in compare_columns:
        if existing[name] != getattr(row, name):
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
    row: object,
    compare_columns: tuple[str, ...],
) -> None:
    """Same checks as verify_row, but a missing row is itself a failure —
    for verification-only call sites that must never insert."""
    if not verify_row(connection, table, id_column, natural_key_columns, row, compare_columns):
        natural_key_value = tuple(getattr(row, name) for name in natural_key_columns)
        raise SeedMissingError(
            f"POINT1-SEED-001: falta la fila canonica v1 en {table.name} "
            f"(clave natural {natural_key_value!r})."
        )


def insert_row(connection: Connection, table: sa.TableClause, row: object) -> None:
    """The only place a dict is built from a canonical row — a brand-new
    copy via dataclasses.asdict(), generated at this exact persistence
    boundary and never reused or stored anywhere else."""
    connection.execute(sa.insert(table).values(**dataclasses.asdict(row)))  # type: ignore[call-overload]


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
