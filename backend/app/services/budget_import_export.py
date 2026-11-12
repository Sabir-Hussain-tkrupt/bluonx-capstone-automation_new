"""Budget import / export (Phase 2 · Task 2.8).

Export: the budget as an Excel workbook (sections, subtotals, a totals row,
money as numeric cells with a currency format) or a flat CSV. Any active user.

Import: early budgets kept in Excel / CSV today are loaded into a DRAFT budget.
Two steps so nothing is written by surprise:
  preview — parse, validate, match rows to existing lines by name (+ section
            when names repeat); report update / add / error per row
  apply   — the confirmed rows go to fn_apply_budget_import in ONE transaction

Both formats are parsed here (openpyxl + csv) so CSV and Excel share one
validator. Headers are matched loosely ("Amount", "Budget", "Cost" …), so the
client's existing spreadsheets work without re-formatting.

Money is Decimal throughout — never float — so totals stay exact to the cent.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import Field

from app.models.budgets import CashBucket
from app.models.common import BluOnXBase
from app.services.budget_service import get_project
from app.services.financial_errors import FinancialError, call_rpc

MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_IMPORT_ROWS = 2000

EXPORT_COLUMNS = [
    ("section_name", "Section"),
    ("name", "Line"),
    ("line_type", "Type"),
    ("task_name", "Task"),
    ("original_estimate", "Original estimate"),
    ("budget_amount", "Budget"),
    ("committed", "Committed"),
    ("spent", "Spent"),
    ("remaining", "Remaining"),
    ("anticipated_start_date", "Start"),
    ("anticipated_end_date", "End"),
    ("payment_terms_days", "Payment terms (days)"),
    ("cash_bucket", "Cash bucket"),
    ("is_locked", "Locked"),
]
MONEY_COLUMNS = {"original_estimate", "budget_amount", "committed", "spent", "remaining"}

TYPE_LABELS = {
    "land": "Land",
    "bid_activity": "Bid activity",
    "internal_tm": "Internal T&M",
    "permit": "Permit",
    "impact_fee": "Impact fee",
    "soft_cost": "Soft cost",
    "contingency": "Contingency",
    "variance": "Variance",
    "long_tail": "Long-tail",
}

# Import header aliases (lower-cased, punctuation stripped) → field
HEADER_ALIASES = {
    "name": {"line", "name", "description", "item", "line item", "activity", "budget line"},
    "section_name": {"section", "category", "heading", "group", "phase"},
    "line_type": {"type", "line type", "kind"},
    "budget_amount": {"amount", "budget", "cost", "estimate", "total", "budget amount", "estimated cost"},
    "anticipated_start_date": {"start", "start date", "anticipated start", "begin"},
    "anticipated_end_date": {"end", "end date", "anticipated end", "finish", "finish date"},
    "payment_terms_days": {"terms", "payment terms", "payment terms days", "net days"},
    "cash_bucket": {"bucket", "cash bucket"},
}

TYPE_ALIASES = {
    "land": "land", "land acquisition": "land",
    "bid": "bid_activity", "bid activity": "bid_activity", "bid_activity": "bid_activity",
    "internal": "internal_tm", "internal t&m": "internal_tm", "t&m": "internal_tm", "internal_tm": "internal_tm",
    "permit": "permit", "permits": "permit",
    "impact fee": "impact_fee", "impact fees": "impact_fee", "impact_fee": "impact_fee",
    "soft cost": "soft_cost", "soft costs": "soft_cost", "soft_cost": "soft_cost", "engineering": "soft_cost",
    "contingency": "contingency",
    "long-tail": "long_tail", "long tail": "long_tail", "long_tail": "long_tail",
    "escrow": "long_tail", "property tax": "long_tail",
}
BUCKET_ALIASES = {
    "land": "land", "vertical": "vertical_construction", "vertical construction": "vertical_construction",
    "vertical_construction": "vertical_construction", "overhead": "overhead",
}


# ── Export ──────────────────────────────────────────────────────────────────


def _lines_for_export(db, project_id: str) -> list[dict]:
    return (
        db.table("v_budget_lines").select("*")
        .eq("project_id", project_id).order("sort_order").execute()
    ).data or []


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "project").lower()).strip("-")[:60] or "project"


def _dec(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal(0)
    return Decimal(str(value))


def export_budget(db, project_id: str, fmt: str) -> tuple[str, str, bytes]:
    project = get_project(db, project_id)
    if project.get("budget_status", "none") == "none":
        raise FinancialError(409, "This project has no budget yet.")
    lines = _lines_for_export(db, project_id)
    stamp = date.today().isoformat()
    base = f"budget-{_slug(project.get('name'))}-{stamp}"
    if fmt == "csv":
        return f"{base}.csv", "text/csv; charset=utf-8", _export_csv(lines)
    return (
        f"{base}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        _export_xlsx(project, lines),
    )


def _cell(key: str, line: dict) -> Any:
    value = line.get(key)
    if key in MONEY_COLUMNS:
        return None if value is None else _dec(value)
    if key == "line_type":
        return TYPE_LABELS.get(value, value)
    if key == "is_locked":
        return "Yes" if value else ""
    return value


def _export_csv(lines: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in EXPORT_COLUMNS])
    totals = {k: Decimal(0) for k in MONEY_COLUMNS}
    for line in lines:
        row = []
        for key, _ in EXPORT_COLUMNS:
            value = _cell(key, line)
            if key in MONEY_COLUMNS and value is not None:
                totals[key] += value
                value = f"{value:.2f}"
            row.append("" if value is None else value)
        writer.writerow(row)
    writer.writerow([
        "Total" if i == 0 else (f"{totals[key]:.2f}" if key in MONEY_COLUMNS else "")
        for i, (key, _) in enumerate(EXPORT_COLUMNS)
    ])
    return buf.getvalue().encode("utf-8-sig")


def _export_xlsx(project: dict, lines: list[dict]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Budget"
    money_fmt = '"$"#,##0.00'
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="E8EEFD")
    sub_fill = PatternFill("solid", fgColor="F1F3F6")

    ws.append([project.get("name") or "Project budget"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Budget status: {project.get('budget_status')} · exported {date.today().isoformat()}"])
    ws.append([])
    ws.append([label for _, label in EXPORT_COLUMNS])
    header_row = ws.max_row
    for cell in ws[header_row]:
        cell.font = bold
        cell.fill = head_fill
        cell.alignment = Alignment(vertical="center")

    money_idx = [i for i, (k, _) in enumerate(EXPORT_COLUMNS) if k in MONEY_COLUMNS]
    grand = {k: Decimal(0) for k in MONEY_COLUMNS}

    def write_subtotal(section: str | None, totals: dict) -> None:
        row = [f"{section or 'Other'} subtotal"] + [None] * (len(EXPORT_COLUMNS) - 1)
        for i in money_idx:
            row[i] = totals[EXPORT_COLUMNS[i][0]]
        ws.append(row)
        for cell in ws[ws.max_row]:
            cell.font = bold
            cell.fill = sub_fill

    sentinel = object()
    current: Any = sentinel
    section_totals = {k: Decimal(0) for k in MONEY_COLUMNS}
    for line in lines:
        section = line.get("section_name")
        if current is not sentinel and section != current:
            write_subtotal(current, section_totals)
            section_totals = {k: Decimal(0) for k in MONEY_COLUMNS}
        current = section
        row = []
        for key, _ in EXPORT_COLUMNS:
            value = _cell(key, line)
            if key in MONEY_COLUMNS and value is not None:
                section_totals[key] += value
                grand[key] += value
            if key in ("anticipated_start_date", "anticipated_end_date") and value:
                value = date.fromisoformat(str(value)[:10])
            row.append(value)
        ws.append(row)
    if current is not sentinel:
        write_subtotal(current, section_totals)

    total_row = ["Total"] + [None] * (len(EXPORT_COLUMNS) - 1)
    for i in money_idx:
        total_row[i] = grand[EXPORT_COLUMNS[i][0]]
    ws.append(total_row)
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)

    for row in ws.iter_rows(min_row=header_row + 1):
        for i in money_idx:
            row[i].number_format = money_fmt
        for key in ("anticipated_start_date", "anticipated_end_date"):
            idx = [k for k, _ in EXPORT_COLUMNS].index(key)
            row[idx].number_format = "yyyy-mm-dd"

    widths = [14, 34, 14, 22, 16, 16, 16, 14, 16, 12, 12, 12, 14, 8]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ── Import ──────────────────────────────────────────────────────────────────


class ImportRow(BluOnXBase):
    line_id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    line_type: str | None = None
    section_name: str | None = Field(default=None, max_length=100)
    budget_amount: Decimal | None = Field(default=None, ge=0)
    anticipated_start_date: date | None = None
    anticipated_end_date: date | None = None
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    cash_bucket: CashBucket | None = None


class ImportApplyRequest(BluOnXBase):
    rows: list[ImportRow] = Field(min_length=1, max_length=MAX_IMPORT_ROWS)


def _norm(text: Any) -> str:
    cleaned = re.sub(r"[^a-z0-9&\- ]+", " ", str(text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _read_rows(filename: str, content: bytes) -> list[list[Any]]:
    if len(content) > MAX_IMPORT_BYTES:
        raise FinancialError(413, "The file is larger than 2 MB.")
    name = filename.lower()
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        return [row for row in csv.reader(io.StringIO(text))]
    if name.endswith(".xlsx"):
        if not content.startswith(b"PK"):
            raise FinancialError(422, "The file is not a valid Excel workbook.")
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001 - any parse failure is a bad file
            raise FinancialError(422, "The Excel file could not be read.") from exc
        ws = wb.active
        return [list(r) for r in ws.iter_rows(values_only=True)]
    raise FinancialError(422, "Upload a .csv or .xlsx file.")


def _find_header(rows: list[list[Any]]) -> tuple[int, dict[str, int]]:
    for idx, row in enumerate(rows[:20]):
        mapping: dict[str, int] = {}
        for col, cell in enumerate(row):
            key = _norm(cell)
            for field, aliases in HEADER_ALIASES.items():
                if key in aliases and field not in mapping:
                    mapping[field] = col
        if "name" in mapping and "budget_amount" in mapping:
            return idx, mapping
    raise FinancialError(
        422,
        "Could not find the header row. The file needs at least a 'Line' (or 'Description') "
        "column and an 'Amount' (or 'Budget') column.",
    )


def _parse_money(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, (int, float, Decimal)):
        amount = Decimal(str(value))
    else:
        text = str(value).strip().replace("$", "").replace(",", "")
        if text.startswith("(") and text.endswith(")"):
            raise ValueError("negative amounts are not allowed")
        amount = Decimal(text)
    if amount < 0:
        raise ValueError("negative amounts are not allowed")
    return amount.quantize(Decimal("0.01"))


def _parse_date(value: Any) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date '{value}'")


def preview_import(db, project_id: str, filename: str, content: bytes) -> dict:
    project = get_project(db, project_id)
    if project.get("budget_status") != "draft":
        raise FinancialError(409, "Budgets can be imported only while they are a draft.")
    rows = _read_rows(filename, content)
    header_idx, cols = _find_header(rows)

    lines = (
        db.table("budget_lines").select("id, name, section_name, line_type, budget_amount, task_id")
        .eq("project_id", project_id).is_("deleted_at", "null").execute()
    ).data or []
    by_name: dict[str, list[dict]] = {}
    for line in lines:
        by_name.setdefault(_norm(line["name"]), []).append(line)

    out: list[dict] = []
    for offset, raw in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        def get(field: str, row: list[Any] = raw) -> Any:
            col = cols.get(field)
            return row[col] if col is not None and col < len(row) else None

        name = str(get("name") or "").strip()
        if not name or _norm(name).startswith(("total", "subtotal", "grand total")):
            continue
        if len(out) >= MAX_IMPORT_ROWS:
            raise FinancialError(422, f"The file has more than {MAX_IMPORT_ROWS} rows.")

        errors: list[str] = []
        warnings: list[str] = []
        item: dict[str, Any] = {"row_number": offset, "name": name[:255]}

        section = str(get("section_name") or "").strip() or None
        item["section_name"] = section[:100] if section else None

        raw_type = _norm(get("line_type"))
        line_type = TYPE_ALIASES.get(raw_type) if raw_type else None
        if raw_type and not line_type:
            warnings.append(f"unknown type '{get('line_type')}', treated as soft cost")
        item["line_type"] = line_type

        for field, parser in (
            ("budget_amount", _parse_money),
            ("anticipated_start_date", _parse_date),
            ("anticipated_end_date", _parse_date),
        ):
            try:
                value = parser(get(field))
                item[field] = value.isoformat() if isinstance(value, date) else (
                    str(value) if value is not None else None)
            except (ValueError, InvalidOperation) as exc:
                item[field] = None
                errors.append(f"{field.replace('_', ' ')}: {exc}" if str(exc) else f"invalid {field}")
        if item.get("anticipated_start_date") and item.get("anticipated_end_date") \
                and item["anticipated_end_date"] < item["anticipated_start_date"]:
            errors.append("end date is before start date")

        terms = get("payment_terms_days")
        if terms not in (None, ""):
            try:
                t = int(Decimal(str(terms).lower().replace("net", "").replace("days", "").strip()))
                if not 0 <= t <= 365:
                    raise ValueError
                item["payment_terms_days"] = t
            except (ValueError, InvalidOperation):
                errors.append(f"payment terms '{terms}' must be 0–365 days")
        bucket = _norm(get("cash_bucket"))
        if bucket:
            if bucket in BUCKET_ALIASES:
                item["cash_bucket"] = BUCKET_ALIASES[bucket]
            else:
                errors.append(f"unknown cash bucket '{get('cash_bucket')}'")

        matches = by_name.get(_norm(name), [])
        if len(matches) > 1 and section:
            matches = [m for m in matches if _norm(m.get("section_name")) == _norm(section)] or matches
        if len(matches) > 1:
            errors.append("several budget lines have this name; add a Section column to tell them apart")
        if len(matches) == 1:
            match = matches[0]
            item["action"] = "update"
            item["line_id"] = match["id"]
            item["current_amount"] = match["budget_amount"]
            if line_type and line_type != match["line_type"]:
                warnings.append(f"type in file ({line_type}) differs from the line ({match['line_type']}); the line keeps its type")
        else:
            item["action"] = "add"
            item["line_id"] = None
            if (line_type or "soft_cost") in ("bid_activity", "contingency", "variance"):
                errors.append("bid activities and contingency come from tasks / the budget — add the task instead")

        if errors:
            item["action"] = "error"
        item["errors"] = errors
        item["warnings"] = warnings
        out.append(item)

    summary = {
        "update": sum(1 for r in out if r["action"] == "update"),
        "add": sum(1 for r in out if r["action"] == "add"),
        "error": sum(1 for r in out if r["action"] == "error"),
    }
    return {"rows": out, "summary": summary}


def apply_import(db, project_id: str, rows: list[ImportRow], actor_id: str) -> dict:
    project = get_project(db, project_id)
    if project.get("archived_at"):
        raise FinancialError(409, "This project is archived.")
    payload = []
    for row in rows:
        if row.anticipated_start_date and row.anticipated_end_date and row.anticipated_end_date < row.anticipated_start_date:
            raise FinancialError(422, f"'{row.name}': end date is before start date.")
        payload.append({
            "line_id": row.line_id,
            "name": row.name,
            "line_type": row.line_type,
            "section_name": row.section_name,
            "budget_amount": str(row.budget_amount) if row.budget_amount is not None else None,
            "anticipated_start_date": row.anticipated_start_date.isoformat() if row.anticipated_start_date else None,
            "anticipated_end_date": row.anticipated_end_date.isoformat() if row.anticipated_end_date else None,
            "payment_terms_days": row.payment_terms_days,
            "cash_bucket": row.cash_bucket,
        })
    result = call_rpc(
        db, "fn_apply_budget_import",
        {"p_project_id": project_id, "p_rows": payload, "p_actor": str(actor_id)},
        "The import could not be applied. Please try again.",
    )
    return result or {"updated": 0, "added": 0}
