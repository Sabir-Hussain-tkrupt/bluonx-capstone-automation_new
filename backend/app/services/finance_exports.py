"""Finance hand-off exports (Phase 6 · Task 6.6): CSV, Excel and the
QuickBooks Online bill import. Pure: rows in, bytes out."""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

from app.services.po_pdf import approvers_text, kind_label

HEADERS = [
    "PO number", "Approved on", "Project", "Line", "Trade", "Vendor", "Contract number", "Invoice number",
    "Payment", "Work value", "Retainage held", "Amount to pay", "Expected payment date", "Approvers",
    "Sent to finance", "Delivery status",
]

# QuickBooks Online → Import data → Bills. Column names as QuickBooks expects.
QB_HEADERS = ["Bill No", "Supplier", "Bill Date", "Due Date", "Terms", "Location", "Memo", "Account",
              "Line Description", "Line Amount"]


def _money(v: Any) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def _us_date(v: Any) -> str:
    if not v:
        return ""
    try:
        return date.fromisoformat(str(v)[:10]).strftime("%m/%d/%Y")
    except ValueError:
        return str(v)


def row_values(h: dict) -> list:
    p = h.get("payload") or {}
    return [
        h.get("po_number"), p.get("approved_on"), p.get("project") or h.get("project_name"), p.get("line"),
        p.get("trade"), p.get("vendor"), p.get("contract_number"), p.get("invoice_number"), kind_label(p),
        _money(p.get("gross_amount")), _money(p.get("retainage_amount")), _money(p.get("amount") or h.get("amount")),
        p.get("expected_payment_date"), approvers_text(p), (h.get("sent_at") or "")[:19],
        h.get("delivery_status") or h.get("status"),
    ]


def to_csv(handoffs: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEADERS)
    for h in handoffs:
        w.writerow(row_values(h))
    return buf.getvalue().encode("utf-8-sig")


def to_xlsx(handoffs: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Finance hand-offs"
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for h in handoffs:
        values = row_values(h)
        ws.append([float(v) if isinstance(v, Decimal) else v for v in values])
        for col in (10, 11, 12):
            ws.cell(row=ws.max_row, column=col).number_format = "$#,##0.00"
    for i, width in enumerate([16, 12, 24, 28, 18, 24, 16, 14, 26, 12, 12, 12, 14, 48, 20, 14], start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def to_quickbooks(handoffs: list[dict], account: str) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(QB_HEADERS)
    for h in handoffs:
        p = h.get("payload") or {}
        w.writerow([
            h.get("po_number"), p.get("vendor") or "", _us_date(p.get("approved_on")),
            _us_date(p.get("expected_payment_date")),
            f"Net {p.get('payment_terms_days')}" if p.get("payment_terms_days") is not None else "",
            p.get("project") or "", f"{kind_label(p)}. Approved by {approvers_text(p)}",
            account, f"{p.get('line')} ({p.get('trade') or 'no trade'})", _money(p.get("amount") or h.get("amount")),
        ])
    return buf.getvalue().encode("utf-8-sig")
