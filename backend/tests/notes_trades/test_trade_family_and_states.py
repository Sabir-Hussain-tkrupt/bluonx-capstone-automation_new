"""Trade-family expansion, US state filters, conflict messages, body limits."""

from __future__ import annotations

from uuid import uuid4

from app.core.body_limit import DEFAULT_MAX_BODY_BYTES, max_body_bytes
from app.core.db_errors import _subtrade_name_conflict, guardrail_status
from app.core.us_states import US_STATES, resolve_state, state_or_filter
from app.services.trade_family import trade_family_ids
from tests.financial._memdb import MemDB, api_error


def _t(name, parent=None):
    return {"id": str(uuid4()), "name": name, "parent_trade_id": parent, "is_active": True}


def test_family_of_parent_includes_subtrades():
    p = _t("Electrical")
    a, b = _t("Commercial", p["id"]), _t("Residential", p["id"])
    other = _t("Plumbing")
    db = MemDB({"trades": [p, a, b, other]})
    fam = trade_family_ids(db, p["id"])
    assert set(fam) == {p["id"], a["id"], b["id"]}
    assert fam[0] == p["id"]


def test_family_of_subtrade_includes_parent_only():
    p = _t("Electrical")
    a, b = _t("Commercial", p["id"]), _t("Residential", p["id"])
    db = MemDB({"trades": [p, a, b]})
    assert trade_family_ids(db, a["id"]) == [a["id"], p["id"]]


def test_family_of_plain_trade_is_itself():
    t = _t("Grading")
    assert trade_family_ids(MemDB({"trades": [t]}), t["id"]) == [t["id"]]


def test_family_degrades_on_error():
    db = MemDB({"trades": []})
    db.errors[("trades", "select")] = api_error("XX000", "boom")
    tid = str(uuid4())
    assert trade_family_ids(db, tid) == [tid]


def test_all_states_and_dc():
    assert len(US_STATES) == 51


def test_resolve_state_by_code_and_name():
    assert resolve_state("mo") == ("MO", "Missouri")
    assert resolve_state("  new   york ") == ("NY", "New York")
    assert resolve_state("Atlantis") is None


def test_state_or_filter_matches_both_spellings():
    assert state_or_filter("Texas") == 'state.ilike.TX,state.ilike."Texas"'
    assert state_or_filter("zz") is None


class _Rec:
    """Records the query chain so the router's filter calls can be asserted."""

    def __init__(self, log):
        self.log = log

    def __getattr__(self, name):
        def call(*a, **k):
            self.log.append((name, a))
            return self
        return call

    @property
    def not_(self):
        return self

    def execute(self):
        class R:
            data: list = []
            count = 0
        return R()


class _RecDB:
    def __init__(self):
        self.log = []

    def table(self, name):
        self.log.append(("table", (name,)))
        return _Rec(self.log)


def test_projects_list_state_filter(fin_client):
    db = _RecDB()
    r = fin_client(db).get("/api/v1/projects", params={"state": "Missouri"})
    assert r.status_code == 200, r.text
    assert ("or_", ('state.ilike.MO,state.ilike."Missouri"',)) in db.log


def test_unknown_state_matches_literally(fin_client):
    db = _RecDB()
    fin_client(db).get("/api/v1/projects", params={"state": "Ontario"})
    assert ("ilike", ("state", "Ontario")) in db.log


def test_vendors_list_state_filter_and_subtrade_family(fin_client):
    p = _t("Electrical")
    a = _t("Commercial", p["id"])
    trades = MemDB({"trades": [p, a]})

    class DB(_RecDB):
        def table(self, name):
            if name == "trades":
                return trades.table("trades")
            return super().table(name)

    db = DB()
    r = fin_client(db).get("/api/v1/vendors", params={"state": "tx", "trade_id": p["id"]})
    assert r.status_code == 200, r.text
    assert ("or_", ('state.ilike.TX,state.ilike."Texas"',)) in db.log
    in_calls = [args for name, args in db.log if name == "in_"]
    assert in_calls and in_calls[0][0] == "vendor_trades.trade_id"
    assert set(in_calls[0][1]) == {p["id"], a["id"]}


def test_subtrade_conflict_message():
    exc = api_error("23505", 'duplicate key value violates unique constraint "uq_trades_subtrade_name"')
    exc.details = "Key (parent_trade_id, name)=(6f1c0000-0000-0000-0000-000000000000, Commercial) already exists."
    assert _subtrade_name_conflict(None, exc) == 'This trade already has a subtrade named "Commercial".'


def test_guardrail_status():
    assert guardrail_status(api_error("PT422", "x")) == 422
    assert guardrail_status(api_error("23505", "x")) is None


def test_body_limits_for_new_and_fixed_routes():
    pid = str(uuid4())
    assert max_body_bytes("POST", f"/api/v1/projects/{pid}/invoices") > 25 * 1024 * 1024
    assert max_body_bytes("POST", f"/api/v1/projects/{pid}/budget/import/preview") > 2 * 1024 * 1024
    assert max_body_bytes("POST", f"/api/v1/projects/{pid}/notes") == 8 * 1024 * 1024
    assert max_body_bytes("PATCH", f"/api/v1/project-notes/{pid}") == 8 * 1024 * 1024
    assert max_body_bytes("GET", f"/api/v1/projects/{pid}/notes") == DEFAULT_MAX_BODY_BYTES
