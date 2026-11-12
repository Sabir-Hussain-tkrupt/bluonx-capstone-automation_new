"""
Admin user-management business rules.

All logic for invite / list / change-role / deactivate / resend-invite lives here
so the router stays thin and the guards are unit-testable. Auth/authz is handled
upstream by `require_admin` (see app/core/auth.py) — every function here assumes
the caller is already a verified admin and receives that admin's id for the
self-protection guards.

Design notes:
  - Writes go through the shared service_role client (RLS-bypassing), so these
    functions are the real gate. Two invariants are enforced here, never in the DB:
      G1 self-protection: an admin cannot change their own role, deactivate
         themselves, or delete themselves.
      G2 last-admin: no operation may drop the number of active admins to zero.
  - User creation is never a direct INSERT. Invites go through Supabase's admin
    auth API; the `fn_handle_new_auth_user` trigger then creates public.users from
    the invite's user_metadata (full_name, role).
  - Error style mirrors the existing services (e.g. contract_service): raise
    HTTPException directly with a mapped status, and guard every DB write against
    APIError + an empty response.data.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from postgrest.exceptions import APIError
from supabase import Client
from supabase_auth.errors import AuthApiError

from app.core.config import settings
from app.models.users import UserUpdate

logger = logging.getLogger(__name__)

# Columns selected whenever we return a public.users row to the admin UI.
_USER_COLUMNS = (
    "id, email, full_name, role, is_active, invited_by, "
    "created_at, updated_at, deleted_at"
)


def _invite_redirect() -> str:
    """Where the Supabase invite email should land the user (our set-password
    page). Never hardcode the base — production points at the real domain."""
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/accept-invite"


# ── Status derivation ────────────────────────────────────────────────────────
def _derive_status(row: dict, confirmed_at) -> str:
    """deactivated if the profile is disabled or soft-deleted; else pending until
    the invited user confirms; else active."""
    if not row.get("is_active") or row.get("deleted_at"):
        return "deactivated"
    if not confirmed_at:
        return "pending"
    return "active"


def _auth_confirmed_at(db: Client, user_id) -> object | None:
    """Read the Supabase auth user's `confirmed_at` (None when not yet confirmed).
    Tolerant: any lookup failure degrades to None rather than failing the request."""
    try:
        resp = db.auth.admin.get_user_by_id(str(user_id))
    except Exception:  # noqa: BLE001 — status is advisory, never fatal
        logger.warning("Could not read auth user %s for status derivation", user_id)
        return None
    user = getattr(resp, "user", None)
    return getattr(user, "confirmed_at", None) if user else None


# ── Guards ───────────────────────────────────────────────────────────────────
def _count_active_admins(db: Client) -> int:
    """Number of admins that are active and not soft-deleted. Counted from the
    returned rows (not count=exact) so it works identically under the test mock."""
    resp = (
        db.table("users")
        .select("id")
        .eq("role", "admin")
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .execute()
    )
    return len(resp.data or [])


def _guard_not_self(admin_id, target_id, action: str) -> None:
    """G1. `action` is one of 'role' | 'deactivate' | 'delete'; each raises a
    distinct 409 so the caller can tell them apart."""
    if str(admin_id) != str(target_id):
        return
    detail = {
        "role": "You cannot change your own role.",
        "deactivate": "You cannot deactivate your own account.",
        "delete": "You cannot delete your own account.",
    }[action]
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _target_is_active_admin(target: dict) -> bool:
    return (
        target.get("role") == "admin"
        and target.get("is_active")
        and not target.get("deleted_at")
    )


def _guard_last_admin(db: Client, *, removing_admin: bool) -> None:
    """G2. When an operation would strip admin-ness from an active admin, block it
    if that admin is the last one standing."""
    if removing_admin and _count_active_admins(db) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot remove the last active admin.",
        )


# ── Row fetch ────────────────────────────────────────────────────────────────
def _get_active_user_row(db: Client, target_id, allow_deleted: bool = False) -> dict:
    """Fetch a public.users row or raise 404."""
    resp = (
        db.table("users")
        .select(_USER_COLUMNS)
        .eq("id", str(target_id))
        .maybe_single()
        .execute()
    )
    row = resp.data if resp else None
    if not row or (not allow_deleted and row.get("deleted_at")):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return row


# ── Operations ───────────────────────────────────────────────────────────────
def invite_user(
    db: Client,
    admin_id,
    email: str,
    full_name: str,
    role: str,
    roles: list[str] | None = None,
    is_employee: bool = True,
) -> dict:
    """Invite a new admin/PM via Supabase's auth admin API, or restore an existing
    soft-deleted account under the same email.
    """
    existing_resp = (
        db.table("users")
        .select(_USER_COLUMNS)
        .eq("email", email)
        .maybe_single()
        .execute()
    )
    existing_user = existing_resp.data if existing_resp else None

    if existing_user:
        if existing_user.get("deleted_at") or not existing_user.get("is_active"):
            target_id = existing_user["id"]
            db.table("users").update({
                "deleted_at": None,
                "is_active": True,
                "full_name": full_name,
                "role": role,
                "invited_by": str(admin_id),
            }).eq("id", str(target_id)).execute()
            if roles or not is_employee:
                _apply_financial_roles(
                    db, target_id, roles or [], is_employee, actor_id=admin_id
                )

            redirect = _invite_redirect()
            try:
                db.auth.admin.invite_user_by_email(email, {"redirect_to": redirect})
            except AuthApiError:
                try:
                    db.auth.admin.generate_link({
                        "type": "invite",
                        "email": email,
                        "options": {"redirect_to": redirect},
                    })
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Re-invite for %s generated error: %s", email, exc)

            updated = (
                db.table("users")
                .select(_USER_COLUMNS)
                .eq("id", str(target_id))
                .maybe_single()
                .execute()
            )
            row = updated.data if updated else existing_user
            return {**row, "status": "pending"}
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            )

    redirect = _invite_redirect()
    try:
        resp = db.auth.admin.invite_user_by_email(
            email,
            {
                "data": _invite_metadata(full_name, role, roles, is_employee),
                "redirect_to": redirect,
            },
        )
    except AuthApiError as exc:
        msg = (exc.message or "").lower()
        already = (
            "already" in msg
            or "registered" in msg
            or "exists" in msg
            or getattr(exc, "status", None) in (400, 422)
        )
        if already:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            ) from exc
        logger.error("Supabase invite failed for %s: %s", email, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send the invite. Please try again.",
        ) from exc
    except APIError as exc:
        if getattr(exc, "code", None) == "23505" or "duplicate key" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            ) from exc
        logger.error("Supabase invite failed for %s: %s", email, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send the invite. Please try again.",
        ) from exc

    new_user = getattr(resp, "user", None)
    new_id = getattr(new_user, "id", None)
    if not new_id:
        logger.error("Supabase invite for %s returned no user id", email)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invite did not return a user; please verify in the dashboard.",
        )

    try:
        db.table("users").update({"invited_by": str(admin_id)}).eq(
            "id", str(new_id)
        ).execute()
    except APIError as exc:
        logger.error(
            "Invite for %s succeeded but stamping invited_by failed: %s", email, exc
        )

    read = (
        db.table("users")
        .select(_USER_COLUMNS)
        .eq("id", str(new_id))
        .maybe_single()
        .execute()
    )
    row = read.data if read else None
    if not row:
        row = {
            "id": str(new_id),
            "email": email,
            "full_name": full_name,
            "role": role,
            "is_active": True,
            "invited_by": str(admin_id),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "deleted_at": None,
        }
    return _with_roles(db, [{**row, "status": "pending"}])[0]


def list_users(db: Client) -> list[dict]:
    """All internal users (including deactivated/soft-deleted, which the admin must
    see), merged with Supabase auth to derive each account's status."""
    resp = db.table("users").select(_USER_COLUMNS).order("created_at").execute()
    rows = resp.data or []

    confirmed_by_id = _confirmed_at_by_id(db)

    out: list[dict] = []
    for row in rows:
        confirmed = confirmed_by_id.get(str(row["id"]))
        out.append({**row, "status": _derive_status(row, confirmed)})
    return _with_roles(db, out)


def _confirmed_at_by_id(db: Client) -> dict[str, object]:
    """Map of auth-user id -> confirmed_at, paginating the admin list."""
    per_page = 200
    max_pages = 50
    mapping: dict[str, object] = {}
    for page in range(1, max_pages + 1):
        try:
            users = db.auth.admin.list_users(page=page, per_page=per_page)
        except Exception:  # noqa: BLE001 — status is advisory, never fatal
            logger.warning("auth.admin.list_users failed on page %s", page)
            break
        if not users:
            break
        for u in users:
            uid = getattr(u, "id", None)
            if uid is not None:
                mapping[str(uid)] = getattr(u, "confirmed_at", None)
        if len(users) < per_page:
            break
    return mapping


def change_user(db: Client, admin_id, target_id, patch: UserUpdate) -> dict:
    """Apply role / is_active / full_name changes with G2 + G1 enforced first."""
    target = _get_active_user_row(db, target_id, allow_deleted=patch.is_active is True)

    demoting = patch.role is not None and patch.role != "admin"
    deactivating = patch.is_active is False
    _guard_last_admin(
        db, removing_admin=_target_is_active_admin(target) and (demoting or deactivating)
    )

    if patch.role is not None:
        _guard_not_self(admin_id, target_id, "role")
    if patch.is_active is False:
        _guard_not_self(admin_id, target_id, "deactivate")

    update: dict = patch.model_dump(exclude_unset=True)
    if patch.is_active is True:
        update["deleted_at"] = None

    if not update:
        confirmed = _auth_confirmed_at(db, target_id)
        return {**target, "status": _derive_status(target, confirmed)}

    try:
        resp = (
            db.table("users").update(update).eq("id", str(target_id)).execute()
        )
    except APIError as exc:
        logger.error("Supabase update failed for users %s: %s", target_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The submitted data was rejected. Please review the values and try again.",
        ) from exc

    if not resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    row = resp.data[0]
    confirmed = _auth_confirmed_at(db, target_id)
    return {**row, "status": _derive_status(row, confirmed)}


def restore_user(db: Client, admin_id, target_id) -> dict:
    """Restore a soft-deleted or deactivated user (clears deleted_at, sets is_active=True)."""
    target = _get_active_user_row(db, target_id, allow_deleted=True)

    try:
        resp = (
            db.table("users")
            .update({"deleted_at": None, "is_active": True})
            .eq("id", str(target_id))
            .execute()
        )
    except APIError as exc:
        logger.error("Supabase restore user failed for %s: %s", target_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Could not restore the user. Please try again.",
        ) from exc

    if not resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    row = resp.data[0]
    confirmed = _auth_confirmed_at(db, target_id)
    return {**row, "status": _derive_status(row, confirmed)}


def soft_delete_user(db: Client, admin_id, target_id) -> None:
    """Soft-delete (deleted_at + is_active=false) with G2 + G1 enforced first."""
    target = _get_active_user_row(db, target_id)

    _guard_last_admin(db, removing_admin=_target_is_active_admin(target))
    _guard_not_self(admin_id, target_id, "delete")

    try:
        resp = (
            db.table("users")
            .update(
                {
                    "deleted_at": datetime.now(timezone.utc).isoformat(),
                    "is_active": False,
                }
            )
            .eq("id", str(target_id))
            .execute()
        )
    except APIError as exc:
        logger.error("Supabase soft-delete failed for users %s: %s", target_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Could not delete the user. Please try again.",
        ) from exc

    if not resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )


def resend_invite(db: Client, target_id) -> dict:
    """Re-send the invite email to a not-yet-confirmed user."""
    row = _get_active_user_row(db, target_id, allow_deleted=True)
    if row.get("deleted_at"):
        db.table("users").update({"deleted_at": None, "is_active": True}).eq("id", str(target_id)).execute()

    email = row["email"]

    if _auth_confirmed_at(db, target_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User has already accepted the invite; nothing to resend.",
        )

    redirect = _invite_redirect()
    try:
        db.auth.admin.invite_user_by_email(email, {"redirect_to": redirect})
    except AuthApiError as exc:
        logger.info(
            "Re-invite for %s raised (%s); falling back to generate_link", email, exc
        )
        try:
            db.auth.admin.generate_link(
                {"type": "invite", "email": email, "options": {"redirect_to": redirect}}
            )
        except AuthApiError as exc2:
            logger.error("Resend invite failed for %s: %s", email, exc2)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not resend the invite. Please try again.",
            ) from exc2

    return {"detail": "Invite resent."}


# ── Financial roles (v4.0) ───────────────────────────────────────────────────
# The base role stays in users.role (admin | project_manager). Financial roles
# (field_manager, executive, finance) live in user_roles; one person may hold
# several. Rows are never deleted: a revoke stamps revoked_at for the audit.
FINANCIAL_ROLE_NAMES = ("field_manager", "executive", "finance")


def _invite_metadata(full_name: str, role: str, roles, is_employee: bool) -> dict:
    """Invite user_metadata. Identical to the pre-financial payload unless extra
    roles are requested or the person is external — fn_handle_new_auth_user reads
    `roles` and `is_employee` when present."""
    data = {"full_name": full_name, "role": role}
    if roles:
        data["roles"] = sorted(set(roles))
    if not is_employee:
        data["is_employee"] = False
    return data


def _with_roles(db: Client, rows: list[dict]) -> list[dict]:
    """Attach `roles` and `is_employee` to user rows. Advisory: on any failure
    (e.g. the financial schema is not installed) each row keeps its base role."""
    by_user: dict[str, set[str]] = {}
    employee: dict[str, bool] = {}
    try:
        resp = (
            db.table("user_roles")
            .select("user_id, role")
            .is_("revoked_at", "null")
            .execute()
        )
        for r in resp.data or []:
            if r.get("user_id") and r.get("role"):
                by_user.setdefault(str(r["user_id"]), set()).add(r["role"])
        emp = db.table("users").select("id, is_employee").execute()
        for r in emp.data or []:
            if r.get("is_employee") is not None:
                employee[str(r["id"])] = bool(r["is_employee"])
    except Exception:  # noqa: BLE001 - advisory enrichment, never fatal
        logger.warning("Could not load user roles; returning base roles only")
    out = []
    for row in rows:
        uid = str(row.get("id"))
        roles = by_user.get(uid, set()) | {row.get("role")}
        out.append(
            {
                **row,
                "roles": sorted(r for r in roles if r),
                "is_employee": employee.get(uid, row.get("is_employee", True)),
            }
        )
    return out


def _apply_financial_roles(
    db: Client, target_id, roles: list[str], is_employee: bool | None, actor_id
) -> None:
    """Make the user's active financial roles exactly `roles` (base role untouched)."""
    wanted = {r for r in roles if r in FINANCIAL_ROLE_NAMES}
    try:
        resp = (
            db.table("user_roles")
            .select("id, role")
            .eq("user_id", str(target_id))
            .is_("revoked_at", "null")
            .execute()
        )
        current = {r["role"]: r["id"] for r in (resp.data or [])}
        now = datetime.now(timezone.utc).isoformat()
        for role_name, row_id in current.items():
            if role_name in FINANCIAL_ROLE_NAMES and role_name not in wanted:
                db.table("user_roles").update(
                    {"revoked_at": now, "revoked_by": str(actor_id)}
                ).eq("id", row_id).execute()
        to_add = [
            {"user_id": str(target_id), "role": r, "granted_by": str(actor_id)}
            for r in sorted(wanted - set(current))
        ]
        if to_add:
            db.table("user_roles").insert(to_add).execute()
        if is_employee is not None:
            db.table("users").update({"is_employee": is_employee}).eq(
                "id", str(target_id)
            ).execute()
    except APIError as exc:
        logger.error("Updating roles for user %s failed: %s", target_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not update the user's roles. Please try again.",
        ) from exc


def set_user_roles(
    db: Client, admin_id, target_id, roles: list[str], is_employee: bool | None
) -> dict:
    """Admin: replace a user's financial roles and optionally the employee flag."""
    row = _get_active_user_row(db, target_id)
    _apply_financial_roles(db, target_id, roles, is_employee, actor_id=admin_id)
    confirmed = _confirmed_at_by_id(db).get(str(target_id))
    return _with_roles(db, [{**row, "status": _derive_status(row, confirmed)}])[0]
