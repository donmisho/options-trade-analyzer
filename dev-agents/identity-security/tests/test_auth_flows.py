"""
Auth flow validation tests.
Uses httpx (async) to test API endpoints directly.
No browser automation needed — these are API-level tests.

Prerequisites:
- Backend running at https://127.0.0.1:8000
- Entra app registration configured
- Database accessible

Note: Tests that require a real Entra login (callback with real code)
are marked as integration tests and skipped in CI. They run in diagnostic mode.
"""
import httpx
import pytest

BASE_URL = "https://127.0.0.1:8000"

@pytest.fixture
def client():
    return httpx.AsyncClient(base_url=BASE_URL, verify=False)

@pytest.mark.asyncio
async def test_unauthenticated_me(client):
    """GET /auth/me without cookie returns 401"""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_login_redirect(client):
    """GET /auth/login redirects to Entra authorize URL"""
    response = await client.get("/api/v1/auth/login", follow_redirects=False)
    assert response.status_code in (302, 307)
    location = response.headers.get("location", "")
    assert "login.microsoftonline.com" in location
    assert "client_id=" in location
    assert "response_type=code" in location
    assert "code_challenge=" in location
    assert "state=" in location

@pytest.mark.asyncio
async def test_login_invalid_provider(client):
    """GET /auth/login?provider=invalid returns 400"""
    response = await client.get("/api/v1/auth/login?provider=invalid")
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_logout_without_session(client):
    """POST /auth/logout without session returns 401 or 200 (graceful)"""
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code in (200, 401)

@pytest.mark.asyncio
async def test_session_status_unauthenticated(client):
    """GET /auth/session/status without cookie returns authenticated=false"""
    response = await client.get("/api/v1/auth/session/status")
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is False

@pytest.mark.asyncio
async def test_schwab_requires_auth(client):
    """Schwab status endpoint requires user session"""
    response = await client.get("/api/v1/auth/schwab/status")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_health_no_auth(client):
    """Health endpoint accessible without auth"""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
