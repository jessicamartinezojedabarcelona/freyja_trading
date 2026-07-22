from fastapi.testclient import TestClient


def test_allowed_host_succeeds(client: TestClient) -> None:
    # The `client` fixture already uses base_url="http://localhost", which is
    # in the default allow-list ("localhost,127.0.0.1") — this just makes
    # that assumption explicit and pins its behavior.
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_disallowed_host_header_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Host": "attacker.example.test"})
    assert response.status_code == 400
