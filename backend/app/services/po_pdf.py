"""Internal invoice / PO record PDF (Phase 6 · Task 6.4).

Built with reportlab, the library the contract PDF uses, from the hand-off
payload that was frozen at final approval.
"""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

KIND_LABELS = {"full": "Full payment", "progress": "Progress payment", "retainage_release": "Retainage release"}
APPROVER_LABELS = (
    ("work_confirmed_by", "Work confirmed by"),
    ("field_approved_by", "Field approval"),
    ("manager_approved_by", "Manager approval"),
    ("executive_approved_by", "Executive approval"),
)


def usd(value: Any) -> str:
    try:
        return f"${Decimal(str(value)):,.2f}"
    except Exception:  # noqa: BLE001 - display only
        return str(value or "")


def kind_label(payload: dict) -> str:
    label = KIND_LABELS.get(payload.get("payment_kind") or "", "Payment")
    if payload.get("payment_kind") == "progress" and payload.get("progress_percent") is not None:
        label += f" ({Decimal(str(payload['progress_percent'])).normalize():f}% of the line)"
    return label


def approvers_text(payload: dict) -> str:
    names = payload.get("approvers") or {}
    seen: list[str] = []
    for key, label in APPROVER_LABELS:
        if names.get(key) and f"{label}: {names[key]}" not in seen:
            if key == "field_approved_by" and names.get(key) == names.get("work_confirmed_by"):
                continue
            seen.append(f"{label}: {names[key]}")
    return "; ".join(seen)


def build(payload: dict) -> bytes:
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                            topMargin=0.8 * inch, bottomMargin=0.8 * inch,
                            title=f"PO {payload.get('po_number')}", author="BluOnX Development LLC")
    rows = [
        ("PO number", payload.get("po_number")),
        ("Contract number", payload.get("contract_number") or "—"),
        ("Approved on", payload.get("approved_on")),
        ("Project", payload.get("project")),
        ("Budget line", payload.get("line")),
        ("Trade", payload.get("trade") or "—"),
        ("Pay to", payload.get("vendor") or "—"),
        ("Invoice number", payload.get("invoice_number") or "—"),
        ("Payment", kind_label(payload)),
        ("Work value", usd(payload.get("gross_amount"))),
        ("Retainage held", usd(payload.get("retainage_amount"))),
        ("Amount to pay", usd(payload.get("amount"))),
        ("Payment terms", f"{payload.get('payment_terms_days')} days"),
        ("Expected payment date", payload.get("expected_payment_date")),
    ]
    table = Table([[Paragraph(f"<b>{k}</b>", styles["Normal"]), Paragraph(str(v or ""), styles["Normal"])] for k, v in rows],
                  colWidths=[2.0 * inch, 4.6 * inch])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f6f8fa")),
        ("BACKGROUND", (0, 11), (-1, 11), colors.HexColor("#e8f0fe")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    names = payload.get("approvers") or {}
    approvals = [
        [Paragraph(f"<b>{label}</b>", styles["Normal"]), Paragraph(str(names[key]), styles["Normal"])]
        for key, label in APPROVER_LABELS if names.get(key)
    ]
    story = [
        Paragraph("BluOnX Development LLC", styles["Title"]),
        Paragraph(f"Internal invoice / purchase order {payload.get('po_number')}", styles["Heading2"]),
        Spacer(1, 0.2 * inch),
        table,
        Spacer(1, 0.3 * inch),
        Paragraph("Approvals", styles["Heading3"]),
    ]
    if approvals:
        approvals_table = Table(approvals, colWidths=[2.0 * inch, 4.6 * inch])
        approvals_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de"))]))
        story.append(approvals_table)
    story += [
        Spacer(1, 0.3 * inch),
        Paragraph("Approved for payment in the BluOnX system. Finance pays outside the system; "
                  "no payment confirmation is required back.", styles["Italic"]),
    ]
    doc.build(story)
    return buf.getvalue()
