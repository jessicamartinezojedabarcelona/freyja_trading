import httpx2
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from freyja_backend.application import auth_service
from freyja_backend.db.models import AuthUser, RateLimitAction

LOGIN_URL = "/api/v1/auth/login"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/auth/me"
CSRF_URL = "/api/v1/auth/csrf"

OWNER_IDENTIFIER = "owner@example.test"
OWNER_PASSWORD = "correct-horse-battery-staple"
WRONG_PASSWORD = "definitely-the-wrong-password"

GENERIC_LOGIN_ERROR = "Credenciales incorrectas."


def _create_owner(db_session: Session) -> None:
    auth_service.create_owner(db_session, identifier=OWNER_IDENTIFIER, password=OWNER_PASSWORD)
    db_session.commit()


def _csrf_token(client: TestClient) -> str:
    client.get(CSRF_URL)
    token = client.cookies.get("freyja_csrf")
    assert token is not None
    return token


def _login(
    client: TestClient, *, identifier: str = OWNER_IDENTIFIER, password: str = OWNER_PASSWORD
) -> httpx2.Response:
    csrf = _csrf_token(client)
    return client.post(
        LOGIN_URL,
        json={"identifier": identifier, "password": password},
        headers={"X-CSRF-Token": csrf},
    )


def test_me_without_session_is_401(client: TestClient) -> None:
    response = client.get(ME_URL)
    assert response.status_code == 401


def test_csrf_endpoint_sets_cookie_for_anonymous_client(client: TestClient) -> None:
    response = client.get(CSRF_URL)
    assert response.status_code == 200
    assert "freyja_csrf" in response.cookies


def test_csrf_endpoint_reuses_existing_cookie_value(client: TestClient) -> None:
    first = client.get(CSRF_URL)
    first_token = first.cookies.get("freyja_csrf")

    second = client.get(CSRF_URL)
    second_token = second.cookies.get("freyja_csrf")

    assert first_token == second_token


def test_csrf_endpoint_creates_no_session(client: TestClient) -> None:
    client.get(CSRF_URL)
    assert "freyja_session" not in client.cookies


def test_login_without_csrf_header_is_403(client: TestClient, db_session: Session) -> None:
    _create_owner(db_session)
    client.get(CSRF_URL)  # obtain csrf cookie, but don't send the header
    response = client.post(
        LOGIN_URL, json={"identifier": OWNER_IDENTIFIER, "password": OWNER_PASSWORD}
    )
    assert response.status_code == 403


def test_login_with_mismatched_csrf_header_is_403(client: TestClient, db_session: Session) -> None:
    _create_owner(db_session)
    client.get(CSRF_URL)
    response = client.post(
        LOGIN_URL,
        json={"identifier": OWNER_IDENTIFIER, "password": OWNER_PASSWORD},
        headers={"X-CSRF-Token": "not-the-real-csrf-token"},
    )
    assert response.status_code == 403


def test_login_success_returns_user_and_sets_session_cookie(
    client: TestClient, db_session: Session
) -> None:
    _create_owner(db_session)
    response = _login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["identifier"] == OWNER_IDENTIFIER
    assert set(body.keys()) == {"id", "identifier"}
    assert "freyja_session" in response.cookies


def test_login_response_never_contains_password_or_hash(
    client: TestClient, db_session: Session
) -> None:
    _create_owner(db_session)
    response = _login(client)

    raw_body = response.text
    assert OWNER_PASSWORD not in raw_body
    assert "argon2" not in raw_body
    assert "password_hash" not in raw_body


def test_session_cookie_is_httponly_and_strict(client: TestClient, db_session: Session) -> None:
    _create_owner(db_session)
    response = _login(client)

    set_cookie_headers = response.headers.get_list("set-cookie")
    session_cookie = next(h for h in set_cookie_headers if h.startswith("freyja_session="))
    assert "httponly" in session_cookie.lower()
    assert "samesite=strict" in session_cookie.lower()


def test_csrf_cookie_is_not_httponly(client: TestClient) -> None:
    response = client.get(CSRF_URL)

    set_cookie_headers = response.headers.get_list("set-cookie")
    csrf_cookie = next(h for h in set_cookie_headers if h.startswith("freyja_csrf="))
    assert "httponly" not in csrf_cookie.lower()


def test_login_wrong_password_is_generic_401(client: TestClient, db_session: Session) -> None:
    _create_owner(db_session)
    response = _login(client, password=WRONG_PASSWORD)

    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_LOGIN_ERROR
    assert WRONG_PASSWORD not in response.text


def test_login_unknown_identifier_is_same_generic_401(
    client: TestClient, db_session: Session
) -> None:
    _create_owner(db_session)
    response = _login(client, identifier="nobody@example.test")

    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_LOGIN_ERROR


def test_login_inactive_user_is_same_generic_401(client: TestClient, db_session: Session) -> None:
    _create_owner(db_session)
    user = db_session.execute(
        select(AuthUser).where(AuthUser.identifier == OWNER_IDENTIFIER)
    ).scalar_one()
    user.is_active = False
    db_session.commit()

    response = _login(client)

    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_LOGIN_ERROR


def test_login_rate_limited_after_max_failures(client: TestClient, db_session: Session) -> None:
    _create_owner(db_session)
    max_failures = auth_service.RATE_LIMITS[RateLimitAction.LOGIN][0]
    for _ in range(max_failures):
        response = _login(client, password=WRONG_PASSWORD)
        assert response.status_code == 401

    response = _login(client)
    assert response.status_code == 429


def test_me_with_valid_session_returns_current_user(
    client: TestClient, db_session: Session
) -> None:
    _create_owner(db_session)
    _login(client)

    response = client.get(ME_URL)
    assert response.status_code == 200
    assert response.json()["identifier"] == OWNER_IDENTIFIER


def test_logout_without_csrf_header_is_403(client: TestClient, db_session: Session) -> None:
    _create_owner(db_session)
    _login(client)

    response = client.post(LOGOUT_URL)
    assert response.status_code == 403


def test_logout_revokes_session(client: TestClient, db_session: Session) -> None:
    _create_owner(db_session)
    _login(client)
    csrf = client.cookies.get("freyja_csrf")
    assert csrf is not None

    logout_response = client.post(LOGOUT_URL, headers={"X-CSRF-Token": csrf})
    assert logout_response.status_code == 200

    me_response = client.get(ME_URL)
    assert me_response.status_code == 401


def test_logout_is_idempotent_without_existing_session(client: TestClient) -> None:
    csrf = _csrf_token(client)
    response = client.post(LOGOUT_URL, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200


def test_openapi_schema_exposes_csrf_endpoint(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/api/v1/auth/csrf" in schema["paths"]


def test_openapi_schema_never_exposes_password_hash(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    user_out_schema = schema["components"]["schemas"]["UserOut"]
    assert set(user_out_schema["properties"]) == {"id", "identifier"}
