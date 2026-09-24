import httpx2
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from freyja_backend.application import auth_service
from freyja_backend.core.email import InMemoryEmailSender

FORGOT_URL = "/api/v1/auth/forgot-password"
RESET_URL = "/api/v1/auth/reset-password"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
CSRF_URL = "/api/v1/auth/csrf"

EMAIL = "newuser@freyja-test.dev"
PASSWORD = "correct-horse-battery-staple"


def _csrf_token(client: TestClient) -> str:
    client.get(CSRF_URL)
    token = client.cookies.get("freyja_csrf")
    assert token is not None
    return token


def _extract_token_from_link(link_text: str, path: str) -> str:
    marker = f"{path}#token="
    start = link_text.index(marker) + len(marker)
    end = link_text.find("\n", start)
    return link_text[start:end] if end != -1 else link_text[start:]


def _create_owner(db_session: Session, *, email: str = EMAIL, password: str = PASSWORD) -> None:
    # The only supported way to provision an account (AUTH-PRIVATE-ACCESS-001):
    # the administrative bootstrap. There is no public registration.
    auth_service.create_owner(db_session, identifier=email, password=password)
    db_session.commit()


def _forgot(client: TestClient, email: str = EMAIL) -> httpx2.Response:
    csrf = _csrf_token(client)
    return client.post(FORGOT_URL, json={"email": email}, headers={"X-CSRF-Token": csrf})


def _reset(client: TestClient, token: str, new_password: str) -> httpx2.Response:
    csrf = _csrf_token(client)
    return client.post(
        RESET_URL,
        json={"token": token, "new_password": new_password},
        headers={"X-CSRF-Token": csrf},
    )


def _login(client: TestClient, *, email: str = EMAIL, password: str = PASSWORD) -> httpx2.Response:
    csrf = _csrf_token(client)
    return client.post(
        LOGIN_URL, json={"identifier": email, "password": password}, headers={"X-CSRF-Token": csrf}
    )


def test_login_wrong_password_is_generic_401(client: TestClient, db_session: Session) -> None:
    _create_owner(db_session)
    response = _login(client, password="definitely-the-wrong-password")
    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales incorrectas."


def test_openapi_schema_has_no_verify_email_path_or_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/api/v1/auth/verify-email" not in schema["paths"]
    assert "VerifyEmailRequest" not in schema["components"]["schemas"]


# --- forgot / reset password ----------------------------------------------------


def test_forgot_password_returns_same_generic_ack_regardless_of_account(
    client: TestClient, db_session: Session
) -> None:
    _create_owner(db_session)

    existing = _forgot(client, EMAIL)
    unknown = _forgot(client, "nobody@freyja-test.dev")

    assert existing.status_code == unknown.status_code == 202
    assert existing.json() == unknown.json()


def test_forgot_password_without_csrf_is_403(client: TestClient) -> None:
    client.get(CSRF_URL)
    response = client.post(FORGOT_URL, json={"email": EMAIL})
    assert response.status_code == 403


def test_reset_password_end_to_end_revokes_sessions_and_allows_new_login(
    client: TestClient, db_session: Session, email_sender: InMemoryEmailSender
) -> None:
    _create_owner(db_session)
    _login(client)
    assert client.get(ME_URL).status_code == 200

    _forgot(client, EMAIL)
    reset_token = _extract_token_from_link(
        email_sender.sent_messages[0].text_body, "/reset-password"
    )

    new_password = "a-brand-new-strong-password"
    reset_response = _reset(client, reset_token, new_password)
    assert reset_response.status_code == 200

    # the session that existed before the reset must now be rejected
    assert client.get(ME_URL).status_code == 401

    # old password no longer works, new one does
    assert _login(client, password=PASSWORD).status_code == 401
    assert _login(client, password=new_password).status_code == 200


def test_reset_password_of_one_account_leaves_another_account_untouched(
    client: TestClient,
    second_client: TestClient,
    db_session: Session,
    email_sender: InMemoryEmailSender,
) -> None:
    """AUTH-PRIVATE-ACCESS-001: accounts are independent, recovery included."""
    other_email = "other-account@freyja-test.dev"
    other_password = "another-long-and-different-password"
    _create_owner(db_session)
    _create_owner(db_session, email=other_email, password=other_password)
    assert _login(client).status_code == 200
    assert _login(second_client, email=other_email, password=other_password).status_code == 200

    _forgot(client, EMAIL)
    reset_token = _extract_token_from_link(
        email_sender.sent_messages[0].text_body, "/reset-password"
    )
    new_password = "a-brand-new-strong-password"
    assert _reset(client, reset_token, new_password).status_code == 200

    assert len(email_sender.sent_messages) == 1  # only the recovering account
    assert client.get(ME_URL).status_code == 401  # its session was revoked...
    assert second_client.get(ME_URL).status_code == 200  # ...the other one was not
    assert _login(client, password=new_password).status_code == 200
    # The other account keeps its own password; the new one does not open it.
    assert _login(second_client, email=other_email, password=other_password).status_code == 200
    assert _login(second_client, email=other_email, password=new_password).status_code == 401


def test_reset_password_unknown_token_returns_token_invalid(client: TestClient) -> None:
    response = _reset(client, "not-a-real-token", "a-new-password-123456")
    assert response.status_code == 400
    assert response.json()["detail"] == "TOKEN_INVALID"


def test_reset_password_short_password_returns_422(
    client: TestClient, db_session: Session, email_sender: InMemoryEmailSender
) -> None:
    _create_owner(db_session)
    _forgot(client, EMAIL)
    reset_token = _extract_token_from_link(
        email_sender.sent_messages[-1].text_body, "/reset-password"
    )

    response = _reset(client, reset_token, "short")
    assert response.status_code == 422


def test_reset_password_response_never_contains_new_password_or_token(
    client: TestClient, db_session: Session, email_sender: InMemoryEmailSender
) -> None:
    _create_owner(db_session)
    _forgot(client, EMAIL)
    reset_token = _extract_token_from_link(
        email_sender.sent_messages[-1].text_body, "/reset-password"
    )

    new_password = "a-brand-new-strong-password"
    response = _reset(client, reset_token, new_password)

    assert new_password not in response.text
    assert reset_token not in response.text


def test_openapi_schema_never_exposes_token_hashes(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    schemas = schema["components"]["schemas"]
    for name in ("StatusOut", "ForgotPasswordRequest", "ResetPasswordRequest"):
        assert "token_hash" not in schemas[name]["properties"]
        assert "password_hash" not in schemas[name]["properties"]
