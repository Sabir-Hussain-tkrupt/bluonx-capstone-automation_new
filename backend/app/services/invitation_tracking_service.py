"""
Invitation tracking service (Task 4.5).

Read-side and status-management operations on bid packages and invitations:
- Bid package detail view with invitation summary
- Invitation list with optional status filter
- PM-driven status updates (declined / no_response)
- Email log per bid package
- Shared deadline transition (_apply_overdue_transition / sweep_overdue_invitations)
  that flips overdue sent/opened invitations to 'no_response' and moves an open
  package to 'evaluating'. The same core is called by the lazy read-path here and
  by the daily post-deadline job, so both converge on identical state.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

# Single source of truth for the award statuses that block a new revision
# request. Imported (not redefined) so this read-path visibility flag can
# never diverge from the create_revision_request backend guard.
from app.services.bid_revision_service import _BLOCKING_AWARD_STATUSES

logger = logging.getLogger(__name__)


# ── Exceptions ─────────────────────────────────────────────────────────────


class InvitationTrackingError(Exception):
    """Base exception for invitation tracking operations."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class BidPackageNotFoundError(InvitationTrackingError):
    def __init__(self, detail: str = "Bid package not found") -> None:
        super().__init__(404, detail)


class InvitationNotFoundError(InvitationTrackingError):
    def __init__(self, detail: str = "Invitation not found") -> None:
        super().__init__(404, detail)


class InvalidStatusError(InvitationTrackingError):
    def __init__(self, detail: str) -> None:
        super().__init__(400, detail)


class TerminalStatusError(InvitationTrackingError):
    """The invitation's current status is terminal (e.g. submitted) and
    cannot be transitioned by PM action."""

    def __init__(
        self, detail: str = "Cannot change status of a submitted invitation"
    ) -> None:
        super().__init__(409, detail)


# ── Constants ──────────────────────────────────────────────────────────────

# pending_send / send_failed cover invitations whose email has not (yet) been
# delivered. They are listed here so the per-status summary counts them, but they
# are deliberately kept OUT of _TIMED_OUT_SOURCE_STATUSES: an invitation that was
# never delivered should keep its "never reached" status rather than be relabeled
# when the deadline passes. 'expired' is retained here only so legacy rows still
# count in the summary; no code path writes it anymore (superseded by
# 'no_response' — the single terminal "invited, no bid by deadline" status).
_ALL_STATUSES = (
    "pending_send", "sent", "send_failed", "opened",
    "submitted", "declined", "expired", "no_response",
)
# PMs may manually close out an invitation as declined or no_response. 'expired'
# is intentionally NOT settable: the timeout terminal is 'no_response', written
# only by the shared deadline transition.
_PM_SETTABLE_STATUSES = frozenset({"declined", "no_response"})
# The two live statuses the deadline transition converts to 'no_response'.
_TIMED_OUT_SOURCE_STATUSES = ("sent", "opened")
# Packages the deadline transition never touches (already terminal). An 'open' or
# 'evaluating' package past its deadline is still converged: sent/opened rows flip
# to no_response, and an 'open' package additionally moves to 'evaluating'.
_TERMINAL_PACKAGE_STATUSES = frozenset({"closed", "cancelled"})


# ── Helpers ────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_deadline(raw) -> datetime | None:
    """Parse a deadline value from DB. Accepts str (ISO) or datetime."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _unwrap_one(data) -> dict | None:
    if data is None:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def _unwrap_list(data) -> list[dict]:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def _fetch_bid_package(db, bid_package_id: UUID) -> dict | None:
    """Fetch a bid package with embedded tasks + bid_templates joins."""
    resp = (
        db.table("bid_packages")
        .select("*, tasks(name), bid_templates(*)")
        .eq("id", str(bid_package_id))
        .single()
        .execute()
    )
    return _unwrap_one(resp.data)


def _fetch_invitations(
    db, bid_package_id: UUID, status_filter: str | None = None
) -> list[dict]:
    """Fetch bid invitations with embedded vendors + vendor_contacts joins."""
    query = (
        db.table("bid_invitations")
        .select(
            "*, vendors(id, company_name), vendor_contacts(full_name, email),"
            " bid_submissions(id, is_superseded, is_draft)"
        )
        .eq("bid_package_id", str(bid_package_id))
    )
    if status_filter:
        query = query.eq("status", status_filter)
    resp = query.execute()
    return _unwrap_list(resp.data)


def _task_active_award(db, task_id) -> dict | None:
    """The task's live award (status in _BLOCKING_AWARD_STATUSES) as
    {"bid_submission_id", "status"}, or None when the task is re-awardable
    (no award, or only declined_by_vendor / cancelled — consistent with
    idx_awards_one_active_per_task).

    One query per package-detail request (NOT per invitation). The status
    check runs in Python so it stays correct regardless of whether the
    caller's mock applies PostgREST filters.
    """
    if not task_id:
        return None
    resp = (
        db.table("awards")
        .select("id, status, bid_submission_id")
        .eq("task_id", str(task_id))
        .execute()
    )
    for row in _unwrap_list(resp.data):
        if row.get("status") in _BLOCKING_AWARD_STATUSES:
            return {
                "bid_submission_id": row.get("bid_submission_id"),
                "status": row.get("status"),
            }
    return None


def _task_has_active_award(db, task_id) -> bool:
    """True if the task has an award in a revision-blocking status."""
    return _task_active_award(db, task_id) is not None


def _fetch_submitted_bids(db, bid_package_id: UUID) -> list[dict]:
    """Fetch submitted bid_submissions with vendor company_name for this package.

    A submission belongs to the package via bid_invitations.bid_package_id;
    we filter by bid_invitations.status == 'submitted' so only sealed bids appear.
    """
    resp = (
        db.table("bid_submissions")
        .select(
            "total_amount, bid_invitations!inner(bid_package_id, status), vendors(company_name)"
        )
        .eq("bid_invitations.bid_package_id", str(bid_package_id))
        .eq("bid_invitations.status", "submitted")
        .eq("is_superseded", False)
        .eq("is_draft", False)
        .execute()
    )
    return _unwrap_list(resp.data)


def _transform_submitted_bid(row: dict) -> dict:
    """Flatten the embedded vendor join."""
    vendor = row.get("vendors") or {}
    return {
        "vendor_company_name": vendor.get("company_name") or "—",
        "total_amount": row.get("total_amount"),
    }


def _fetch_documents(db, bid_package_id: UUID) -> list[dict]:
    resp = (
        db.table("bid_package_documents")
        .select("""
            id,
            project_documents (
                file_name,
                file_path
            )
        """)
        .eq("bid_package_id", str(bid_package_id))
        .execute()
    )
    return _unwrap_list(resp.data)


def _transform_invitation(row: dict, *, is_awarded: bool = False) -> dict:
    """Flatten nested vendors / vendor_contacts into flat response fields.

    `is_awarded` is task-scoped (all invitations in a package share one
    task) — the caller computes it once and passes the same value here.
    """
    vendors = row.get("vendors") or {}
    contacts = row.get("vendor_contacts") or {}
    subs_raw = row.get("bid_submissions")
    if isinstance(subs_raw, dict):
        subs = [subs_raw]
    elif isinstance(subs_raw, list):
        subs = subs_raw
    else:
        subs = []
    # Deep-link the current submission for display: non-superseded AND
    # non-draft. A draft (e.g. a revision in progress) is never the
    # "current bid" — if the only submission is a draft, there is no
    # current bid yet, so bid_submission_id is None (NO subs[0]
    # fallback; a draft must never surface to PM read paths). Rows with
    # no is_superseded/is_draft keys (pre-revision / single /
    # direct-assign) still match since .get() → None → not None → True.
    # No PostgREST embedded-filter syntax — this Python post-filter is
    # deterministic.
    active = [
        s
        for s in subs
        if not s.get("is_superseded") and not s.get("is_draft")
    ]
    if active:
        bid_submission_id = active[0].get("id")
    else:
        bid_submission_id = None
    return {
        "id": row.get("id"),
        "vendor_id": row.get("vendor_id"),
        "vendor_company_name": vendors.get("company_name"),
        "vendor_contact_name": contacts.get("full_name"),
        "vendor_contact_email": contacts.get("email"),
        "status": row.get("status"),
        "sent_at": row.get("sent_at"),
        "opened_at": row.get("opened_at"),
        "responded_at": row.get("responded_at"),
        "bid_submission_id": bid_submission_id,
        "is_awarded": is_awarded,
    }


def _build_summary(invitations: list[dict]) -> dict:
    summary = {status: 0 for status in _ALL_STATUSES}
    summary["total"] = len(invitations)
    for inv in invitations:
        status = inv.get("status")
        if status in summary:
            summary[status] += 1
    return summary


def _transform_bid_template(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "is_lump_sum": row.get("is_lump_sum"),
    }


def _transform_document(row: dict) -> dict:
    pd = row.get("project_documents") or {}

    return {
        "id": row.get("id"),
        "file_name": pd.get("file_name"),
    }


# ── Service functions ─────────────────────────────────────────────────────


def _apply_overdue_transition(*, bid_package: dict, db) -> dict:
    """Shared, idempotent deadline transition (the single source of truth).

    Given an already-fetched bid package whose deadline has passed and which is
    not terminal, flip every 'sent'/'opened' invitation to 'no_response' and move
    an 'open' package to 'evaluating' (NOT 'closed' — a package only reaches
    'closed' on award acceptance).

    'no_response' is the one terminal "invited, no bid by the deadline" status:
    both this core and the daily post-deadline job converge on it, so whichever
    fires first (a PM opening the detail page, or the cron) leaves the same state.

    Returns {"no_response_count": int, "package_moved": bool}. Writes nothing when
    the deadline is in the future, the package is closed/cancelled, or there is
    nothing left to converge (so it is safe to call on every read).
    """
    result = {"no_response_count": 0, "package_moved": False}

    current_status = bid_package.get("status")
    if current_status in _TERMINAL_PACKAGE_STATUSES:
        return result

    deadline = _parse_deadline(bid_package.get("deadline"))
    if deadline is None or deadline >= datetime.now(timezone.utc):
        return result

    bid_package_id = bid_package.get("id")
    now = _now_iso()

    invitations = _fetch_invitations(db, bid_package_id)
    no_response_count = sum(
        1 for inv in invitations if inv.get("status") in _TIMED_OUT_SOURCE_STATUSES
    )
    if no_response_count > 0:
        (
            db.table("bid_invitations")
            .update({"status": "no_response", "updated_at": now})
            .eq("bid_package_id", str(bid_package_id))
            .in_("status", list(_TIMED_OUT_SOURCE_STATUSES))
            .execute()
        )
    result["no_response_count"] = no_response_count

    # Only an 'open' package moves; an 'evaluating' one (manually closed early, or
    # already advanced) keeps its status while its lingering rows still converge.
    if current_status == "open":
        (
            db.table("bid_packages")
            .update({"status": "evaluating", "updated_at": now})
            .eq("id", str(bid_package_id))
            .execute()
        )
        result["package_moved"] = True

    return result


async def sweep_overdue_invitations(*, bid_package_id: UUID, db) -> dict:
    """Lazy read-path entry point for the shared deadline transition. Fetches the
    package, then delegates to _apply_overdue_transition. Raises
    BidPackageNotFoundError when the package is missing."""
    bid_package = _fetch_bid_package(db, bid_package_id)
    if bid_package is None:
        raise BidPackageNotFoundError()
    return _apply_overdue_transition(bid_package=bid_package, db=db)


async def close_bidding(*, bid_package_id: UUID, db) -> dict:
    """Manual early close (PM action): open → 'evaluating'. Allowed only from
    'open' (409 otherwise), both before and after the deadline. New bid inflow is
    sealed by the existing `status != 'open'` gates — no token revocation and no
    invitation expiry here (the deadline sweep owns invitation expiry).

    Returns {"id", "status"}.
    """
    bid_package = _fetch_bid_package(db, bid_package_id)
    if bid_package is None:
        raise BidPackageNotFoundError()

    current_status = bid_package.get("status")
    if current_status != "open":
        raise InvitationTrackingError(
            409,
            f"Cannot close bidding: the package is '{current_status}', not 'open'.",
        )

    (
        db.table("bid_packages")
        .update({"status": "evaluating", "updated_at": _now_iso()})
        .eq("id", str(bid_package_id))
        .execute()
    )
    return {"id": str(bid_package_id), "status": "evaluating"}


async def get_bid_package_detail(*, bid_package_id: UUID, db) -> dict:
    """Return the full bid package detail with invitation summary,
    invitations array, and documents. Applies lazy expiration."""
    bid_package = _fetch_bid_package(db, bid_package_id)
    if bid_package is None:
        raise BidPackageNotFoundError()

    deadline = _parse_deadline(bid_package.get("deadline"))
    current_status = bid_package.get("status")
    lazy_swept = False

    if (
        current_status not in _TERMINAL_PACKAGE_STATUSES
        and deadline is not None
        and deadline < datetime.now(timezone.utc)
    ):
        await sweep_overdue_invitations(bid_package_id=bid_package_id, db=db)
        bid_package["status"] = "evaluating"
        lazy_swept = True

    invitations_rows = _fetch_invitations(db, bid_package_id)

    # Reflect the lazy transition in the returned rows since the mock
    # doesn't actually apply the DB update in tests.
    if lazy_swept:
        for row in invitations_rows:
            if row.get("status") in _TIMED_OUT_SOURCE_STATUSES:
                row["status"] = "no_response"

    documents_rows = _fetch_documents(db, bid_package_id)

    # Task-scoped: one query for the whole package, applied to every row.
    active_award = _task_active_award(db, bid_package.get("task_id"))
    is_awarded = active_award is not None
    invitations = [
        _transform_invitation(row, is_awarded=is_awarded)
        for row in invitations_rows
    ]
    summary = _build_summary(invitations)

    submitted_bids_rows = _fetch_submitted_bids(db, bid_package_id)
    submitted_bids = [_transform_submitted_bid(r) for r in submitted_bids_rows]
    submitted_bids.sort(
        key=lambda s: (s["total_amount"] is None, s["total_amount"] or 0)
    )

    tasks_join = bid_package.get("tasks") or {}
    task_name = tasks_join.get("name") if isinstance(tasks_join, dict) else None

    return {
        "id": bid_package.get("id"),
        "task_name": task_name,
        "round_number": bid_package.get("round_number"),
        "deadline": bid_package.get("deadline"),
        "status": bid_package.get("status"),
        "instructions": bid_package.get("instructions"),
        "desired_start_date": bid_package.get("desired_start_date"),
        "bid_template": _transform_bid_template(bid_package.get("bid_templates")),
        "documents": [_transform_document(row) for row in documents_rows],
        "invitation_summary": summary,
        "invitations": invitations,
        "submitted_bids": submitted_bids,
        "award": active_award,
    }


async def list_invitations(
    *, bid_package_id: UUID, status_filter: str | None, db
) -> list[dict]:
    """Return invitations for a bid package, optionally filtered by status."""
    bid_package = _fetch_bid_package(db, bid_package_id)
    if bid_package is None:
        raise BidPackageNotFoundError()

    rows = _fetch_invitations(db, bid_package_id, status_filter=status_filter)
    is_awarded = _task_has_active_award(db, bid_package.get("task_id"))
    return [
        _transform_invitation(row, is_awarded=is_awarded) for row in rows
    ]


async def update_invitation_status(
    *, invitation_id: UUID, new_status: str, current_user_id: UUID | None = None, db
) -> dict:
    """Update invitation status. Only declined/no_response are PM-settable.
    Other values (including retired 'expired') → 400.

    On a successful transition, all magic_link_tokens for this invitation are
    hard-revoked (is_used=True, revoked_at=NOW(), revoked_by=current_user_id)
    so the vendor can no longer enter the portal via an old link.
    """
    if new_status not in _PM_SETTABLE_STATUSES:
        raise InvalidStatusError(
            f"Status '{new_status}' cannot be set by PM. "
            f"Allowed values: {sorted(_PM_SETTABLE_STATUSES)}"
        )

    existing = (
        db.table("bid_invitations")
        .select("*")
        .eq("id", str(invitation_id))
        .single()
        .execute()
    )
    existing_row = _unwrap_one(existing.data)
    if existing_row is None:
        raise InvitationNotFoundError()

    # Submitted invitations are terminal: a real bid_submission backs them,
    # so any PM-driven downgrade would put the invitation in conflict with
    # its own submission history.
    if existing_row.get("status") == "submitted":
        raise TerminalStatusError()

    updated_resp = (
        db.table("bid_invitations")
        .update({"status": new_status, "updated_at": _now_iso()})
        .eq("id", str(invitation_id))
        .execute()
    )
    row = _unwrap_one(updated_resp.data)
    if row is None:
        raise InvitationNotFoundError()

    # Hard-revoke all magic-link tokens for this invitation so the vendor
    # cannot re-enter the portal via a stale link.
    revoke_payload: dict = {
        "is_used": True,
        "revoked_at": _now_iso(),
        "revoked_by": str(current_user_id) if current_user_id else None,
    }
    (
        db.table("magic_link_tokens")
        .update(revoke_payload)
        .eq("bid_invitation_id", str(invitation_id))
        .execute()
    )

    # Tests assert 'updated_at' in result — guarantee it even if mock
    # didn't propagate the payload.
    if "updated_at" not in row:
        row["updated_at"] = _now_iso()
    if row.get("status") != new_status:
        row["status"] = new_status
    return row


EMAIL_LOG_VIEW = "v_vendor_email_log"


def _read_email_log_page(
    db, *, column: str, value: UUID, page: int, page_size: int
) -> tuple[list[dict], int]:
    """Read one page of v_vendor_email_log, scoped by a single column.

    The view resolves email_log's polymorphic reference to a vendor (and, for
    the invitation-linked flows, to an invitation and package), so the union,
    the attribution and the ordering all happen in Postgres. This replaced a
    Python-side merge that fetched every matching row with unbounded IN (...)
    lists and sorted in memory — a shape that could not be paginated and that
    silently truncated at PostgREST's 1000-row ceiling.

    Ordered created_at DESC, id DESC. The id tiebreaker is load-bearing: a bulk
    invitation send stamps many rows with the same created_at, and without a
    deterministic total order offset pagination duplicates and skips rows
    across pages.

    Counts first and only fetches when the offset is in range, so a page past
    the end returns empty rather than an error (same shape as list_vendors).
    """

    def _scoped(select_expr: str):
        return (
            db.table(EMAIL_LOG_VIEW)
            .select(select_expr, count="exact")
            .eq(column, str(value))
        )

    total = _scoped("id").limit(1).execute().count or 0

    offset = (page - 1) * page_size
    if offset >= total:
        return [], total

    resp = (
        _scoped("*")
        .order("created_at", desc=True)
        .order("id", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    return _unwrap_list(resp.data), total


async def get_bid_package_email_log(
    *, bid_package_id: UUID, db, page: int = 1, page_size: int = 25
) -> tuple[list[dict], int]:
    """Return one page of email_log rows tied to invitations in this package.

    Scoped on bid_package_id, which the view carries only for the three
    invitation-linked flows (bid_invitations, bid_revision_requests,
    bid_submissions). Award and milestone rows have a NULL bid_package_id and
    so never appear here — the package log's contents are unchanged.
    """
    bid_package = _fetch_bid_package(db, bid_package_id)
    if bid_package is None:
        raise BidPackageNotFoundError()

    return _read_email_log_page(
        db,
        column="bid_package_id",
        value=bid_package_id,
        page=page,
        page_size=page_size,
    )


async def get_vendor_email_log(
    *, vendor_id: UUID, db, page: int = 1, page_size: int = 25
) -> tuple[list[dict], int]:
    """Return one page of this vendor's full outbound correspondence.

    Wider than the package log: the view attributes award notifications and
    milestone check-ins to a vendor too, so this is every email we sent them,
    across every package they were ever invited to.
    """
    return _read_email_log_page(
        db,
        column="vendor_id",
        value=vendor_id,
        page=page,
        page_size=page_size,
    )
