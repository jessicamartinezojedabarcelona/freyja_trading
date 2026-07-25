import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

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
    ExecutionContextRegulatoryRule,
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
        "freyja2_execution_context_regulatory_rules",
    }
)

# Unambiguously fictitious fixtures — no real broker, exchange, owner, or
# regulatory citation is named or seeded anywhere in this task.
_TEST_VENUE_CODE = "TEST_CAP_EXCHANGE"
_TEST_SOURCE_CODE = "TEST_CAP_MARKET_DATA"
_TEST_JURISDICTION = "TEST_XX"
_TEST_CLASSIFICATION = "TEST_RETAIL"
_TEST_CITATION = "TEST fixture citation — not a real regulatory source"
_TEST_ACCOUNT_1 = "TEST_ACCOUNT_1"
_TEST_ACCOUNT_2 = "TEST_ACCOUNT_2"
_BLANK_OR_PADDED = ["", "   ", " X", "X "]


@pytest.fixture(autouse=True)
def _truncate_capability_tables(auth_test_engine: Engine) -> None:
    with auth_test_engine.connect() as connection:
        connection.execute(
            text(
                "TRUNCATE "
                "freyja2_execution_context_regulatory_rules, freyja2_execution_contexts, "
                "freyja2_technical_capabilities, freyja2_regulatory_rules, "
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
        "regulatory_eligibility_status": RegulatoryEligibilityStatus.ELIGIBLE,
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
    jurisdiction=invalid_value) without every other required column also
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
        "jurisdiction": _TEST_JURISDICTION,
        "client_classification": _TEST_CLASSIFICATION,
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


# --- Schema shape right after migration -------------------------------------


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


# --- RegulatoryRule: versionable, citable, evidence-only --------------------


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


# --- Block 3: ExecutionContext <-> RegulatoryRule many-to-many --------------


def test_execution_context_can_be_associated_with_multiple_regulatory_rules(
    db_session: Session,
) -> None:
    owner = _make_owner(db_session, "owner-multi-rule@example.test")
    venue = _make_venue(db_session)
    context = _make_execution_context(db_session, owner=owner, venue=venue)
    rule_a = _make_regulatory_rule(db_session, effect=RegulatoryRuleEffect.NOT_ELIGIBLE)
    rule_b = _make_regulatory_rule(
        db_session, jurisdiction="TEST_YY", effect=RegulatoryRuleEffect.ELIGIBLE
    )

    db_session.add_all(
        [
            ExecutionContextRegulatoryRule(
                execution_context_id=context.id, regulatory_rule_id=rule_a.id
            ),
            ExecutionContextRegulatoryRule(
                execution_context_id=context.id, regulatory_rule_id=rule_b.id
            ),
        ]
    )
    db_session.flush()

    count = (
        db_session.query(ExecutionContextRegulatoryRule)
        .filter(ExecutionContextRegulatoryRule.execution_context_id == context.id)
        .count()
    )
    assert count == 2


def test_execution_context_can_have_zero_regulatory_rule_associations(
    db_session: Session,
) -> None:
    owner = _make_owner(db_session, "owner-zero-rules@example.test")
    venue = _make_venue(db_session)
    context = _make_execution_context(db_session, owner=owner, venue=venue)

    count = (
        db_session.query(ExecutionContextRegulatoryRule)
        .filter(ExecutionContextRegulatoryRule.execution_context_id == context.id)
        .count()
    )
    assert count == 0


def test_duplicate_regulatory_rule_association_is_rejected(db_session: Session) -> None:
    owner = _make_owner(db_session, "owner-duplicate-rule@example.test")
    venue = _make_venue(db_session)
    context = _make_execution_context(db_session, owner=owner, venue=venue)
    rule = _make_regulatory_rule(db_session)

    db_session.add(
        ExecutionContextRegulatoryRule(execution_context_id=context.id, regulatory_rule_id=rule.id)
    )
    db_session.flush()

    db_session.add(
        ExecutionContextRegulatoryRule(execution_context_id=context.id, regulatory_rule_id=rule.id)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_fk_prevents_deleting_a_regulatory_rule_referenced_by_association(
    db_session: Session,
) -> None:
    owner = _make_owner(db_session, "owner-rule-protected@example.test")
    venue = _make_venue(db_session)
    context = _make_execution_context(db_session, owner=owner, venue=venue)
    rule = _make_regulatory_rule(db_session)
    db_session.add(
        ExecutionContextRegulatoryRule(execution_context_id=context.id, regulatory_rule_id=rule.id)
    )
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("DELETE FROM freyja2_regulatory_rules WHERE id = :id"), {"id": rule.id}
        )
        db_session.flush()
    db_session.rollback()


def test_fk_prevents_deleting_an_execution_context_referenced_by_association(
    db_session: Session,
) -> None:
    owner = _make_owner(db_session, "owner-context-protected@example.test")
    venue = _make_venue(db_session)
    context = _make_execution_context(db_session, owner=owner, venue=venue)
    rule = _make_regulatory_rule(db_session)
    db_session.add(
        ExecutionContextRegulatoryRule(execution_context_id=context.id, regulatory_rule_id=rule.id)
    )
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("DELETE FROM freyja2_execution_contexts WHERE id = :id"), {"id": context.id}
        )
        db_session.flush()
    db_session.rollback()


# --- Blank/padded rejection, invalid enum values ----------------------------


@pytest.mark.parametrize("invalid_value", _BLANK_OR_PADDED)
def test_execution_context_jurisdiction_rejects_blank_or_padded(
    db_session: Session, invalid_value: str
) -> None:
    owner = _make_owner(db_session, "owner-bad-jurisdiction@example.test")
    venue = _make_venue(db_session)

    db_session.add(
        ExecutionContext(
            **_execution_context_kwargs(
                db_session, owner=owner, venue=venue, jurisdiction=invalid_value
            )
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
            **_execution_context_kwargs(
                db_session, owner=owner, venue=venue, client_classification=invalid_value
            )
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


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
                "jurisdiction, client_classification, activation_status) "
                "VALUES (:id, :owner_id, :venue_id, :account_key, 'DEMO', :product_type_id, "
                ":jurisdiction, :classification, 'HACKED_STATUS')"
            ),
            {
                "id": uuid.uuid4(),
                "owner_id": owner.id,
                "venue_id": venue.id,
                "account_key": _TEST_ACCOUNT_1,
                "product_type_id": product_type_id,
                "jurisdiction": _TEST_JURISDICTION,
                "classification": _TEST_CLASSIFICATION,
            },
        )
    db_session.rollback()


# --- No contradictory ENABLED/SUSPENDED declarations ------------------------


def test_enabled_requires_all_four_positive_substatuses(db_session: Session) -> None:
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


def test_enabled_succeeds_when_all_four_substatuses_are_positive(db_session: Session) -> None:
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
        suspension_reasons=["Fixture: BINARY_OPTION not eligible under TEST_XX retail rules."],
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
        suspension_reasons=["Fixture: not eligible under TEST_XX retail rules."],
    )

    other_owner = _make_owner(db_session, "owner-unaffected@example.test")
    other_context = _make_execution_context(
        db_session,
        owner=other_owner,
        venue=venue,
        environment=ExecutionEnvironment.REAL,
        jurisdiction="TEST_YY",
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
