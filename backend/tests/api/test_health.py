from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from freyja_backend.core.config import Settings
from freyja_backend.db import deps as db_deps

EXPECTED_HEALTH_CONTRACT = {
    "status": "ok",
    "service": "Freyja 2.0 Backend",
    "version": "0.1.0",
    # The whole suite is forced to FREYJA_ENVIRONMENT=test (see conftest.py's
    # pytest_configure), regardless of whatever a developer's local .env says.
    "environment": "test",
}


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_matches_contract(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.json() == EXPECTED_HEALTH_CONTRACT


def test_openapi_documents_health_response_model(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    health_response_schema = schema["components"]["schemas"]["HealthResponse"]
    assert set(health_response_schema["properties"]) == {
        "status",
        "service",
        "version",
        "environment",
    }


def test_valid_environment_variable_changes_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREYJA_ENVIRONMENT", "test")
    settings = Settings(_env_file=None)
    assert settings.environment == "test"


def test_invalid_environment_variable_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREYJA_ENVIRONMENT", "staging")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_readiness_returns_200_when_database_is_reachable(
    client: TestClient, auth_test_engine: Engine
) -> None:
    del auth_test_engine  # ensures the real test-DB engine override is active
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.fixture
def unreachable_db_engine(auth_test_engine: Engine) -> Iterator[Engine]:
    """A real Engine object pointed at a host that cannot be connected to —
    a test double for "PostgreSQL is down", never a real dependency touched
    or damaged. A short connect_timeout keeps the test fast instead of
    hanging on the OS-level TCP timeout. Restores the override back to the
    real test-database engine afterward, so later tests are unaffected."""
    broken_engine = create_engine(
        "postgresql+psycopg://nobody:nothing@127.0.0.1:1/does_not_exist",
        connect_args={"connect_timeout": 1},
    )
    db_deps.set_engine_override(broken_engine)
    try:
        yield broken_engine
    finally:
        db_deps.set_engine_override(auth_test_engine)
        broken_engine.dispose()


def test_readiness_returns_503_when_database_is_unreachable(
    client: TestClient, unreachable_db_engine: Engine
) -> None:
    del unreachable_db_engine
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503


def test_readiness_failure_never_leaks_connection_details(
    client: TestClient, unreachable_db_engine: Engine
) -> None:
    del unreachable_db_engine
    response = client.get("/api/v1/health/ready")
    body_text = response.text
    assert "nobody" not in body_text
    assert "nothing" not in body_text
    assert "does_not_exist" not in body_text
    assert "127.0.0.1:1" not in body_text


def test_health_liveness_still_succeeds_when_database_is_unreachable(
    client: TestClient, unreachable_db_engine: Engine
) -> None:
    """Liveness must stay independent of the database: it reports the process
    is up, not that every dependency is healthy — that is readiness's job."""
    del unreachable_db_engine
    response = client.get("/api/v1/health")
    assert response.status_code == 200
