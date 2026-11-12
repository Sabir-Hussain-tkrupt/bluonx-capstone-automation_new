"""
JWT authentication and role-based authorization for FastAPI.

Three-tier dependency chain:
  1. get_current_user       — JWT validation only (no DB call)
  2. get_current_active_user — JWT + DB lookup (checks is_active, gets role,
                               financial roles from user_roles, is_employee)
  3. require_admin           — Extends above with admin role check
     require_roles(*roles)   — Extends above: admin or any of the given roles

Supports both ES256 (modern Supabase projects, verified via JWKS) and
HS256 (legacy projects, verified via shared JWT secret). The algorithm
is auto-detected from the token header.

Most endpoints use get_current_active_user. Admin-only endpoints use require_admin.
"""

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from supabase import Client

from app.core.config import settings
from app.core.logging_config import set_actor
from app.core.supabase_client import get_supabase

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer()

# Clock-skew tolerance for time-based JWT claims (iat / nbf / exp). Supabase
# stamps `iat` from its own clock, so a validating host running a second or two
# behind would otherwise reject a freshly-issued, valid token as "not yet valid".
# 30s is the conventional allowance.
_JWT_LEEWAY_SECONDS = 30

# JWKS client for ES256 verification — caches keys automatically.
# Supabase publishes public keys at /.well-known/jwks.json.
_jwks_client = PyJWKClient(
    f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json",
    cache_keys=True,
    lifespan=3600,  # re-fetch keys every hour
)


def _decode_token(token: str) -> dict:
    """
    Decode a Supabase JWT, auto-detecting the signing algorithm.

    - ES256 tokens (modern): verified via JWKS public key
    - HS256 tokens (legacy): verified via SUPABASE_JWT_SECRET
    """
    # Peek at the header to determine the algorithm
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError:
        raise jwt.InvalidTokenError("Malformed token header")

    alg = header.get("alg", "")

    if alg == "ES256":
        # Fetch the matching public key from Supabase JWKS
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
            leeway=_JWT_LEEWAY_SECONDS,
        )
    elif alg == "HS256":
        # Legacy: shared secret verification
        return jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
            leeway=_JWT_LEEWAY_SECONDS,
        )
    else:
        raise jwt.InvalidTokenError(f"Unsupported algorithm: {alg}")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """
    Validate the Supabase JWT and return basic identity.

    Returns: {"user_id": "uuid", "email": "..."}
    Fast path — no DB call. Use when you only need identity, not role.
    """
    token = credentials.credentials
    try:
        payload = _decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError as e:
        logger.warning("JWT validation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Attribute this request in the logs. Covers endpoints that stop at the fast
    # path; get_current_active_user adds the role on top.
    set_actor(user_id=user_id)

    return {"user_id": user_id, "email": payload.get("email", "")}


async def get_current_active_user(
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase),
) -> dict:
    """
    Extend get_current_user with a DB lookup on public.users.

    Checks is_active and deleted_at. Returns full user dict with role.
    This is the standard dependency for most protected endpoints.

    Returns: {"user_id": "uuid", "email": "...", "full_name": "...",
              "role": "admin"|"project_manager", "is_active": True}
    """
    response = (
        db.table("users")
        .select("id, email, full_name, role, is_active, deleted_at")
        .eq("id", user["user_id"])
        .maybe_single()
        .execute()
    )

    if not response or not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found",
        )

    profile = response.data

    if profile.get("deleted_at"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account has been deleted",
        )

    if not profile.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    set_actor(user_id=profile["id"], role=profile["role"])

    roles, is_employee = _load_financial_roles(db, profile)

    return {
        "user_id": profile["id"],
        "email": profile["email"],
        "full_name": profile["full_name"],
        "role": profile["role"],
        "is_active": profile["is_active"],
        "roles": roles,
        "is_employee": is_employee,
    }


# Every role the financial module knows (users.role holds only the first two).
FINANCIAL_ROLES = ("admin", "project_manager", "field_manager", "executive", "finance")


def _load_financial_roles(db: Client, profile: dict) -> tuple[list[str], bool]:
    """Active roles from user_roles (+ the base users.role) and the is_employee flag.

    Defensive by design: if the financial schema is missing or the read fails,
    the caller still gets its base role and is treated as an employee, so no
    existing endpoint can break because of this lookup.
    """
    roles = {profile["role"]}
    is_employee = True
    try:
        resp = (
            db.table("user_roles")
            .select("role")
            .eq("user_id", profile["id"])
            .is_("revoked_at", "null")
            .execute()
        )
        roles.update(r["role"] for r in (resp.data or []) if r.get("role"))
        emp = (
            db.table("users")
            .select("is_employee")
            .eq("id", profile["id"])
            .maybe_single()
            .execute()
        )
        if emp and emp.data and emp.data.get("is_employee") is False:
            is_employee = False
    except Exception:  # noqa: BLE001 - advisory lookup, never fatal
        logger.warning("Could not load financial roles for user %s", profile.get("id"))
    return sorted(roles), is_employee


def user_has_any_role(user: dict, *roles: str) -> bool:
    """True when the caller is an admin or holds any of `roles`.

    Works with both the full dependency output (has `roles`) and the slimmer
    dicts some tests inject (only `role`).
    """
    held = set(user.get("roles") or []) | {user.get("role")}
    return "admin" in held or bool(held & set(roles))


def require_roles(*roles: str):
    """Dependency factory: admin, or at least one of `roles` (users.role or user_roles).

        @router.post(..., dependencies=[Depends(require_roles("finance"))])
    """

    async def _dependency(user: dict = Depends(get_current_active_user)) -> dict:
        if not user_has_any_role(user, *roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return user

    return _dependency


async def require_admin(
    user: dict = Depends(get_current_active_user),
) -> dict:
    """Dependency that requires admin role. Extends get_current_active_user."""
    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
