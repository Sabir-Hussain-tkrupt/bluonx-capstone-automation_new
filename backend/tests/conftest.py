"""
Shared fixtures for backend tests.

Uses real Supabase instance — signs in with the test admin user to get
a real JWT, then uses that token for authenticated endpoint tests.
"""

import os

import httpx
import pytest
from fastapi.testclient import TestClient

# Ensure the backend .env is loaded before importing app modules
os.environ.setdefault("DOTENV_PATH", os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.main import app  # noqa: E402
from app.core.config import settings  # noqa: E402


# ── Test user credentials (pre-created in Supabase) ─────────────────────
TEST_ADMIN_EMAIL = "admin@bluonx.dev"
TEST_ADMIN_PASSWORD = "TestPassword123!"


@pytest.fixture(scope="session")
def supabase_url() -> str:
    return settings.SUPABASE_URL


@pytest.fixture(scope="session")
def admin_jwt(supabase_url: str) -> str:
    """
    Sign in as the test admin user via Supabase Auth REST API.
    Returns a valid JWT access token for the session.
    """
    url = f"{supabase_url}/auth/v1/token?grant_type=password"
    resp = httpx.post(
        url,
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD},
        headers={
            "apikey": settings.SUPABASE_JWT_SECRET.split("==")[0][:20] if False else _get_anon_key(),
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    # If the above approach doesn't work with anon key, use the GoTrue endpoint directly
    if resp.status_code != 200:
        # Fallback: use service role key to sign in
        resp = httpx.post(
            url,
            json={"email": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD},
            headers={
                "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                "Content-Type": "application/json",
            },
            timeout=15,
        )

    assert resp.status_code == 200, f"Failed to sign in test user: {resp.status_code} {resp.text}"
    data = resp.json()
    token = data.get("access_token")
    assert token, f"No access_token in response: {data}"
    return token


def _get_anon_key() -> str:
    """Read anon key from frontend .env (since backend only has service_role)."""
    frontend_env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    if os.path.exists(frontend_env):
        with open(frontend_env) as f:
            for line in f:
                if line.startswith("VITE_SUPABASE_ANON_KEY="):
                    return line.split("=", 1)[1].strip()
    # Fallback: use the service role key (works but less ideal)
    return settings.SUPABASE_SERVICE_ROLE_KEY


@pytest.fixture(scope="session")
def client() -> TestClient:
    """FastAPI TestClient with Supabase client initialized via lifespan."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth_headers(admin_jwt: str) -> dict[str, str]:
    """Authorization headers with a valid admin JWT."""
    return {"Authorization": f"Bearer {admin_jwt}"}
