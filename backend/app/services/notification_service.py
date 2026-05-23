"""
In-app notification service (Phase 7, Task 7.4).

Single source of truth for inserting rows into the `notifications` table.
Validates `notification_type` against a controlled vocabulary and dedupes
unread notifications by (user_id, notification_type, reference_id) so jobs
re-running the same day don't stack duplicates.

The DB client is passed in as the first positional arg, mirroring the
stateless-utility pattern used by `bid_revision_service`.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


# ── Controlled vocabulary ────────────────────────────────────────────────
# Documented in CURRENT_PHASE_TASKS.md → "Notification type vocabulary".
# Jobs added in later Phase 7 tasks must use one of these values; unknown
# values are rejected at the service layer.
NOTIFICATION_TYPES: frozenset[str] = frozenset({
    "insurance_expiring",
    "insurance_expired",
    "post_deadline_non_responders",
    "scheduler_alert",
})


def _coerce_id(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def create_notification(
    db,
    *,
    user_id: UUID | str,
    notification_type: str,
    title: str,
    message: str | None = None,
    reference_type: str | None = None,
    reference_id: UUID | str | None = None,
    dedupe: bool = True,
) -> dict:
    """Insert a notification row, or return an existing unread match.

    Raises ValueError if notification_type is outside NOTIFICATION_TYPES.

    Dedupe key when enabled: (user_id, notification_type, reference_id).
    NULL reference_id matches NULL reference_id only.
    """
    if notification_type not in NOTIFICATION_TYPES:
        raise ValueError(
            f"Unknown notification_type: {notification_type!r}. "
            f"Allowed: {sorted(NOTIFICATION_TYPES)}"
        )

    user_id_str = _coerce_id(user_id)
    reference_id_str = _coerce_id(reference_id)

    if dedupe:
        query = (
            db.table("notifications")
            .select("*")
            .eq("user_id", user_id_str)
            .eq("notification_type", notification_type)
            .eq("is_read", False)
        )
        if reference_id_str is None:
            query = query.is_("reference_id", "null")
        else:
            query = query.eq("reference_id", reference_id_str)
        existing = query.limit(1).execute()
        rows = existing.data or []
        if rows:
            return rows[0]

    payload: dict[str, Any] = {
        "user_id": user_id_str,
        "title": title,
        "message": message,
        "notification_type": notification_type,
        "reference_type": reference_type,
        "reference_id": reference_id_str,
        "is_read": False,
    }
    result = db.table("notifications").insert(payload).execute()
    data = result.data or []
    if not data:
        # Defensive — supabase-py returns the inserted row on success.
        raise RuntimeError("Notification insert returned no row")
    return data[0]


def create_notifications_bulk(
    db,
    *,
    notifications: list[dict],
) -> list[dict]:
    """Loop create_notification per item. MVP volume — no batched SQL.

    Each item must contain the kwargs accepted by create_notification.
    Per-item failures propagate; callers wrap if they want partial success.
    """
    out: list[dict] = []
    for item in notifications:
        out.append(create_notification(db, **item))
    return out


def build_notification_deep_link(notification: dict, db) -> str | None:
    """Return a relative frontend path for the notification, or None.

    Switches on reference_type:
      - 'vendors'      → /vendors/{vendor_id}
      - 'bid_packages' → /projects/{project_id}/tasks/{task_id}/bid-packages/{id}
      - anything else  → None
    """
    ref_type = notification.get("reference_type")
    ref_id = notification.get("reference_id")
    if not ref_type or not ref_id:
        return None

    if ref_type == "vendors":
        return f"/vendors/{ref_id}"

    if ref_type == "bid_packages":
        try:
            resp = (
                db.table("bid_packages")
                .select("id, task_id, tasks(id, project_id)")
                .eq("id", str(ref_id))
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception("Failed to resolve bid_package deep link for %s", ref_id)
            return None
        rows = resp.data or []
        if not rows:
            return None
        pkg = rows[0]
        task = pkg.get("tasks") or {}
        project_id = task.get("project_id")
        task_id = pkg.get("task_id") or task.get("id")
        if not project_id or not task_id:
            return None
        return f"/projects/{project_id}/tasks/{task_id}/bid-packages/{ref_id}"

    return None
