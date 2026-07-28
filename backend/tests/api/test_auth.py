import httpx2
import pytest
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

# Mirrors the real cross-site Render topology (AUTH-CSRF-CROSS-ORIGIN-001):
# frontend and backend on different onrender.com subdomains — different
# sites, not just different origins.
_PRODUCTION_ENV = {
    "FREYJA_ENVIRONMENT": "production",
    "FREYJA_RATE_LIMIT_HMAC_KEY": "a-real-secret-key-value",
    "FREYJA_FRONTEND_ORIGIN": "https://freyja-frontend-lwy0.onrender.com",
    "FREYJA_ALLOWED_HOSTS": "freyja-backend-lwy0.onrender.com",
}


def _set_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _PRODUCTION_ENV.items():
        monkeypatch.setenv(key, value)


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


def test_csrf_endpoint_returns_token_in_body_matching_cookie(client: TestClient) -> None:
    """The frontend runs on a different origin than the backend in
    production, so it cannot read the freyja_csrf cookie via document.cookie
    — the body is the only channel it can actually use to obtain the token."""
    response = client.get(CSRF_URL)

    body = response.json()
    assert body["status"] == "ok"
    assert body["csrf_token"]
    assert body["csrf_token"] == response.cookies.get("freyja_csrf")


def test_login_succeeds_using_csrf_token_read_from_response_body(
    client: TestClient, db_session: Session
) -> None:
    """Reproduces the real cross-origin topology end to end: the token used
    for the X-CSRF-Token header comes from the JSON body of GET /auth/csrf
    (what a frontend kept it in memory from), not from reading the cookie
    jar directly."""
    _create_owner(db_session)
    csrf_response = client.get(CSRF_URL)
    token_from_body = csrf_response.json()["csrf_token"]

    response = client.post(
        LOGIN_URL,
        json={"identifier": OWNER_IDENTIFIER, "password": OWNER_PASSWORD},
        headers={"X-CSRF-Token": token_from_body},
    )
    assert response.status_code == 200


def test_production_environment_cookies_are_secure_and_samesite_none(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cross-site production topology (separate onrender.com subdomains):
    both the CSRF and session cookies must be Secure and SameSite=None, or a
    real browser would refuse to send them back on the cross-site request in
    the first place.

    Uses an https:// base_url deliberately: httpx's cookie jar (like a real
    browser) refuses to resend a Secure cookie over a plain http:// request,
    so this is the one test in the module that cannot reuse the default
    http://localhost client — it would otherwise fail for the same reason a
    misconfigured Secure cookie would fail in a real browser."""
    _create_owner(db_session)
    _set_production_env(monkeypatch)

    with TestClient(client.app, base_url="https://localhost") as https_client:
        csrf_response = https_client.get(CSRF_URL)
        csrf_cookie = next(
            header
            for header in csrf_response.headers.get_list("set-cookie")
            if header.startswith("freyja_csrf=")
        )
        assert "secure" in csrf_cookie.lower()
        assert "samesite=none" in csrf_cookie.lower()

        token = csrf_response.json()["csrf_token"]
        login_response = https_client.post(
            LOGIN_URL,
            json={"identifier": OWNER_IDENTIFIER, "password": OWNER_PASSWORD},
            headers={"X-CSRF-Token": token},
        )
        assert login_response.status_code == 200
        session_cookie = next(
            header
            for header in login_response.headers.get_list("set-cookie")
            if header.startswith("freyja_session=")
        )
        assert "secure" in session_cookie.lower()
        assert "samesite=none" in session_cookie.lower()
        assert "httponly" in session_cookie.lower()


def test_login_missing_csrf_header_is_still_403_in_production(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """require_csrf stays enforced regardless of environment — the
    SameSite=None/Secure change only affects whether the browser sends the
    cookie back, never whether the server checks it."""
    _create_owner(db_session)
    _set_production_env(monkeypatch)

    client.get(CSRF_URL)
    response = client.post(
        LOGIN_URL, json={"identifier": OWNER_IDENTIFIER, "password": OWNER_PASSWORD}
    )
    assert response.status_code == 403


def test_login_divergent_csrf_header_is_still_403_in_production(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_owner(db_session)
    _set_production_env(monkeypatch)

    client.get(CSRF_URL)
    response = client.post(
        LOGIN_URL,
        json={"identifier": OWNER_IDENTIFIER, "password": OWNER_PASSWORD},
        headers={"X-CSRF-Token": "not-the-real-csrf-token"},
    )
    assert response.status_code == 403


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
