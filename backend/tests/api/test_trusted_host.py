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


def test_disallowed_host_header_is_rejected_on_cors_preflight(client: TestClient) -> None:
    """TrustedHostMiddleware must be the outermost layer: if CORSMiddleware
    were registered last (and therefore outermost — Starlette wraps in
    reverse registration order), it would answer OPTIONS preflight requests
    directly and the Host check below it would never run."""
    response = client.options(
        "/api/v1/health",
        headers={
            "Host": "attacker.example.test",
            "Origin": "http://localhost:4200",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
