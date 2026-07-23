"""
Shared fixtures for Bid Template Freeze Guard tests (Task 8.1).

Pattern follows backend/tests/bid_submission_detail/conftest.py:
  - Per-table data dispatcher on the mocked Supabase client.
  - FastAPI TestClient with auth + db dependency overrides.
  - Function-scoped fixtures with deterministic UUIDs.

The mock chain returns the same row-set regardless of the .eq()/.neq()
filters applied. Tests opt into specific "world states" by choosing
which fixture variant to mount (no live refs / live refs / cancelled
only / mixed).
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


# ── Deterministic IDs ──────────────────────────────────────────────────────

TEMPLATE_ID = uuid4()
TRADE_ID = uuid4()
TASK_ID_OPEN = uuid4()
TASK_ID_CLOSED = uuid4()
TASK_ID_EVAL = uuid4()
TASK_ID_CANCELLED = uuid4()
PACKAGE_ID_OPEN = uuid4()
PACKAGE_ID_CLOSED = uuid4()
PACKAGE_ID_EVAL = uuid4()
PACKAGE_ID_CANCELLED = uuid4()
ITEM_IDS = [uuid4() for _ in range(3)]
PM_USER_ID = uuid4()

NONEXISTENT_TEMPLATE_ID = uuid4()


# ── Sample rows ────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture()
def sample_template() -> dict:
    return {
        "id": str(TEMPLATE_ID),
        "name": "Standard Grading Template",
        "trade_id": str(TRADE_ID),
        "is_lump_sum": False,
        "created_by": str(PM_USER_ID),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


@pytest.fixture()
def sample_template_items() -> list[dict]:
    return [
        {
            "id": str(ITEM_IDS[0]),
            "bid_template_id": str(TEMPLATE_ID),
            "description": "Mobilization",
            "item_type": "lump_sum",
            "unit_of_measure": None,
            "sort_order": 0,
        },
        {
            "id": str(ITEM_IDS[1]),
            "bid_template_id": str(TEMPLATE_ID),
            "description": "Excavation",
            "item_type": "unit_price",
            "unit_of_measure": "CY",
            "sort_order": 1,
        },
        {
            "id": str(ITEM_IDS[2]),
            "bid_template_id": str(TEMPLATE_ID),
            "description": "Final grade",
            "item_type": "lump_sum",
            "unit_of_measure": None,
            "sort_order": 2,
        },
    ]


@pytest.fixture()
def sample_trade() -> dict:
    return {"id": str(TRADE_ID), "name": "Grading"}


def _pkg(pkg_id, task_id, task_name, status):
    """Shape matches the Supabase `select("id, status, task_id, tasks(name)")` response.

    `bid_template_id` is carried too: the batched list enrichment selects it
    and groups by it to build the in-use set, so a row without it would never
    mark its template as in use.
    """
    return {
        "id": str(pkg_id),
        "status": status,
        "task_id": str(task_id),
        "tasks": {"name": task_name},
        "bid_template_id": str(TEMPLATE_ID),
    }


@pytest.fixture()
def package_open() -> dict:
    return _pkg(PACKAGE_ID_OPEN, TASK_ID_OPEN, "Rough Grading", "open")


@pytest.fixture()
def package_closed() -> dict:
    return _pkg(PACKAGE_ID_CLOSED, TASK_ID_CLOSED, "Mass Excavation", "closed")


@pytest.fixture()
def package_evaluating() -> dict:
    return _pkg(PACKAGE_ID_EVAL, TASK_ID_EVAL, "Storm Drain", "evaluating")


@pytest.fixture()
def package_cancelled() -> dict:
    return _pkg(PACKAGE_ID_CANCELLED, TASK_ID_CANCELLED, "Cancelled Scope", "cancelled")


# ── Mock chain helpers ─────────────────────────────────────────────────────


def build_chain(data=None, count=None):
    """Build a Supabase-style chainable mock whose .execute() yields the data."""
    chain = MagicMock()
    result = MagicMock()
    result.data = data if data is not None else []
    result.count = count if count is not None else (len(data) if isinstance(data, list) else 0)

    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.delete.return_value = chain
    chain.eq.return_value = chain
    chain.neq.return_value = chain
    chain.is_.return_value = chain
    chain.in_.return_value = chain
    chain.ilike.return_value = chain
    chain.order.return_value = chain
    chain.range.return_value = chain
    chain.limit.return_value = chain
    chain.single.return_value = chain
    chain.maybe_single.return_value = chain
    chain.execute.return_value = result
    return chain


def build_bid_templates_chain(source_row: dict | None):
    """Chain for the `bid_templates` table that handles both:
      - SELECT (e.g. `_get_template_or_404`) → returns the configured row.
      - INSERT (duplicate endpoint) → reflects the payload back with a
        synthesized id + timestamps so `_build_detail_response` works.

    The router's UPDATE path doesn't inspect `.data`, so the default
    `data=source_row` is fine for PUT.
    """
    state = {"last_insert": None, "single": False}
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.neq.return_value = chain
    chain.is_.return_value = chain
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
            payload = state["last_insert"]
            state["last_insert"] = None
            state["single"] = False
            row = dict(payload) if isinstance(payload, dict) else payload
            if isinstance(row, dict):
                row.setdefault("id", str(uuid4()))
                row.setdefault("created_at", _now_iso())
                row.setdefault("updated_at", _now_iso())
                result.data = [row]
                result.count = 1
            else:
                result.data = list(payload)
                result.count = len(payload)
        else:
            if state["single"]:
                result.data = source_row
                result.count = 1 if source_row else 0
            else:
                result.data = [source_row] if source_row else []
                result.count = 1 if source_row else 0
            state["single"] = False
        return result

    chain.execute.side_effect = _execute
    return chain


def build_trades_chain(row: dict | None):
    """Chain for `trades` that answers both access shapes correctly.

    The detail path fetches one trade with `.maybe_single()` and expects a
    dict; the batched list path fetches many with `.in_()` and expects a list.
    A plain build_chain() would hand the same payload to both, so the list path
    would iterate a dict's keys and blow up on row["id"].
    """
    state = {"single": False}
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.neq.return_value = chain
    chain.in_.return_value = chain
    chain.ilike.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain

    def _single():
        state["single"] = True
        return chain

    chain.single.side_effect = _single
    chain.maybe_single.side_effect = _single

    def _execute():
        result = MagicMock()
        if state["single"]:
            result.data = row
            result.count = 1 if row else 0
        else:
            result.data = [row] if row else []
            result.count = 1 if row else 0
        state["single"] = False
        return result

    chain.execute.side_effect = _execute
    return chain


def build_bid_packages_chain(all_rows: list[dict]):
    """Chainable mock for the `bid_packages` table that respects the
    `.neq("status","cancelled")` filter applied by the live-refs helper.

    When `.neq("status","cancelled")` is invoked in the chain before
    `.execute()`, only non-cancelled rows are returned (simulates the
    DB-side WHERE filter). Without `.neq`, all rows come back: this is
    what the all-refs helper relies on for the delete message.

    State resets on every `.execute()` so the same chain object can serve
    multiple sequential queries within one request.
    """
    state = {"filter_cancelled": False}
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    # The batched list enrichment filters by .in_("bid_template_id", [...])
    # instead of .eq(); without this the MagicMock would hand back a fresh
    # mock and drop out of the chain.
    chain.in_.return_value = chain

    def _neq(field, value):
        if field == "status" and value == "cancelled":
            state["filter_cancelled"] = True
        return chain

    chain.neq.side_effect = _neq

    # Other terminal/passthrough methods used elsewhere; keep the chain alive.
    chain.order.return_value = chain
    chain.range.return_value = chain
    chain.limit.return_value = chain

    def _execute():
        result = MagicMock()
        if state["filter_cancelled"]:
            result.data = [r for r in all_rows if r.get("status") != "cancelled"]
        else:
            result.data = list(all_rows)
        result.count = len(result.data)
        state["filter_cancelled"] = False  # reset for next chain call
        return result

    chain.execute.side_effect = _execute
    return chain


class TableCallRecorder:
    """Holds per-table mock chains so tests can assert which tables were touched.

    For tables that may be hit multiple times in different shapes (e.g. an
    insert *and* a follow-up select on the same table), we hand back the
    SAME chain on every `table(name)` call. That's fine for our assertions
    They only care whether `delete()`/`insert()` were called at all.
    """

    def __init__(self, table_data: dict[str, object]):
        self._chains: dict[str, MagicMock] = {}
        for name, payload in table_data.items():
            if isinstance(payload, MagicMock):
                self._chains[name] = payload
            elif isinstance(payload, dict):
                # Single-row payload (e.g. trades.single().execute())
                self._chains[name] = build_chain(data=payload)
            elif isinstance(payload, list):
                self._chains[name] = build_chain(data=payload)
            else:
                self._chains[name] = build_chain(data=None)

    def __call__(self, name: str) -> MagicMock:
        if name not in self._chains:
            self._chains[name] = build_chain(data=[])
        return self._chains[name]

    def chain(self, name: str) -> MagicMock:
        return self._chains.setdefault(name, build_chain(data=[]))


def make_db(table_data: dict[str, object]) -> MagicMock:
    """Build a mocked Supabase client whose `.table(name)` returns canned chains."""
    client = MagicMock()
    recorder = TableCallRecorder(table_data)
    client.table.side_effect = recorder
    client._recorder = recorder  # noqa: SLF001 (test-only handle)
    return client


# ── DB fixtures: world states ──────────────────────────────────────────────


def _db_with_packages(
    sample_template, sample_template_items, sample_trade, package_rows
) -> MagicMock:
    return make_db({
        "bid_templates": build_bid_templates_chain(sample_template),
        "bid_template_items": sample_template_items,
        "trades": build_trades_chain(sample_trade),
        "bid_packages": build_bid_packages_chain(package_rows),
    })


@pytest.fixture()
def db_no_refs(sample_template, sample_template_items, sample_trade) -> MagicMock:
    """Template exists with items + trade; no referencing bid_packages."""
    return _db_with_packages(sample_template, sample_template_items, sample_trade, [])


@pytest.fixture()
def db_live_open(
    sample_template, sample_template_items, sample_trade, package_open
) -> MagicMock:
    """Template referenced by a single OPEN package (locked)."""
    return _db_with_packages(
        sample_template, sample_template_items, sample_trade, [package_open]
    )


@pytest.fixture()
def db_live_closed(
    sample_template, sample_template_items, sample_trade, package_closed
) -> MagicMock:
    return _db_with_packages(
        sample_template, sample_template_items, sample_trade, [package_closed]
    )


@pytest.fixture()
def db_live_evaluating(
    sample_template, sample_template_items, sample_trade, package_evaluating
) -> MagicMock:
    return _db_with_packages(
        sample_template, sample_template_items, sample_trade, [package_evaluating]
    )


@pytest.fixture()
def db_cancelled_only(
    sample_template, sample_template_items, sample_trade, package_cancelled
) -> MagicMock:
    """Only a cancelled reference exists.

    For the live-refs helper this is editable (DB filter strips the cancelled
    row). For the all-refs helper used by the delete message it still appears.
    The smart `bid_packages` chain handles both via the `.neq` filter.
    """
    return _db_with_packages(
        sample_template, sample_template_items, sample_trade, [package_cancelled]
    )


@pytest.fixture()
def db_mixed_open_and_cancelled(
    sample_template, sample_template_items, sample_trade, package_open, package_cancelled
) -> MagicMock:
    return _db_with_packages(
        sample_template,
        sample_template_items,
        sample_trade,
        [package_open, package_cancelled],
    )


@pytest.fixture()
def many_live_packages() -> list[dict]:
    """Five live (open) packages, used to exercise the +N more truncation
    in 409 messages. Names are deterministic so tests can assert which
    ones make the cut and which collapse into the overflow count.
    """
    return [
        _pkg(uuid4(), uuid4(), f"Task {i}", "open")
        for i in range(5)
    ]


@pytest.fixture()
def db_many_live(
    sample_template, sample_template_items, sample_trade, many_live_packages
) -> MagicMock:
    return _db_with_packages(
        sample_template, sample_template_items, sample_trade, many_live_packages
    )


@pytest.fixture()
def db_template_missing() -> MagicMock:
    """Template fetch returns no row (triggers 404)."""
    return make_db({
        "bid_templates": build_bid_templates_chain(None),
        "bid_template_items": [],
        "trades": build_trades_chain(None),
        "bid_packages": build_bid_packages_chain([]),
    })


# ── FastAPI TestClient + auth override ─────────────────────────────────────


@pytest.fixture()
def authed_user() -> dict:
    return {
        "user_id": str(PM_USER_ID),
        "email": "pm@example.com",
        "full_name": "PM User",
        "role": "project_manager",
        "is_active": True,
    }


def _client_with(db, authed_user):
    app.dependency_overrides[get_current_active_user] = lambda: authed_user
    app.dependency_overrides[get_supabase] = lambda: db
    client = TestClient(app)
    return client


@pytest.fixture()
def client_no_refs(db_no_refs, authed_user):
    yield from _yield_client(db_no_refs, authed_user)


@pytest.fixture()
def client_live_open(db_live_open, authed_user):
    yield from _yield_client(db_live_open, authed_user)


@pytest.fixture()
def client_live_closed(db_live_closed, authed_user):
    yield from _yield_client(db_live_closed, authed_user)


@pytest.fixture()
def client_live_evaluating(db_live_evaluating, authed_user):
    yield from _yield_client(db_live_evaluating, authed_user)


@pytest.fixture()
def client_cancelled_only(db_cancelled_only, authed_user):
    yield from _yield_client(db_cancelled_only, authed_user)


@pytest.fixture()
def client_mixed(db_mixed_open_and_cancelled, authed_user):
    yield from _yield_client(db_mixed_open_and_cancelled, authed_user)


@pytest.fixture()
def client_many_live(db_many_live, authed_user):
    yield from _yield_client(db_many_live, authed_user)


@pytest.fixture()
def client_template_missing(db_template_missing, authed_user):
    yield from _yield_client(db_template_missing, authed_user)


def _yield_client(db, authed_user):
    app.dependency_overrides[get_current_active_user] = lambda: authed_user
    app.dependency_overrides[get_supabase] = lambda: db
    with TestClient(app) as c:
        yield c, db
    app.dependency_overrides.clear()
