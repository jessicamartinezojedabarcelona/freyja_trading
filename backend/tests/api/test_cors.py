from fastapi.testclient import TestClient


def test_cors_allows_the_exact_configured_frontend_origin(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:4200"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:4200"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_rejects_an_origin_not_on_the_allow_list(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "https://evil.example.test"})
    # Starlette's CORSMiddleware simply omits the header for a disallowed
    # origin — the request itself still completes at the HTTP level (CORS is
    # enforced by the browser, not the server), but no origin is echoed back,
    # so a browser would block the response from being read by that origin.
    assert response.headers.get("access-control-allow-origin") != "https://evil.example.test"


def test_cors_preflight_only_allows_get_and_post(client: TestClient) -> None:
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:4200",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    allowed_methods = response.headers.get("access-control-allow-methods", "")
    assert "DELETE" not in allowed_methods


def test_cors_preflight_allows_declared_headers(client: TestClient) -> None:
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:4200",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )
    allowed_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "content-type" in allowed_headers
    assert "x-csrf-token" in allowed_headers
