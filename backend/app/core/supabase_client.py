"""
Global Supabase admin client (service_role key).

Created once in FastAPI lifespan, injected via Depends().
Safe for concurrent async requests — httpx.AsyncClient is task-safe
and the service_role key is stateless (no session bleed).
"""

from fastapi import Request
from supabase import Client, create_client


def init_supabase(url: str, service_role_key: str) -> Client:
    """Create the global Supabase client. Called once in FastAPI lifespan."""
    return create_client(url, service_role_key)


def get_supabase(request: Request) -> Client:
    """FastAPI dependency — injects the global Supabase client from app.state."""
    return request.app.state.supabase
