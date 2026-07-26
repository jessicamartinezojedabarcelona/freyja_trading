from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from freyja_backend.application import auth_service
from freyja_backend.db import deps as db_deps
from freyja_backend.main import create_app

CSRF_URL = "/api/v1/auth/csrf"
LOGIN_URL = "/api/v1/auth/login"

_TEST_USER_IDENTIFIER = "contracts-reader@example.test"
_TEST_USER_PASSWORD = "correct-horse-battery-staple"

_NEW_PREFIXES = ("/catalog", "/capabilities", "/execution-contexts")


def _login(client: TestClient, db_session: Session) -> None:
    auth_service.create_owner(
        db_session, identifier=_TEST_USER_IDENTIFIER, password=_TEST_USER_PASSWORD
    )
    db_session.commit()
    client.get(CSRF_URL)
    csrf = client.cookies.get("freyja_csrf")
    assert csrf is not None
    response = client.post(
        LOGIN_URL,
        json={"identifier": _TEST_USER_IDENTIFIER, "password": _TEST_USER_PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200


def test_new_endpoints_never_expose_write_methods() -> None:
    app = create_app()
    schema = app.openapi()
    write_methods = {"post", "put", "patch", "delete"}
    for path, operations in schema["paths"].items():
        if any(path.startswith(f"/api/v1{prefix}") for prefix in _NEW_PREFIXES):
            assert write_methods.isdisjoint(operations.keys()), (
                f"{path} exposes a write method {set(operations) & write_methods} — "
                "POINT1-API-001 is read-only"
            )


@contextmanager
def _unreachable_engine_override() -> Iterator[Engine]:
    # A real, genuinely unreachable connection target (invalid port on
    # loopback) — proves the fail-closed 500 path with an actual failed
    # connection attempt, never a mock standing in for it. Entered only
    # around the single call under test, after login has already used the
    # real engine, and always restored afterward.
    engine = create_engine(
        "postgresql+psycopg://freyja:wrong@127.0.0.1:1/does_not_matter",
        connect_args={"connect_timeout": 2},
    )
    previous = db_deps._engine_override
    db_deps.set_engine_override(engine)
    try:
        yield engine
    finally:
        db_deps.set_engine_override(previous)
        engine.dispose()


def test_persistence_failure_returns_generic_error_never_invented_data(db_session: Session) -> None:
    # raise_server_exceptions=False: an unhandled exception should surface as
    # the same generic 500 a real deployment (uvicorn, no debug mode) would
    # return — not re-raise into the test process the way TestClient does by
    # default, which would hide the actual fail-closed HTTP behaviour.
    app = create_app()
    with TestClient(
        app, base_url="http://localhost", raise_server_exceptions=False
    ) as non_raising_client:
        _login(non_raising_client, db_session)
        with _unreachable_engine_override():
            response = non_raising_client.get("/api/v1/catalog/instruments")
    assert response.status_code == 500
    # Starlette's default handler for an unhandled exception: plain text,
    # never SQL, connection strings, or any other internal detail.
    assert response.text == "Internal Server Error"
