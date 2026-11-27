"""Contingency health calculation (Phase 5 · Tasks 5.1 to 5.3).

Pure: no database, no settings lookup, no clock. `financial_health_service`
feeds it and acts on the result.

  contingency left %  = contingency now ÷ contingency at groundbreaking
  work left % ($)     = budget not yet spent ÷ total budget
  work left % (phys.) = milestones not complete ÷ milestones
  work left %         = whichever is higher
  health alert        = contingency left % < work left %  (no buffer)

Spent, per line, is what was committed at award or what was approved / sent /
closed, whichever is higher, so a committed contract that is later paid counts
once.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

ZERO = Decimal("0")
HUNDRED = Decimal("100")
_CENT = Decimal("0.01")
_PCT_LIMIT = Decimal("99999.99")  # financial_alerts columns are DECIMAL(7,2)

HEALTH = "contingency_health"
NEAR_ZERO = "contingency_near_zero"
NEGATIVE = "contingency_negative"
RESERVE = "long_tail_reserve"
ALERT_TYPES = (HEALTH, NEAR_ZERO, NEGATIVE, RESERVE)


@dataclass(frozen=True)
class Line:
    committed: Decimal = ZERO
    approved: Decimal = ZERO
    sent: Decimal = ZERO
    land_closed: Decimal = ZERO


@dataclass(frozen=True)
class HealthInput:
    total_budget: Decimal
    contingency: Decimal
    contingency_base: Decimal | None  # at groundbreaking
    lines: tuple[Line, ...] = ()
    milestones_total: int = 0
    milestones_completed: int = 0
    near_zero_percent: Decimal = Decimal("5")
    reserve: Decimal | None = None
    live: bool = True  # baselined, and not completed / cancelled / archived


@dataclass(frozen=True)
class Check:
    type: str
    active: bool
    severity: str
    message: str


@dataclass(frozen=True)
class HealthResult:
    contingency_left_pct: Decimal | None
    work_left_dollars_pct: Decimal | None
    work_left_physical_pct: Decimal | None
    work_left_pct: Decimal | None
    work_left_basis: str | None  # "dollars" | "physical"
    spent: Decimal
    committed: Decimal   # committed at award, not yet approved
    approved: Decimal    # approved for payment, not yet sent
    sent: Decimal        # sent to finance
    land_closed: Decimal
    checks: tuple[Check, ...]


def dec(value: Any) -> Decimal:
    return ZERO if value is None or value == "" else Decimal(str(value))


def cents(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def pct_out(value: Decimal | None) -> str | None:
    """Rounded for display and storage. Comparisons use the exact value."""
    if value is None:
        return None
    return str(cents(max(min(value, _PCT_LIMIT), -_PCT_LIMIT)))


def _usd(value: Decimal) -> str:
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"


def from_row(row: dict) -> HealthInput:
    """Input from fn_project_health_inputs."""
    return HealthInput(
        total_budget=dec(row.get("total_budget")),
        contingency=dec(row.get("contingency")),
        contingency_base=None if row.get("contingency_base") is None else dec(row["contingency_base"]),
        lines=tuple(
            Line(dec(l.get("committed")), dec(l.get("approved")), dec(l.get("sent")), dec(l.get("land_closed")))
            for l in row.get("lines") or []
        ),
        milestones_total=int(row.get("milestones_total") or 0),
        milestones_completed=int(row.get("milestones_completed") or 0),
        near_zero_percent=dec(row.get("near_zero_percent", 5)),
        reserve=None if row.get("reserve") is None else dec(row["reserve"]),
        live=(
            row.get("budget_status") == "baselined"
            and row.get("contingency") is not None
            and row.get("status") in ("planning", "active", "on_hold")
            and not row.get("archived")
        ),
    )


def calculate(data: HealthInput) -> HealthResult:
    approved = sum((l.approved for l in data.lines), ZERO)
    sent = sum((l.sent for l in data.lines), ZERO)
    land = sum((l.land_closed for l in data.lines), ZERO)
    committed = sum((max(l.committed - l.approved - l.sent - l.land_closed, ZERO) for l in data.lines), ZERO)
    spent = committed + approved + sent + land

    left = None
    if data.contingency_base is not None and data.contingency_base > 0:
        left = data.contingency * HUNDRED / data.contingency_base

    dollars = None
    if data.total_budget > 0:
        dollars = max(data.total_budget - spent, ZERO) * HUNDRED / data.total_budget
    physical = None
    if data.milestones_total > 0:
        open_ = data.milestones_total - data.milestones_completed
        physical = Decimal(open_) * HUNDRED / Decimal(data.milestones_total)

    work, basis = dollars, "dollars" if dollars is not None else None
    if physical is not None and (work is None or physical > work):
        work, basis = physical, "physical"

    amount = _usd(data.contingency)
    reserve = data.reserve if data.reserve and data.reserve > 0 else None
    checks = (
        Check(
            HEALTH, data.live and left is not None and work is not None and left < work, "warning",
            f"Contingency left is {pct_out(left)}% but work left is {pct_out(work)}%"
            f" ({'milestones' if basis == 'physical' else 'budget'}). {amount} contingency remains.",
        ),
        Check(
            NEAR_ZERO,
            data.live and data.contingency >= 0 and left is not None and left <= data.near_zero_percent, "urgent",
            f"Contingency is nearly used up: {amount} left ({pct_out(left)}%, alert at {data.near_zero_percent}%).",
        ),
        Check(NEGATIVE, data.live and data.contingency < 0, "critical", f"Contingency is negative: {amount}."),
        Check(
            RESERVE, data.live and reserve is not None and data.contingency < reserve, "warning",
            f"Contingency of {amount} is below the {_usd(reserve or ZERO)} reserve for open escrows and property taxes.",
        ),
    )
    return HealthResult(left, dollars, physical, work, basis, spent, committed, approved, sent, land, checks)


def checks_payload(data: HealthInput, result: HealthResult) -> list[dict]:
    """Argument of fn_sync_financial_alerts."""
    return [
        {
            "type": c.type,
            "active": c.active,
            "severity": c.severity,
            "left_pct": pct_out(result.contingency_left_pct),
            "work_left_pct": pct_out(result.work_left_pct) if c.type == HEALTH else None,
            "remaining": str(data.contingency),
            "reserve": str(data.reserve) if c.type == RESERVE and data.reserve is not None else None,
            "message": c.message,
        }
        for c in result.checks
    ]
