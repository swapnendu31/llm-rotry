import pytest
from fastapi import FastAPI, Depends, Request
from fastapi.testclient import TestClient
from src.main import app
from src.helper.security import check_allowed_origin


class MockClientMiddleware:
    """ASGI middleware to simulate a specific client host for testing."""
    def __init__(self, asgi_app, host: str):
        self.asgi_app = asgi_app
        self.host = host

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            scope["client"] = (self.host, 50000)
        await self.asgi_app(scope, receive, send)


@pytest.fixture
def local_client():
    """TestClient simulating local connection (127.0.0.1)."""
    wrapped = MockClientMiddleware(app, "127.0.0.1")
    with TestClient(wrapped, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def remote_client():
    """TestClient simulating remote connection (e.g. public IP 198.51.100.1)."""
    wrapped = MockClientMiddleware(app, "198.51.100.1")
    with TestClient(wrapped, raise_server_exceptions=False) as c:
        yield c


# ============================================================================
# Swagger & OpenAPI Documentation Tests (Local Only)
# ============================================================================

def test_docs_local_access_success(local_client):
    """Local client can access /docs, /redoc, and /openapi.json."""
    resp_docs = local_client.get("/docs")
    assert resp_docs.status_code == 200
    assert "Swagger UI" in resp_docs.text

    resp_redoc = local_client.get("/redoc")
    assert resp_redoc.status_code == 200
    assert "ReDoc" in resp_redoc.text

    resp_schema = local_client.get("/openapi.json")
    assert resp_schema.status_code == 200
    assert resp_schema.json()["info"]["title"] == "LLM-rotry"


def test_docs_remote_access_forbidden(remote_client):
    """Remote client is rejected with 403 on docs and OpenAPI schema."""
    resp_docs = remote_client.get("/docs")
    assert resp_docs.status_code == 403
    assert "only accessible locally" in resp_docs.json()["detail"]

    resp_redoc = remote_client.get("/redoc")
    assert resp_redoc.status_code == 403
    assert "only accessible locally" in resp_redoc.json()["detail"]

    resp_schema = remote_client.get("/openapi.json")
    assert resp_schema.status_code == 403
    assert "only accessible locally" in resp_schema.json()["detail"]


def test_docs_x_forwarded_for_remote_forbidden(local_client):
    """Remote IP in X-Forwarded-For via local reverse proxy is also rejected."""
    headers = {"x-forwarded-for": "203.0.113.55, 127.0.0.1"}
    resp = local_client.get("/docs", headers=headers)
    assert resp.status_code == 403
    assert "only accessible locally" in resp.json()["detail"]


# ============================================================================
# Dashboard & Keys Tests (Local Access + Basic Auth)
# ============================================================================

def test_dashboard_unauthorized(local_client):
    """Accessing dashboard without auth returns 401 with WWW-Authenticate header."""
    resp = local_client.get("/dashboard")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Basic"

    resp_root = local_client.get("/")
    assert resp_root.status_code == 401


def test_dashboard_wrong_credentials(local_client):
    """Accessing dashboard with incorrect credentials returns 401."""
    resp = local_client.get("/dashboard", auth=("admin", "wrongpass"))
    assert resp.status_code == 401


def test_dashboard_authorized_local(local_client):
    """Accessing dashboard with valid credentials from localhost succeeds."""
    resp = local_client.get("/dashboard", auth=("admin", "admin"))
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" in resp.text or "<html" in resp.text


def test_dashboard_remote_forbidden_even_with_auth(remote_client):
    """Accessing dashboard from remote client is blocked with 403 even with correct credentials."""
    resp = remote_client.get("/dashboard", auth=("admin", "admin"))
    assert resp.status_code == 403
    assert "only accessible locally" in resp.json()["detail"]


def test_keys_api_unauthorized(local_client):
    """Accessing /keys REST API without auth returns 401."""
    resp = local_client.get("/keys")
    assert resp.status_code == 401


def test_keys_api_remote_forbidden_even_with_auth(remote_client):
    """Accessing /keys REST API from remote IP returns 403."""
    resp = remote_client.get("/keys", auth=("admin", "admin"))
    assert resp.status_code == 403
    assert "only accessible locally" in resp.json()["detail"]


def test_keys_api_authorized_local(monkeypatch, local_client):
    """Accessing /keys REST API locally with valid credentials succeeds."""
    monkeypatch.setattr("src.controller.controller_key.get_all_keys", lambda: [])
    resp = local_client.get("/keys", auth=("admin", "admin"))
    assert resp.status_code == 200
    assert resp.json() == []


# ============================================================================
# Runtime Rotation & Proxy Accessibility
# ============================================================================

def test_runtime_api_missing_auth_key(remote_client):
    """Calling /acquire or /proxy without Auth Key returns 401."""
    resp = remote_client.get("/acquire/openai")
    assert resp.status_code == 401
    assert "Invalid or missing Auth Key" in resp.json()["detail"]


def test_runtime_api_invalid_auth_key(remote_client):
    """Calling /acquire or /proxy with wrong Auth Key returns 401."""
    resp = remote_client.get("/acquire/openai", headers={"X-Auth-Key": "wrong-key"})
    assert resp.status_code == 401
    assert "Invalid or missing Auth Key" in resp.json()["detail"]


def test_runtime_api_success_with_x_auth_key(monkeypatch, remote_client):
    """Calling /acquire or /proxy with X-Auth-Key header succeeds."""
    monkeypatch.setattr(
        "src.controller.controller_run.get_key_from_redis",
        lambda provider, tokens=0: "sk-runtime-key",
    )
    resp = remote_client.get("/acquire/openai", headers={"X-Auth-Key": "rotator_secret_key_123"})
    assert resp.status_code == 200
    assert resp.json() == {"provider": "openai", "api_key": "sk-runtime-key"}


def test_runtime_api_success_with_bearer_token(monkeypatch, remote_client):
    """Calling /acquire or /proxy with Authorization: Bearer <key> succeeds."""
    monkeypatch.setattr(
        "src.controller.controller_run.get_key_from_redis",
        lambda provider, tokens=0: "sk-runtime-key",
    )
    resp = remote_client.get("/acquire/openai", headers={"Authorization": "Bearer rotator_secret_key_123"})
    assert resp.status_code == 200
    assert resp.json() == {"provider": "openai", "api_key": "sk-runtime-key"}


def test_runtime_api_success_with_x_api_key(monkeypatch, remote_client):
    """Calling /acquire or /proxy with X-API-Key header succeeds."""
    monkeypatch.setattr(
        "src.controller.controller_run.get_key_from_redis",
        lambda provider, tokens=0: "sk-runtime-key",
    )
    resp = remote_client.get("/acquire/openai", headers={"X-API-Key": "rotator_secret_key_123"})
    assert resp.status_code == 200
    assert resp.json() == {"provider": "openai", "api_key": "sk-runtime-key"}


# ============================================================================
# Origin Checking Helper
# ============================================================================

def test_check_allowed_origin_helper():
    """Verify check_allowed_origin correctly validates origins."""
    app_test = FastAPI()
    origin_dep = check_allowed_origin(["https://trusted-dashboard.com", "http://127.0.0.1"])

    @app_test.get("/test-origin", dependencies=[Depends(origin_dep)])
    def origin_endpoint():
        return {"status": "ok"}

    client = TestClient(app_test)

    # Allowed origin
    res_ok = client.get("/test-origin", headers={"Origin": "https://trusted-dashboard.com"})
    assert res_ok.status_code == 200

    # Disallowed origin
    res_bad = client.get("/test-origin", headers={"Origin": "https://malicious-site.com"})
    assert res_bad.status_code == 403
