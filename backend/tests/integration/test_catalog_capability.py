import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from freyja_backend.db.models.auth import AuthUser, UserOrigin
from freyja_backend.db.models.capability import (
    ActivationStatus,
    CapabilityStatus,
    CredentialsStatus,
    ExecutionContext,
    ExecutionEnvironment,
    OwnerAuthorizationStatus,
    RegulatoryEligibilityStatus,
    RegulatoryRule,
    RegulatoryRuleEffect,
    TechnicalCapability,
    VenuePermissionStatus,
)
from freyja_backend.db.models.provider import DataSource, DataSourceType, Venue, VenueType

_CAPABILITY_TABLES = frozenset(
    {
        "freyja2_technical_capabilities",
        "freyja2_execution_contexts",
        "freyja2_regulatory_rules",
    }
)

# Unambiguously fictitious fixtures — no real broker, exchange, owner, or
# regulatory citation is named or seeded anywhere in this task.
_TEST_VENUE_CODE = "TEST_CAP_EXCHANGE"
_TEST_SOURCE_CODE = "TEST_CAP_MARKET_DATA"
_TEST_JURISDICTION = "TEST_XX"
_TEST_CLASSIFICATION = "TEST_RETAIL"
_TEST_CITATION = "TEST fixture citation — not a real regulatory source"
_BLANK_OR_PADDED = ["", "   ", " X", "X "]


@pytest.fixture(autouse=True)
def _truncate_capability_tables(auth_test_engine: Engine) -> None:
    with auth_test_engine.connect() as connection:
        connection.execute(
            text(
                "TRUNCATE "
                "freyja2_execution_contexts, freyja2_technical_capabilities, "
                "freyja2_regulatory_rules, freyja2_venues, freyja2_data_sources "
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


def _enabled_context_kwargs() -> dict[str, object]:
    return {
        "credentials_status": CredentialsStatus.CONFIGURED,
        "venue_permission_status": VenuePermissionStatus.GRANTED,
        "regulatory_eligibility_status": RegulatoryEligibilityStatus.ELIGIBLE,
        "owner_authorization_status": OwnerAuthorizationStatus.AUTHORIZED,
        "activation_status": ActivationStatus.ENABLED,
    }


def _make_regulatory_rule(session: Session, **overrides: object) -> RegulatoryRule:
    defaults: dict[str, object] = {
        "jurisdiction": _TEST_JURISDICTION,
        "effect": RegulatoryRuleEffect.NOT_ELIGIBLE,
        "source_citation": _TEST_CITATION,
        "verified_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    rule = RegulatoryRule(**defaults)
    session.add(rule)
    session.flush()
    return rule


# --- Items 16, 1-2, 15: schema shape right after migration -----------------


def test_new_tables_are_empty_after_migration(auth_test_engine: Engine) -> None:
    with auth_test_engine.connect() as connection:
        for table in _CAPABILITY_TABLES:
            count = connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            assert count == 0, f"{table} must be empty — 0011 creates schema only, never data"


def test_capability_table_has_no_activation_or_eligibility_columns(
    auth_test_engine: Engine,
) -> None:
    inspector = inspect(auth_test_engine)
    columns = {c["name"] for c in inspector.get_columns("freyja2_technical_capabilities")}
    for forbidden in ("activation_status", "credentials_status", "owner_id", "jurisdiction"):
        assert forbidden not in columns


def test_execution_context_has_no_technical_capability_columns(auth_test_engine: Engine) -> None:
    inspector = inspect(auth_test_engine)
    columns = {c["name"] for c in inspector.get_columns("freyja2_execution_contexts")}
    for forbidden in (
        "market_data_status",
        "signal_detection_status",
        "backtest_status",
        "demo_execution_status",
        "real_execution_status",
        "settlement_status",
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
    inspector = inspect(auth_test_engine)
    for table in _CAPABILITY_TABLES:
        for column in inspector.get_columns(table):
            column_name = column["name"].lower()
            for forbidden in _FORBIDDEN_SECRET_SUBSTRINGS:
                assert forbidden not in column_name, (
                    f"{table}.{column['name']} looks like a secret-shaped column "
                    f"(matches {forbidden!r}) — forbidden by POINT1-CAPABILITY-001"
                )


# --- Item 1: exactly one of venue_id/data_source_id on TechnicalCapability --


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


def test_technical_capability_accepts_data_source_axis(db_session: Session) -> None:
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")
    source = _make_data_source(db_session)

    capability = _make_capability(
        db_session, instrument_id=instrument_id, timeframe_id=timeframe_id, data_source_id=source.id
    )
    assert capability.venue_id is None


# --- Item 5: absence of evidence is never read as supported -----------------


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


# --- Reason required when NOT_SUPPORTED -------------------------------------


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


# --- Item 8: valid vigencia windows, reject impossible intervals -----------


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


def test_regulatory_rule_rejects_impossible_effective_window(db_session: Session) -> None:
    now = datetime.now(UTC)
    db_session.add(
        RegulatoryRule(
            jurisdiction=_TEST_JURISDICTION,
            effect=RegulatoryRuleEffect.NOT_ELIGIBLE,
            source_citation=_TEST_CITATION,
            verified_at=now,
            effective_from=now,
            effective_to=now,
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


# --- Item 9: regulatory rules are versionable, citable, evidence-only ------


def test_regulatory_rule_requires_source_citation_and_verified_at(db_session: Session) -> None:
    rule = _make_regulatory_rule(db_session)
    assert rule.source_citation == _TEST_CITATION
    assert rule.verified_at is not None


def test_regulatory_rule_can_have_multiple_versions_over_time(db_session: Session) -> None:
    earlier = datetime.now(UTC) - timedelta(days=60)
    closed_end = datetime.now(UTC) - timedelta(days=1)

    _make_regulatory_rule(
        db_session,
        effect=RegulatoryRuleEffect.ELIGIBLE,
        effective_from=earlier,
        effective_to=closed_end,
    )
    superseding = _make_regulatory_rule(db_session, effect=RegulatoryRuleEffect.NOT_ELIGIBLE)

    count = (
        db_session.query(RegulatoryRule)
        .filter(RegulatoryRule.jurisdiction == _TEST_JURISDICTION)
        .count()
    )
    assert count == 2
    assert superseding.effective_to is None


def test_execution_context_can_cite_the_regulatory_rule_that_determined_it(
    db_session: Session,
) -> None:
    rule = _make_regulatory_rule(db_session, effect=RegulatoryRuleEffect.NOT_ELIGIBLE)
    owner = _make_owner(db_session, "owner-cites-rule@example.test")
    venue = _make_venue(db_session)

    context = ExecutionContext(
        owner_id=owner.id,
        venue_id=venue.id,
        execution_environment=ExecutionEnvironment.REAL,
        jurisdiction=_TEST_JURISDICTION,
        client_classification=_TEST_CLASSIFICATION,
        regulatory_eligibility_status=RegulatoryEligibilityStatus.NOT_ELIGIBLE,
        regulatory_rule_id=rule.id,
    )
    db_session.add(context)
    db_session.flush()
    db_session.refresh(context)

    assert context.regulatory_rule_id == rule.id


# --- Item 10: blank/padded rejection, invalid enum values -------------------


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_execution_context_jurisdiction_rejects_blank_or_padded(
    db_session: Session, invalid_value: str
) -> None:
    owner = _make_owner(db_session, "owner-bad-jurisdiction@example.test")
    venue = _make_venue(db_session)

    db_session.add(
        ExecutionContext(
            owner_id=owner.id,
            venue_id=venue.id,
            execution_environment=ExecutionEnvironment.DEMO,
            jurisdiction=invalid_value,
            client_classification=_TEST_CLASSIFICATION,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_execution_context_client_classification_rejects_blank_or_padded(
    db_session: Session, invalid_value: str
) -> None:
    owner = _make_owner(db_session, "owner-bad-classification@example.test")
    venue = _make_venue(db_session)

    db_session.add(
        ExecutionContext(
            owner_id=owner.id,
            venue_id=venue.id,
            execution_environment=ExecutionEnvironment.DEMO,
            jurisdiction=_TEST_JURISDICTION,
            client_classification=invalid_value,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_regulatory_rule_jurisdiction_rejects_blank_or_padded(
    db_session: Session, invalid_value: str
) -> None:
    db_session.add(
        RegulatoryRule(
            jurisdiction=invalid_value,
            effect=RegulatoryRuleEffect.NOT_ELIGIBLE,
            source_citation=_TEST_CITATION,
            verified_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_regulatory_rule_source_citation_rejects_blank_or_padded(
    db_session: Session, invalid_value: str
) -> None:
    db_session.add(
        RegulatoryRule(
            jurisdiction=_TEST_JURISDICTION,
            effect=RegulatoryRuleEffect.NOT_ELIGIBLE,
            source_citation=invalid_value,
            verified_at=datetime.now(UTC),
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

    with pytest.raises(DBAPIError):
        db_session.execute(
            text(
                "INSERT INTO freyja2_execution_contexts "
                "(id, owner_id, venue_id, execution_environment, jurisdiction, "
                "client_classification, activation_status) "
                "VALUES (:id, :owner_id, :venue_id, 'DEMO', :jurisdiction, :classification, "
                "'HACKED_STATUS')"
            ),
            {
                "id": uuid.uuid4(),
                "owner_id": owner.id,
                "venue_id": venue.id,
                "jurisdiction": _TEST_JURISDICTION,
                "classification": _TEST_CLASSIFICATION,
            },
        )
    db_session.rollback()


# --- Item 7: no contradictory ENABLED/SUSPENDED declarations ---------------


def test_enabled_requires_all_four_positive_substatuses(db_session: Session) -> None:
    owner = _make_owner(db_session, "owner-partial-enabled@example.test")
    venue = _make_venue(db_session)

    kwargs = _enabled_context_kwargs()
    kwargs["venue_permission_status"] = VenuePermissionStatus.DENIED  # one negative dimension

    db_session.add(
        ExecutionContext(
            owner_id=owner.id,
            venue_id=venue.id,
            execution_environment=ExecutionEnvironment.REAL,
            jurisdiction=_TEST_JURISDICTION,
            client_classification=_TEST_CLASSIFICATION,
            **kwargs,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_enabled_succeeds_when_all_four_substatuses_are_positive(db_session: Session) -> None:
    owner = _make_owner(db_session, "owner-fully-enabled@example.test")
    venue = _make_venue(db_session)

    context = ExecutionContext(
        owner_id=owner.id,
        venue_id=venue.id,
        execution_environment=ExecutionEnvironment.REAL,
        jurisdiction=_TEST_JURISDICTION,
        client_classification=_TEST_CLASSIFICATION,
        **_enabled_context_kwargs(),
    )
    db_session.add(context)
    db_session.flush()
    db_session.refresh(context)
    assert context.activation_status == ActivationStatus.ENABLED


def test_suspended_requires_nonempty_suspension_reasons(db_session: Session) -> None:
    owner = _make_owner(db_session, "owner-suspended-no-reason@example.test")
    venue = _make_venue(db_session)

    db_session.add(
        ExecutionContext(
            owner_id=owner.id,
            venue_id=venue.id,
            execution_environment=ExecutionEnvironment.REAL,
            jurisdiction=_TEST_JURISDICTION,
            client_classification=_TEST_CLASSIFICATION,
            activation_status=ActivationStatus.SUSPENDED,
            suspension_reasons=None,
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
            owner_id=owner.id,
            venue_id=venue.id,
            execution_environment=ExecutionEnvironment.REAL,
            jurisdiction=_TEST_JURISDICTION,
            client_classification=_TEST_CLASSIFICATION,
            activation_status=ActivationStatus.NOT_CONFIGURED,
            suspension_reasons=["This should not be allowed alongside NOT_CONFIGURED."],
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# --- Item 6: suspension is scoped to one ExecutionContext, never global ---


def test_suspended_context_does_not_affect_other_owners_or_capability(
    db_session: Session,
) -> None:
    venue = _make_venue(db_session)
    instrument_id = _seeded_instrument_id(db_session, "CRYPTO", "SPOT", "BTC/USDT")
    timeframe_id = _seeded_timeframe_id(db_session, "1m")

    suspended_owner = _make_owner(db_session, "owner-suspended@example.test")
    db_session.add(
        ExecutionContext(
            owner_id=suspended_owner.id,
            venue_id=venue.id,
            execution_environment=ExecutionEnvironment.REAL,
            jurisdiction=_TEST_JURISDICTION,
            client_classification=_TEST_CLASSIFICATION,
            activation_status=ActivationStatus.SUSPENDED,
            suspension_reasons=["Fixture: not eligible under TEST_XX retail rules."],
        )
    )
    db_session.flush()

    other_owner = _make_owner(db_session, "owner-unaffected@example.test")
    other_context = ExecutionContext(
        owner_id=other_owner.id,
        venue_id=venue.id,
        execution_environment=ExecutionEnvironment.REAL,
        jurisdiction="TEST_YY",
        client_classification=_TEST_CLASSIFICATION,
        **_enabled_context_kwargs(),
    )
    db_session.add(other_context)
    db_session.flush()
    db_session.refresh(other_context)
    assert other_context.activation_status == ActivationStatus.ENABLED

    # The venue's own TechnicalCapability is untouched by either owner's
    # ExecutionContext — suspension is per-account, never global.
    capability = _make_capability(
        db_session, instrument_id=instrument_id, timeframe_id=timeframe_id, venue_id=venue.id
    )
    assert capability.market_data_status == CapabilityStatus.NOT_EVALUATED


# --- Items 3-4: multiple accounts/contexts, DEMO vs REAL --------------------


def test_multiple_owners_can_use_the_same_venue_without_collision(db_session: Session) -> None:
    venue = _make_venue(db_session)
    owner_a = _make_owner(db_session, "owner-a@example.test")
    owner_b = _make_owner(db_session, "owner-b@example.test")

    db_session.add_all(
        [
            ExecutionContext(
                owner_id=owner_a.id,
                venue_id=venue.id,
                execution_environment=ExecutionEnvironment.DEMO,
                jurisdiction=_TEST_JURISDICTION,
                client_classification=_TEST_CLASSIFICATION,
            ),
            ExecutionContext(
                owner_id=owner_b.id,
                venue_id=venue.id,
                execution_environment=ExecutionEnvironment.DEMO,
                jurisdiction=_TEST_JURISDICTION,
                client_classification=_TEST_CLASSIFICATION,
            ),
        ]
    )
    db_session.flush()

    count = db_session.query(ExecutionContext).filter(ExecutionContext.venue_id == venue.id).count()
    assert count == 2


def test_demo_and_real_are_distinct_contexts_for_the_same_owner_and_venue(
    db_session: Session,
) -> None:
    venue = _make_venue(db_session)
    owner = _make_owner(db_session, "owner-demo-and-real@example.test")

    db_session.add_all(
        [
            ExecutionContext(
                owner_id=owner.id,
                venue_id=venue.id,
                execution_environment=ExecutionEnvironment.DEMO,
                jurisdiction=_TEST_JURISDICTION,
                client_classification=_TEST_CLASSIFICATION,
            ),
            ExecutionContext(
                owner_id=owner.id,
                venue_id=venue.id,
                execution_environment=ExecutionEnvironment.REAL,
                jurisdiction=_TEST_JURISDICTION,
                client_classification=_TEST_CLASSIFICATION,
            ),
        ]
    )
    db_session.flush()

    count = (
        db_session.query(ExecutionContext)
        .filter(ExecutionContext.owner_id == owner.id, ExecutionContext.venue_id == venue.id)
        .count()
    )
    assert count == 2


def test_duplicate_owner_venue_environment_is_rejected(db_session: Session) -> None:
    venue = _make_venue(db_session)
    owner = _make_owner(db_session, "owner-duplicate@example.test")

    db_session.add(
        ExecutionContext(
            owner_id=owner.id,
            venue_id=venue.id,
            execution_environment=ExecutionEnvironment.DEMO,
            jurisdiction=_TEST_JURISDICTION,
            client_classification=_TEST_CLASSIFICATION,
        )
    )
    db_session.flush()

    db_session.add(
        ExecutionContext(
            owner_id=owner.id,
            venue_id=venue.id,
            execution_environment=ExecutionEnvironment.DEMO,
            jurisdiction=_TEST_JURISDICTION,
            client_classification=_TEST_CLASSIFICATION,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# --- Item 11: referential integrity, no CASCADE -----------------------------


def test_fk_prevents_deleting_a_referenced_owner(db_session: Session) -> None:
    owner = _make_owner(db_session, "owner-protected@example.test")
    venue = _make_venue(db_session)
    db_session.add(
        ExecutionContext(
            owner_id=owner.id,
            venue_id=venue.id,
            execution_environment=ExecutionEnvironment.DEMO,
            jurisdiction=_TEST_JURISDICTION,
            client_classification=_TEST_CLASSIFICATION,
        )
    )
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.execute(text("DELETE FROM auth_users WHERE id = :id"), {"id": owner.id})
        db_session.flush()
    db_session.rollback()


def test_fk_prevents_deleting_a_venue_referenced_by_execution_context(
    db_session: Session,
) -> None:
    owner = _make_owner(db_session, "owner-venue-protected@example.test")
    venue = _make_venue(db_session)
    db_session.add(
        ExecutionContext(
            owner_id=owner.id,
            venue_id=venue.id,
            execution_environment=ExecutionEnvironment.DEMO,
            jurisdiction=_TEST_JURISDICTION,
            client_classification=_TEST_CLASSIFICATION,
        )
    )
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.execute(text("DELETE FROM freyja2_venues WHERE id = :id"), {"id": venue.id})
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


def test_fk_prevents_deleting_a_regulatory_rule_referenced_by_execution_context(
    db_session: Session,
) -> None:
    rule = _make_regulatory_rule(db_session)
    owner = _make_owner(db_session, "owner-rule-protected@example.test")
    venue = _make_venue(db_session)
    db_session.add(
        ExecutionContext(
            owner_id=owner.id,
            venue_id=venue.id,
            execution_environment=ExecutionEnvironment.REAL,
            jurisdiction=_TEST_JURISDICTION,
            client_classification=_TEST_CLASSIFICATION,
            regulatory_rule_id=rule.id,
        )
    )
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("DELETE FROM freyja2_regulatory_rules WHERE id = :id"), {"id": rule.id}
        )
        db_session.flush()
    db_session.rollback()
