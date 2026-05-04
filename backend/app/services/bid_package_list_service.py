"""
Cross-project bid package list service (Task 6.2).

Returns a denormalized list of bid packages with project / task names and
SQL-computed invitation counts in a single PostgREST request via aliased
embeds.
"""

from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


# ── Exceptions ─────────────────────────────────────────────────────────────


class BidPackageListValidationError(Exception):
    """Raised when query parameters fail validation (mapped to 400)."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ── Constants ──────────────────────────────────────────────────────────────

_VALID_STATUSES = frozenset({"open", "closed", "evaluating", "cancelled"})
_DB_SORT_FIELDS = frozenset({"deadline", "created_at"})
_IN_MEMORY_SORT_FIELDS = frozenset({"project_name"})
_VALID_SORT_FIELDS = _DB_SORT_FIELDS | _IN_MEMORY_SORT_FIELDS
_VALID_SORT_ORDERS = frozenset({"asc", "desc"})


_SELECT_CLAUSE = (
    "id, task_id, round_number, deadline, status, created_at, "
    "tasks!inner(id, name, project_id, projects!inner(id, name)), "
    "all_invitations:bid_invitations(count), "
    "submitted_invitations:bid_invitations(count)"
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _extract_count(embed_value) -> int:
    """PostgREST returns aggregated counts as `[{"count": N}]`."""
    if isinstance(embed_value, list) and embed_value:
        first = embed_value[0]
        if isinstance(first, dict):
            return int(first.get("count") or 0)
    if isinstance(embed_value, dict):
        return int(embed_value.get("count") or 0)
    return 0


def _flatten_row(row: dict) -> dict:
    tasks = row.get("tasks") or {}
    if isinstance(tasks, list):
        tasks = tasks[0] if tasks else {}
    projects = tasks.get("projects") if isinstance(tasks, dict) else None
    if isinstance(projects, list):
        projects = projects[0] if projects else {}
    projects = projects or {}

    return {
        "id": row.get("id"),
        "task_id": row.get("task_id"),
        "task_name": tasks.get("name") if isinstance(tasks, dict) else None,
        "project_id": (
            tasks.get("project_id") if isinstance(tasks, dict) else None
        ),
        "project_name": projects.get("name") if isinstance(projects, dict) else None,
        "round_number": row.get("round_number"),
        "deadline": row.get("deadline"),
        "status": row.get("status"),
        "total_invitations": _extract_count(row.get("all_invitations")),
        "submitted_count": _extract_count(row.get("submitted_invitations")),
        "created_at": row.get("created_at"),
    }


# ── Service ────────────────────────────────────────────────────────────────


async def list_bid_packages(
    *,
    db,
    status: str | None,
    project_id: UUID | None,
    sort_by: str,
    sort_order: str,
) -> list[dict]:
    """List bid packages across all projects with denormalized join fields
    and SQL-computed invitation counts.

    Filters: optional `status`, optional `project_id` (joined via
    `tasks.project_id`).

    Sort: `deadline` / `created_at` use SQL ordering; `project_name` is
    sorted in-memory after the fetch (PostgREST embed-ordering is brittle
    and the result set is small in practice).
    """
    if status is not None and status not in _VALID_STATUSES:
        raise BidPackageListValidationError(
            status_code=400,
            detail=(
                f"Invalid status '{status}'. "
                f"Allowed: {sorted(_VALID_STATUSES)}"
            ),
        )
    if sort_by not in _VALID_SORT_FIELDS:
        raise BidPackageListValidationError(
            status_code=400,
            detail=(
                f"Invalid sort_by '{sort_by}'. "
                f"Allowed: {sorted(_VALID_SORT_FIELDS)}"
            ),
        )
    if sort_order not in _VALID_SORT_ORDERS:
        raise BidPackageListValidationError(
            status_code=400,
            detail=(
                f"Invalid sort_order '{sort_order}'. "
                f"Allowed: {sorted(_VALID_SORT_ORDERS)}"
            ),
        )

    query = (
        db.table("bid_packages")
        .select(_SELECT_CLAUSE)
        .eq("submitted_invitations.status", "submitted")
    )

    if status is not None:
        query = query.eq("status", status)
    if project_id is not None:
        query = query.eq("tasks.project_id", str(project_id))

    if sort_by in _DB_SORT_FIELDS:
        query = query.order(sort_by, desc=(sort_order == "desc"))
    else:
        # Always order by something deterministic at the DB layer; the
        # in-memory sort below will reorder for project_name.
        query = query.order("deadline", desc=False)

    resp = query.execute()
    rows = resp.data or []

    items = [_flatten_row(row) for row in rows]

    if sort_by in _IN_MEMORY_SORT_FIELDS:
        items.sort(
            key=lambda item: (item.get(sort_by) or "").lower(),
            reverse=(sort_order == "desc"),
        )

    return items
