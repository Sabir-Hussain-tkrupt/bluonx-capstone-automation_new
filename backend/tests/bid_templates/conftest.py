"""
Fixtures for the bid-template CRUD hardening tests (Task 3.6).

Distinct from tests/bid_template_freeze/, which pins the edit/delete freeze
guard. This module covers the ordinary CRUD axes: input validation, the
duplicate-name policy, trade validation, error sanitization and the batched
list enrichment.

The mock chain here is filter-aware where it matters — `bid_templates`
answers the duplicate-name probe from a configurable roster, so a test can
say "these names already exist" without hand-wiring call order.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app


TEMPLATE_ID = uuid4()
OTHER_TEMPLATE_ID = uuid4()
TRADE_ID = uuid4()
INACTIVE_TRADE_ID = uuid4()
PM_USER_ID = uuid4()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_template(template_id=None, name="Standard Grading Template", trade_id=None):
    return {
        "id": str(template_id or TEMPLATE_ID),
        "name": name,
        "trade_id": str(trade_id) if trade_id else None,
        "is_lump_sum": False,
        "created_by": str(PM_USER_ID),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


# ── Chains ─────────────────────────────────────────────────────────────────


def build_templates_chain(roster: list[dict], *, target: dict | None = None):
    """`bid_templates` chain backed by a roster of existing rows.

    - `.maybe_single()` → the `target` row (the one being fetched by id), or
      None to drive a 404.
    - `.ilike(...)` (the duplicate-name probe) → the full roster. The router
      re-compares names in Python, so returning everything is faithful to how
      ilike behaves before that filter.
    - `.insert(...)` → reflects the payload back with a synthesized id.
    """
    state = {"single": False, "last_insert": None}
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.neq.return_value = chain
    chain.is_.return_value = chain
    chain.in_.return_value = chain
    chain.ilike.return_value = chain
    chain.order.return_value = chain
    chain.range.return_value = chain
    chain.update.return_value = chain
    chain.delete.return_value = chain

    def _single():
        state["single"] = True
        return chain

    chain.single.side_effect = _single
    chain.maybe_single.side_effect = _single

    def _insert(payload):
        state["last_insert"] = payload
        return chain

    chain.insert.side_effect = _insert

    def _execute():
        result = MagicMock()
        if state["last_insert"] is not None:
            payload = dict(state["last_insert"])
            state["last_insert"] = None
            state["single"] = False
            payload.setdefault("id", str(uuid4()))
            payload.setdefault("created_at", _now_iso())
            payload.setdefault("updated_at", _now_iso())
            result.data = [payload]
            result.count = 1
        elif state["single"]:
            state["single"] = False
            result.data = target
            result.count = 1 if target else 0
        else:
            result.data = list(roster)
            result.count = len(roster)
        return result

    chain.execute.side_effect = _execute
    return chain


def build_trades_chain(rows: list[dict]):
    """`trades` chain that honours the `.eq("is_active", True)` filter."""
    state = {"single": False, "active_only": False, "wanted_id": None}
    chain = MagicMock()
    chain.select.return_value = chain
    chain.neq.return_value = chain
    chain.in_.return_value = chain
    chain.order.return_value = chain

    def _eq(field, value):
        if field == "is_active" and value is True:
            state["active_only"] = True
        if field == "id":
            state["wanted_id"] = str(value)
        return chain

    chain.eq.side_effect = _eq

    def _single():
        state["single"] = True
        return chain

    chain.single.side_effect = _single
    chain.maybe_single.side_effect = _single

    def _execute():
        matched = list(rows)
        if state["wanted_id"] is not None:
            matched = [r for r in matched if str(r["id"]) == state["wanted_id"]]
        if state["active_only"]:
            matched = [r for r in matched if r.get("is_active", True)]

        result = MagicMock()
        if state["single"]:
            result.data = matched[0] if matched else None
            result.count = len(matched)
        else:
            result.data = matched
            result.count = len(matched)
        state.update({"single": False, "active_only": False, "wanted_id": None})
        return result

    chain.execute.side_effect = _execute
    return chain


def build_simple_chain(data=None, count=None):
    chain = MagicMock()
    result = MagicMock()
    result.data = data if data is not None else []
    result.count = count if count is not None else (
        len(data) if isinstance(data, list) else 0
    )
    for method in (
        "select", "insert", "update", "delete", "eq", "neq", "is_", "in_",
        "ilike", "order", "range", "limit", "single", "maybe_single",
    ):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = result
    return chain


class _Recorder:
    def __init__(self, table_data: dict[str, object]):
        self._chains: dict[str, MagicMock] = {}
        for name, payload in table_data.items():
            if isinstance(payload, MagicMock):
                self._chains[name] = payload
            else:
                self._chains[name] = build_simple_chain(data=payload)

    def __call__(self, name: str) -> MagicMock:
        if name not in self._chains:
            self._chains[name] = build_simple_chain(data=[])
        return self._chains[name]

    def chain(self, name: str) -> MagicMock:
        return self._chains.setdefault(name, build_simple_chain(data=[]))


def make_db(table_data: dict[str, object]) -> MagicMock:
    client = MagicMock()
    recorder = _Recorder(table_data)
    client.table.side_effect = recorder
    client._recorder = recorder  # noqa: SLF001 (test-only handle)
    return client


# ── Standard world ─────────────────────────────────────────────────────────


@pytest.fixture()
def active_trade() -> dict:
    return {"id": str(TRADE_ID), "name": "Grading", "is_active": True}


@pytest.fixture()
def inactive_trade() -> dict:
    return {"id": str(INACTIVE_TRADE_ID), "name": "Retired Trade", "is_active": False}


@pytest.fixture()
def existing_template() -> dict:
    return make_template()


@pytest.fixture()
def db(existing_template, active_trade, inactive_trade) -> MagicMock:
    """One existing template, one active + one inactive trade, no packages."""
    return make_db({
        "bid_templates": build_templates_chain(
            [existing_template], target=existing_template
        ),
        "bid_template_items": [],
        "trades": build_trades_chain([active_trade, inactive_trade]),
        "bid_packages": build_simple_chain(data=[]),
    })


@pytest.fixture()
def authed_user() -> dict:
    return {
        "user_id": str(PM_USER_ID),
        "email": "pm@example.com",
        "full_name": "PM User",
        "role": "project_manager",
        "is_active": True,
    }


def _yield_client(db, authed_user):
    app.dependency_overrides[get_current_active_user] = lambda: authed_user
    app.dependency_overrides[get_supabase] = lambda: db
    with TestClient(app) as c:
        yield c, db
    app.dependency_overrides.clear()


@pytest.fixture()
def client(db, authed_user):
    yield from _yield_client(db, authed_user)


@pytest.fixture()
def client_factory(authed_user):
    """Build a client over a custom db for one-off world states."""
    created = []

    def _make(db):
        app.dependency_overrides[get_current_active_user] = lambda: authed_user
        app.dependency_overrides[get_supabase] = lambda: db
        c = TestClient(app)
        created.append(c)
        return c

    yield _make
    app.dependency_overrides.clear()
