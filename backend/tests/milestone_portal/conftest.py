"""
Fixtures for the milestone check-in (Phase 10.2) test suite.

Unlike the bid vendor-auth suite (which hits live Supabase), these tests run
against an in-memory `FakeDB` double so they exercise the service/gate/job
logic without a database or the deployed RPC. The end-to-end DB path (the
`fn_record_milestone_response` RPC, real concurrency) is covered by the manual
verification flow after the migration is applied.

Two throwaway auth endpoints are registered on the app at import so the
JWT-isolation tests can drive `get_milestone_context` / `get_vendor_context`
without any DB rows.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import Depends
from postgrest.exceptions import APIError

from app.core.vendor_auth import (
    VendorContext,
    get_milestone_context,
    get_vendor_context,
)
from app.main import app


# ── Throwaway auth endpoints (only exist under pytest) ──────────────────────


@app.get("/api/v1/__ms_test__/milestone")
async def _ms_protected(
    ctx: VendorContext = Depends(get_milestone_context),
) -> dict:
    return {
        "vendor_id": str(ctx.vendor_id),
        "vendor_contact_id": str(ctx.vendor_contact_id),
        "milestone_alert_id": str(ctx.milestone_alert_id),
        "milestone_id": str(ctx.milestone_id),
        "cycle_number": ctx.cycle_number,
    }


@app.get("/api/v1/__ms_test__/bid")
async def _bid_protected(ctx: VendorContext = Depends(get_vendor_context)) -> dict:
    return {"vendor_id": str(ctx.vendor_id)}


@pytest_asyncio.fixture
async def auth_client():
    """httpx.AsyncClient bound to the FastAPI app via ASGITransport (no DB)."""
    import httpx
    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as ac:
        yield ac


# ── FakeDB: in-memory supabase-py double ────────────────────────────────────


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, fake: "FakeDB", table: str):
        self._fake = fake
        self._table = table
        self._op = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, str, Any]] = []
        self._single = False
        self._limit: int | None = None

    # write ops
    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    # read shaping
    def select(self, *_a, **_k):
        self._op = self._op if self._op != "select" else "select"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self._filters.append(("neq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._single = True
        return self

    def execute(self):
        return self._fake._resolve(
            self._table, self._op, self._filters, self._payload, self._single, self._limit
        )


class FakeDB:
    """Minimal supabase-py stand-in backed by per-table row lists.

    `tables` maps table name → list[dict]. Inserts append (with a generated id
    if absent) and are recorded on `inserts`; updates mutate matched rows and
    are recorded on `updates`. `rpc_result` / `rpc_error` drive `.rpc(...)`.
    """

    def __init__(self, tables: dict[str, list[dict]] | None = None):
        self.tables: dict[str, list[dict]] = {k: list(v) for k, v in (tables or {}).items()}
        self.inserts: list[tuple[str, Any]] = []
        self.updates: list[tuple[str, dict, list]] = []
        self.rpc_calls: list[tuple[str, dict]] = []
        self.rpc_result: Any = None
        self.rpc_error: Exception | None = None

    def table(self, name):
        return _Query(self, name)

    # rpc
    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        fake = self

        class _RpcExec:
            def execute(self_inner):
                if fake.rpc_error is not None:
                    raise fake.rpc_error
                return _Result(fake.rpc_result)

        return _RpcExec()

    # helpers
    @staticmethod
    def _matches(row: dict, filters: list) -> bool:
        for kind, col, val in filters:
            actual = row.get(col)
            if kind == "eq" and actual != val:
                return False
            if kind == "neq" and actual == val:
                return False
            if kind == "in" and actual not in val:
                return False
        return True

    def _resolve(self, table, op, filters, payload, single, limit):
        rows = self.tables.setdefault(table, [])

        if op == "insert":
            items = payload if isinstance(payload, list) else [payload]
            inserted = []
            for item in items:
                row = dict(item)
                row.setdefault("id", str(uuid4()))
                rows.append(row)
                inserted.append(row)
            self.inserts.append((table, inserted))
            return _Result(inserted)

        matched = [r for r in rows if self._matches(r, filters)]

        if op == "update":
            for r in matched:
                r.update(payload)
            self.updates.append((table, payload, matched))
            return _Result(matched)

        if op == "delete":
            for r in matched:
                rows.remove(r)
            return _Result(matched)

        # select
        if limit is not None:
            matched = matched[:limit]
        if single:
            return _Result(matched[0] if matched else None)
        return _Result(matched)


@pytest.fixture
def make_db():
    def _make(tables=None) -> FakeDB:
        return FakeDB(tables=tables)

    return _make


def make_api_error(code: str, message: str = "") -> APIError:
    """Build a postgrest APIError carrying a SQLSTATE-like code (e.g. 'PT409')."""
    return APIError({"code": code, "message": message or code})
