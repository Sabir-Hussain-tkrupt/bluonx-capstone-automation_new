"""Phase 2 · Task 2.6 — internal invoice intake."""

from tests.financial._memdb import MemDB, api_error
from tests.financial.conftest import ADMIN, FIELD_MANAGER, FINANCE, PM, identity

P = "11111111-1111-1111-1111-111111111111"
INV = "88888888-8888-8888-8888-888888888888"
LINE = "99999999-9999-9999-9999-999999999999"
OTHER_INV = "aaaaaaaa-1111-1111-1111-111111111111"
OTHER_USER = "bbbbbbbb-1111-1111-1111-111111111111"
PDF = b"%PDF-1.4\n%fake\n" + b"0" * 100


def project(**kw):
    return {"id": P, "budget_status": "baselined", "status": "active", "archived_at": None, "deleted_at": None, **kw}


def invoice(**kw):
    return {"id": INV, "project_id": P, "budget_line_id": None, "vendor_id": None, "payee_name": "Law LLP",
            "invoice_number": "INV-1", "invoice_date": "2027-02-05", "amount": "1200.00",
            "file_path": f"{P}/invoices/x/inv.pdf", "file_name": "inv.pdf", "file_size": 10,
            "status": "received", "notes": None, "uploaded_by": FIELD_MANAGER["user_id"],
            "created_at": "2027-02-05T10:00:00+00:00", "deleted_at": None, **kw}


def upload(tc, **fields):
    data = {"amount": "1,200.00", "payee_name": "Law LLP", "invoice_number": "INV-1", **fields}
    return tc.post(f"/api/v1/projects/{P}/invoices", data=data,
                   files={"file": ("inv.pdf", PDF, "application/pdf")})


class TestWhoCanUpload:
    def test_field_manager_pm_finance_admin_can_upload(self, fin_client):
        for who in (FIELD_MANAGER, PM, FINANCE, ADMIN):
            db = MemDB({"projects": [project()]})
            resp = upload(fin_client(db, who))
            assert resp.status_code == 201, (who["roles"], resp.text)
            assert db.uploads[0][0] == "finance-documents"

    def test_executive_only_cannot_upload(self, fin_client):
        exec_only = identity("e" * 8 + "-0000-0000-0000-000000000000", "executive")
        exec_only["roles"] = ["executive"]
        resp = upload(fin_client(MemDB({"projects": [project()]}), exec_only))
        assert resp.status_code == 403


class TestUploadValidation:
    def test_amount_parsed_exactly(self, fin_client):
        db = MemDB({"projects": [project()]})
        upload(fin_client(db, FIELD_MANAGER), amount="$1,234.56")
        row = db.tables["internal_invoices"][0]
        assert row["amount"] == "1234.56" and row["status"] == "received"
        assert row["file_path"].startswith(f"{P}/invoices/")

    def test_bad_amount(self, fin_client):
        for bad in ("abc", "0", "-5", "1.005"):
            assert upload(fin_client(MemDB({"projects": [project()]}), FIELD_MANAGER), amount=bad).status_code == 422

    def test_payee_or_vendor_required(self, fin_client):
        assert upload(fin_client(MemDB({"projects": [project()]}), FIELD_MANAGER), payee_name="").status_code == 422

    def test_file_signature_checked(self, fin_client):
        tc = fin_client(MemDB({"projects": [project()]}), FIELD_MANAGER)
        resp = tc.post(f"/api/v1/projects/{P}/invoices", data={"amount": "10", "payee_name": "X"},
                       files={"file": ("inv.pdf", b"not a pdf at all", "application/pdf")})
        assert resp.status_code in (400, 415, 422)

    def test_disallowed_extension(self, fin_client):
        tc = fin_client(MemDB({"projects": [project()]}), FIELD_MANAGER)
        resp = tc.post(f"/api/v1/projects/{P}/invoices", data={"amount": "10", "payee_name": "X"},
                       files={"file": ("run.exe", b"MZ" + b"0" * 50, "application/octet-stream")})
        assert resp.status_code in (400, 415, 422)

    def test_archived_project(self, fin_client):
        resp = upload(fin_client(MemDB({"projects": [project(archived_at="2026-01-01")]}), FIELD_MANAGER))
        assert resp.status_code == 409

    def test_file_removed_if_row_insert_fails(self, fin_client):
        db = MemDB({"projects": [project()]})
        db.errors[("internal_invoices", "insert")] = api_error("23514", "check")
        assert upload(fin_client(db, FIELD_MANAGER)).status_code == 422
        assert db.removed and db.removed[0][0] == "finance-documents"


class TestVisibility:
    def _db(self):
        return MemDB({
            "projects": [project()],
            "internal_invoices": [invoice(), invoice(id=OTHER_INV, uploaded_by=OTHER_USER)],
            "users": [], "vendors": [], "budget_lines": [],
        })

    def test_finance_sees_all(self, fin_client):
        resp = fin_client(self._db(), FINANCE).get(f"/api/v1/projects/{P}/invoices")
        assert len(resp.json()) == 2

    def test_uploader_sees_own_only(self, fin_client):
        resp = fin_client(self._db(), FIELD_MANAGER).get(f"/api/v1/projects/{P}/invoices")
        assert [r["id"] for r in resp.json()] == [INV]

    def test_other_users_invoice_is_404(self, fin_client):
        db = self._db()
        db.tables["internal_invoices"][0]["uploaded_by"] = OTHER_USER
        resp = fin_client(db, FIELD_MANAGER).get(f"/api/v1/invoices/{INV}/url")
        assert resp.status_code == 404

    def test_signed_url(self, fin_client):
        resp = fin_client(self._db(), FIELD_MANAGER).get(f"/api/v1/invoices/{INV}/url")
        assert resp.status_code == 200 and "finance-documents" in resp.json()["url"]


class TestCategorise:
    def test_calls_procedure_and_returns_overage(self, fin_client):
        result = {"invoice_id": INV, "budget_line_id": LINE, "status": "in_approval", "allowance": "800.00",
                  "overage": "400.00", "variance_id": "aaaaaaaa-0000-0000-0000-000000000000",
                  "variance_line_id": "bbbbbbbb-0000-0000-0000-000000000000", "budget_status": "baselined",
                  "payment_approvals": [{"id": "p1", "amount": 800}, {"id": "p2", "amount": 400}]}
        db = MemDB({"projects": [project()], "internal_invoices": [invoice()]},
                   rpc={"fn_categorise_internal_invoice": lambda p: result})
        resp = fin_client(db, FIELD_MANAGER).post(f"/api/v1/invoices/{INV}/categorise", json={"budget_line_id": LINE})
        assert resp.status_code == 200, resp.text
        assert resp.json()["overage"] == "400.00"
        (params,) = db.calls("fn_categorise_internal_invoice")
        assert params == {"p_invoice_id": INV, "p_line_id": LINE, "p_actor": FIELD_MANAGER["user_id"]}

    def test_wrong_line_type_message(self, fin_client):
        db = MemDB({"projects": [project()], "internal_invoices": [invoice()]}, rpc={
            "fn_categorise_internal_invoice": lambda p: api_error(
                "PT422", 'Invoices are categorised to internal T&M lines only (line "Clearing" is bid_activity)')})
        resp = fin_client(db, FIELD_MANAGER).post(f"/api/v1/invoices/{INV}/categorise", json={"budget_line_id": LINE})
        assert resp.status_code == 422 and "internal T&M" in resp.json()["detail"]


class TestEditCancel:
    def test_edit_only_while_received(self, fin_client):
        db = MemDB({"projects": [project()], "internal_invoices": [invoice(status="in_approval")]})
        resp = fin_client(db, FIELD_MANAGER).patch(f"/api/v1/invoices/{INV}", json={"amount": "10"})
        assert resp.status_code == 409

    def test_edit_received(self, fin_client):
        db = MemDB({"projects": [project()], "internal_invoices": [invoice()], "users": [], "vendors": [],
                    "budget_lines": []})
        resp = fin_client(db, FIELD_MANAGER).patch(f"/api/v1/invoices/{INV}", json={"amount": "1300.50"})
        assert resp.status_code == 200 and db.tables["internal_invoices"][0]["amount"] == "1300.50"

    def test_cancel(self, fin_client):
        db = MemDB({"projects": [project()], "internal_invoices": [invoice()], "users": [], "vendors": [],
                    "budget_lines": []})
        resp = fin_client(db, FIELD_MANAGER).post(f"/api/v1/invoices/{INV}/cancel")
        assert resp.status_code == 200 and resp.json()["status"] == "cancelled"

    def test_cannot_cancel_in_approval(self, fin_client):
        db = MemDB({"projects": [project()], "internal_invoices": [invoice(status="in_approval")]})
        assert fin_client(db, FIELD_MANAGER).post(f"/api/v1/invoices/{INV}/cancel").status_code == 409
