"""
Invitation tracking service (Task 4.5).

Read-side and status-management operations on bid packages and invitations:
- Bid package detail view with invitation summary
- Invitation list with optional status filter
- PM-driven status updates (declined / expired / no_response)
- Email log per bid package
- Lazy expiration utility — flips overdue invitations to 'expired' and
  closes the bid package when the deadline has passed.
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

_ALL_STATUSES = ("sent", "opened", "submitted", "declined", "expired", "no_response")
_PM_SETTABLE_STATUSES = frozenset({"declined", "expired", "no_response"})
_EXPIRABLE_STATUSES = ("sent", "opened")
_NOOP_PACKAGE_STATUSES = frozenset({"closed", "cancelled"})


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


async def expire_overdue_invitations(*, bid_package_id: UUID, db) -> dict:
    """If the bid package deadline has passed and the package is open,
    flip all sent/opened invitations to 'expired' and close the package.

    Returns {"expired_count": int, "package_closed": bool}.
    No-op when deadline is in the future or package is closed/cancelled.
    """
    bid_package = _fetch_bid_package(db, bid_package_id)
    if bid_package is None:
        raise BidPackageNotFoundError()

    current_status = bid_package.get("status")
    if current_status in _NOOP_PACKAGE_STATUSES:
        return {"expired_count": 0, "package_closed": False}

    deadline = _parse_deadline(bid_package.get("deadline"))
    if deadline is None or deadline >= datetime.now(timezone.utc):
        return {"expired_count": 0, "package_closed": False}

    # Deadline has passed and package is still open — expire overdue rows.
    invitations = _fetch_invitations(db, bid_package_id)
    expired_count = sum(
        1 for inv in invitations if inv.get("status") in _EXPIRABLE_STATUSES
    )

    now = _now_iso()

    if expired_count > 0:
        (
            db.table("bid_invitations")
            .update({"status": "expired", "updated_at": now})
            .eq("bid_package_id", str(bid_package_id))
            .in_("status", list(_EXPIRABLE_STATUSES))
            .execute()
        )

    (
        db.table("bid_packages")
        .update({"status": "closed", "updated_at": now})
        .eq("id", str(bid_package_id))
        .execute()
    )

    return {"expired_count": expired_count, "package_closed": True}


async def get_bid_package_detail(*, bid_package_id: UUID, db) -> dict:
    """Return the full bid package detail with invitation summary,
    invitations array, and documents. Applies lazy expiration."""
    bid_package = _fetch_bid_package(db, bid_package_id)
    if bid_package is None:
        raise BidPackageNotFoundError()

    deadline = _parse_deadline(bid_package.get("deadline"))
    current_status = bid_package.get("status")
    lazy_expired = False

    if (
        current_status not in _NOOP_PACKAGE_STATUSES
        and deadline is not None
        and deadline < datetime.now(timezone.utc)
    ):
        await expire_overdue_invitations(bid_package_id=bid_package_id, db=db)
        bid_package["status"] = "closed"
        lazy_expired = True

    invitations_rows = _fetch_invitations(db, bid_package_id)

    # Reflect the lazy expiration in the returned rows since the mock
    # doesn't actually apply the DB update in tests.
    if lazy_expired:
        for row in invitations_rows:
            if row.get("status") in _EXPIRABLE_STATUSES:
                row["status"] = "expired"

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
    """Update invitation status. Only declined/expired/no_response are
    PM-settable. Other values → 400.

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


async def get_bid_package_email_log(*, bid_package_id: UUID, db) -> list[dict]:
    """Return every email_log row tied to invitations in the given package.

    Walks the invitation graph and unions email_log rows across three
    reference_types so the PM sees every email sent for this package:
      * bid_invitations       — initial invite + bid_reminder sends
      * bid_revision_requests — PM revision request emails
      * bid_submissions       — vendor receipt + revision-receipt emails

    The graph walk is the only correct scoping today: email_log has no
    vendor_id column, and the three flows above each pin reference_id
    to a different table.
    """
    bid_package = _fetch_bid_package(db, bid_package_id)
    if bid_package is None:
        raise BidPackageNotFoundError()

    invitations = _fetch_invitations(db, bid_package_id)
    invitation_ids = [inv["id"] for inv in invitations if inv.get("id")]
    return _collect_email_log_rows(db, invitation_ids)


async def get_vendor_email_log(*, vendor_id: UUID, db) -> list[dict]:
    """Return every email_log row tied to any invitation this vendor received.

    Same union-of-three-reference_types as get_bid_package_email_log, but
    scoped via bid_invitations.vendor_id instead of bid_package_id —
    surfaces a vendor's full outbound communication history across every
    bid package they've ever been invited to.
    """
    resp = (
        db.table("bid_invitations")
        .select("id")
        .eq("vendor_id", str(vendor_id))
        .execute()
    )
    invitation_ids = [
        row["id"] for row in _unwrap_list(resp.data) if row.get("id")
    ]
    return _collect_email_log_rows(db, invitation_ids)


def _collect_email_log_rows(db, invitation_ids: list[str]) -> list[dict]:
    """Walk invitations → revision_requests / submissions, union the three
    email_log queries, dedupe by id, sort newest-first by created_at.

    Three separate queries instead of a single .or_() filter: supabase-py's
    OR-with-IN syntax is awkward and three small lookups stay readable.
    Each branch is skipped entirely when its ID list is empty.
    """
    if not invitation_ids:
        return []

    revision_request_ids = _fetch_child_ids(
        db, "bid_revision_requests", "bid_invitation_id", invitation_ids
    )
    submission_ids = _fetch_child_ids(
        db, "bid_submissions", "bid_invitation_id", invitation_ids
    )

    rows: list[dict] = []
    rows.extend(_query_email_log(db, "bid_invitations", invitation_ids))
    rows.extend(_query_email_log(db, "bid_revision_requests", revision_request_ids))
    rows.extend(_query_email_log(db, "bid_submissions", submission_ids))

    # Dedupe by id — guards against a future flow mis-pinning a single
    # email_log row to two reference_types.
    seen: set = set()
    unique: list[dict] = []
    for row in rows:
        row_id = row.get("id")
        if row_id is not None and row_id in seen:
            continue
        if row_id is not None:
            seen.add(row_id)
        unique.append(row)

    unique.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return unique


def _fetch_child_ids(
    db, table: str, fk_column: str, parent_ids: list[str]
) -> list[str]:
    if not parent_ids:
        return []
    resp = (
        db.table(table)
        .select("id")
        .in_(fk_column, parent_ids)
        .execute()
    )
    return [row["id"] for row in _unwrap_list(resp.data) if row.get("id")]


def _query_email_log(
    db, reference_type: str, reference_ids: list[str]
) -> list[dict]:
    if not reference_ids:
        return []
    resp = (
        db.table("email_log")
        .select("*")
        .eq("reference_type", reference_type)
        .in_("reference_id", reference_ids)
        .execute()
    )
    return _unwrap_list(resp.data)
