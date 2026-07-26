import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from freyja_backend.application import auth_service
from freyja_backend.db.models.auth import AuthUser
from freyja_backend.db.models.capability import (
    ActivationStatus,
    ExecutionContext,
    ExecutionContextRegulatoryRule,
    ExecutionEnvironment,
    RegulatoryEligibilityStatus,
    RegulatoryRule,
    RegulatoryRuleEffect,
)
from freyja_backend.db.models.provider import Venue, VenueType

CSRF_URL = "/api/v1/auth/csrf"
LOGIN_URL = "/api/v1/auth/login"
CONTEXTS_URL = "/api/v1/execution-contexts"

_OWNER_A_IDENTIFIER = "owner-a@example.test"
_OWNER_B_IDENTIFIER = "owner-b@example.test"
_PASSWORD = "correct-horse-battery-staple"

_TEST_VENUE_CODE = "TEST_EC_API_EXCHANGE"
_TEST_JURISDICTION = "TEST_XX"
_TEST_CLASSIFICATION = "TEST_RETAIL"
_TEST_CITATION = "TEST fixture citation — not a real regulatory source"

_TABLES = (
    "freyja2_execution_context_regulatory_rules",
    "freyja2_execution_contexts",
    "freyja2_regulatory_rules",
    "freyja2_venues",
)


@pytest.fixture(autouse=True)
def _truncate_tables(auth_test_engine: Engine) -> Iterator[None]:
    yield
    with auth_test_engine.connect() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
        connection.commit()


def _create_owner(db_session: Session, identifier: str) -> AuthUser:
    user = auth_service.create_owner(db_session, identifier=identifier, password=_PASSWORD)
    db_session.commit()
    return user


def _login_as(client: TestClient, identifier: str) -> None:
    client.cookies.clear()
    client.get(CSRF_URL)
    csrf = client.cookies.get("freyja_csrf")
    assert csrf is not None
    response = client.post(
        LOGIN_URL,
        json={"identifier": identifier, "password": _PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200


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


def _make_context(
    session: Session,
    *,
    owner: AuthUser,
    venue: Venue,
    product_type_id: uuid.UUID,
    account_key: str = "TEST_ACCOUNT_1",
    environment: ExecutionEnvironment = ExecutionEnvironment.DEMO,
    **overrides: object,
) -> ExecutionContext:
    kwargs: dict[str, object] = {
        "owner_id": owner.id,
        "venue_id": venue.id,
        "account_key": account_key,
        "execution_environment": environment,
        "product_type_id": product_type_id,
        "jurisdiction": _TEST_JURISDICTION,
        "client_classification": _TEST_CLASSIFICATION,
    }
    kwargs.update(overrides)
    context = ExecutionContext(**kwargs)
    session.add(context)
    session.flush()
    return context


def test_list_contexts_requires_authentication(client: TestClient) -> None:
    response = client.get(CONTEXTS_URL)
    assert response.status_code == 401


def test_demo_and_real_are_separate_contexts(client: TestClient, db_session: Session) -> None:
    owner = _create_owner(db_session, _OWNER_A_IDENTIFIER)
    venue = _make_venue(db_session)
    product_type_id = _seeded_product_type_id(db_session, "SPOT")

    _make_context(
        db_session,
        owner=owner,
        venue=venue,
        product_type_id=product_type_id,
        environment=ExecutionEnvironment.DEMO,
    )
    _make_context(
        db_session,
        owner=owner,
        venue=venue,
        product_type_id=product_type_id,
        environment=ExecutionEnvironment.REAL,
    )
    db_session.commit()

    _login_as(client, _OWNER_A_IDENTIFIER)

    demo_only = client.get(CONTEXTS_URL, params={"execution_environment": "DEMO"}).json()
    assert demo_only["total"] == 1
    assert demo_only["items"][0]["execution_environment"] == "DEMO"

    real_only = client.get(CONTEXTS_URL, params={"execution_environment": "REAL"}).json()
    assert real_only["total"] == 1
    assert real_only["items"][0]["execution_environment"] == "REAL"

    both = client.get(CONTEXTS_URL).json()
    assert both["total"] == 2


def test_products_and_accounts_are_separate_contexts(
    client: TestClient, db_session: Session
) -> None:
    owner = _create_owner(db_session, _OWNER_A_IDENTIFIER)
    venue = _make_venue(db_session)
    spot_id = _seeded_product_type_id(db_session, "SPOT")
    binary_id = _seeded_product_type_id(db_session, "BINARY_OPTION")

    _make_context(
        db_session, owner=owner, venue=venue, product_type_id=spot_id, account_key="ACC_1"
    )
    _make_context(
        db_session, owner=owner, venue=venue, product_type_id=binary_id, account_key="ACC_1"
    )
    _make_context(
        db_session, owner=owner, venue=venue, product_type_id=spot_id, account_key="ACC_2"
    )
    db_session.commit()

    _login_as(client, _OWNER_A_IDENTIFIER)
    body = client.get(CONTEXTS_URL).json()
    assert body["total"] == 3

    only_spot = client.get(CONTEXTS_URL, params={"product_type_id": str(spot_id)}).json()
    assert only_spot["total"] == 2


def test_suspended_binary_option_real_does_not_affect_spot_real(
    client: TestClient, db_session: Session
) -> None:
    owner = _create_owner(db_session, _OWNER_A_IDENTIFIER)
    venue = _make_venue(db_session)
    spot_id = _seeded_product_type_id(db_session, "SPOT")
    binary_id = _seeded_product_type_id(db_session, "BINARY_OPTION")

    _make_context(
        db_session,
        owner=owner,
        venue=venue,
        product_type_id=binary_id,
        environment=ExecutionEnvironment.REAL,
        activation_status=ActivationStatus.SUSPENDED,
        suspension_reasons=["TEST fixture: binary options suspended in this jurisdiction"],
    )
    _make_context(
        db_session,
        owner=owner,
        venue=venue,
        product_type_id=spot_id,
        environment=ExecutionEnvironment.REAL,
        activation_status=ActivationStatus.NOT_CONFIGURED,
    )
    db_session.commit()

    _login_as(client, _OWNER_A_IDENTIFIER)
    body = client.get(CONTEXTS_URL, params={"execution_environment": "REAL"}).json()
    by_product = {item["product_type"]["code"]: item for item in body["items"]}

    assert by_product["BINARY_OPTION"]["activation_status"] == "SUSPENDED"
    assert by_product["BINARY_OPTION"]["suspension_reasons"] == [
        "TEST fixture: binary options suspended in this jurisdiction"
    ]
    assert by_product["SPOT"]["activation_status"] == "NOT_CONFIGURED"
    assert by_product["SPOT"]["suspension_reasons"] is None


def test_not_configured_and_not_evaluated_are_never_presented_as_not_eligible(
    client: TestClient, db_session: Session
) -> None:
    owner = _create_owner(db_session, _OWNER_A_IDENTIFIER)
    venue = _make_venue(db_session)
    product_type_id = _seeded_product_type_id(db_session, "SPOT")

    _make_context(
        db_session,
        owner=owner,
        venue=venue,
        product_type_id=product_type_id,
        activation_status=ActivationStatus.NOT_CONFIGURED,
    )
    db_session.commit()

    _login_as(client, _OWNER_A_IDENTIFIER)
    item = client.get(CONTEXTS_URL).json()["items"][0]
    assert item["activation_status"] == "NOT_CONFIGURED"
    assert item["regulatory_eligibility_status"] == "NOT_EVALUATED"
    assert item["activation_status"] != "NOT_ELIGIBLE"
    assert item["regulatory_eligibility_status"] != "NOT_ELIGIBLE"


def test_multiple_regulatory_rules_appear_as_separate_evidence(
    client: TestClient, db_session: Session
) -> None:
    owner = _create_owner(db_session, _OWNER_A_IDENTIFIER)
    venue = _make_venue(db_session)
    binary_id = _seeded_product_type_id(db_session, "BINARY_OPTION")
    spot_id = _seeded_product_type_id(db_session, "SPOT")

    context = _make_context(
        db_session,
        owner=owner,
        venue=venue,
        product_type_id=binary_id,
        regulatory_eligibility_status=RegulatoryEligibilityStatus.NOT_ELIGIBLE,
    )
    # Four distinct regulatory scopes — product_type_id/venue_id come from
    # RegulatoryRule itself, never reconstructed from the ExecutionContext,
    # since a rule's own scope can differ from the context it applies to.
    rule_general = RegulatoryRule(
        jurisdiction=_TEST_JURISDICTION,
        effect=RegulatoryRuleEffect.NOT_ELIGIBLE,
        source_citation=_TEST_CITATION + " (general)",
        verified_at=datetime.now(UTC),
    )
    rule_product_scoped = RegulatoryRule(
        jurisdiction=_TEST_JURISDICTION,
        product_type_id=spot_id,
        effect=RegulatoryRuleEffect.NOT_ELIGIBLE,
        source_citation=_TEST_CITATION + " (product-scoped)",
        verified_at=datetime.now(UTC),
    )
    rule_venue_scoped = RegulatoryRule(
        jurisdiction=_TEST_JURISDICTION,
        venue_id=venue.id,
        effect=RegulatoryRuleEffect.NOT_ELIGIBLE,
        source_citation=_TEST_CITATION + " (venue-scoped)",
        verified_at=datetime.now(UTC),
    )
    rule_product_and_venue_scoped = RegulatoryRule(
        jurisdiction=_TEST_JURISDICTION,
        client_classification=_TEST_CLASSIFICATION,
        product_type_id=binary_id,
        venue_id=venue.id,
        effect=RegulatoryRuleEffect.NOT_ELIGIBLE,
        source_citation=_TEST_CITATION + " (product-and-venue-scoped)",
        verified_at=datetime.now(UTC),
    )
    rules = [rule_general, rule_product_scoped, rule_venue_scoped, rule_product_and_venue_scoped]
    db_session.add_all(rules)
    db_session.flush()
    db_session.add_all(
        [
            ExecutionContextRegulatoryRule(
                execution_context_id=context.id, regulatory_rule_id=rule.id
            )
            for rule in rules
        ]
    )
    db_session.commit()

    _login_as(client, _OWNER_A_IDENTIFIER)
    item = client.get(CONTEXTS_URL).json()["items"][0]
    assert len(item["regulatory_rules"]) == 4
    by_citation = {rule["source_citation"]: rule for rule in item["regulatory_rules"]}

    general = by_citation[_TEST_CITATION + " (general)"]
    assert general["id"] == str(rule_general.id)
    assert general["product_type_id"] is None
    assert general["venue_id"] is None

    product_scoped = by_citation[_TEST_CITATION + " (product-scoped)"]
    assert product_scoped["id"] == str(rule_product_scoped.id)
    assert product_scoped["product_type_id"] == str(spot_id)
    assert product_scoped["venue_id"] is None

    venue_scoped = by_citation[_TEST_CITATION + " (venue-scoped)"]
    assert venue_scoped["id"] == str(rule_venue_scoped.id)
    assert venue_scoped["product_type_id"] is None
    assert venue_scoped["venue_id"] == str(venue.id)

    product_and_venue_scoped = by_citation[_TEST_CITATION + " (product-and-venue-scoped)"]
    assert product_and_venue_scoped["id"] == str(rule_product_and_venue_scoped.id)
    assert product_and_venue_scoped["product_type_id"] == str(binary_id)
    assert product_and_venue_scoped["venue_id"] == str(venue.id)


def test_owner_cannot_list_another_owners_contexts(client: TestClient, db_session: Session) -> None:
    owner_a = _create_owner(db_session, _OWNER_A_IDENTIFIER)
    _create_owner(db_session, _OWNER_B_IDENTIFIER)
    venue = _make_venue(db_session)
    product_type_id = _seeded_product_type_id(db_session, "SPOT")
    _make_context(db_session, owner=owner_a, venue=venue, product_type_id=product_type_id)
    db_session.commit()

    _login_as(client, _OWNER_B_IDENTIFIER)
    body = client.get(CONTEXTS_URL).json()
    assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_owner_cannot_fetch_another_owners_context_by_id_same_404_as_missing(
    client: TestClient, db_session: Session
) -> None:
    owner_a = _create_owner(db_session, _OWNER_A_IDENTIFIER)
    _create_owner(db_session, _OWNER_B_IDENTIFIER)
    venue = _make_venue(db_session)
    product_type_id = _seeded_product_type_id(db_session, "SPOT")
    context = _make_context(db_session, owner=owner_a, venue=venue, product_type_id=product_type_id)
    db_session.commit()

    _login_as(client, _OWNER_B_IDENTIFIER)
    other_owners_context_response = client.get(f"{CONTEXTS_URL}/{context.id}")
    missing_context_response = client.get(f"{CONTEXTS_URL}/{uuid.uuid4()}")

    assert other_owners_context_response.status_code == 404
    assert missing_context_response.status_code == 404
    assert other_owners_context_response.json() == missing_context_response.json()


def test_owner_can_fetch_own_context_by_id(client: TestClient, db_session: Session) -> None:
    owner = _create_owner(db_session, _OWNER_A_IDENTIFIER)
    venue = _make_venue(db_session)
    product_type_id = _seeded_product_type_id(db_session, "SPOT")
    context = _make_context(db_session, owner=owner, venue=venue, product_type_id=product_type_id)
    db_session.commit()

    _login_as(client, _OWNER_A_IDENTIFIER)
    response = client.get(f"{CONTEXTS_URL}/{context.id}")
    assert response.status_code == 200
    assert response.json()["id"] == str(context.id)


def test_response_never_contains_secret_shaped_fields(
    client: TestClient, db_session: Session
) -> None:
    owner = _create_owner(db_session, _OWNER_A_IDENTIFIER)
    venue = _make_venue(db_session)
    product_type_id = _seeded_product_type_id(db_session, "SPOT")
    _make_context(db_session, owner=owner, venue=venue, product_type_id=product_type_id)
    db_session.commit()

    _login_as(client, _OWNER_A_IDENTIFIER)
    item = client.get(CONTEXTS_URL).json()["items"][0]

    def _walk(value: object) -> Iterator[str]:
        if isinstance(value, dict):
            for key, nested in value.items():
                yield key
                yield from _walk(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from _walk(nested)

    forbidden = ("password", "secret", "token", "api_key", "apikey", "credential_value", "hash")
    for key in _walk(item):
        lowered = key.lower()
        for bad in forbidden:
            assert bad not in lowered, f"response field {key!r} looks secret-shaped"
