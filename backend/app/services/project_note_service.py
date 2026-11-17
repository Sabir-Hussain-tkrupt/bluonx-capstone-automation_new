"""Project notes — rich-text notes on a project.

Who may do what
---------------
* Any active user reads notes (also directly, through RLS) and adds notes.
* The author or an admin edits or deletes a note.
* Notes on an archived project are read-only.

HTML safety
-----------
The editor emits a small, known set of tags, and the frontend renders stored
HTML back through the same editor schema (never with innerHTML), which drops
anything outside it. As defence in depth the API also refuses HTML carrying
script-capable content, so nothing executable is ever stored.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from supabase import Client

from app.models.project_notes import ProjectNoteCreate, ProjectNoteUpdate

logger = logging.getLogger(__name__)

_UNSAFE_HTML = re.compile(
    r"<\s*/?\s*(script|iframe|object|embed|style|link|meta|base|form|input|button|textarea|svg|math)\b"
    r"|\son[a-z]+\s*="
    r"|(?:java|vb)script\s*:"
    r"|data\s*:\s*text/html",
    re.IGNORECASE,
)


def ensure_safe_html(html: str) -> None:
    if html and _UNSAFE_HTML.search(html):
        raise HTTPException(
            status_code=422,
            detail="The note contains content that is not allowed (scripts, embedded frames or event handlers).",
        )


def _project_or_404(db: Client, project_id: UUID | str) -> dict:
    resp = (
        db.table("projects")
        .select("id, archived_at")
        .eq("id", str(project_id))
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return resp.data


def _ensure_not_archived(project: dict) -> None:
    if project.get("archived_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Notes on an archived project are read-only. Unarchive the project first.",
        )


def _note_or_404(db: Client, note_id: UUID | str) -> dict:
    resp = (
        db.table("project_notes")
        .select("*")
        .eq("id", str(note_id))
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return resp.data


def _can_edit(user: dict, note: dict) -> bool:
    return user.get("role") == "admin" or str(note.get("created_by")) == str(user.get("user_id"))


def _ensure_can_edit(user: dict, note: dict) -> None:
    if not _can_edit(user, note):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the note's author or an admin can change it.",
        )


def _enrich(db: Client, user: dict, rows: list[dict]) -> list[dict]:
    ids = {str(r[k]) for r in rows for k in ("created_by", "updated_by") if r.get(k)}
    names: dict[str, str] = {}
    if ids:
        try:
            resp = db.table("users").select("id, full_name").in_("id", sorted(ids)).execute()
            names = {str(u["id"]): u.get("full_name") for u in (resp.data or []) if isinstance(u, dict)}
        except Exception:  # noqa: BLE001 - names are cosmetic
            logger.warning("Could not load note author names", exc_info=True)
    out = []
    for r in rows:
        out.append({
            **r,
            "created_by_name": names.get(str(r.get("created_by"))),
            "updated_by_name": names.get(str(r.get("updated_by"))) if r.get("updated_by") else None,
            "can_edit": _can_edit(user, r),
        })
    return out


def list_notes(db: Client, user: dict, project_id: UUID) -> list[dict]:
    _project_or_404(db, project_id)
    resp = (
        db.table("project_notes")
        .select("*")
        .eq("project_id", str(project_id))
        .is_("deleted_at", "null")
        .order("updated_at", desc=True)
        .execute()
    )
    return _enrich(db, user, resp.data or [])


def create_note(db: Client, user: dict, project_id: UUID, body: ProjectNoteCreate) -> dict:
    project = _project_or_404(db, project_id)
    _ensure_not_archived(project)
    ensure_safe_html(body.content_html)
    payload = {
        "project_id": str(project_id),
        "title": body.title,
        "content_html": body.content_html,
        "content_text": body.content_text,
        "created_by": str(user["user_id"]),
    }
    resp = db.table("project_notes").insert(payload).execute()
    if not resp.data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to save the note")
    return _enrich(db, user, [resp.data[0]])[0]


def update_note(db: Client, user: dict, note_id: UUID, body: ProjectNoteUpdate) -> dict:
    note = _note_or_404(db, note_id)
    _ensure_can_edit(user, note)
    _ensure_not_archived(_project_or_404(db, note["project_id"]))

    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    if "content_html" in changes:
        ensure_safe_html(changes["content_html"])
    changes["updated_by"] = str(user["user_id"])

    resp = (
        db.table("project_notes")
        .update(changes)
        .eq("id", str(note_id))
        .is_("deleted_at", "null")
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return _enrich(db, user, [resp.data[0]])[0]


def delete_note(db: Client, user: dict, note_id: UUID) -> None:
    note = _note_or_404(db, note_id)
    _ensure_can_edit(user, note)
    _ensure_not_archived(_project_or_404(db, note["project_id"]))
    db.table("project_notes").update({
        "deleted_at": datetime.now(UTC).isoformat(),
        "updated_by": str(user["user_id"]),
    }).eq("id", str(note_id)).execute()
