import httpx2
from fastapi.testclient import TestClient

from freyja_backend.core.email import InMemoryEmailSender

REGISTER_URL = "/api/v1/auth/register"
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


def _register(
    client: TestClient, *, email: str = EMAIL, password: str = PASSWORD
) -> httpx2.Response:
    csrf = _csrf_token(client)
    return client.post(
        REGISTER_URL,
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": csrf},
    )


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


# --- registration: no email verification, account active immediately --------


def test_register_without_csrf_is_403(client: TestClient) -> None:
    client.get(CSRF_URL)
    response = client.post(REGISTER_URL, json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 403


def test_register_rejects_malformed_email_with_422(client: TestClient) -> None:
    response = _register(client, email="not-an-email")
    assert response.status_code == 422


def test_register_rejects_short_password_with_422(client: TestClient) -> None:
    response = _register(client, password="short")
    assert response.status_code == 422


def test_register_returns_generic_ack_and_sends_no_email(
    client: TestClient, email_sender: InMemoryEmailSender
) -> None:
    response = _register(client)
    assert response.status_code == 200
    assert response.json()["message"] == "Tu cuenta ha sido creada. Ya puedes iniciar sesión."
    assert PASSWORD not in response.text
    assert email_sender.sent_messages == []


def test_register_then_login_succeeds_immediately(client: TestClient) -> None:
    register_response = _register(client)
    assert register_response.status_code == 200

    login_response = _login(client)
    assert login_response.status_code == 200
    assert login_response.json()["identifier"] == EMAIL


def test_register_duplicate_email_returns_same_generic_ack(client: TestClient) -> None:
    first = _register(client)
    second = _register(client)  # already registered: safe no-op internally

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_register_response_is_identical_for_new_and_already_registered_accounts(
    client: TestClient,
) -> None:
    """The public /auth/register response (status + body) must not reveal
    whether the account already existed."""
    existing_email = "already-registered@freyja-test.dev"
    _register(client, email=existing_email)

    new_response = _register(client, email="brand-new@freyja-test.dev")
    duplicate_response = _register(client, email=existing_email)

    assert new_response.status_code == duplicate_response.status_code == 200
    assert new_response.json() == duplicate_response.json()


def test_login_wrong_password_is_generic_401(client: TestClient) -> None:
    _register(client)
    response = _login(client, password="definitely-the-wrong-password")
    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales incorrectas."


def test_openapi_schema_has_no_verify_email_path_or_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/api/v1/auth/verify-email" not in schema["paths"]
    assert "VerifyEmailRequest" not in schema["components"]["schemas"]


# --- forgot / reset password ----------------------------------------------------


def test_forgot_password_returns_same_generic_ack_regardless_of_account(
    client: TestClient,
) -> None:
    _register(client)

    existing = _forgot(client, EMAIL)
    unknown = _forgot(client, "nobody@freyja-test.dev")

    assert existing.status_code == unknown.status_code == 202
    assert existing.json() == unknown.json()


def test_forgot_password_without_csrf_is_403(client: TestClient) -> None:
    client.get(CSRF_URL)
    response = client.post(FORGOT_URL, json={"email": EMAIL})
    assert response.status_code == 403


def test_reset_password_end_to_end_revokes_sessions_and_allows_new_login(
    client: TestClient, email_sender: InMemoryEmailSender
) -> None:
    _register(client)
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


def test_reset_password_unknown_token_returns_token_invalid(client: TestClient) -> None:
    response = _reset(client, "not-a-real-token", "a-new-password-123456")
    assert response.status_code == 400
    assert response.json()["detail"] == "TOKEN_INVALID"


def test_reset_password_short_password_returns_422(
    client: TestClient, email_sender: InMemoryEmailSender
) -> None:
    _register(client)
    _forgot(client, EMAIL)
    reset_token = _extract_token_from_link(
        email_sender.sent_messages[-1].text_body, "/reset-password"
    )

    response = _reset(client, reset_token, "short")
    assert response.status_code == 422


def test_reset_password_response_never_contains_new_password_or_token(
    client: TestClient, email_sender: InMemoryEmailSender
) -> None:
    _register(client)
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
    for name in ("StatusOut", "RegisterRequest"):
        assert "token_hash" not in schemas[name]["properties"]
        assert "password_hash" not in schemas[name]["properties"]
