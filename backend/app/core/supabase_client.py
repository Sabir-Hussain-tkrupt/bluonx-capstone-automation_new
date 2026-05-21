"""
Global Supabase admin client (service_role key).

Created once in FastAPI lifespan, injected via Depends().
Safe for concurrent async requests — httpx.AsyncClient is task-safe
and the service_role key is stateless (no session bleed).
"""

from fastapi import Request
from supabase import Client, create_client

# Module-level singleton. Populated by init_supabase() at app startup so
# non-request contexts (background jobs) can reach the client without a Request.
_client: Client | None = None


def init_supabase(url: str, service_role_key: str) -> Client:
    """Create the global Supabase client. Called once in FastAPI lifespan."""
    global _client
    _client = create_client(url, service_role_key)
    return _client


def get_supabase(request: Request) -> Client:
    """FastAPI dependency — injects the global Supabase client from app.state."""
    return request.app.state.supabase


def get_supabase_client() -> Client:
    """Module-level accessor for non-request contexts (e.g. scheduled jobs)."""
    if _client is None:
        raise RuntimeError("Supabase client not initialized")
    return _client
