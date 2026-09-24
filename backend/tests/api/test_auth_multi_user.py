"""Public registration and independent user accounts.

Freyja lets anyone create their own account from the registration screen.
Each person signs in with their own credentials and session; market data
(the catalog) is common to everyone, while personal data stays isolated by
owner. Every account below is created through the public endpoint, the way a
real person would — never seeded behind the API's back.
"""

import uuid
from collections.abc import Iterator

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from freyja_backend.application import auth_service
from freyja_backend.core.database import get_postgres_settings
from freyja_backend.core.email import InMemoryEmailSender
from freyja_backend.db import deps as db_deps
from freyja_backend.db.models import AuthUser, RateLimitAction, UserOrigin
from freyja_backend.db.models.capability import ExecutionContext, ExecutionEnvironment
from freyja_backend.db.models.provider import Venue, VenueType

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/auth/me"
CSRF_URL = "/api/v1/auth/csrf"
FORGOT_URL = "/api/v1/auth/forgot-password"
RESET_URL = "/api/v1/auth/reset-password"
CONTEXTS_URL = "/api/v1/execution-contexts"
SHARED_DATA_URLS = (
    "/api/v1/catalog/instruments",
    "/api/v1/catalog/venues",
    "/api/v1/catalog/data-sources",
    "/api/v1/capabilities",
)

# Two different people (fictitious test data only).
EMAIL_A = "person-a@freyja-test.dev"
PASSWORD_A = "correct-horse-battery-staple"
EMAIL_B = "person-b@freyja-test.dev"
PASSWORD_B = "another-long-and-different-password"

_TEST_VENUE_CODE = "TEST_MU_EXCHANGE"


@pytest.fixture(autouse=True)
def _remove_test_venue(auth_test_engine: Engine) -> Iterator[None]:
    yield
    with auth_test_engine.connect() as connection:
        connection.execute(text("TRUNCATE freyja2_venues RESTART IDENTITY CASCADE"))
        connection.commit()


def _csrf_token(client: TestClient) -> str:
    client.get(CSRF_URL)
    token = client.cookies.get("freyja_csrf")
    assert token is not None
    return token


def _register(client: TestClient, email: str, password: str) -> httpx2.Response:
    return client.post(
        REGISTER_URL,
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": _csrf_token(client)},
    )


def _login(client: TestClient, identifier: str, password: str) -> int:
    response = client.post(
        LOGIN_URL,
        json={"identifier": identifier, "password": password},
        headers={"X-CSRF-Token": _csrf_token(client)},
    )
    return response.status_code


def _logout(client: TestClient) -> int:
    return client.post(LOGOUT_URL, headers={"X-CSRF-Token": _csrf_token(client)}).status_code


def _me_identifier(client: TestClient) -> str | None:
    response = client.get(ME_URL)
    if response.status_code != 200:
        return None
    identifier: str = response.json()["identifier"]
    return identifier


def _count_users(db_session: Session) -> int:
    return db_session.execute(select(func.count()).select_from(AuthUser)).scalar_one()


def _user(db_session: Session, identifier: str) -> AuthUser:
    return db_session.execute(
        select(AuthUser).where(AuthUser.identifier == identifier)
    ).scalar_one()


def _register_two_people(client: TestClient, second_client: TestClient) -> None:
    assert _register(client, EMAIL_A, PASSWORD_A).status_code == 200
    assert _register(second_client, EMAIL_B, PASSWORD_B).status_code == 200


def _reset_token_from(link_text: str) -> str:
    marker = "/reset-password#token="
    start = link_text.index(marker) + len(marker)
    end = link_text.find(chr(10), start)
    return link_text[start:end] if end != -1 else link_text[start:]


def _database_seen_by_the_api() -> str:
    """The database every route resolves to, through the same `get_db()`
    dependency the routes use."""
    generator = db_deps.get_db()
    session = next(generator)
    try:
        return str(session.execute(text("SELECT current_database()")).scalar_one())
    finally:
        next(generator, None)


# --- registration: persistence, validation, duplicates, errors -----------------


def test_register_persists_an_active_account_with_a_hashed_password(
    client: TestClient, db_session: Session
) -> None:
    response = _register(client, "  Person.A@Freyja-Test.DEV ", PASSWORD_A)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "message": "Tu cuenta ha sido creada. Ya puedes iniciar sesión.",
    }
    assert _count_users(db_session) == 1
    user = _user(db_session, "person.a@freyja-test.dev")  # stored normalized
    assert user.is_active is True
    assert user.created_via == UserOrigin.SELF_REGISTRATION
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD_A not in user.password_hash


def test_register_does_not_start_a_session(client: TestClient) -> None:
    assert _register(client, EMAIL_A, PASSWORD_A).status_code == 200

    assert _me_identifier(client) is None


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": PASSWORD_A},
        {"email": EMAIL_A, "password": "short"},
        {"email": EMAIL_A},
        {"password": PASSWORD_A},
        {},
    ],
)
def test_register_validation_errors_create_no_account(
    client: TestClient, db_session: Session, payload: dict[str, str]
) -> None:
    response = client.post(
        REGISTER_URL, json=payload, headers={"X-CSRF-Token": _csrf_token(client)}
    )

    assert response.status_code == 422
    assert _count_users(db_session) == 0


def test_register_without_csrf_creates_no_account(client: TestClient, db_session: Session) -> None:
    client.get(CSRF_URL)

    response = client.post(REGISTER_URL, json={"email": EMAIL_A, "password": PASSWORD_A})

    assert response.status_code == 403
    assert _count_users(db_session) == 0


def test_registering_an_existing_email_never_overwrites_its_password(
    client: TestClient, db_session: Session
) -> None:
    first = _register(client, EMAIL_A, PASSWORD_A)
    again = _register(client, EMAIL_A, PASSWORD_B)  # someone else, same email

    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()  # nothing reveals that the email already existed
    assert _count_users(db_session) == 1
    assert _login(client, EMAIL_A, PASSWORD_B) == 401
    assert _login(client, EMAIL_A, PASSWORD_A) == 200


def test_register_is_rate_limited_after_too_many_attempts(client: TestClient) -> None:
    limit = auth_service.RATE_LIMITS[RateLimitAction.REGISTER][0]
    for _ in range(limit):
        assert _register(client, EMAIL_A, PASSWORD_A).status_code == 200

    blocked = _register(client, EMAIL_A, PASSWORD_A)

    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Demasiados intentos. Vuelve a intentarlo más tarde."


# --- every person gets an independent account ---------------------------------


def test_two_people_get_independent_accounts_and_sessions(
    client: TestClient, second_client: TestClient, db_session: Session
) -> None:
    _register_two_people(client, second_client)
    assert _count_users(db_session) == 2

    assert _login(client, EMAIL_A, PASSWORD_A) == 200
    assert _login(second_client, EMAIL_B, PASSWORD_B) == 200

    # Each browser sees only its own account.
    assert _me_identifier(client) == EMAIL_A
    assert _me_identifier(second_client) == EMAIL_B

    # Ending one session leaves the other untouched.
    assert _logout(client) == 200
    assert _me_identifier(client) is None
    assert _me_identifier(second_client) == EMAIL_B
    assert _logout(second_client) == 200
    assert _me_identifier(second_client) is None


def test_credentials_are_independent_per_account(
    client: TestClient, second_client: TestClient
) -> None:
    """One account's password never opens another, and locking one account out
    with failed attempts does not lock the other."""
    _register_two_people(client, second_client)
    assert _login(client, EMAIL_B, PASSWORD_A) == 401

    for _ in range(auth_service.RATE_LIMITS[RateLimitAction.LOGIN][0]):
        assert _login(client, EMAIL_A, "definitely-the-wrong-password") == 401
    assert _login(client, EMAIL_A, PASSWORD_A) == 429  # A is throttled...
    assert _login(second_client, EMAIL_B, PASSWORD_B) == 200  # ...B is not


def test_registered_accounts_see_the_same_market_data(
    client: TestClient, second_client: TestClient
) -> None:
    _register_two_people(client, second_client)
    assert _login(client, EMAIL_A, PASSWORD_A) == 200
    assert _login(second_client, EMAIL_B, PASSWORD_B) == 200

    for url in SHARED_DATA_URLS:
        seen_by_a = client.get(url)
        seen_by_b = second_client.get(url)
        assert seen_by_a.status_code == seen_by_b.status_code == 200, url
        assert seen_by_a.json() == seen_by_b.json(), url

    # The seeded catalog is really there, so the equality is not "both empty".
    assert client.get(SHARED_DATA_URLS[0]).json()["total"] > 0


def test_registered_accounts_keep_personal_resources_private(
    client: TestClient, second_client: TestClient, db_session: Session
) -> None:
    _register_two_people(client, second_client)
    owner_a = _user(db_session, EMAIL_A)
    venue = Venue(code=_TEST_VENUE_CODE, display_name="Test", venue_type=VenueType.EXCHANGE)
    db_session.add(venue)
    db_session.flush()
    product_type_id = uuid.UUID(
        str(db_session.execute(text("SELECT id FROM freyja2_product_types LIMIT 1")).scalar_one())
    )
    context = ExecutionContext(
        owner_id=owner_a.id,
        venue_id=venue.id,
        account_key="TEST_ACCOUNT_1",
        execution_environment=ExecutionEnvironment.DEMO,
        product_type_id=product_type_id,
    )
    db_session.add(context)
    db_session.commit()
    assert _login(client, EMAIL_A, PASSWORD_A) == 200
    assert _login(second_client, EMAIL_B, PASSWORD_B) == 200

    mine = client.get(CONTEXTS_URL).json()
    theirs = second_client.get(CONTEXTS_URL).json()
    assert mine["total"] == 1
    assert theirs == {"items": [], "total": 0, "limit": 50, "offset": 0}
    # The other person cannot fetch it by id either: same 404 as a missing one.
    assert second_client.get(f"{CONTEXTS_URL}/{context.id}").status_code == 404
    assert client.get(f"{CONTEXTS_URL}/{context.id}").status_code == 200


def test_recovery_of_one_account_leaves_another_untouched(
    client: TestClient, second_client: TestClient, email_sender: InMemoryEmailSender
) -> None:
    _register_two_people(client, second_client)
    assert _login(client, EMAIL_A, PASSWORD_A) == 200
    assert _login(second_client, EMAIL_B, PASSWORD_B) == 200

    forgot = client.post(
        FORGOT_URL, json={"email": EMAIL_A}, headers={"X-CSRF-Token": _csrf_token(client)}
    )
    assert forgot.status_code == 202
    assert [message.to for message in email_sender.sent_messages] == [EMAIL_A]
    token = _reset_token_from(email_sender.sent_messages[0].text_body)
    new_password = "a-brand-new-strong-password"
    reset = client.post(
        RESET_URL,
        json={"token": token, "new_password": new_password},
        headers={"X-CSRF-Token": _csrf_token(client)},
    )
    assert reset.status_code == 200

    assert _me_identifier(client) is None  # A's previous session was revoked...
    assert _me_identifier(second_client) == EMAIL_B  # ...B's was not
    assert _login(client, EMAIL_A, new_password) == 200
    assert _login(second_client, EMAIL_B, PASSWORD_B) == 200  # B's password is unchanged
    assert _login(second_client, EMAIL_B, new_password) == 401


def test_both_clients_use_the_same_isolated_test_database(
    client: TestClient,
    second_client: TestClient,
    auth_test_engine: Engine,
) -> None:
    """The second browser is a second application instance, but it must talk
    to the very same throwaway database as the first — never to the database
    configured for development or production."""
    assert client.app is not second_client.app

    seen_by_the_api = _database_seen_by_the_api()
    assert seen_by_the_api == auth_test_engine.url.database
    assert seen_by_the_api != get_postgres_settings().url.database

    # An account registered through one browser is visible to the other.
    assert _register(client, EMAIL_A, PASSWORD_A).status_code == 200
    assert _login(second_client, EMAIL_A, PASSWORD_A) == 200
