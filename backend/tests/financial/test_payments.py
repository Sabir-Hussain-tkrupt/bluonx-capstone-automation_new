"""Payment approvals (Phase 6): the rules engine, PO PDF, exports and emails."""

from __future__ import annotations

import csv
import io
from decimal import Decimal as D

import pytest
from openpyxl import load_workbook

from app.services import finance_exports, payment_rules as r, po_pdf
from app.services.template_renderer import template_renderer

POL = r.Policy(default_limit=D("5000"), executive_threshold=D("50000"))
FM = r.Approver("fm", frozenset({"project_manager", "field_manager"}) - {"project_manager"})
EXT = r.Approver("ext", frozenset({"field_manager"}), is_employee=False)
PM = r.Approver("pm", frozenset({"project_manager"}))
PM2 = r.Approver("pm2", frozenset({"project_manager"}))
EXEC = r.Approver("ex", frozenset({"project_manager", "executive"}))
EXEC2 = r.Approver("ex2", frozenset({"executive"}))
FINANCE = r.Approver("fin", frozenset({"finance"}))


def pay(status="pending", gross="1000", **kw) -> r.Payment:
    return r.Payment(status=status, gross=D(gross), **kw)


# ── First step: the field manager ───────────────────────────────────────────


def test_internal_within_limit_is_one_approver():
    assert r.decide(pay(gross="5000"), FM, POL) == r.Decision(True, "field", "approved")


def test_over_limit_goes_to_a_manager():
    d = r.decide(pay(gross="5000.01"), FM, POL)
    assert (d.step, d.next_status, d.route_to_manager) == ("field", "awaiting_manager", True)


def test_external_confirms_but_never_authorises():
    d = r.decide(pay(gross="1"), EXT, POL)
    assert (d.allowed, d.next_status, d.route_to_manager) == (True, "awaiting_manager", True)
    assert not r.decide(pay("awaiting_manager", field_approved_by="fm"), EXT, POL).allowed


def test_personal_limit_overrides_default():
    big = r.Approver("fm", frozenset({"field_manager"}), approval_limit=D("20000"))
    assert r.decide(pay(gross="20000"), big, POL).next_status == "approved"
    small_pm = r.Approver("pm", frozenset({"project_manager"}), approval_limit=D("100"))
    assert r.decide(pay(gross="101"), small_pm, POL).next_status == "awaiting_manager"


def test_manager_without_limit_has_no_limit_but_executive_level_applies():
    assert r.decide(pay(gross="49999"), PM, POL).next_status == "approved"
    assert r.decide(pay(gross="50001"), PM, POL).next_status == "awaiting_executive"
    assert r.decide(pay(gross="50001"), PM, r.Policy()).next_status == "approved"


def test_finance_cannot_confirm_work():
    assert not r.decide(pay(), FINANCE, POL).allowed


def test_variance_creator_never_approves():
    assert not r.decide(pay(variance_created_by="fm"), FM, POL).allowed
    assert not r.can_reject(pay(variance_created_by="pm"), PM)


# ── Second and executive steps ──────────────────────────────────────────────


def test_two_person_rule():
    p = pay("awaiting_manager", "8000", field_approved_by="pm")
    assert not r.decide(p, PM, POL).allowed
    assert r.decide(p, PM2, POL) == r.Decision(True, "manager", "approved")


def test_second_approval_by_routed_person_or_manager_only():
    p = pay("awaiting_manager", "8000", field_approved_by="fm", routed_to="boss")
    assert not r.decide(p, r.Approver("other", frozenset({"field_manager"})), POL).allowed
    assert r.decide(p, r.Approver("boss", frozenset({"field_manager"})), POL).allowed


def test_manager_over_own_limit_is_refused():
    p = pay("awaiting_manager", "8000", field_approved_by="fm")
    assert not r.decide(p, r.Approver("pm", frozenset({"project_manager"}), approval_limit=D("7000")), POL).allowed


def test_executive_after_manager_above_threshold():
    p = pay("awaiting_manager", "60000", field_approved_by="fm")
    assert r.decide(p, PM, POL).next_status == "awaiting_executive"
    p = pay("awaiting_executive", "60000", field_approved_by="fm", manager_approved_by="ex")
    assert not r.decide(p, PM2, POL).allowed            # not an executive
    assert not r.decide(p, EXEC, POL).allowed           # already approved it
    assert r.decide(p, EXEC2, POL) == r.Decision(True, "executive", "approved")


def test_closed_statuses_are_not_actionable():
    for status in ("approved", "sent_to_finance", "rejected", "cancelled"):
        assert not r.decide(pay(status), PM, POL).allowed
        assert not r.can_reject(pay(status), PM)


def test_reject_needs_an_internal_reviewer():
    assert r.can_reject(pay("awaiting_manager"), PM)
    assert not r.can_reject(pay("awaiting_manager"), EXT)
    assert not r.can_reject(pay("awaiting_manager"), FINANCE)
    assert r.can_reject(pay("awaiting_manager", routed_to="fin"), FINANCE)


# ── Routing ─────────────────────────────────────────────────────────────────


def test_routing_manager_then_delegate_then_backup_then_project_manager():
    assert r.pick_manager([("m", None, "b", True)], {"fm"}) == "m"
    assert r.pick_manager([("m", "d", "b", True)], {"fm"}) == "d"          # away: delegate
    assert r.pick_manager([("m", None, "b", False)], {"fm"}) == "b"        # unavailable: backup
    assert r.pick_manager([(None, None, None, True), ("pm", None, None, True)], set()) == "pm"
    assert r.pick_manager([("fm", None, None, True)], {"fm"}) is None      # never back to yourself
    assert r.pick_manager([], set()) is None


# ── PO, exports, emails ─────────────────────────────────────────────────────

PAYLOAD = {
    "po_number": "C-7-001", "project": "Oak <Ridge>", "line": "Grading", "trade": "Grading", "vendor": "Dirt Co",
    "contract_number": "C-7", "payment_kind": "progress", "progress_percent": "50.00", "gross_amount": "10000.00",
    "retainage_amount": "1000.00", "amount": "9000.00", "approved_on": "2026-11-27",
    "expected_payment_date": "2027-01-11", "payment_terms_days": 45,
    "approvers": {"work_confirmed_by": "Fay", "field_approved_by": "Fay", "manager_approved_by": "Pat"},
}
HANDOFF = {"po_number": "C-7-001", "amount": "9000.00", "payload": PAYLOAD, "sent_at": "2026-11-27T10:00:00+00:00",
           "delivery_status": "delivered"}


def test_po_pdf_contains_the_record():
    pdf = po_pdf.build(PAYLOAD)
    assert pdf.startswith(b"%PDF")
    assert po_pdf.approvers_text(PAYLOAD) == "Work confirmed by: Fay; Manager approval: Pat"
    assert po_pdf.kind_label(PAYLOAD) == "Progress payment (50% of the line)"


def test_exports():
    rows = list(csv.reader(io.StringIO(finance_exports.to_csv([HANDOFF]).decode("utf-8-sig"))))
    assert rows[0] == finance_exports.HEADERS
    assert rows[1][0] == "C-7-001" and rows[1][11] == "9000.00" and rows[1][-1] == "delivered"
    ws = load_workbook(io.BytesIO(finance_exports.to_xlsx([HANDOFF]))).active
    assert ws["A2"].value == "C-7-001" and ws["L2"].value == 9000
    qb = list(csv.reader(io.StringIO(finance_exports.to_quickbooks([HANDOFF], "Job Expenses").decode("utf-8-sig"))))
    assert qb[0] == finance_exports.QB_HEADERS
    assert qb[1][:5] == ["C-7-001", "Dirt Co", "11/27/2026", "01/11/2027", "Net 45"]
    assert qb[1][7:] == ["Job Expenses", "Grading (Grading)", "9000.00"]


@pytest.mark.parametrize("name", ["payment_approval_request", "payment_rejected", "payment_approved_trade",
                                  "payment_approved_team"])
def test_notice_emails_render(name):
    ctx = {"heading": "H", "intro": "Intro", "rows": [("Project", "Oak <Ridge>")], "link": "https://x.test/p/1",
           "vendor": "Dirt Co", "approvers": "Pat", "cc": "Fay", "is_copy": True}
    html = template_renderer.render(f"{name}.html", ctx)
    text = template_renderer.render_text(f"{name}.txt", ctx)
    assert "Oak &lt;Ridge&gt;" in html and "Oak <Ridge>" in text and "https://x.test/p/1" in text


def test_finance_emails_render():
    ctx = {"payload": PAYLOAD, "approvers": "Pat", "kind": "Progress", "usd": po_pdf.usd, "link": "https://x.test"}
    for ext in ("html", "txt"):
        body = getattr(template_renderer, "render" if ext == "html" else "render_text")(f"finance_handoff.{ext}", ctx)
        assert "C-7-001" in body and "$9,000.00" in body
        summary = getattr(template_renderer, "render" if ext == "html" else "render_text")(
            f"finance_daily_summary.{ext}", {"new": [HANDOFF], "pending": [HANDOFF], "usd": po_pdf.usd, "link": "x"})
        assert "C-7-001" in summary and "Dirt Co" in summary
