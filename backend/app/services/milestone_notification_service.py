"""
Milestone in-app notification helpers (Phase 10.4).

Thin wrappers over `notification_service.create_notification` that resolve the
milestone's owning PM (`milestones.created_by`) and emit one of the three
milestone notification types with a `milestones` deep-link reference. Service
default dedupe (True) applies: a re-emit for the same unread
(user, type, milestone) is a no-op.

These are callable, tested building blocks. Wiring them into
`transition_milestone()` / scheduler jobs is Phase 10.2 / 10.3, not here.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)


def _fetch_milestone_owner(db, milestone_id: UUID | str) -> dict | None:
    """Return {'name', 'created_by'} for the milestone, or None if unreadable."""
    try:
        resp = (
            db.table("milestones")
            .select("id, name, created_by")
            .eq("id", str(milestone_id))
            .limit(1)
            .execute()
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read milestone %s for notification", milestone_id)
        return None
    rows = resp.data or []
    if not rows:
        logger.warning("Milestone %s not found; skipping notification", milestone_id)
        return None
    row = rows[0]
    if not row.get("created_by"):
        logger.warning(
            "Milestone %s has no created_by; skipping notification", milestone_id
        )
        return None
    return {"name": row.get("name") or "", "created_by": row["created_by"]}


def _notify(
    db, milestone_id: UUID | str, *, notification_type: str, title_prefix: str
) -> dict | None:
    """Shared body: resolve the PM owner and create the notification."""
    owner = _fetch_milestone_owner(db, milestone_id)
    if owner is None:
        return None
    return create_notification(
        db,
        user_id=owner["created_by"],
        notification_type=notification_type,
        title=f"{title_prefix}: {owner['name']}",
        reference_type="milestones",
        reference_id=str(milestone_id),
        dedupe=True,
    )


def notify_milestone_delayed(db, milestone_id: UUID | str) -> dict | None:
    """Notify the owning PM that the vendor reported a delay."""
    return _notify(
        db,
        milestone_id,
        notification_type="milestone_delayed",
        title_prefix="Delay reported",
    )


def notify_milestone_unresponsive(db, milestone_id: UUID | str) -> dict | None:
    """Notify the owning PM that the vendor went silent past the grace window."""
    return _notify(
        db,
        milestone_id,
        notification_type="milestone_unresponsive",
        title_prefix="No response",
    )


def notify_milestone_completed(db, milestone_id: UUID | str) -> dict | None:
    """Notify the owning PM that the milestone was completed."""
    return _notify(
        db,
        milestone_id,
        notification_type="milestone_completed",
        title_prefix="Completed",
    )
