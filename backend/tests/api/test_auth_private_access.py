"""AUTH-PRIVATE-ACCESS-001: regression tests for private access.

Freyja 2.0 is private: there is no public self-registration (hiding the link
in the UI would not be enough), but several authorized accounts can exist,
provisioned locally by Jessica. Each account has its own credentials and
sessions; the catalog and market data are shared.

These tests deliberately assert what an *anonymous visitor* cannot do
(create an account, leaving no new row). They do not forbid a future,
authenticated administration route — that would need its own task.
"""

from pathlib import Path

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

SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "freyja_backend"

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/auth/me"
CSRF_URL = "/api/v1/auth/csrf"
FORGOT_URL = "/api/v1/auth/forgot-password"
RESET_URL = "/api/v1/auth/reset-password"
INSTRUMENTS_URL = "/api/v1/catalog/instruments"
VENUES_URL = "/api/v1/catalog/venues"
DATA_SOURCES_URL = "/api/v1/catalog/data-sources"
CAPABILITIES_URL = "/api/v1/capabilities"

# Two authorized accounts (fictitious test data only — no real account is ever
# provisioned by the tests).
ACCOUNT_A = "account-a@freyja-test.dev"
PASSWORD_A = "correct-horse-battery-staple"
ACCOUNT_B = "account-b@freyja-test.dev"
PASSWORD_B = "another-long-and-different-password"

INTRUDER_EMAIL = "intruder@freyja-test.dev"
INTRUDER_PASSWORD = "a-perfectly-valid-intruder-password"
REGISTRATION_PAYLOAD = {"email": INTRUDER_EMAIL, "password": INTRUDER_PASSWORD}


def _csrf_token(client: TestClient) -> str:
    client.get(CSRF_URL)
    token = client.cookies.get("freyja_csrf")
    assert token is not None
    return token


def _provision(db_session: Session, identifier: str, password: str) -> None:
    """The local administrative path — the only way an account is created."""
    auth_service.create_owner(db_session, identifier=identifier, password=password)
    db_session.commit()


def _count_users(db_session: Session) -> int:
    return db_session.execute(select(func.count()).select_from(AuthUser)).scalar_one()


def _login(client: TestClient, identifier: str, password: str) -> int:
    csrf = _csrf_token(client)
    response = client.post(
        LOGIN_URL,
        json={"identifier": identifier, "password": password},
        headers={"X-CSRF-Token": csrf},
    )
    return response.status_code


def _logout(client: TestClient) -> int:
    csrf = _csrf_token(client)
    return client.post(LOGOUT_URL, headers={"X-CSRF-Token": csrf}).status_code


def _me_identifier(client: TestClient) -> str | None:
    response = client.get(ME_URL)
    if response.status_code != 200:
        return None
    identifier: str = response.json()["identifier"]
    return identifier


def _reset_token_from(link_text: str) -> str:
    marker = "/reset-password#token="
    start = link_text.index(marker) + len(marker)
    end = link_text.find("\n", start)
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


def _assert_refused(status_code: int) -> None:
    """An anonymous request that would create an account must be turned away
    (client error) — whatever the exact code, never accepted."""
    assert 400 <= status_code < 500, status_code


# --- anonymous visitors cannot create accounts --------------------------------


def test_anonymous_register_post_creates_no_account(
    client: TestClient, db_session: Session
) -> None:
    csrf = _csrf_token(client)

    response = client.post(REGISTER_URL, json=REGISTRATION_PAYLOAD, headers={"X-CSRF-Token": csrf})

    _assert_refused(response.status_code)
    assert _count_users(db_session) == 0
    assert INTRUDER_PASSWORD not in response.text


def test_anonymous_register_post_without_csrf_creates_no_account(
    client: TestClient, db_session: Session
) -> None:
    client.get(CSRF_URL)

    response = client.post(REGISTER_URL, json=REGISTRATION_PAYLOAD)

    _assert_refused(response.status_code)
    assert _count_users(db_session) == 0


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
def test_anonymous_register_path_accepts_no_method(
    client: TestClient, db_session: Session, method: str
) -> None:
    response = client.request(method, REGISTER_URL, json=REGISTRATION_PAYLOAD)

    _assert_refused(response.status_code)
    assert _count_users(db_session) == 0


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/signup",
        "/api/v1/auth/sign-up",
        "/api/v1/auth/registration",
        "/api/v1/register",
        "/api/v1/users",
        "/register",
    ],
)
def test_no_known_public_route_creates_an_account(
    client: TestClient, db_session: Session, path: str
) -> None:
    csrf = _csrf_token(client)

    response = client.post(path, json=REGISTRATION_PAYLOAD, headers={"X-CSRF-Token": csrf})

    _assert_refused(response.status_code)
    assert _count_users(db_session) == 0


def test_recovery_of_an_unknown_identifier_creates_no_account_and_reveals_nothing(
    client: TestClient, db_session: Session, email_sender: InMemoryEmailSender
) -> None:
    """Password recovery must not become a back door for account creation,
    and must answer identically whether or not the account exists."""
    _provision(db_session, ACCOUNT_A, PASSWORD_A)
    csrf = _csrf_token(client)

    known = client.post(FORGOT_URL, json={"email": ACCOUNT_A}, headers={"X-CSRF-Token": csrf})
    unknown = client.post(
        FORGOT_URL, json={"email": INTRUDER_EMAIL}, headers={"X-CSRF-Token": csrf}
    )
    bad_reset = client.post(
        RESET_URL,
        json={"token": "not-a-real-token", "new_password": INTRUDER_PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert bad_reset.status_code == 400
    assert len(email_sender.sent_messages) == 1  # only the real account got a link
    assert _count_users(db_session) == 1


def test_valid_recovery_works_for_an_existing_account(
    client: TestClient, db_session: Session, email_sender: InMemoryEmailSender
) -> None:
    """The happy path for a real account: link by email, single-use token,
    new password, previous session revoked — and no account is created."""
    _provision(db_session, ACCOUNT_A, PASSWORD_A)
    assert _login(client, ACCOUNT_A, PASSWORD_A) == 200
    csrf = _csrf_token(client)

    forgot = client.post(FORGOT_URL, json={"email": ACCOUNT_A}, headers={"X-CSRF-Token": csrf})

    assert forgot.status_code == 202
    assert len(email_sender.sent_messages) == 1
    message = email_sender.sent_messages[0]
    assert message.to == ACCOUNT_A
    token = _reset_token_from(message.text_body)

    new_password = "a-brand-new-strong-password"
    reset = client.post(
        RESET_URL,
        json={"token": token, "new_password": new_password},
        headers={"X-CSRF-Token": csrf},
    )

    assert reset.status_code == 200
    assert token not in reset.text
    assert new_password not in reset.text
    assert _me_identifier(client) is None  # the session from before the reset is revoked
    assert _login(client, ACCOUNT_A, PASSWORD_A) == 401
    assert _login(client, ACCOUNT_A, new_password) == 200
    assert _count_users(db_session) == 1

    reuse = client.post(
        RESET_URL,
        json={"token": token, "new_password": "yet-another-long-password"},
        headers={"X-CSRF-Token": _csrf_token(client)},
    )
    assert reuse.status_code == 400  # single use


# --- no code path can create a self-registered account ----------------------


def test_auth_service_exposes_no_anonymous_registration_function() -> None:
    """The retired self-service function is gone; provisioning is
    `create_owner`, reachable only from the local administrative script."""
    assert not hasattr(auth_service, "register_user")


def test_no_production_code_writes_self_registration_records() -> None:
    """UserOrigin.SELF_REGISTRATION and RateLimitAction.REGISTER remain in
    the enums only for the existing database constraints and historical rows.
    Nothing in production code may reference them as a value to write."""
    offenders = [
        str(path.relative_to(SRC_DIR))
        for path in SRC_DIR.rglob("*.py")
        if "__pycache__" not in path.parts
        and any(
            token in path.read_text(encoding="utf-8")
            for token in ("UserOrigin.SELF_REGISTRATION", "RateLimitAction.REGISTER")
        )
    ]
    assert offenders == []


# --- several authorized accounts, provisioned locally -------------------------


def test_both_clients_use_the_same_isolated_test_database(
    client: TestClient,
    second_client: TestClient,
    auth_test_engine: Engine,
    db_session: Session,
) -> None:
    """The second browser is a second application instance, but it must talk
    to the very same throwaway database as the first — never to the database
    configured for development or production."""
    assert client.app is not second_client.app

    seen_by_the_api = _database_seen_by_the_api()
    assert seen_by_the_api == auth_test_engine.url.database
    assert seen_by_the_api != get_postgres_settings().url.database

    # And what is written through the isolated engine is what both read.
    _provision(db_session, ACCOUNT_A, PASSWORD_A)
    assert _login(client, ACCOUNT_A, PASSWORD_A) == 200
    assert _login(second_client, ACCOUNT_A, PASSWORD_A) == 200


def test_two_distinct_accounts_can_be_provisioned(db_session: Session) -> None:
    _provision(db_session, ACCOUNT_A, PASSWORD_A)
    _provision(db_session, ACCOUNT_B, PASSWORD_B)

    users = db_session.execute(select(AuthUser).order_by(AuthUser.identifier)).scalars().all()
    assert [user.identifier for user in users] == [ACCOUNT_A, ACCOUNT_B]
    assert {user.created_via for user in users} == {UserOrigin.ADMIN_BOOTSTRAP}
    assert all(user.is_active for user in users)
    # Independent credentials: separate salted hashes, never the plaintext.
    assert users[0].password_hash != users[1].password_hash
    assert PASSWORD_A not in users[0].password_hash
    assert PASSWORD_B not in users[1].password_hash


def test_duplicate_provisioning_is_rejected_and_never_overwrites_the_password(
    client: TestClient, db_session: Session
) -> None:
    _provision(db_session, ACCOUNT_A, PASSWORD_A)

    with pytest.raises(auth_service.OwnerAlreadyExistsError):
        auth_service.create_owner(db_session, identifier=ACCOUNT_A, password=PASSWORD_B)
    # Same identifier once normalized (case and surrounding whitespace).
    with pytest.raises(auth_service.OwnerAlreadyExistsError):
        auth_service.create_owner(
            db_session, identifier=f"  {ACCOUNT_A.upper()} ", password=PASSWORD_B
        )

    assert _count_users(db_session) == 1
    assert _login(client, ACCOUNT_A, PASSWORD_B) == 401
    assert _login(client, ACCOUNT_A, PASSWORD_A) == 200


def test_two_accounts_have_independent_sessions(
    client: TestClient, second_client: TestClient, db_session: Session
) -> None:
    _provision(db_session, ACCOUNT_A, PASSWORD_A)
    _provision(db_session, ACCOUNT_B, PASSWORD_B)

    assert _login(client, ACCOUNT_A, PASSWORD_A) == 200
    assert _login(second_client, ACCOUNT_B, PASSWORD_B) == 200

    # Each browser sees only its own account.
    assert _me_identifier(client) == ACCOUNT_A
    assert _me_identifier(second_client) == ACCOUNT_B

    # Ending A's session leaves B's untouched, and vice versa.
    assert _logout(client) == 200
    assert _me_identifier(client) is None
    assert _me_identifier(second_client) == ACCOUNT_B

    assert _logout(second_client) == 200
    assert _me_identifier(second_client) is None


def test_credentials_are_independent_per_account(
    client: TestClient, second_client: TestClient, db_session: Session
) -> None:
    """Locking out one account with failed attempts must not affect another,
    and one account's password never opens the other."""
    _provision(db_session, ACCOUNT_A, PASSWORD_A)
    _provision(db_session, ACCOUNT_B, PASSWORD_B)

    assert _login(client, ACCOUNT_B, PASSWORD_A) == 401  # A's password is not B's

    for _ in range(auth_service.RATE_LIMITS[RateLimitAction.LOGIN][0]):
        assert _login(client, ACCOUNT_A, "definitely-the-wrong-password") == 401
    assert _login(client, ACCOUNT_A, PASSWORD_A) == 429  # A is throttled...
    assert _login(second_client, ACCOUNT_B, PASSWORD_B) == 200  # ...B is not


def test_both_accounts_see_the_same_shared_catalog_data(
    client: TestClient, second_client: TestClient, db_session: Session
) -> None:
    _provision(db_session, ACCOUNT_A, PASSWORD_A)
    _provision(db_session, ACCOUNT_B, PASSWORD_B)
    assert _login(client, ACCOUNT_A, PASSWORD_A) == 200
    assert _login(second_client, ACCOUNT_B, PASSWORD_B) == 200

    for url in (INSTRUMENTS_URL, VENUES_URL, DATA_SOURCES_URL, CAPABILITIES_URL):
        seen_by_a = client.get(url)
        seen_by_b = second_client.get(url)
        assert seen_by_a.status_code == seen_by_b.status_code == 200, url
        assert seen_by_a.json() == seen_by_b.json(), url

    # The shared catalog is really there (seeded), so the equality is not
    # just "both empty".
    assert client.get(INSTRUMENTS_URL).json()["total"] > 0


# --- existing accounts keep working -------------------------------------------


def test_registration_attempts_cannot_touch_existing_accounts(
    client: TestClient, db_session: Session
) -> None:
    _provision(db_session, ACCOUNT_A, PASSWORD_A)
    _provision(db_session, ACCOUNT_B, PASSWORD_B)
    csrf = _csrf_token(client)

    new_identity = client.post(
        REGISTER_URL, json=REGISTRATION_PAYLOAD, headers={"X-CSRF-Token": csrf}
    )
    # An existing identifier with a different password must never overwrite
    # or re-provision that account.
    takeover = client.post(
        REGISTER_URL,
        json={"email": ACCOUNT_A, "password": INTRUDER_PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )

    _assert_refused(new_identity.status_code)
    _assert_refused(takeover.status_code)
    assert _count_users(db_session) == 2
    assert _login(client, INTRUDER_EMAIL, INTRUDER_PASSWORD) == 401
    assert _login(client, ACCOUNT_A, INTRUDER_PASSWORD) == 401
    assert _login(client, ACCOUNT_A, PASSWORD_A) == 200
    assert _login(client, ACCOUNT_B, PASSWORD_B) == 200


def test_existing_account_login_session_and_logout_still_work(
    client: TestClient, db_session: Session
) -> None:
    _provision(db_session, ACCOUNT_A, PASSWORD_A)

    assert _login(client, ACCOUNT_A, PASSWORD_A) == 200
    assert _me_identifier(client) == ACCOUNT_A
    assert _logout(client) == 200
    assert _me_identifier(client) is None
