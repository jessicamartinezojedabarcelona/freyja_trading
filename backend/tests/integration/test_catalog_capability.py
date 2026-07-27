import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from freyja_backend.core.database import get_postgres_settings
from freyja_backend.db.models.auth import AuthUser, UserOrigin
from freyja_backend.db.models.capability import (
    ActivationStatus,
    CapabilityStatus,
    CredentialsStatus,
    ExecutionContext,
    ExecutionEnvironment,
    OwnerAuthorizationStatus,
    TechnicalCapability,
    VenuePermissionStatus,
)
from freyja_backend.db.models.provider import (
    DataSource,
    DataSourceType,
    Venue,
    VenueInstrument,
    VenueType,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

_CAPABILITY_TABLES = frozenset(
    {
        "freyja2_technical_capabilities",
        "freyja2_execution_contexts",
    }
)

# Tables that must no longer exist at all as of
# 0012_remove_regulatory_engine (POINT1-CAPABILITY-API-CORRECTION-001) —
# Freyja does not maintain an internal regulatory-eligibility engine; the
# connected broker is the sole authority over availability/permissions.
_REMOVED_REGULATORY_TABLES = frozenset(
    {
        "freyja2_regulatory_rules",
        "freyja2_execution_context_regulatory_rules",
    }
)

# Unambiguously fictitious fixtures — no real broker, exchange, or owner is
# named or seeded anywhere in this task.
_TEST_VENUE_CODE = "TEST_CAP_EXCHANGE"
_TEST_SOURCE_CODE = "TEST_CAP_MARKET_DATA"
_TEST_ACCOUNT_1 = "TEST_ACCOUNT_1"
_TEST_ACCOUNT_2 = "TEST_ACCOUNT_2"
_BLANK_OR_PADDED = ["", "   ", " X", "X "]


@pytest.fixture(autouse=True)
def _truncate_capability_tables(auth_test_engine: Engine) -> None:
    with auth_test_engine.connect() as connection:
        connection.execute(
            text(
                "TRUNCATE "
                "freyja2_execution_contexts, freyja2_technical_capabilities, "
                "freyja2_venues, freyja2_data_sources "
                "RESTART IDENTITY CASCADE"
            )
        )
        connection.commit()


def _seeded_instrument_id(
    session: Session, market_code: str, product_code: str, symbol: str
) -> uuid.UUID:
    row = session.execute(
        text(
            "SELECT i.instrument_id FROM freyja2_instruments i "
            "JOIN freyja2_underlying_markets m ON m.id = i.underlying_market_id "
            "JOIN freyja2_product_types p ON p.id = i.product_type_id "
            "WHERE m.code = :market_code AND p.code = :product_code "
            "AND i.canonical_symbol = :symbol"
        ),
        {"market_code": market_code, "product_code": product_code, "symbol": symbol},
    ).scalar_one()
    return uuid.UUID(str(row))


def _seeded_timeframe_id(session: Session, code: str) -> uuid.UUID:
    row = session.execute(
        text("SELECT id FROM freyja2_timeframes WHERE code = :code"), {"code": code}
    ).scalar_one()
    return uuid.UUID(str(row))


def _seeded_product_type_id(session: Session, code: str) -> uuid.UUID:
    row = session.execute(
        text("SELECT id FROM freyja2_product_types WHERE code = :code"), {"code": code}
    ).scalar_one()
    return uuid.UUID(str(row))


def _make_venue(session: Session, code: str = _TEST_VENUE_CODE) -> Venue:
    venue = Venue(code=code, display_name=code.title(), venue_type=VenueType.EXCHANGE)
    session.add(venue)
    session.flush()
    return venue


def _make_data_source(session: Session, code: str = _TEST_SOURCE_CODE) -> DataSource:
    source = DataSource(
        code=code, display_name=code.title(), source_type=DataSourceType.MARKET_DATA
    )
    session.add(source)
    session.flush()
    return source


def _make_owner(session: Session, identifier: str) -> AuthUser:
    owner = AuthUser(
        identifier=identifier,
        password_hash="$argon2id$v=19$m=19456,t=2,p=1$testsalt$testhash",
        created_via=UserOrigin.SELF_REGISTRATION,
    )
    session.add(owner)
    session.flush()
    return owner


def _make_capability(
    session: Session,
    *,
    instrument_id: uuid.UUID,
    timeframe_id: uuid.UUID,
    venue_id: uuid.UUID | None = None,
    data_source_id: uuid.UUID | None = None,
    **overrides: object,
) -> TechnicalCapability:
    # A DataSource never executes or settles anything (POINT1-PROVIDER-001):
    # default the three execution/settlement dimensions to NOT_APPLICABLE
    # whenever data_source_id is used, unless the caller overrides them
    # explicitly (e.g. to exercise the negative/rejection path).
    if data_source_id is not None:
        overrides.setdefault("demo_execution_status", CapabilityStatus.NOT_APPLICABLE)
        overrides.setdefault("real_execution_status", CapabilityStatus.NOT_APPLICABLE)
        overrides.setdefault("settlement_status", CapabilityStatus.NOT_APPLICABLE)

    capability = TechnicalCapability(
        instrument_id=instrument_id,
        venue_id=venue_id,
        data_source_id=data_source_id,
        timeframe_id=timeframe_id,
        **overrides,
    )
    session.add(capability)
    session.flush()
    return capability


def _enabled_context_kwargs() -> dict[str, Any]:
    return {
        "credentials_status": CredentialsStatus.CONFIGURED,
        "venue_permission_status": VenuePermissionStatus.GRANTED,
        "owner_authorization_status": OwnerAuthorizationStatus.AUTHORIZED,
        "activation_status": ActivationStatus.ENABLED,
    }


def _execution_context_kwargs(
    session: Session,
    *,
    owner: AuthUser,
    venue: Venue,
    product_type_id: uuid.UUID | None = None,
    account_key: str = _TEST_ACCOUNT_1,
    environment: ExecutionEnvironment = ExecutionEnvironment.DEMO,
    **overrides: object,
) -> dict[str, object]:
    """Builds a fully-valid ExecutionContext constructor kwargs dict, so each
    test can override exactly the one field it means to test (e.g.
    account_key=invalid_value) without every other required column also
    being missing/invalid and masking which constraint actually fired."""
    resolved_product_type_id = (
        product_type_id if product_type_id is not None else _seeded_product_type_id(session, "SPOT")
    )
    kwargs: dict[str, object] = {
        "owner_id": owner.id,
        "venue_id": venue.id,
        "account_key": account_key,
        "execution_environment": environment,
        "product_type_id": resolved_product_type_id,
    }
    kwargs.update(overrides)
    return kwargs


def _make_execution_context(
    session: Session,
    *,
    owner: AuthUser,
    venue: Venue,
    product_type_id: uuid.UUID | None = None,
    account_key: str = _TEST_ACCOUNT_1,
    environment: ExecutionEnvironment = ExecutionEnvironment.DEMO,
    **overrides: object,
) -> ExecutionContext:
    context = ExecutionContext(
        **_execution_context_kwargs(
            session,
            owner=owner,
            venue=venue,
            product_type_id=product_type_id,
            account_key=account_key,
            environment=environment,
            **overrides,
        )
    )
    session.add(context)
    session.flush()
    return context


# --- Schema shape right after migration -------------------------------------


def test_new_tables_are_empty_after_migration(auth_test_engine: Engine) -> None:
    with auth_test_engine.connect() as connection:
        for table in _CAPABILITY_TABLES:
            count = connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            assert count == 0, f"{table} must be empty — 0011 creates schema only, never data"


def test_regulatory_tables_no_longer_exist_at_head(auth_test_engine: Engine) -> None:
    """POINT1-CAPABILITY-API-CORRECTION-001: freyja2_regulatory_rules and
    freyja2_execution_context_regulatory_rules were dropped by
    0012_remove_regulatory_engine — Freyja does not maintain an internal
    regulatory-eligibility engine; the connected broker is the sole
    authority over availability/permissions."""
    inspector = inspect(auth_test_engine)
    existing_table_names = set(inspector.get_table_names())
    for table in _REMOVED_REGULATORY_TABLES:
        assert table not in existing_table_names, f"{table} must not exist at head"


def test_orm_does_not_export_regulatory_entities() -> None:
    """The ORM package must not export RegulatoryRule, RegulatoryRuleEffect,
    RegulatoryEligibilityStatus, or ExecutionContextRegulatoryRule — a
    consumer importing these by name gets an ImportError, not a stale
    class bound to a table that no longer exists."""
    import freyja_backend.db.models as models_package
    import freyja_backend.db.models.capability as capability_module

    for removed_name in (
        "RegulatoryRule",
        "RegulatoryRuleEffect",
        "RegulatoryEligibilityStatus",
        "ExecutionContextRegulatoryRule",
    ):
        assert not hasattr(capability_module, removed_name), (
            f"freyja_backend.db.models.capability must not export {removed_name!r}"
        )
        assert not hasattr(models_package, removed_name), (
            f"freyja_backend.db.models must not export {removed_name!r}"
        )
        assert removed_name not in models_package.__all__


def test_capability_table_has_no_activation_or_eligibility_columns(
    auth_test_engine: Engine,
) -> None:
    inspector = inspect(auth_test_engine)
    columns = {c["name"] for c in inspector.get_columns("freyja2_technical_capabilities")}
    for forbidden in ("activation_status", "credentials_status", "owner_id"):
        assert forbidden not in columns


def test_execution_context_has_no_technical_capability_or_regulatory_columns(
    auth_test_engine: Engine,
) -> None:
    inspector = inspect(auth_test_engine)
    columns = {c["name"] for c in inspector.get_columns("freyja2_execution_contexts")}
    for forbidden in (
        "market_data_status",
        "signal_detection_status",
        "backtest_status",
        "demo_execution_status",
        "real_execution_status",
        "settlement_status",
        "jurisdiction",
        "client_classification",
        "regulatory_eligibility_status",
    ):
        assert forbidden not in columns


def test_instrument_table_has_no_new_operational_columns(auth_test_engine: Engine) -> None:
    """POINT1-CAPABILITY-001 must never add activation_status, jurisdiction,
    or DEMO/REAL to freyja2_instruments."""
    inspector = inspect(auth_test_engine)
    columns = {c["name"] for c in inspector.get_columns("freyja2_instruments")}
    for forbidden in (
        "activation_status",
        "jurisdiction",
        "execution_environment",
        "credentials_status",
    ):
        assert forbidden not in columns


_FORBIDDEN_SECRET_SUBSTRINGS = ("password", "secret", "token", "api_key", "apikey")


def test_no_new_table_has_secret_shaped_columns(auth_test_engine: Engine) -> None:
    """Covers account_key too: it is an opaque internal bookkeeping key,
    never a credential/token/API key, and must never trip this check."""
    inspector = inspect(auth_test_engine)
    for table in _CAPABILITY_TABLES:
        for column in inspector.get_columns(table):
            column_name = column["name"].lower()
            for forbidden in _FORBIDDEN_SECRET_SUBSTRINGS:
                assert forbidden not in column_name, (
                    f"{table}.{column['name']} looks like a secret-shaped column "
                    f"(matches {forbidden!r}) — forbidden by POINT1-CAPABILITY-001"
                )


# --- TechnicalCapability: exactly one provider axis -------------------------


def test_technical_capability_requires_exactly_one_provider_axis(db_session: Session) -> None:
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")

    db_session.add(
        TechnicalCapability(
            instrument_id=instrument_id,
            timeframe_id=timeframe_id,
            venue_id=None,
            data_source_id=None,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    venue = _make_venue(db_session)
    source = _make_data_source(db_session)
    db_session.add(
        TechnicalCapability(
            instrument_id=instrument_id,
            timeframe_id=timeframe_id,
            venue_id=venue.id,
            data_source_id=source.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# --- Block 4: DataSource vs Venue capability coherence ----------------------


def test_technical_capability_accepts_data_source_axis(db_session: Session) -> None:
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    source = _make_data_source(db_session)

    capability = _make_capability(
        db_session, instrument_id=instrument_id, timeframe_id=timeframe_id, data_source_id=source.id
    )
    db_session.refresh(capability)
    assert capability.venue_id is None
    assert capability.demo_execution_status == CapabilityStatus.NOT_APPLICABLE
    assert capability.real_execution_status == CapabilityStatus.NOT_APPLICABLE
    assert capability.settlement_status == CapabilityStatus.NOT_APPLICABLE


@pytest.mark.parametrize(
    "field", ["demo_execution_status", "real_execution_status", "settlement_status"]
)
def test_data_source_capability_rejects_non_not_applicable_execution_or_settlement(
    db_session: Session, field: str
) -> None:
    """A DataSource is market-data-only (POINT1-PROVIDER-001): it never
    executes or settles anything, so PostgreSQL itself must reject any of
    these three dimensions being anything other than NOT_APPLICABLE."""
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    source = _make_data_source(db_session)

    db_session.add(_capability_with_one_field_broken(instrument_id, timeframe_id, source.id, field))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def _capability_with_one_field_broken(
    instrument_id: uuid.UUID, timeframe_id: uuid.UUID, data_source_id: uuid.UUID, broken_field: str
) -> TechnicalCapability:
    fields = {
        "demo_execution_status": CapabilityStatus.NOT_APPLICABLE,
        "real_execution_status": CapabilityStatus.NOT_APPLICABLE,
        "settlement_status": CapabilityStatus.NOT_APPLICABLE,
    }
    fields[broken_field] = CapabilityStatus.NOT_EVALUATED
    return TechnicalCapability(
        instrument_id=instrument_id,
        timeframe_id=timeframe_id,
        data_source_id=data_source_id,
        **fields,
    )


def test_not_applicable_distinct_from_not_evaluated_and_not_supported(
    db_session: Session,
) -> None:
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    venue = _make_venue(db_session)

    capability = _make_capability(
        db_session,
        instrument_id=instrument_id,
        timeframe_id=timeframe_id,
        venue_id=venue.id,
        real_execution_status=CapabilityStatus.NOT_EVALUATED,
    )
    db_session.refresh(capability)
    assert capability.real_execution_status != CapabilityStatus.NOT_APPLICABLE
    assert capability.real_execution_status == CapabilityStatus.NOT_EVALUATED


# --- Capability status semantics: absence of evidence is never SUPPORTED ---


def test_technical_capability_defaults_to_not_evaluated(db_session: Session) -> None:
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    venue = _make_venue(db_session)

    capability = _make_capability(
        db_session, instrument_id=instrument_id, timeframe_id=timeframe_id, venue_id=venue.id
    )
    db_session.refresh(capability)

    assert capability.market_data_status == CapabilityStatus.NOT_EVALUATED
    assert capability.signal_detection_status == CapabilityStatus.NOT_EVALUATED
    assert capability.backtest_status == CapabilityStatus.NOT_EVALUATED
    assert capability.demo_execution_status == CapabilityStatus.NOT_EVALUATED
    assert capability.real_execution_status == CapabilityStatus.NOT_EVALUATED
    assert capability.settlement_status == CapabilityStatus.NOT_EVALUATED


def test_not_implemented_and_not_evaluated_are_distinguishable(db_session: Session) -> None:
    """NOT_IMPLEMENTED (Freyja hasn't built this yet, e.g. backtesting before
    POINT15) must remain distinguishable from NOT_EVALUATED (could exist,
    no evidence gathered) — never collapsed into one flag."""
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    venue = _make_venue(db_session)

    capability = _make_capability(
        db_session,
        instrument_id=instrument_id,
        timeframe_id=timeframe_id,
        venue_id=venue.id,
        backtest_status=CapabilityStatus.NOT_IMPLEMENTED,
        market_data_status=CapabilityStatus.NOT_EVALUATED,
    )
    db_session.refresh(capability)
    assert capability.backtest_status == CapabilityStatus.NOT_IMPLEMENTED
    assert capability.market_data_status == CapabilityStatus.NOT_EVALUATED


# --- Block 6: bidirectional reason_unavailable coherence --------------------


def test_reason_unavailable_required_when_any_status_not_supported(db_session: Session) -> None:
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    venue = _make_venue(db_session)

    db_session.add(
        TechnicalCapability(
            instrument_id=instrument_id,
            timeframe_id=timeframe_id,
            venue_id=venue.id,
            real_execution_status=CapabilityStatus.NOT_SUPPORTED,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    venue2 = _make_venue(db_session, "TEST_CAP_EXCHANGE_2")
    capability = _make_capability(
        db_session,
        instrument_id=instrument_id,
        timeframe_id=timeframe_id,
        venue_id=venue2.id,
        real_execution_status=CapabilityStatus.NOT_SUPPORTED,
        reason_unavailable="Fixture: venue does not offer real execution for this instrument.",
    )
    assert capability.reason_unavailable is not None


def test_reason_unavailable_forbidden_when_nothing_not_supported(db_session: Session) -> None:
    """The converse of the rule above: NOT_IMPLEMENTED, NOT_EVALUATED, and
    NOT_APPLICABLE never justify a reason_unavailable by themselves."""
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    venue = _make_venue(db_session)

    db_session.add(
        TechnicalCapability(
            instrument_id=instrument_id,
            timeframe_id=timeframe_id,
            venue_id=venue.id,
            backtest_status=CapabilityStatus.NOT_IMPLEMENTED,
            reason_unavailable="This should not be allowed without a NOT_SUPPORTED dimension.",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("invalid_reason", ["", "   "])
def test_reason_unavailable_rejects_blank_when_required(
    db_session: Session, invalid_reason: str
) -> None:
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    venue = _make_venue(db_session)

    db_session.add(
        TechnicalCapability(
            instrument_id=instrument_id,
            timeframe_id=timeframe_id,
            venue_id=venue.id,
            real_execution_status=CapabilityStatus.NOT_SUPPORTED,
            reason_unavailable=invalid_reason,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("padded_reason", [" padded reason", "padded reason "])
def test_reason_unavailable_rejects_padded_when_required(
    db_session: Session, padded_reason: str
) -> None:
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    venue = _make_venue(db_session)

    db_session.add(
        TechnicalCapability(
            instrument_id=instrument_id,
            timeframe_id=timeframe_id,
            venue_id=venue.id,
            real_execution_status=CapabilityStatus.NOT_SUPPORTED,
            reason_unavailable=padded_reason,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# --- Valid vigencia windows, reject impossible intervals --------------------


def test_technical_capability_rejects_impossible_effective_window(db_session: Session) -> None:
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    venue = _make_venue(db_session)
    now = datetime.now(UTC)

    db_session.add(
        TechnicalCapability(
            instrument_id=instrument_id,
            timeframe_id=timeframe_id,
            venue_id=venue.id,
            effective_from=now,
            effective_to=now - timedelta(days=1),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_technical_capability_allows_versioned_history_but_only_one_open_row(
    db_session: Session,
) -> None:
    """Proves the partial-unique-index reasoning: a closed (historical) row
    and a currently-open row for the SAME combination may coexist, but two
    open rows for the same combination collide."""
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    venue = _make_venue(db_session)
    earlier = datetime.now(UTC) - timedelta(days=30)
    closed_end = datetime.now(UTC) - timedelta(days=1)

    _make_capability(
        db_session,
        instrument_id=instrument_id,
        timeframe_id=timeframe_id,
        venue_id=venue.id,
        effective_from=earlier,
        effective_to=closed_end,
    )
    _make_capability(
        db_session, instrument_id=instrument_id, timeframe_id=timeframe_id, venue_id=venue.id
    )

    db_session.add(
        TechnicalCapability(
            instrument_id=instrument_id, timeframe_id=timeframe_id, venue_id=venue.id
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# --- Blank/padded rejection, invalid enum values ----------------------------


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_execution_context_account_key_rejects_blank_or_padded(
    db_session: Session, invalid_value: str
) -> None:
    owner = _make_owner(db_session, "owner-bad-account-key@example.test")
    venue = _make_venue(db_session)

    db_session.add(
        ExecutionContext(
            **_execution_context_kwargs(
                db_session, owner=owner, venue=venue, account_key=invalid_value
            )
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_invalid_activation_status_value_is_rejected_by_the_database(
    db_session: Session,
) -> None:
    owner = _make_owner(db_session, "owner-invalid-enum@example.test")
    venue = _make_venue(db_session)
    product_type_id = _seeded_product_type_id(db_session, "SPOT")

    with pytest.raises(DBAPIError):
        db_session.execute(
            text(
                "INSERT INTO freyja2_execution_contexts "
                "(id, owner_id, venue_id, account_key, execution_environment, product_type_id, "
                "activation_status) "
                "VALUES (:id, :owner_id, :venue_id, :account_key, 'DEMO', :product_type_id, "
                "'HACKED_STATUS')"
            ),
            {
                "id": uuid.uuid4(),
                "owner_id": owner.id,
                "venue_id": venue.id,
                "account_key": _TEST_ACCOUNT_1,
                "product_type_id": product_type_id,
            },
        )
    db_session.rollback()


# --- No contradictory ENABLED/SUSPENDED declarations ------------------------


def test_enabled_requires_all_three_positive_substatuses(db_session: Session) -> None:
    owner = _make_owner(db_session, "owner-partial-enabled@example.test")
    venue = _make_venue(db_session)

    kwargs = _enabled_context_kwargs()
    kwargs["venue_permission_status"] = VenuePermissionStatus.DENIED  # one negative dimension

    db_session.add(
        ExecutionContext(
            **_execution_context_kwargs(
                db_session,
                owner=owner,
                venue=venue,
                environment=ExecutionEnvironment.REAL,
                **kwargs,
            )
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize(
    "case_id,blocking_field,blocking_value",
    [
        ("credentials", "credentials_status", CredentialsStatus.NOT_CONFIGURED),
        ("denied", "venue_permission_status", VenuePermissionStatus.DENIED),
        ("not-evaluated", "venue_permission_status", VenuePermissionStatus.NOT_EVALUATED),
        ("owner-auth", "owner_authorization_status", OwnerAuthorizationStatus.NOT_AUTHORIZED),
    ],
)
def test_enabled_is_blocked_by_each_substatus_individually_including_defaults(
    db_session: Session, case_id: str, blocking_field: str, blocking_value: object
) -> None:
    """Beyond the single DENIED case above, this parametrizes across every
    substatus, including the DEFAULT NOT_EVALUATED broker-permission state —
    proving an unevaluated/unknown broker response is never silently treated
    as GRANTED, exactly like a missing credential or missing user
    authorization blocks ENABLED."""
    owner = _make_owner(db_session, f"owner-blocked-{case_id}@example.test")
    venue = _make_venue(db_session)

    kwargs = _enabled_context_kwargs()
    kwargs[blocking_field] = blocking_value

    db_session.add(
        ExecutionContext(
            **_execution_context_kwargs(
                db_session,
                owner=owner,
                venue=venue,
                environment=ExecutionEnvironment.REAL,
                **kwargs,
            )
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_enabled_succeeds_when_all_three_substatuses_are_positive(db_session: Session) -> None:
    owner = _make_owner(db_session, "owner-fully-enabled@example.test")
    venue = _make_venue(db_session)

    context = _make_execution_context(
        db_session,
        owner=owner,
        venue=venue,
        environment=ExecutionEnvironment.REAL,
        **_enabled_context_kwargs(),
    )
    db_session.refresh(context)
    assert context.activation_status == ActivationStatus.ENABLED


def test_suspended_requires_nonempty_suspension_reasons(db_session: Session) -> None:
    owner = _make_owner(db_session, "owner-suspended-no-reason@example.test")
    venue = _make_venue(db_session)

    db_session.add(
        ExecutionContext(
            **_execution_context_kwargs(
                db_session,
                owner=owner,
                venue=venue,
                environment=ExecutionEnvironment.REAL,
                activation_status=ActivationStatus.SUSPENDED,
                suspension_reasons=None,
            )
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_non_suspended_context_rejects_populated_suspension_reasons(
    db_session: Session,
) -> None:
    owner = _make_owner(db_session, "owner-contradictory-reasons@example.test")
    venue = _make_venue(db_session)

    db_session.add(
        ExecutionContext(
            **_execution_context_kwargs(
                db_session,
                owner=owner,
                venue=venue,
                environment=ExecutionEnvironment.REAL,
                activation_status=ActivationStatus.NOT_CONFIGURED,
                suspension_reasons=["This should not be allowed alongside NOT_CONFIGURED."],
            )
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# --- Block 5: strict suspension_reasons element validation ------------------


def test_suspension_reasons_rejects_null_element(db_session: Session) -> None:
    owner = _make_owner(db_session, "owner-null-reason@example.test")
    venue = _make_venue(db_session)

    db_session.add(
        ExecutionContext(
            **_execution_context_kwargs(
                db_session,
                owner=owner,
                venue=venue,
                environment=ExecutionEnvironment.REAL,
                activation_status=ActivationStatus.SUSPENDED,
                suspension_reasons=["valid reason", None],
            )
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("invalid_element", ["", "   "])
def test_suspension_reasons_rejects_blank_or_whitespace_element(
    db_session: Session, invalid_element: str
) -> None:
    owner = _make_owner(db_session, "owner-blank-reason@example.test")
    venue = _make_venue(db_session)

    db_session.add(
        ExecutionContext(
            **_execution_context_kwargs(
                db_session,
                owner=owner,
                venue=venue,
                environment=ExecutionEnvironment.REAL,
                activation_status=ActivationStatus.SUSPENDED,
                suspension_reasons=["valid reason", invalid_element],
            )
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("padded_element", [" padded reason", "padded reason "])
def test_suspension_reasons_rejects_padded_element(
    db_session: Session, padded_element: str
) -> None:
    owner = _make_owner(db_session, "owner-padded-reason@example.test")
    venue = _make_venue(db_session)

    db_session.add(
        ExecutionContext(
            **_execution_context_kwargs(
                db_session,
                owner=owner,
                venue=venue,
                environment=ExecutionEnvironment.REAL,
                activation_status=ActivationStatus.SUSPENDED,
                suspension_reasons=[padded_element],
            )
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_suspension_reasons_accepts_multiple_valid_reasons(db_session: Session) -> None:
    owner = _make_owner(db_session, "owner-valid-reasons@example.test")
    venue = _make_venue(db_session)

    context = _make_execution_context(
        db_session,
        owner=owner,
        venue=venue,
        environment=ExecutionEnvironment.REAL,
        activation_status=ActivationStatus.SUSPENDED,
        suspension_reasons=["reason one", "reason two", "reason three"],
    )
    db_session.refresh(context)
    assert context.suspension_reasons == ["reason one", "reason two", "reason three"]


# --- Block 1 & 2: account_key + product_type_id identity --------------------


def test_same_owner_can_have_two_accounts_at_same_venue_and_environment(
    db_session: Session,
) -> None:
    owner = _make_owner(db_session, "owner-two-accounts@example.test")
    venue = _make_venue(db_session)

    _make_execution_context(db_session, owner=owner, venue=venue, account_key=_TEST_ACCOUNT_1)
    _make_execution_context(db_session, owner=owner, venue=venue, account_key=_TEST_ACCOUNT_2)

    count = (
        db_session.query(ExecutionContext)
        .filter(ExecutionContext.owner_id == owner.id, ExecutionContext.venue_id == venue.id)
        .count()
    )
    assert count == 2


def test_same_account_can_have_independent_contexts_per_product(db_session: Session) -> None:
    owner = _make_owner(db_session, "owner-per-product@example.test")
    venue = _make_venue(db_session)
    spot_id = _seeded_product_type_id(db_session, "SPOT")
    binary_id = _seeded_product_type_id(db_session, "BINARY_OPTION")

    _make_execution_context(db_session, owner=owner, venue=venue, product_type_id=spot_id)
    _make_execution_context(db_session, owner=owner, venue=venue, product_type_id=binary_id)

    count = (
        db_session.query(ExecutionContext)
        .filter(
            ExecutionContext.owner_id == owner.id,
            ExecutionContext.venue_id == venue.id,
            ExecutionContext.account_key == _TEST_ACCOUNT_1,
        )
        .count()
    )
    assert count == 2


def test_duplicate_execution_context_identity_is_rejected(db_session: Session) -> None:
    owner = _make_owner(db_session, "owner-duplicate-identity@example.test")
    venue = _make_venue(db_session)

    _make_execution_context(db_session, owner=owner, venue=venue)

    db_session.add(
        ExecutionContext(**_execution_context_kwargs(db_session, owner=owner, venue=venue))
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_demo_and_real_are_independent_for_the_same_account_and_product(
    db_session: Session,
) -> None:
    owner = _make_owner(db_session, "owner-demo-and-real@example.test")
    venue = _make_venue(db_session)

    _make_execution_context(
        db_session, owner=owner, venue=venue, environment=ExecutionEnvironment.DEMO
    )
    _make_execution_context(
        db_session, owner=owner, venue=venue, environment=ExecutionEnvironment.REAL
    )

    count = (
        db_session.query(ExecutionContext)
        .filter(ExecutionContext.owner_id == owner.id, ExecutionContext.venue_id == venue.id)
        .count()
    )
    assert count == 2


def test_binary_option_real_suspended_does_not_affect_spot_real_for_same_account(
    db_session: Session,
) -> None:
    """The canonical scenario from the task spec: the SAME owner+venue+
    account has BINARY_OPTION REAL suspended while SPOT REAL is an entirely
    independent row — suspending one product never suspends another."""
    owner = _make_owner(db_session, "owner-binary-vs-spot@example.test")
    venue = _make_venue(db_session)
    spot_id = _seeded_product_type_id(db_session, "SPOT")
    binary_id = _seeded_product_type_id(db_session, "BINARY_OPTION")

    binary_context = _make_execution_context(
        db_session,
        owner=owner,
        venue=venue,
        product_type_id=binary_id,
        environment=ExecutionEnvironment.REAL,
        activation_status=ActivationStatus.SUSPENDED,
        suspension_reasons=["Fixture: broker denied venue permission for BINARY_OPTION."],
    )
    spot_context = _make_execution_context(
        db_session,
        owner=owner,
        venue=venue,
        product_type_id=spot_id,
        environment=ExecutionEnvironment.REAL,
    )

    db_session.refresh(binary_context)
    db_session.refresh(spot_context)
    assert binary_context.activation_status == ActivationStatus.SUSPENDED
    assert spot_context.activation_status == ActivationStatus.NOT_CONFIGURED


def test_suspended_context_does_not_affect_other_owners_or_capability(
    db_session: Session,
) -> None:
    venue = _make_venue(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")

    suspended_owner = _make_owner(db_session, "owner-suspended@example.test")
    _make_execution_context(
        db_session,
        owner=suspended_owner,
        venue=venue,
        environment=ExecutionEnvironment.REAL,
        activation_status=ActivationStatus.SUSPENDED,
        suspension_reasons=["Fixture: broker denied venue permission for this account."],
    )

    other_owner = _make_owner(db_session, "owner-unaffected@example.test")
    other_context = _make_execution_context(
        db_session,
        owner=other_owner,
        venue=venue,
        environment=ExecutionEnvironment.REAL,
        **_enabled_context_kwargs(),
    )
    db_session.refresh(other_context)
    assert other_context.activation_status == ActivationStatus.ENABLED

    # The venue's own TechnicalCapability is untouched by either owner's
    # ExecutionContext — suspension is per-account, never global.
    capability = _make_capability(
        db_session, instrument_id=instrument_id, timeframe_id=timeframe_id, venue_id=venue.id
    )
    assert capability.market_data_status == CapabilityStatus.NOT_EVALUATED


def test_multiple_owners_can_use_the_same_venue_without_collision(db_session: Session) -> None:
    venue = _make_venue(db_session)
    owner_a = _make_owner(db_session, "owner-a@example.test")
    owner_b = _make_owner(db_session, "owner-b@example.test")

    _make_execution_context(db_session, owner=owner_a, venue=venue)
    _make_execution_context(db_session, owner=owner_b, venue=venue)

    count = db_session.query(ExecutionContext).filter(ExecutionContext.venue_id == venue.id).count()
    assert count == 2


# --- Referential integrity, no CASCADE --------------------------------------


def test_fk_prevents_deleting_a_referenced_owner(db_session: Session) -> None:
    owner = _make_owner(db_session, "owner-protected@example.test")
    venue = _make_venue(db_session)
    _make_execution_context(db_session, owner=owner, venue=venue)

    with pytest.raises(IntegrityError):
        db_session.execute(text("DELETE FROM auth_users WHERE id = :id"), {"id": owner.id})
        db_session.flush()
    db_session.rollback()


def test_fk_prevents_deleting_a_venue_referenced_by_execution_context(
    db_session: Session,
) -> None:
    owner = _make_owner(db_session, "owner-venue-protected@example.test")
    venue = _make_venue(db_session)
    _make_execution_context(db_session, owner=owner, venue=venue)

    with pytest.raises(IntegrityError):
        db_session.execute(text("DELETE FROM freyja2_venues WHERE id = :id"), {"id": venue.id})
        db_session.flush()
    db_session.rollback()


def test_fk_prevents_deleting_a_product_type_referenced_by_execution_context(
    db_session: Session,
) -> None:
    owner = _make_owner(db_session, "owner-product-protected@example.test")
    venue = _make_venue(db_session)
    spot_id = _seeded_product_type_id(db_session, "SPOT")
    _make_execution_context(db_session, owner=owner, venue=venue, product_type_id=spot_id)

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("DELETE FROM freyja2_product_types WHERE id = :id"), {"id": spot_id}
        )
        db_session.flush()
    db_session.rollback()


def test_fk_prevents_deleting_an_instrument_referenced_by_technical_capability(
    db_session: Session,
) -> None:
    venue = _make_venue(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "ETH/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "5m")
    _make_capability(
        db_session, instrument_id=instrument_id, timeframe_id=timeframe_id, venue_id=venue.id
    )

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("DELETE FROM freyja2_instruments WHERE instrument_id = :id"),
            {"id": instrument_id},
        )
        db_session.flush()
    db_session.rollback()


def test_fk_prevents_deleting_a_timeframe_referenced_by_technical_capability(
    db_session: Session,
) -> None:
    venue = _make_venue(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "ETH/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "15m")
    _make_capability(
        db_session, instrument_id=instrument_id, timeframe_id=timeframe_id, venue_id=venue.id
    )

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("DELETE FROM freyja2_timeframes WHERE id = :id"), {"id": timeframe_id}
        )
        db_session.flush()
    db_session.rollback()


# --- POINT1-TEST-001: capability-layer analog of the architectural case ----
# (SPOT vs BINARY_OPTION on the same symbol text getting independent
# TechnicalCapability rows) -- uses its own throwaway database, never the
# shared auth_test_engine/db_session, so the temporary BINARY_OPTION
# instrument never touches the approved v1 seed.


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture
def isolated_seeded_database() -> Iterator[Engine]:
    settings = get_postgres_settings()
    admin_url = settings.url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    db_name = f"freyja_test_{uuid.uuid4().hex[:12]}"

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{db_name}"'))

    try:
        temp_url = settings.url.set(database=db_name)
        cfg = _alembic_config()
        cfg.attributes["database_url"] = temp_url
        command.upgrade(cfg, "head")

        engine = create_engine(temp_url)
        try:
            yield engine
        finally:
            engine.dispose()
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db_name AND pid <> pg_backend_pid()"
                ),
                {"db_name": db_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin_engine.dispose()


def test_spot_and_binary_option_on_same_symbol_get_independent_capability_rows(
    isolated_seeded_database: Engine,
) -> None:
    """CRYPTO x SPOT x BTC/USDT and CRYPTO x BINARY_OPTION x BTC/USDT are
    distinct canonical instruments sharing symbol text (test_catalog_provider.
    py proves this at the catalog/provider layer) — this proves the same
    independence one layer up: each gets its own TechnicalCapability row,
    and a status change on one never touches the other."""
    engine = isolated_seeded_database
    with engine.begin() as connection:
        crypto_market_id = connection.execute(
            text("SELECT id FROM freyja2_underlying_markets WHERE code = 'CRYPTO'")
        ).scalar_one()
        spot_product_id = connection.execute(
            text("SELECT id FROM freyja2_product_types WHERE code = 'SPOT'")
        ).scalar_one()
        binary_product_id = connection.execute(
            text("SELECT id FROM freyja2_product_types WHERE code = 'BINARY_OPTION'")
        ).scalar_one()
        spot_btc_usdt_id = connection.execute(
            text(
                "SELECT instrument_id FROM freyja2_instruments "
                "WHERE underlying_market_id = :market_id AND product_type_id = :product_id "
                "AND canonical_symbol = 'BTC/USDT'"
            ),
            {"market_id": crypto_market_id, "product_id": spot_product_id},
        ).scalar_one()
        one_minute_id = connection.execute(
            text("SELECT id FROM freyja2_timeframes WHERE code = '1m'")
        ).scalar_one()

        binary_instrument_id = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO freyja2_instruments "
                "(instrument_id, underlying_market_id, product_type_id, canonical_symbol, "
                "underlying_instrument_id, is_active) "
                "VALUES (:id, :market_id, :product_id, 'BTC/USDT', :underlying, true)"
            ),
            {
                "id": binary_instrument_id,
                "market_id": crypto_market_id,
                "product_id": binary_product_id,
                "underlying": spot_btc_usdt_id,
            },
        )

        venue_id = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO freyja2_venues (id, code, display_name, venue_type, is_active) "
                "VALUES (:id, 'TEST_CAP_ARCH_VENUE', 'Test Venue', 'EXCHANGE', true)"
            ),
            {"id": venue_id},
        )

        spot_capability_id = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO freyja2_technical_capabilities "
                "(id, instrument_id, venue_id, timeframe_id, market_data_status, "
                "signal_detection_status, backtest_status, demo_execution_status, "
                "real_execution_status, settlement_status, effective_from) "
                "VALUES (:id, :instrument_id, :venue_id, :timeframe_id, 'SUPPORTED', "
                "'NOT_EVALUATED', 'NOT_EVALUATED', 'NOT_EVALUATED', 'NOT_EVALUATED', "
                "'NOT_APPLICABLE', now())"
            ),
            {
                "id": spot_capability_id,
                "instrument_id": spot_btc_usdt_id,
                "venue_id": venue_id,
                "timeframe_id": one_minute_id,
            },
        )
        binary_capability_id = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO freyja2_technical_capabilities "
                "(id, instrument_id, venue_id, timeframe_id, market_data_status, "
                "signal_detection_status, backtest_status, demo_execution_status, "
                "real_execution_status, settlement_status, reason_unavailable, "
                "effective_from) "
                "VALUES (:id, :instrument_id, :venue_id, :timeframe_id, 'NOT_SUPPORTED', "
                "'NOT_EVALUATED', 'NOT_EVALUATED', 'NOT_APPLICABLE', 'NOT_APPLICABLE', "
                "'NOT_APPLICABLE', :reason, now())"
            ),
            {
                "id": binary_capability_id,
                "instrument_id": binary_instrument_id,
                "venue_id": venue_id,
                "timeframe_id": one_minute_id,
                "reason": "TEST fixture reason — not real supportability evidence",
            },
        )

        spot_status = connection.execute(
            text("SELECT market_data_status FROM freyja2_technical_capabilities WHERE id = :id"),
            {"id": spot_capability_id},
        ).scalar_one()
        binary_status = connection.execute(
            text("SELECT market_data_status FROM freyja2_technical_capabilities WHERE id = :id"),
            {"id": binary_capability_id},
        ).scalar_one()

    assert spot_status == "SUPPORTED"
    assert binary_status == "NOT_SUPPORTED"


# --- POINT1-CAPABILITY-API-CORRECTION-001: broker-authority guarantees -----


def test_supported_capability_without_any_execution_context_grants_no_authorization(
    db_session: Session,
) -> None:
    """A TechnicalCapability row expresses what the venue/Freyja can
    technically do — it never creates, implies, or substitutes for an
    ExecutionContext, and it is not the broker's permission either. Marking
    real_execution_status SUPPORTED must not leave any owner authorized to
    trade absent an actual ExecutionContext row with a GRANTED broker
    permission and an AUTHORIZED user."""
    venue = _make_venue(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")

    capability = _make_capability(
        db_session,
        instrument_id=instrument_id,
        timeframe_id=timeframe_id,
        venue_id=venue.id,
        market_data_status=CapabilityStatus.SUPPORTED,
        signal_detection_status=CapabilityStatus.SUPPORTED,
        backtest_status=CapabilityStatus.SUPPORTED,
        demo_execution_status=CapabilityStatus.SUPPORTED,
        real_execution_status=CapabilityStatus.SUPPORTED,
    )
    assert capability.real_execution_status == CapabilityStatus.SUPPORTED

    context_count = (
        db_session.query(ExecutionContext).filter(ExecutionContext.venue_id == venue.id).count()
    )
    assert context_count == 0, (
        "a fully SUPPORTED capability must not create or imply any "
        "ExecutionContext — technical support is never broker permission or "
        "user authorization"
    )


# --- POINT1-TEST-001: broader forbidden-column guard for capability tables --


_FORBIDDEN_OPERATIONAL_SUBSTRINGS = (
    "balance",
    "order",
    "position",
    "credential",
    "fill",
    "pnl",
)


def test_capability_tables_have_no_account_balance_order_or_position_columns(
    auth_test_engine: Engine,
) -> None:
    """Broader than test_no_new_table_has_secret_shaped_columns (secrets
    only) — this guards against operational/trading state (balances,
    orders, positions) leaking into what must remain pure capability/
    eligibility/activation bookkeeping. account_key/execution_environment/
    demo_execution_status/real_execution_status are legitimate columns here
    and must never trip this check, hence the narrower substring list vs.
    test_catalog_provider.py's _FORBIDDEN_COLUMN_SUBSTRINGS. Columns ending
    in _status are exempt from this check (e.g. credentials_status) — they
    only ever carry an enum tag, never the credential/balance/order value
    itself."""
    inspector = inspect(auth_test_engine)
    for table in _CAPABILITY_TABLES:
        for column in inspector.get_columns(table):
            column_name = column["name"].lower()
            if column_name.endswith("_status"):
                continue
            for forbidden in _FORBIDDEN_OPERATIONAL_SUBSTRINGS:
                assert forbidden not in column_name, (
                    f"{table}.{column['name']} looks like operational trading state "
                    f"(matches {forbidden!r}) — forbidden by POINT1-CAPABILITY-001"
                )


def test_absence_of_execution_context_never_implies_authorization(db_session: Session) -> None:
    """An owner with zero ExecutionContext rows for a venue has no
    authorization state at all — never an implicit ENABLED/authorized
    default. Absence of a row is absence of permission, not a fallback
    granted state."""
    owner = _make_owner(db_session, "owner-no-context-at-all@example.test")
    venue = _make_venue(db_session)

    count = (
        db_session.query(ExecutionContext)
        .filter(ExecutionContext.owner_id == owner.id, ExecutionContext.venue_id == venue.id)
        .count()
    )
    assert count == 0


def test_changing_broker_permission_never_mutates_instrument_or_capability(
    db_session: Session,
) -> None:
    """venue_permission_status is normalized from the broker's own response
    (POINT1-CAPABILITY-API-CORRECTION-001) — updating it on an
    ExecutionContext must never mutate the referenced Instrument or any
    TechnicalCapability row."""
    venue = _make_venue(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")

    db_session.add(
        VenueInstrument(
            venue_id=venue.id, instrument_id=instrument_id, provider_symbol="TEST_BROKER_PERM_BTC"
        )
    )
    db_session.flush()

    capability = _make_capability(
        db_session,
        instrument_id=instrument_id,
        timeframe_id=timeframe_id,
        venue_id=venue.id,
        market_data_status=CapabilityStatus.SUPPORTED,
    )

    owner = _make_owner(db_session, "owner-broker-permission-change@example.test")
    context = _make_execution_context(db_session, owner=owner, venue=venue)

    before_instrument = (
        db_session.execute(
            text("SELECT * FROM freyja2_instruments WHERE instrument_id = :id"),
            {"id": instrument_id},
        )
        .mappings()
        .one()
    )
    before_venue_instrument = (
        db_session.execute(
            text(
                "SELECT * FROM freyja2_venue_instruments "
                "WHERE venue_id = :venue_id AND instrument_id = :instrument_id"
            ),
            {"venue_id": venue.id, "instrument_id": instrument_id},
        )
        .mappings()
        .one()
    )
    before_capability = (
        db_session.execute(
            text("SELECT * FROM freyja2_technical_capabilities WHERE id = :id"),
            {"id": capability.id},
        )
        .mappings()
        .one()
    )

    # Simulate the broker denying permission after a prior GRANT.
    context.venue_permission_status = VenuePermissionStatus.DENIED
    context.activation_status = ActivationStatus.SUSPENDED
    context.suspension_reasons = ["Fixture: broker revoked venue permission for this account."]
    db_session.flush()

    after_instrument = (
        db_session.execute(
            text("SELECT * FROM freyja2_instruments WHERE instrument_id = :id"),
            {"id": instrument_id},
        )
        .mappings()
        .one()
    )
    after_venue_instrument = (
        db_session.execute(
            text(
                "SELECT * FROM freyja2_venue_instruments "
                "WHERE venue_id = :venue_id AND instrument_id = :instrument_id"
            ),
            {"venue_id": venue.id, "instrument_id": instrument_id},
        )
        .mappings()
        .one()
    )
    after_capability = (
        db_session.execute(
            text("SELECT * FROM freyja2_technical_capabilities WHERE id = :id"),
            {"id": capability.id},
        )
        .mappings()
        .one()
    )

    assert dict(after_instrument) == dict(before_instrument)
    assert dict(after_venue_instrument) == dict(before_venue_instrument)
    assert dict(after_capability) == dict(before_capability)


def test_demo_and_real_can_have_independent_credentials_and_broker_permission(
    db_session: Session,
) -> None:
    """DEMO and REAL share the same domain/catalog/business rules (one
    table, two rows) but never share account/credentials/broker-permission
    state — each row's credentials_status and venue_permission_status are
    fully independent, even for the same owner+venue+account+product."""
    owner = _make_owner(db_session, "owner-demo-real-independent@example.test")
    venue = _make_venue(db_session)

    demo_context = _make_execution_context(
        db_session,
        owner=owner,
        venue=venue,
        environment=ExecutionEnvironment.DEMO,
        credentials_status=CredentialsStatus.CONFIGURED,
        venue_permission_status=VenuePermissionStatus.GRANTED,
    )
    real_context = _make_execution_context(
        db_session,
        owner=owner,
        venue=venue,
        environment=ExecutionEnvironment.REAL,
        credentials_status=CredentialsStatus.NOT_CONFIGURED,
        venue_permission_status=VenuePermissionStatus.NOT_EVALUATED,
    )

    db_session.refresh(demo_context)
    db_session.refresh(real_context)
    assert demo_context.credentials_status == CredentialsStatus.CONFIGURED
    assert demo_context.venue_permission_status == VenuePermissionStatus.GRANTED
    assert real_context.credentials_status == CredentialsStatus.NOT_CONFIGURED
    assert real_context.venue_permission_status == VenuePermissionStatus.NOT_EVALUATED
