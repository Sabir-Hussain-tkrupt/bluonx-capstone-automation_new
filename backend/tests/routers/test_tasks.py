"""Router tests for task CRUD (`/api/v1/projects/{id}/tasks`).

The tasks router shipped with no test coverage. These lock in the guards it
already enforces: trade-vs-phase compatibility, unique task names, the
bid_type lock after a task leaves draft, status-transition rules, and the
delete referential-integrity guard (active bid package / award / contract).

The fake applies filters, the `trades(name)` join, and the `not_.in_` blocker
checks for real, so a regression that dropped a guard would fail these rather
than pass them.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app

USER = {
    "user_id": str(uuid4()),
    "email": "pm@example.com",
    "full_name": "PM",
    "role": "project_manager",
    "is_active": True,
}

PROJECT_ID = str(uuid4())
TRADE_DEV = str(uuid4())        # phase=development
TRADE_BOTH = str(uuid4())       # phase=both
TRADE_DD = str(uuid4())         # phase=due_diligence
TRADE_INACTIVE = str(uuid4())   # is_active=False


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Not:
    def __init__(self, query: "_Query"):
        self._q = query

    def is_(self, col, val):
        self._q._filters.append(("not_is", col, val))
        return self._q

    def in_(self, col, vals):
        self._q._filters.append(("not_in", col, list(vals)))
        return self._q


class _Query:
    def __init__(self, fake: "FakeDB", table: str):
        self._fake = fake
        self._table = table
        self._op = "select"
        self._select = "*"
        self._payload = None
        self._filters: list[tuple] = []
        self._want_count = False
        self._single = False
        self._order = None
        self._range = None
        self._limit = None

    def select(self, expr="*", *, count=None, **_k):
        self._op = "select"
        self._select = expr
        if count == "exact":
            self._want_count = True
        return self

    def insert(self, payload, *_a, **_k):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload, *_a, **_k):
        self._op = "update"
        self._payload = payload
        return self

    @property
    def not_(self):
        return _Not(self)

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self._filters.append(("neq", col, val))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    def ilike(self, col, pattern):
        self._filters.append(("ilike", col, pattern))
        return self

    def order(self, col, desc=False, **_k):
        self._order = (col, desc)
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def maybe_single(self, *_a, **_k):
        self._single = True
        return self

    def single(self, *_a, **_k):
        self._single = True
        return self

    def execute(self):
        return self._fake._resolve(self)


def _matches(row, filters) -> bool:
    for kind, col, val in filters:
        actual = row.get(col)
        if kind == "eq" and str(actual) != str(val):
            return False
        if kind == "neq" and str(actual) == str(val):
            return False
        if kind == "is" and val == "null" and actual is not None:
            return False
        if kind == "not_is" and val == "null" and actual is None:
            return False
        if kind == "not_in" and actual in val:
            return False
        if kind == "ilike":
            needle = str(val).strip("%").lower()
            if needle not in str(actual or "").lower():
                return False
    return True


class FakeDB:
    def __init__(self, **tables):
        self.tables: dict[str, list[dict]] = {
            "projects": tables.get("projects", []),
            "tasks": tables.get("tasks", []),
            "trades": tables.get("trades", []),
            "bid_packages": tables.get("bid_packages", []),
            "awards": tables.get("awards", []),
            "contracts": tables.get("contracts", []),
        }

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def _attach_trade(self, row: dict, select_expr: str) -> dict:
        out = dict(row)
        if "trades(" in select_expr:
            trade = next((t for t in self.tables["trades"] if str(t["id"]) == str(row.get("trade_id"))), None)
            out["trades"] = {"name": trade["name"]} if trade else None
        return out

    def _resolve(self, q: _Query):
        rows = [r for r in self.tables[q._table] if _matches(r, q._filters)]

        if q._op == "insert":
            new = {
                "id": str(uuid4()),
                "description": None,
                "budget_estimate": None,
                "deleted_at": None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                **q._payload,
            }
            self.tables[q._table].append(new)
            return _Result([new])

        if q._op == "update":
            for r in rows:
                r.update(q._payload)
            return _Result(rows)

        # select
        total = len(rows)
        if q._order:
            col, desc = q._order
            rows = sorted(rows, key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
        if q._limit is not None:
            rows = rows[: q._limit]
        if q._range:
            start, end = q._range
            rows = rows[start : end + 1]
        rows = [self._attach_trade(r, q._select) for r in rows]

        if q._single:
            return _Result(rows[0] if rows else None)
        return _Result(rows, count=total if q._want_count else None)


def _project(**over) -> dict:
    return {"id": PROJECT_ID, "name": "Riverside", "budget": None, "archived_at": None, "deleted_at": None, **over}


def _trade(tid, name, phase, is_active=True) -> dict:
    return {"id": tid, "name": name, "phase": phase, "is_active": is_active}


def _task(name="Grading", *, status="draft", bid_type="competitive", phase="development", trade_id=TRADE_DEV, sort_order=1, **over) -> dict:
    return {
        "id": over.get("id", str(uuid4())),
        "project_id": PROJECT_ID,
        "trade_id": trade_id,
        "name": name,
        "description": None,
        "phase": phase,
        "bid_type": bid_type,
        "budget_estimate": None,
        "sort_order": sort_order,
        "status": status,
        "created_by": USER["user_id"],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "deleted_at": None,
        **{k: v for k, v in over.items() if k != "id"},
    }


def _trades() -> list[dict]:
    return [
        _trade(TRADE_DEV, "Grading", "development"),
        _trade(TRADE_BOTH, "Engineering", "both"),
        _trade(TRADE_DD, "Geotech", "due_diligence"),
        _trade(TRADE_INACTIVE, "Retired", "development", is_active=False),
    ]


@pytest.fixture()
def client_with():
    def _bind(fake):
        app.dependency_overrides[get_current_active_user] = lambda: USER
        app.dependency_overrides[get_supabase] = lambda: fake
        return TestClient(app)

    yield _bind
    app.dependency_overrides.clear()


BASE = f"/api/v1/projects/{PROJECT_ID}/tasks"


class TestListTasks:
    def test_lists_non_deleted_sorted_by_sort_order(self, client_with):
        fake = FakeDB(
            projects=[_project()],
            tasks=[
                _task("Second", sort_order=2),
                _task("First", sort_order=1),
                _task("Gone", sort_order=3, deleted_at="2026-02-01T00:00:00Z"),
            ],
            trades=_trades(),
        )
        resp = client_with(fake).get(BASE)
        assert resp.status_code == 200
        body = resp.json()
        assert [t["name"] for t in body["items"]] == ["First", "Second"]
        assert body["total"] == 2
        assert body["items"][0]["trade_name"] == "Grading"

    def test_unknown_project_is_404(self, client_with):
        fake = FakeDB(projects=[], tasks=[], trades=_trades())
        resp = client_with(fake).get(BASE)
        assert resp.status_code == 404


class TestCreateTask:
    def _fake(self, tasks=None):
        return FakeDB(projects=[_project()], tasks=tasks or [], trades=_trades())

    def _payload(self, **over):
        return {"trade_id": TRADE_DEV, "name": "Mass Grading", "phase": "development", "bid_type": "competitive", **over}

    def test_creates_with_next_sort_order_and_draft_status(self, client_with):
        fake = self._fake(tasks=[_task("Existing", sort_order=1)])
        resp = client_with(fake).post(BASE, json=self._payload())
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "draft"
        assert body["sort_order"] == 2
        assert body["trade_name"] == "Grading"

    def test_trade_incompatible_with_phase_is_422(self, client_with):
        # Geotech is a due_diligence trade; the task phase is development.
        resp = client_with(self._fake()).post(BASE, json=self._payload(trade_id=TRADE_DD))
        assert resp.status_code == 422
        assert "not valid for task phase" in resp.json()["detail"]

    def test_inactive_trade_is_422(self, client_with):
        resp = client_with(self._fake()).post(BASE, json=self._payload(trade_id=TRADE_INACTIVE))
        assert resp.status_code == 422
        assert "inactive" in resp.json()["detail"].lower()

    def test_both_phase_trade_is_accepted(self, client_with):
        resp = client_with(self._fake()).post(BASE, json=self._payload(trade_id=TRADE_BOTH))
        assert resp.status_code == 201

    def test_duplicate_name_is_409(self, client_with):
        fake = self._fake(tasks=[_task("Mass Grading")])
        resp = client_with(fake).post(BASE, json=self._payload(name="Mass Grading"))
        assert resp.status_code == 409

    def test_archived_project_is_400(self, client_with):
        fake = FakeDB(projects=[_project(archived_at="2026-02-01T00:00:00Z")], tasks=[], trades=_trades())
        resp = client_with(fake).post(BASE, json=self._payload())
        assert resp.status_code == 400

    def test_direct_assign_is_422(self, client_with):
        """direct_assign is out of product scope and has no award flow, so the
        API must refuse it — the task form is not the only gate."""
        resp = client_with(self._fake()).post(BASE, json=self._payload(bid_type="direct_assign"))
        assert resp.status_code == 422

    def test_internal_is_still_accepted(self, client_with):
        """Guard against the rejection over-reaching: internal stays valid."""
        resp = client_with(self._fake()).post(BASE, json=self._payload(bid_type="internal"))
        assert resp.status_code == 201


class TestUpdateTask:
    def test_bid_type_cannot_be_patched_to_direct_assign(self, client_with):
        """A draft task may change bid_type, but never to the dropped value."""
        task = _task(status="draft", bid_type="competitive")
        fake = FakeDB(projects=[_project()], tasks=[task], trades=_trades())
        resp = client_with(fake).patch(f"{BASE}/{task['id']}", json={"bid_type": "direct_assign"})
        assert resp.status_code == 422

    def test_bid_type_locked_after_draft_is_409(self, client_with):
        task = _task(status="bidding", bid_type="competitive")
        fake = FakeDB(projects=[_project()], tasks=[task], trades=_trades())
        resp = client_with(fake).patch(f"{BASE}/{task['id']}", json={"bid_type": "internal"})
        assert resp.status_code == 409
        assert "bid_type" in resp.json()["detail"]

    def test_illegal_status_transition_is_422(self, client_with):
        task = _task(status="draft")
        fake = FakeDB(projects=[_project()], tasks=[task], trades=_trades())
        resp = client_with(fake).patch(f"{BASE}/{task['id']}", json={"status": "completed"})
        assert resp.status_code == 422

    def test_rename_succeeds(self, client_with):
        task = _task("Old Name")
        fake = FakeDB(projects=[_project()], tasks=[task], trades=_trades())
        resp = client_with(fake).patch(f"{BASE}/{task['id']}", json={"name": "New Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"


class TestDeleteTask:
    def _fake(self, **extra):
        task = _task()
        fake = FakeDB(projects=[_project()], tasks=[task], trades=_trades(), **extra)
        return fake, task

    def test_clean_delete_is_204(self, client_with):
        fake, task = self._fake()
        resp = client_with(fake).delete(f"{BASE}/{task['id']}")
        assert resp.status_code == 204
        assert fake.tables["tasks"][0]["deleted_at"] is not None

    def test_active_bid_package_blocks_with_409(self, client_with):
        task = _task()
        fake = FakeDB(
            projects=[_project()],
            tasks=[task],
            trades=_trades(),
            bid_packages=[{"id": str(uuid4()), "task_id": task["id"], "status": "collecting"}],
        )
        resp = client_with(fake).delete(f"{BASE}/{task['id']}")
        assert resp.status_code == 409
        assert "bid packages" in resp.json()["detail"]

    def test_active_award_blocks_with_409(self, client_with):
        task = _task()
        fake = FakeDB(
            projects=[_project()],
            tasks=[task],
            trades=_trades(),
            awards=[{"id": str(uuid4()), "task_id": task["id"], "status": "accepted"}],
        )
        resp = client_with(fake).delete(f"{BASE}/{task['id']}")
        assert resp.status_code == 409
        assert "awards" in resp.json()["detail"]

    def test_active_contract_blocks_with_409(self, client_with):
        task = _task()
        fake = FakeDB(
            projects=[_project()],
            tasks=[task],
            trades=_trades(),
            contracts=[{"id": str(uuid4()), "task_id": task["id"], "status": "active"}],
        )
        resp = client_with(fake).delete(f"{BASE}/{task['id']}")
        assert resp.status_code == 409
        assert "contracts" in resp.json()["detail"]

    def test_completed_bid_package_does_not_block(self, client_with):
        task = _task()
        fake = FakeDB(
            projects=[_project()],
            tasks=[task],
            trades=_trades(),
            bid_packages=[{"id": str(uuid4()), "task_id": task["id"], "status": "completed"}],
        )
        resp = client_with(fake).delete(f"{BASE}/{task['id']}")
        assert resp.status_code == 204


class TestReorderTasks:
    def test_updates_sort_order(self, client_with):
        t1 = _task("A", sort_order=1)
        t2 = _task("B", sort_order=2)
        fake = FakeDB(projects=[_project()], tasks=[t1, t2], trades=_trades())
        resp = client_with(fake).put(
            f"{BASE}/reorder",
            json=[{"task_id": t1["id"], "sort_order": 2}, {"task_id": t2["id"], "sort_order": 1}],
        )
        assert resp.status_code == 204
        by_id = {t["id"]: t["sort_order"] for t in fake.tables["tasks"]}
        assert by_id[t1["id"]] == 2
        assert by_id[t2["id"]] == 1
