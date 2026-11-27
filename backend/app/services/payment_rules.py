"""Payment approver rules (Phase 6 · Task 6.2). Pure: no database, no clock.

Who may take the next step on a payment, and where it goes next:

  pending            → the field manager confirms the work is complete.
                       Internal and within their limit: approved (one approver).
                       Above their limit, or external: a manager must approve.
  awaiting_manager   → a different, internal manager (or the person it was
                       routed to) approves, within their own limit if they
                       have one.
  awaiting_executive → a different, internal executive approves.

Above the executive threshold an executive approval is always added last.
External (is_employee = False) people can confirm work but never authorise
payment. The creator of a variance never approves it. The database re-checks
the hard rules (fn_payment_approval_step).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

MANAGER_ROLES = frozenset({"project_manager", "executive", "admin"})
CONFIRM_ROLES = MANAGER_ROLES | {"field_manager"}
OPEN = ("pending", "field_approved", "awaiting_manager", "awaiting_executive")


@dataclass(frozen=True)
class Approver:
    id: str
    roles: frozenset[str] = field(default_factory=frozenset)
    is_employee: bool = True
    approval_limit: Decimal | None = None

    @property
    def is_manager(self) -> bool:
        return bool(self.roles & MANAGER_ROLES)


@dataclass(frozen=True)
class Policy:
    default_limit: Decimal = Decimal("5000")
    executive_threshold: Decimal | None = None


@dataclass(frozen=True)
class Payment:
    status: str
    gross: Decimal
    field_approved_by: str | None = None
    manager_approved_by: str | None = None
    executive_approved_by: str | None = None
    confirmed_by_external: bool = False
    routed_to: str | None = None
    variance_created_by: str | None = None


@dataclass(frozen=True)
class Decision:
    allowed: bool
    step: str | None = None          # field | manager | executive
    next_status: str | None = None
    route_to_manager: bool = False   # caller picks who (reports-to / backup)
    reason: str | None = None


def effective_limit(a: Approver, policy: Policy) -> Decimal | None:
    """None = no limit (a manager without a personal limit)."""
    if a.approval_limit is not None:
        return a.approval_limit
    return None if a.is_manager else policy.default_limit


def executive_needed(p: Payment, policy: Policy) -> bool:
    return policy.executive_threshold is not None and p.gross > policy.executive_threshold


def _no(reason: str) -> Decision:
    return Decision(False, reason=reason)


def decide(p: Payment, actor: Approver, policy: Policy) -> Decision:
    if p.variance_created_by and actor.id == p.variance_created_by:
        return _no("You created this variance, so a different person must approve it.")

    if p.status == "pending":
        if not actor.roles & CONFIRM_ROLES:
            return _no("Only a field manager, project manager, executive or admin can confirm the work.")
        if not actor.is_employee:
            return Decision(True, "field", "awaiting_manager", route_to_manager=True)
        limit = effective_limit(actor, policy)
        if limit is not None and p.gross > limit:
            return Decision(True, "field", "awaiting_manager", route_to_manager=True)
        if executive_needed(p, policy):
            return Decision(True, "field", "awaiting_executive")
        return Decision(True, "field", "approved")

    if p.status == "awaiting_manager":
        if not actor.is_employee:
            return _no("Only internal employees can authorise payment.")
        if actor.id == p.field_approved_by:
            return _no("You gave the first approval, so a different person must give the second.")
        if not actor.is_manager and actor.id != p.routed_to:
            return _no("Waiting for a manager's approval.")
        if actor.approval_limit is not None and p.gross > actor.approval_limit:
            return _no(f"This amount is above your approval limit of ${actor.approval_limit:,.2f}.")
        if executive_needed(p, policy):
            return Decision(True, "manager", "awaiting_executive")
        return Decision(True, "manager", "approved")

    if p.status == "awaiting_executive":
        if not actor.is_employee or "executive" not in actor.roles:
            return _no("Waiting for an executive's approval.")
        if actor.id in (p.field_approved_by, p.manager_approved_by):
            return _no("You already approved this payment, so a different executive must approve it.")
        return Decision(True, "executive", "approved")

    return _no(f"This payment is {p.status.replace('_', ' ')}.")


def can_reject(p: Payment, actor: Approver) -> bool:
    if p.status not in OPEN or not actor.is_employee:
        return False
    if p.variance_created_by and actor.id == p.variance_created_by:
        return False
    return bool(actor.roles & CONFIRM_ROLES) or actor.id == p.routed_to


def pick_manager(candidates: list[tuple[str | None, str | None, str | None, bool]], exclude: set[str]) -> str | None:
    """Second approver from (manager, active delegate, backup, manager available)
    tuples in order: the person's reports-to, then the project's manager.

    A delegate stands in while one is set; an unavailable manager is replaced by
    their backup. None = nobody specific: any manager may approve.
    """
    for manager, delegate, backup, available in candidates:
        if not manager:
            continue
        for who in (delegate, manager if available else None, backup):
            if who and who not in exclude:
                return who
    return None
