"""Phase 2 · Task 2.8 — budget import / export; totals exact to the cent."""

import csv
import io
from decimal import Decimal

from openpyxl import Workbook, load_workbook

from tests.financial._memdb import MemDB
from tests.financial.conftest import ADMIN, PM

P = "11111111-1111-1111-1111-111111111111"
L1 = "22222222-2222-2222-2222-222222222222"
L2 = "33333333-3333-3333-3333-333333333333"
L3 = "44444444-4444-4444-4444-444444444444"


def view_row(id_, name, section, amount, **kw):
    base = {"id": id_, "project_id": P, "name": name, "section_name": section, "line_type": "soft_cost",
            "task_name": None, "original_estimate": None, "budget_amount": amount, "committed": "0",
            "spent": "0", "remaining": amount, "anticipated_start_date": None, "anticipated_end_date": None,
            "payment_terms_days": 30, "cash_bucket": "land", "is_locked": False, "sort_order": 0}
    base.update(kw)
    return base


# Amounts chosen so a float sum would drift (0.1 + 0.2 …)
VIEW = [
    view_row(L1, "Land purchase", "Land", "400000.10", line_type="land", sort_order=10),
    view_row(L2, "Permits", "Soft costs", "1234.20", sort_order=20,
             anticipated_start_date="2027-01-04", anticipated_end_date="2027-01-29"),
    view_row(L3, "Clearing", "Site work", "22000.03", line_type="bid_activity", task_name="Clearing",
             original_estimate="20000.00", committed="22000.03", sort_order=30, is_locked=True),
]
EXPECTED_TOTAL = Decimal("400000.10") + Decimal("1234.20") + Decimal("22000.03")


def db(status="baselined"):
    return MemDB({
        "projects": [{"id": P, "name": "Old Willow", "budget_status": status, "archived_at": None, "deleted_at": None}],
        "v_budget_lines": VIEW,
        "budget_lines": [
            {"id": L1, "project_id": P, "name": "Land purchase", "section_name": "Land", "line_type": "land",
             "budget_amount": "400000.10", "task_id": None, "deleted_at": None},
            {"id": L2, "project_id": P, "name": "Permits", "section_name": "Soft costs", "line_type": "permit",
             "budget_amount": "1234.20", "task_id": None, "deleted_at": None},
            {"id": L3, "project_id": P, "name": "Clearing", "section_name": "Site work", "line_type": "bid_activity",
             "budget_amount": "22000.03", "task_id": "t", "deleted_at": None},
        ],
    }, rpc={"fn_apply_budget_import": lambda p: {"updated": sum(1 for r in p["p_rows"] if r["line_id"]),
                                                 "added": sum(1 for r in p["p_rows"] if not r["line_id"])}})


class TestExport:
    def test_csv_total_exact(self, fin_client):
        resp = fin_client(db(), PM).get(f"/api/v1/projects/{P}/budget/export?format=csv")
        assert resp.status_code == 200
        assert "old-willow" in resp.headers["content-disposition"]
        rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
        header, total = rows[0], rows[-1]
        assert total[0] == "Total"
        assert Decimal(total[header.index("Budget")]) == EXPECTED_TOTAL
        assert rows[3][header.index("Locked")] == "Yes"

    def test_xlsx_money_cells_and_subtotals(self, fin_client):
        resp = fin_client(db(), PM).get(f"/api/v1/projects/{P}/budget/export?format=xlsx")
        assert resp.status_code == 200
        ws = load_workbook(io.BytesIO(resp.content)).active
        values = [[c.value for c in row] for row in ws.iter_rows()]
        header_idx = next(i for i, r in enumerate(values) if r[0] == "Section")
        budget_col = values[header_idx].index("Budget")
        subtotals = [r for r in values if isinstance(r[0], str) and r[0].endswith("subtotal")]
        assert [r[0] for r in subtotals] == ["Land subtotal", "Soft costs subtotal", "Site work subtotal"]
        total = next(r for r in values if r[0] == "Total")
        assert Decimal(str(total[budget_col])) == EXPECTED_TOTAL
        money_cell = ws.cell(row=header_idx + 2, column=budget_col + 1)
        assert "$" in money_cell.number_format

    def test_no_budget_409(self, fin_client):
        assert fin_client(db("none"), PM).get(f"/api/v1/projects/{P}/budget/export").status_code == 409

    def test_bad_format_422(self, fin_client):
        assert fin_client(db(), PM).get(f"/api/v1/projects/{P}/budget/export?format=pdf").status_code == 422


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestImportPreview:
    def test_csv_matching_aliases_and_errors(self, fin_client):
        content = (
            b"My company budget,,,\n"
            b"Description,Category,Cost,Start Date,Finish,Terms,Type\n"
            b"Permits,Soft costs,\"$1,500.55\",01/04/2027,01/29/2027,Net 45,\n"
            b"Survey,Soft costs,2000,,,,soft cost\n"
            b"Clearing,Site work,25000,,,,\n"
            b"Mobilisation,Site work,500,,,,bid\n"
            b"Bad dates,,10,2027-05-01,2027-04-01,,\n"
            b"Negative,,(100),,,,\n"
            b"Subtotal,,999999,,,,\n"
        )
        resp = fin_client(db("draft"), ADMIN).post(
            f"/api/v1/projects/{P}/budget/import/preview",
            files={"file": ("budget.csv", content, "text/csv")})
        assert resp.status_code == 200, resp.text
        rows = {r["name"]: r for r in resp.json()["rows"]}
        assert "Subtotal" not in rows
        assert rows["Permits"]["action"] == "update" and rows["Permits"]["line_id"] == L2
        assert rows["Permits"]["budget_amount"] == "1500.55"
        assert rows["Permits"]["anticipated_start_date"] == "2027-01-04"
        assert rows["Permits"]["payment_terms_days"] == 45
        assert rows["Survey"]["action"] == "add" and rows["Survey"]["line_type"] == "soft_cost"
        assert rows["Clearing"]["action"] == "update"            # task line: amount only
        assert rows["Mobilisation"]["action"] == "error"         # bid activity must be a task
        assert rows["Bad dates"]["action"] == "error"
        assert rows["Negative"]["action"] == "error"
        assert resp.json()["summary"] == {"update": 2, "add": 1, "error": 3}

    def test_xlsx(self, fin_client):
        content = _xlsx([["Line", "Amount"], ["Permits", 1700.1], ["New fee", 50]])
        resp = fin_client(db("draft"), ADMIN).post(
            f"/api/v1/projects/{P}/budget/import/preview",
            files={"file": ("b.xlsx", content, "application/octet-stream")})
        assert resp.status_code == 200
        rows = resp.json()["rows"]
        assert [r["action"] for r in rows] == ["update", "add"]
        assert rows[0]["budget_amount"] == "1700.10"

    def test_missing_header(self, fin_client):
        resp = fin_client(db("draft"), ADMIN).post(
            f"/api/v1/projects/{P}/budget/import/preview",
            files={"file": ("b.csv", b"foo,bar\n1,2\n", "text/csv")})
        assert resp.status_code == 422 and "header" in resp.json()["detail"]

    def test_draft_only(self, fin_client):
        resp = fin_client(db("baselined"), ADMIN).post(
            f"/api/v1/projects/{P}/budget/import/preview",
            files={"file": ("b.csv", b"Line,Amount\nPermits,1\n", "text/csv")})
        assert resp.status_code == 409

    def test_wrong_file_type(self, fin_client):
        resp = fin_client(db("draft"), ADMIN).post(
            f"/api/v1/projects/{P}/budget/import/preview",
            files={"file": ("b.pdf", b"%PDF", "application/pdf")})
        assert resp.status_code == 422

    def test_admin_only(self, fin_client):
        resp = fin_client(db("draft"), PM).post(
            f"/api/v1/projects/{P}/budget/import/preview",
            files={"file": ("b.csv", b"Line,Amount\n", "text/csv")})
        assert resp.status_code == 403


class TestImportApply:
    def test_rows_go_to_one_procedure_call(self, fin_client):
        d = db("draft")
        resp = fin_client(d, ADMIN).post(f"/api/v1/projects/{P}/budget/import/apply", json={"rows": [
            {"line_id": L2, "name": "Permits", "budget_amount": "1500.55", "anticipated_start_date": "2027-01-04",
             "anticipated_end_date": "2027-01-29", "payment_terms_days": 45},
            {"name": "Survey", "line_type": "soft_cost", "section_name": "Soft costs", "budget_amount": "2000"},
        ]})
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"updated": 1, "added": 1}
        (params,) = d.calls("fn_apply_budget_import")
        assert params["p_rows"][0]["budget_amount"] == "1500.55"
        assert params["p_actor"] == ADMIN["user_id"]

    def test_round_trip_export_then_import_changes_nothing(self, fin_client):
        d = db("draft")
        tc = fin_client(d, ADMIN)
        csv_bytes = tc.get(f"/api/v1/projects/{P}/budget/export?format=csv").content
        preview = tc.post(f"/api/v1/projects/{P}/budget/import/preview",
                          files={"file": ("b.csv", csv_bytes, "text/csv")}).json()
        current = {r["id"]: Decimal(r["budget_amount"]) for r in d.tables["budget_lines"]}
        for row in preview["rows"]:
            assert row["action"] == "update", row
            assert Decimal(row["budget_amount"]) == current[row["line_id"]]
