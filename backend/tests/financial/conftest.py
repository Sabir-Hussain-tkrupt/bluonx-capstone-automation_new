"""Shared fixtures for the financial-module router tests.

`fin_client(db, user)` returns a TestClient with `get_supabase` → the MemDB and
`get_current_active_user` → the given identity. No live Supabase, no JWT.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app

ADMIN_ID = str(uuid4())
PM_ID = str(uuid4())
FM_ID = str(uuid4())
FIN_ID = str(uuid4())


def identity(user_id: str, role: str = "project_manager", roles: list[str] | None = None,
             is_employee: bool = True) -> dict:
    return {
        "user_id": user_id,
        "email": f"{user_id[:8]}@example.test",
        "full_name": "Test User",
        "role": role,
        "is_active": True,
        "roles": sorted(set((roles or []) + [role])),
        "is_employee": is_employee,
    }


ADMIN = identity(ADMIN_ID, "admin")
PM = identity(PM_ID, "project_manager")
FIELD_MANAGER = identity(FM_ID, "project_manager", ["field_manager"])
FINANCE = identity(FIN_ID, "project_manager", ["finance"])


@pytest.fixture
def fin_client():
    clients = []

    def _make(db, user: dict = ADMIN) -> TestClient:
        app.dependency_overrides[get_supabase] = lambda: db
        app.dependency_overrides[get_current_active_user] = lambda: user
        tc = TestClient(app)
        tc.db = db
        clients.append(tc)
        return tc

    yield _make
    app.dependency_overrides.pop(get_supabase, None)
    app.dependency_overrides.pop(get_current_active_user, None)
