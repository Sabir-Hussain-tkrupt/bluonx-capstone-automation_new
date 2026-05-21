"""
Shared fixtures for backend tests.

Uses real Supabase instance — signs in with the test admin user to get
a real JWT, then uses that token for authenticated endpoint tests.
"""

import os

import httpx
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

# Load backend/.env into os.environ before anything else so that
# os.getenv(...) below picks up TEST_ADMIN_EMAIL / TEST_ADMIN_PASSWORD.
# pydantic-settings reads .env into the Settings class only — it does
# not populate os.environ.
_BACKEND_ENV = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(_BACKEND_ENV)

from app.main import app  # noqa: E402
from app.core.config import settings  # noqa: E402
import app.main as _app_main  # noqa: E402

# The root `client` fixture starts the app via `with TestClient(app)`, which
# runs the FastAPI lifespan — and the lifespan calls start_scheduler(). Patch
# both lifecycle hooks to no-ops so a real APScheduler never runs during the
# test suite (the hourly job would otherwise fire against the real test DB).
_app_main.start_scheduler = lambda: None
_app_main.stop_scheduler = lambda: None


# ── Test user credentials (pre-created in Supabase) ─────────────────────
TEST_ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL")
TEST_ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD")
assert TEST_ADMIN_EMAIL and TEST_ADMIN_PASSWORD, (
    "TEST_ADMIN_EMAIL and TEST_ADMIN_PASSWORD must be set in backend/.env"
)


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
