"""Phase 2 · Tasks 2.1–2.4 — budget, template and land-closing write paths."""

from decimal import Decimal

from tests.financial._memdb import MemDB, api_error
from tests.financial.conftest import ADMIN, FIELD_MANAGER, FINANCE, PM

P = "11111111-1111-1111-1111-111111111111"
L_PERMIT = "22222222-2222-2222-2222-222222222222"
L_TASK = "33333333-3333-3333-3333-333333333333"
L_LAND = "44444444-4444-4444-4444-444444444444"
L_CONT = "55555555-5555-5555-5555-555555555555"
TMPL = "66666666-6666-6666-6666-666666666666"


def project(status="draft", archived=False):
    return {"id": P, "name": "Demo", "status": "active", "budget_status": status,
            "archived_at": "2026-01-01" if archived else None, "deleted_at": None}


def line(id_, **kw):
    base = {"id": id_, "project_id": P, "task_id": None, "line_type": "permit", "name": "Permits",
            "section_name": "Soft costs", "sort_order": 50, "budget_amount": "3000.00",
            "committed_amount": "0", "is_locked": False, "deleted_at": None,
            "anticipated_start_date": None, "anticipated_end_date": None, "payment_terms_days": 30,
            "cash_bucket": "land", "approval_state": "not_requested", "parent_line_id": None}
    base.update(kw)
    return base


def db_with(status="draft", **extra):
    tables = {
        "projects": [project(status)],
        "budget_lines": [
            line(L_PERMIT),
            line(L_TASK, task_id="t1", line_type="bid_activity", name="Clearing", section_name="Site work", sort_order=80),
            line(L_LAND, line_type="land", name="Land purchase", section_name="Land", sort_order=10),
            line(L_CONT, line_type="contingency", name="Contingency", section_name="Contingency", sort_order=140),
        ],
        "land_closings": [],
    }
    tables.update(extra)
    return MemDB(tables)


# ── Authorization: only admins create and edit budgets ──────────────────────
class TestAdminOnly:
    def test_every_write_is_admin_only(self, fin_client):
        for who in (PM, FIELD_MANAGER, FINANCE):
            tc = fin_client(db_with(), who)
            checks = [
                tc.post(f"/api/v1/projects/{P}/budget", json={}),
                tc.post(f"/api/v1/projects/{P}/budget/baseline"),
                tc.post(f"/api/v1/projects/{P}/budget/lines", json={"line_type": "permit", "name": "X"}),
                tc.patch(f"/api/v1/budget-lines/{L_PERMIT}", json={"payment_terms_days": 45}),
                tc.delete(f"/api/v1/budget-lines/{L_PERMIT}"),
                tc.put(f"/api/v1/projects/{P}/budget/lines/order", json={"line_ids": [L_PERMIT]}),
                tc.post(f"/api/v1/projects/{P}/budget/sync-awards"),
                tc.post(f"/api/v1/budget-lines/{L_LAND}/closings",
                        json={"amount": "10", "planned_closing_date": "2027-01-01"}),
                tc.post(f"/api/v1/budget-templates/{TMPL}/lines", json={"line_type": "permit", "name": "X"}),
            ]
            assert [r.status_code for r in checks] == [403] * len(checks), who["roles"]

    def test_export_is_open_to_any_active_user(self, fin_client):
        db = db_with(v_budget_lines=[])
        tc = fin_client(db, PM)
        resp = tc.get(f"/api/v1/projects/{P}/budget/export?format=csv")
        assert resp.status_code == 200


# ── Create / baseline ───────────────────────────────────────────────────────
class TestCreateBudget:
    def test_calls_procedure_with_actor_and_percent(self, fin_client):
        db = MemDB({"projects": [project("none")]},
                   rpc={"fn_create_project_budget": lambda p: [{"id": "a"}, {"id": "b"}]})
        tc = fin_client(db, ADMIN)
        resp = tc.post(f"/api/v1/projects/{P}/budget", json={"contingency_percent": "12.5"})
        assert resp.status_code == 201
        assert resp.json() == {"line_count": 2}
        (params,) = db.calls("fn_create_project_budget")
        assert params["p_actor"] == ADMIN["user_id"]
        assert params["p_contingency_percent"] == "12.5"
        assert params["p_template_id"] is None

    def test_second_budget_is_409(self, fin_client):
        tc = fin_client(db_with("draft"), ADMIN)
        assert tc.post(f"/api/v1/projects/{P}/budget", json={}).status_code == 409

    def test_archived_project_is_409(self, fin_client):
        tc = fin_client(MemDB({"projects": [project("none", archived=True)]}), ADMIN)
        assert tc.post(f"/api/v1/projects/{P}/budget", json={}).status_code == 409

    def test_percent_out_of_range_is_422(self, fin_client):
        tc = fin_client(MemDB({"projects": [project("none")]}), ADMIN)
        assert tc.post(f"/api/v1/projects/{P}/budget", json={"contingency_percent": 120}).status_code == 422

    def test_db_message_passes_through(self, fin_client):
        db = MemDB({"projects": [project("none")]},
                   rpc={"fn_create_project_budget": lambda p: api_error("PT409", "No active budget template found.")})
        tc = fin_client(db, ADMIN)
        resp = tc.post(f"/api/v1/projects/{P}/budget", json={})
        assert resp.status_code == 409
        assert resp.json()["detail"] == "No active budget template found."

    def test_baseline(self, fin_client):
        db = db_with("draft")
        db.rpc_handlers["fn_baseline_project_budget"] = lambda p: [
            {"budget_status": "baselined", "approved_budget_total": "100000.00"}]
        tc = fin_client(db, ADMIN)
        resp = tc.post(f"/api/v1/projects/{P}/budget/baseline")
        assert resp.status_code == 200
        assert resp.json() == {"budget_status": "baselined", "approved_budget_total": "100000.00"}


# ── Lines ───────────────────────────────────────────────────────────────────
class TestLines:
    def test_add_line_without_task_lands_in_its_section(self, fin_client):
        db = db_with()
        tc = fin_client(db, ADMIN)
        resp = tc.post(f"/api/v1/projects/{P}/budget/lines", json={
            "line_type": "impact_fee", "name": "County impact fee", "section_name": "Soft costs",
            "budget_amount": "1234.56", "anticipated_start_date": "2027-03-01",
            "anticipated_end_date": "2027-03-01", "payment_terms_days": 0, "cash_bucket": "land"})
        assert resp.status_code == 201, resp.text
        row = db.tables["budget_lines"][-1]
        assert row["budget_amount"] == "1234.56"           # exact, as a string
        assert row["sort_order"] == 51                      # after the last Soft costs line
        assert row["is_payment_exempt"] is False
        assert row["created_by"] == ADMIN["user_id"]

    def test_land_line_is_payment_exempt(self, fin_client):
        db = db_with()
        fin_client(db, ADMIN).post(f"/api/v1/projects/{P}/budget/lines",
                                   json={"line_type": "land", "line_subtype": "earnest_money", "name": "Earnest money"})
        assert db.tables["budget_lines"][-1]["is_payment_exempt"] is True

    def test_engineering_tm_portion_sits_under_parent(self, fin_client):
        db = db_with()
        resp = fin_client(db, ADMIN).post(f"/api/v1/projects/{P}/budget/lines", json={
            "line_type": "internal_tm", "name": "Engineering T&M", "parent_line_id": L_TASK})
        assert resp.status_code == 201
        row = db.tables["budget_lines"][-1]
        assert row["parent_line_id"] == L_TASK and row["section_name"] == "Site work" and row["sort_order"] == 81

    def test_bid_activity_cannot_be_added_by_hand(self, fin_client):
        resp = fin_client(db_with(), ADMIN).post(f"/api/v1/projects/{P}/budget/lines",
                                                 json={"line_type": "bid_activity", "name": "X"})
        assert resp.status_code == 422

    def test_negative_and_sub_cent_amounts_rejected(self, fin_client):
        tc = fin_client(db_with(), ADMIN)
        for amount in ("-1", "10.001"):
            assert tc.post(f"/api/v1/projects/{P}/budget/lines",
                           json={"line_type": "permit", "name": "X", "budget_amount": amount}).status_code == 422

    def test_end_before_start_rejected(self, fin_client):
        resp = fin_client(db_with(), ADMIN).post(f"/api/v1/projects/{P}/budget/lines", json={
            "line_type": "permit", "name": "X", "anticipated_start_date": "2027-05-01",
            "anticipated_end_date": "2027-04-01"})
        assert resp.status_code == 422

    def test_baselined_new_line_must_start_at_zero(self, fin_client):
        tc = fin_client(db_with("baselined"), ADMIN)
        resp = tc.post(f"/api/v1/projects/{P}/budget/lines",
                       json={"line_type": "permit", "name": "X", "budget_amount": "10"})
        assert resp.status_code == 409
        resp = tc.post(f"/api/v1/projects/{P}/budget/lines", json={"line_type": "permit", "name": "X"})
        assert resp.status_code == 201

    def test_no_budget_is_409(self, fin_client):
        tc = fin_client(MemDB({"projects": [project("none")]}), ADMIN)
        assert tc.post(f"/api/v1/projects/{P}/budget/lines",
                       json={"line_type": "permit", "name": "X"}).status_code == 409

    def test_update_dates_terms_bucket(self, fin_client):
        db = db_with("baselined")
        resp = fin_client(db, ADMIN).patch(f"/api/v1/budget-lines/{L_PERMIT}", json={
            "anticipated_start_date": "2027-02-01", "anticipated_end_date": "2027-02-28",
            "payment_terms_days": 45, "cash_bucket": "overhead"})
        assert resp.status_code == 200, resp.text
        row = db.tables["budget_lines"][0]
        assert (row["anticipated_end_date"], row["payment_terms_days"], row["cash_bucket"]) == ("2027-02-28", 45, "overhead")

    def test_amount_frozen_after_baseline(self, fin_client):
        resp = fin_client(db_with("baselined"), ADMIN).patch(
            f"/api/v1/budget-lines/{L_PERMIT}", json={"budget_amount": "1"})
        assert resp.status_code == 409

    def test_amount_editable_in_draft(self, fin_client):
        db = db_with("draft")
        assert fin_client(db, ADMIN).patch(f"/api/v1/budget-lines/{L_PERMIT}",
                                           json={"budget_amount": "3500.25"}).status_code == 200
        assert db.tables["budget_lines"][0]["budget_amount"] == "3500.25"

    def test_task_line_name_follows_task(self, fin_client):
        resp = fin_client(db_with(), ADMIN).patch(f"/api/v1/budget-lines/{L_TASK}", json={"name": "New"})
        assert resp.status_code == 422

    def test_merged_dates_checked(self, fin_client):
        db = db_with()
        db.tables["budget_lines"][0]["anticipated_start_date"] = "2027-06-01"
        resp = fin_client(db, ADMIN).patch(f"/api/v1/budget-lines/{L_PERMIT}",
                                           json={"anticipated_end_date": "2027-05-01"})
        assert resp.status_code == 422

    def test_locked_line_guard_message_passes_through(self, fin_client):
        db = db_with("draft")
        db.errors[("budget_lines", "update")] = api_error("PT409", "Budget line X is locked (contract executed).")
        resp = fin_client(db, ADMIN).patch(f"/api/v1/budget-lines/{L_PERMIT}", json={"payment_terms_days": 10})
        assert resp.status_code == 409 and "locked" in resp.json()["detail"]

    def test_remove_and_reorder_use_procedures(self, fin_client):
        db = db_with()
        db.rpc_handlers["fn_remove_budget_line"] = lambda p: [{"id": p["p_line_id"]}]
        db.rpc_handlers["fn_reorder_budget_lines"] = lambda p: [{"id": x} for x in p["p_line_ids"]]
        tc = fin_client(db, ADMIN)
        assert tc.delete(f"/api/v1/budget-lines/{L_PERMIT}").status_code == 204
        resp = tc.put(f"/api/v1/projects/{P}/budget/lines/order", json={"line_ids": [L_LAND, L_PERMIT]})
        assert resp.json() == {"line_count": 2}
        assert db.calls("fn_reorder_budget_lines")[0]["p_line_ids"] == [L_LAND, L_PERMIT]

    def test_remove_task_line_conflict(self, fin_client):
        db = db_with()
        db.rpc_handlers["fn_remove_budget_line"] = lambda p: api_error(
            "PT409", 'This line belongs to task "Clearing". Delete the task (Tasks tab) and its budget line goes with it.')
        resp = fin_client(db, ADMIN).delete(f"/api/v1/budget-lines/{L_TASK}")
        assert resp.status_code == 409 and "Delete the task" in resp.json()["detail"]


# ── Land closings ───────────────────────────────────────────────────────────
class TestLandClosings:
    def test_sequence_increments(self, fin_client):
        db = db_with()
        tc = fin_client(db, ADMIN)
        for amount in ("160000", "240000.50"):
            assert tc.post(f"/api/v1/budget-lines/{L_LAND}/closings", json={
                "acres": "40", "amount": amount, "planned_closing_date": "2027-01-15"}).status_code == 201
        rows = db.tables["land_closings"]
        assert [r["closing_sequence"] for r in rows] == [1, 2]
        assert rows[1]["amount"] == "240000.50"

    def test_only_on_land_lines(self, fin_client):
        resp = fin_client(db_with(), ADMIN).post(f"/api/v1/budget-lines/{L_PERMIT}/closings",
                                                 json={"amount": "1", "planned_closing_date": "2027-01-01"})
        assert resp.status_code == 422

    def test_close_requires_actual_date(self, fin_client):
        db = db_with(land_closings=[{"id": "c1", "project_id": P, "budget_line_id": L_LAND, "closing_sequence": 1,
                                     "amount": "1", "planned_closing_date": "2027-01-01", "status": "planned",
                                     "actual_closing_date": None}])
        tc = fin_client(db, ADMIN)
        cid = "77777777-7777-7777-7777-777777777777"
        db.tables["land_closings"][0]["id"] = cid
        assert tc.patch(f"/api/v1/land-closings/{cid}", json={"status": "closed"}).status_code == 422
        resp = tc.patch(f"/api/v1/land-closings/{cid}", json={"status": "closed", "actual_closing_date": "2027-01-20"})
        assert resp.status_code == 200 and db.tables["land_closings"][0]["status"] == "closed"


# ── Template (Task 2.1) ─────────────────────────────────────────────────────
class TestTemplate:
    def _db(self):
        return MemDB({
            "budget_templates": [{"id": TMPL, "is_default": True, "is_active": True, "deleted_at": None}],
            "budget_template_lines": [
                {"id": "a1", "budget_template_id": TMPL, "line_type": "land", "name": "Land", "sort_order": 10, "is_active": True},
                {"id": "a2", "budget_template_id": TMPL, "line_type": "contingency", "name": "Contingency", "sort_order": 20, "is_active": True},
            ],
        })

    def test_add_line_appends(self, fin_client):
        db = self._db()
        resp = fin_client(db, ADMIN).post(f"/api/v1/budget-templates/{TMPL}/lines", json={
            "line_type": "bid_activity", "name": "Clearing", "section_name": "Site work", "default_amount": "0"})
        assert resp.status_code == 201
        assert db.tables["budget_template_lines"][-1]["sort_order"] == 30

    def test_single_contingency(self, fin_client):
        resp = fin_client(self._db(), ADMIN).post(f"/api/v1/budget-templates/{TMPL}/lines",
                                                  json={"line_type": "contingency", "name": "C2"})
        assert resp.status_code == 409

    def test_variance_not_allowed_in_template(self, fin_client):
        resp = fin_client(self._db(), ADMIN).post(f"/api/v1/budget-templates/{TMPL}/lines",
                                                  json={"line_type": "variance", "name": "V"})
        assert resp.status_code == 422

    def test_reorder_requires_every_line(self, fin_client):
        db = self._db()
        tc = fin_client(db, ADMIN)
        a1 = "a1a1a1a1-0000-0000-0000-000000000000"
        a2 = "a2a2a2a2-0000-0000-0000-000000000000"
        db.tables["budget_template_lines"][0]["id"] = a1
        db.tables["budget_template_lines"][1]["id"] = a2
        assert tc.put(f"/api/v1/budget-templates/{TMPL}/lines/order", json={"line_ids": [a2]}).status_code == 422
        assert tc.put(f"/api/v1/budget-templates/{TMPL}/lines/order", json={"line_ids": [a2, a1]}).status_code == 200
        order = {r["id"]: r["sort_order"] for r in db.tables["budget_template_lines"]}
        assert order == {a2: 10, a1: 20}

    def test_template_edits_never_touch_budget_lines(self, fin_client):
        db = self._db()
        db.tables["budget_lines"] = [line(L_PERMIT, template_line_id="a1")]
        tid = "a1a1a1a1-0000-0000-0000-000000000000"
        db.tables["budget_template_lines"][0]["id"] = tid
        tc = fin_client(db, ADMIN)
        assert tc.patch(f"/api/v1/budget-template-lines/{tid}", json={"name": "Renamed"}).status_code == 200
        assert tc.delete(f"/api/v1/budget-template-lines/{tid}").status_code == 204
        assert db.tables["budget_lines"][0]["name"] == "Permits"


def test_money_never_becomes_float():
    from app.services.financial_errors import money
    assert money(Decimal("0.10") + Decimal("0.20")) == "0.30"


class TestResetDraft:
    def test_reset_draft_calls_procedure(self, fin_client):
        db = db_with("draft")
        db.rpc_handlers["fn_reset_draft_budget"] = lambda p: [{"budget_status": "none"}]
        resp = fin_client(db, ADMIN).post(f"/api/v1/projects/{P}/budget/reset")
        assert resp.status_code == 200 and resp.json() == {"budget_status": "none"}
        assert db.calls("fn_reset_draft_budget")[0]["p_actor"] == ADMIN["user_id"]

    def test_baselined_cannot_be_reset(self, fin_client):
        assert fin_client(db_with("baselined"), ADMIN).post(f"/api/v1/projects/{P}/budget/reset").status_code == 409

    def test_admin_only(self, fin_client):
        assert fin_client(db_with("draft"), PM).post(f"/api/v1/projects/{P}/budget/reset").status_code == 403
