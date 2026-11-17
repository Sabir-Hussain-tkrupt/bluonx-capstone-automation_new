"""Trades API: subtrades, usage check, edit / delete guards."""

from __future__ import annotations

from uuid import uuid4

from tests.financial._memdb import MemDB, api_error
from tests.notes_trades.conftest import ADMIN, PM

NOW = "2026-11-17T00:00:00+00:00"


def _trade(name, phase="development", parent=None, **kw):
    return {"id": str(uuid4()), "name": name, "phase": phase, "is_active": True,
            "parent_trade_id": parent, "created_at": NOW, "updated_at": NOW, **kw}


def _usage(**counts):
    base = {k: 0 for k in ("tasks", "vendors", "task_templates", "bid_templates",
                           "budget_template_lines", "variances", "subtrades")}
    base.update(counts)
    base["total"] = sum(base.values())
    return lambda _p: base


class _StampDB(MemDB):
    """MemDB whose inserts get the timestamps the database would add."""

    def table(self, name):
        q = super().table(name)
        run = q.execute

        def execute():
            r = run()
            for row in self.tables.get(name, []):
                row.setdefault("created_at", NOW)
                row.setdefault("updated_at", NOW)
            if r is not None and isinstance(r.data, list):
                for row in r.data:
                    row.setdefault("created_at", NOW)
                    row.setdefault("updated_at", NOW)
            return r

        q.execute = execute
        return q


def test_create_subtrade_takes_parent_phase(fin_client):
    parent = _trade("Electrical", "both")
    c = fin_client(_StampDB({"trades": [parent]}), ADMIN)
    r = c.post("/api/v1/trades", json={"name": "  Commercial ", "parent_trade_id": parent["id"]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["phase"] == "both"
    assert body["name"] == "Commercial"
    assert body["parent_trade_id"] == parent["id"]


def test_create_top_level_requires_phase(fin_client):
    c = fin_client(MemDB({"trades": []}), ADMIN)
    r = c.post("/api/v1/trades", json={"name": "Roofing"})
    assert r.status_code == 422


def test_subtrade_of_subtrade_refused(fin_client):
    parent = _trade("Electrical")
    sub = _trade("Commercial", parent=parent["id"])
    c = fin_client(MemDB({"trades": [parent, sub]}), ADMIN)
    r = c.post("/api/v1/trades", json={"name": "Deep", "parent_trade_id": sub["id"]})
    assert r.status_code == 422
    assert "already a subtrade" in r.json()["detail"]


def test_create_requires_admin(fin_client):
    c = fin_client(MemDB({"trades": []}), PM)
    r = c.post("/api/v1/trades", json={"name": "Roofing", "phase": "development"})
    assert r.status_code == 403


def test_usage_endpoint(fin_client):
    t = _trade("Grading")
    db = MemDB({"trades": [t]}, rpc={"fn_trade_usage": _usage(tasks=2, vendors=1)})
    r = fin_client(db, PM).get(f"/api/v1/trades/{t['id']}/usage")
    assert r.status_code == 200
    body = r.json()
    assert body["tasks"] == 2 and body["vendors"] == 1 and body["total"] == 3
    assert body["in_use"] is True and body["can_edit"] is False and body["can_delete"] is False


def test_trade_with_only_subtrades_can_be_renamed_not_deleted(fin_client):
    t = _trade("Electrical")
    db = MemDB({"trades": [t]}, rpc={"fn_trade_usage": _usage(subtrades=2)})
    c = fin_client(db, ADMIN)
    usage = c.get(f"/api/v1/trades/{t['id']}/usage").json()
    assert usage["can_edit"] is True and usage["can_delete"] is False
    assert c.patch(f"/api/v1/trades/{t['id']}", json={"name": "Electric"}).status_code == 200
    r = c.delete(f"/api/v1/trades/{t['id']}")
    assert r.status_code == 409
    assert "2 subtrades" in r.json()["detail"]


def test_rename_blocked_when_in_use(fin_client):
    t = _trade("Grading")
    db = MemDB({"trades": [t]}, rpc={"fn_trade_usage": _usage(tasks=1, vendors=3)})
    r = fin_client(db, ADMIN).patch(f"/api/v1/trades/{t['id']}", json={"name": "Earthwork"})
    assert r.status_code == 409
    assert "1 task, 3 vendors" in r.json()["detail"]
    assert db.tables["trades"][0]["name"] == "Grading"


def test_toggle_active_allowed_when_in_use(fin_client):
    t = _trade("Grading")
    db = MemDB({"trades": [t]}, rpc={"fn_trade_usage": _usage(tasks=1)})
    r = fin_client(db, ADMIN).patch(f"/api/v1/trades/{t['id']}", json={"is_active": False})
    assert r.status_code == 200
    assert db.tables["trades"][0]["is_active"] is False
    assert db.calls("fn_trade_usage") == []


def test_subtrade_phase_cannot_be_changed(fin_client):
    parent = _trade("Electrical")
    sub = _trade("Commercial", parent=parent["id"])
    db = MemDB({"trades": [parent, sub]}, rpc={"fn_trade_usage": _usage()})
    r = fin_client(db, ADMIN).patch(f"/api/v1/trades/{sub['id']}", json={"phase": "both"})
    assert r.status_code == 422


def test_delete_unused_calls_safe_delete(fin_client):
    t = _trade("Old trade")
    db = MemDB({"trades": [t]}, rpc={"fn_trade_usage": _usage(), "fn_delete_trade": lambda p: [t]})
    r = fin_client(db, ADMIN).delete(f"/api/v1/trades/{t['id']}")
    assert r.status_code == 204
    assert db.calls("fn_delete_trade") == [{"p_trade_id": t["id"]}]


def test_delete_race_maps_database_refusal(fin_client):
    t = _trade("Old trade")
    db = MemDB({"trades": [t]}, rpc={
        "fn_trade_usage": _usage(),
        "fn_delete_trade": lambda p: api_error("PT409", '"Old trade" cannot be deleted because it is in use (1 tasks).'),
    })
    r = fin_client(db, ADMIN).delete(f"/api/v1/trades/{t['id']}")
    assert r.status_code == 409
    assert "in use" in r.json()["detail"]


def test_delete_missing_trade_404(fin_client):
    r = fin_client(MemDB({"trades": []}), ADMIN).delete(f"/api/v1/trades/{uuid4()}")
    assert r.status_code == 404


def test_guardrail_error_from_any_route_is_not_a_500(fin_client):
    """A PT422 from the leaf-trade trigger surfaces as 422 with its message,
    even on routes that do not catch APIError themselves."""
    db = MemDB({"trades": []})
    db.errors[("trades", "insert")] = api_error(
        "PT422", 'Trade "Electrical" has subtrades — choose one of its subtrades.')
    r = fin_client(db, ADMIN).post("/api/v1/trades", json={"name": "X", "phase": "development"})
    assert r.status_code == 422
    assert "choose one of its subtrades" in r.json()["detail"]


def test_list_includes_parent_id(fin_client):
    parent = _trade("Electrical")
    sub = _trade("Commercial", parent=parent["id"])
    rows = fin_client(MemDB({"trades": [parent, sub]}), PM).get("/api/v1/trades").json()
    assert {r["name"]: r["parent_trade_id"] for r in rows} == {"Electrical": None, "Commercial": parent["id"]}
