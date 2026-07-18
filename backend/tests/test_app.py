from fastapi import FastAPI
from fastapi.testclient import TestClient

from freyja_backend.main import create_app


def test_create_app_returns_fastapi_instance() -> None:
    app = create_app()
    assert isinstance(app, FastAPI)


def test_root_path_is_not_defined(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 404
