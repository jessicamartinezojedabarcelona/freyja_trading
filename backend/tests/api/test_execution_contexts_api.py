import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from freyja_backend.application import auth_service
from freyja_backend.db.models.auth import AuthUser
from freyja_backend.db.models.capability import (
    ActivationStatus,
    ExecutionContext,
    ExecutionEnvironment,
)
from freyja_backend.db.models.provider import Venue, VenueType

CSRF_URL = "/api/v1/auth/csrf"
LOGIN_URL = "/api/v1/auth/login"
CONTEXTS_URL = "/api/v1/execution-contexts"

_OWNER_A_IDENTIFIER = "owner-a@example.test"
_OWNER_B_IDENTIFIER = "owner-b@example.test"
_PASSWORD = "correct-horse-battery-staple"

_TEST_VENUE_CODE = "TEST_EC_API_EXCHANGE"

_TABLES = (
    "freyja2_execution_contexts",
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
        suspension_reasons=["TEST fixture: broker denied venue permission for BINARY_OPTION"],
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
        "TEST fixture: broker denied venue permission for BINARY_OPTION"
    ]
    assert by_product["SPOT"]["activation_status"] == "NOT_CONFIGURED"
    assert by_product["SPOT"]["suspension_reasons"] is None


def test_not_configured_and_not_evaluated_are_never_presented_as_denied(
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
    # venue_permission_status defaults to NOT_EVALUATED (broker not yet
    # queried) — never silently presented as DENIED or coerced to a boolean.
    assert item["venue_permission_status"] == "NOT_EVALUATED"
    assert item["activation_status"] != "DENIED"
    assert item["venue_permission_status"] != "DENIED"


@pytest.mark.parametrize(
    "removed_param,removed_value",
    [
        ("jurisdiction", "ANY_XX"),
        ("client_classification", "ANY_RETAIL"),
        ("regulatory_eligibility_status", "NOT_EVALUATED"),
    ],
)
def test_removed_regulatory_filters_return_422_not_silently_ignored(
    client: TestClient, db_session: Session, removed_param: str, removed_value: str
) -> None:
    """POINT1-CAPABILITY-API-CORRECTION-001 (corrected after independent
    audit): a filter this endpoint no longer supports must fail closed with
    422 — silently ignoring it would let an old client believe the filter
    had been applied when it was not."""
    owner = _create_owner(db_session, _OWNER_A_IDENTIFIER)
    venue = _make_venue(db_session)
    product_type_id = _seeded_product_type_id(db_session, "SPOT")
    _make_context(db_session, owner=owner, venue=venue, product_type_id=product_type_id)
    db_session.commit()

    _login_as(client, _OWNER_A_IDENTIFIER)
    response = client.get(CONTEXTS_URL, params={removed_param: removed_value})
    assert response.status_code == 422


def test_unknown_arbitrary_query_param_returns_422(client: TestClient, db_session: Session) -> None:
    owner = _create_owner(db_session, _OWNER_A_IDENTIFIER)
    venue = _make_venue(db_session)
    product_type_id = _seeded_product_type_id(db_session, "SPOT")
    _make_context(db_session, owner=owner, venue=venue, product_type_id=product_type_id)
    db_session.commit()

    _login_as(client, _OWNER_A_IDENTIFIER)
    response = client.get(CONTEXTS_URL, params={"totally_made_up_filter": "x"})
    assert response.status_code == 422


def test_valid_filters_still_return_200_and_filter_correctly(
    client: TestClient, db_session: Session
) -> None:
    owner = _create_owner(db_session, _OWNER_A_IDENTIFIER)
    venue = _make_venue(db_session)
    spot_id = _seeded_product_type_id(db_session, "SPOT")
    binary_id = _seeded_product_type_id(db_session, "BINARY_OPTION")
    _make_context(db_session, owner=owner, venue=venue, product_type_id=spot_id)
    _make_context(
        db_session, owner=owner, venue=venue, product_type_id=binary_id, account_key="ACC_2"
    )
    db_session.commit()

    _login_as(client, _OWNER_A_IDENTIFIER)
    response = client.get(
        CONTEXTS_URL,
        params={
            "venue_id": str(venue.id),
            "product_type_id": str(spot_id),
            "execution_environment": "DEMO",
            "limit": 10,
            "offset": 0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["product_type"]["code"] == "SPOT"


def test_response_never_contains_a_regulatory_field(
    client: TestClient, db_session: Session
) -> None:
    owner = _create_owner(db_session, _OWNER_A_IDENTIFIER)
    venue = _make_venue(db_session)
    product_type_id = _seeded_product_type_id(db_session, "SPOT")
    _make_context(db_session, owner=owner, venue=venue, product_type_id=product_type_id)
    db_session.commit()

    _login_as(client, _OWNER_A_IDENTIFIER)
    response = client.get(CONTEXTS_URL)
    assert response.status_code == 200
    body = response.json()

    for forbidden_key in (
        "jurisdiction",
        "client_classification",
        "regulatory_eligibility_status",
        "regulatory_rules",
    ):
        assert forbidden_key not in body["items"][0]


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


def test_owner_with_no_contexts_gets_an_honest_empty_list(
    client: TestClient, db_session: Session
) -> None:
    """Absence of any ExecutionContext row must never be presented as an
    error or as a fabricated/default authorized context — a semantically
    correct empty page, exactly like a filter matching nothing."""
    _create_owner(db_session, _OWNER_A_IDENTIFIER)
    _login_as(client, _OWNER_A_IDENTIFIER)

    response = client.get(CONTEXTS_URL)
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_listing_contexts_does_not_grow_query_count_with_more_rows(
    client: TestClient, db_session: Session, auth_test_engine: Engine
) -> None:
    owner = _create_owner(db_session, _OWNER_A_IDENTIFIER)
    venue = _make_venue(db_session)
    spot_id = _seeded_product_type_id(db_session, "SPOT")
    _make_context(
        db_session, owner=owner, venue=venue, product_type_id=spot_id, account_key="ACC_BASE"
    )
    db_session.commit()

    _login_as(client, _OWNER_A_IDENTIFIER)

    def _count_queries() -> int:
        counter = {"n": 0}

        def _before_cursor_execute(*_args: object, **_kwargs: object) -> None:
            counter["n"] += 1

        event.listen(auth_test_engine, "before_cursor_execute", _before_cursor_execute)
        try:
            response = client.get(CONTEXTS_URL, params={"limit": 50, "offset": 0})
            assert response.status_code == 200
        finally:
            event.remove(auth_test_engine, "before_cursor_execute", _before_cursor_execute)
        return counter["n"]

    before = _count_queries()

    for i in range(3):
        _make_context(
            db_session,
            owner=owner,
            venue=venue,
            product_type_id=spot_id,
            account_key=f"ACC_EXTRA_{i}",
        )
    db_session.commit()

    after = _count_queries()

    assert before == after, (
        "query count must stay constant as row count grows — a per-row query "
        "would be an N+1 regression"
    )
