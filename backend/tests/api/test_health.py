import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from freyja_backend.core.config import Settings

EXPECTED_HEALTH_CONTRACT = {
    "status": "ok",
    "service": "Freyja 2.0 Backend",
    "version": "0.1.0",
    "environment": "development",
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
    settings = Settings()
    assert settings.environment == "test"


def test_invalid_environment_variable_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREYJA_ENVIRONMENT", "staging")
    with pytest.raises(ValidationError):
        Settings()
