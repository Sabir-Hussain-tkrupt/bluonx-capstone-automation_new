# Deferred Items

Items intentionally deferred during implementation. Reference this file when moving to production or starting later phases.


## User Management — invite rate limiter is per-process (Phase 3 / user management)

`POST /api/v1/users/invite` reuses the in-memory sliding-window limiter in `backend/app/core/rate_limit.py` (`validate_token_rate_limit`, 10 req / 60s / IP). State is per worker process, not cluster-wide. This is acceptable today because production runs a single Fargate task (desiredCount=1), so per-process is effectively cluster-wide. Before scaling horizontally past one instance, move the limiter to a shared store (Redis or a DB-backed counter) so the bound holds across workers. Touchpoint: `backend/app/core/rate_limit.py` (swap the module-level `_buckets` dict for a shared backend); the invite endpoint dependency wiring stays the same.

## User Management — per-service APIError/PT-code mapping un-refactored

`user_service.py` follows the existing convention of each service catching `postgrest.exceptions.APIError` (and, elsewhere, PT4xx SQLSTATE codes) and mapping to HTTP status locally, rather than a shared exception handler. The copy-paste `_is_unique_violation` / `_has_pt_code` helper pattern remains duplicated across services (contract_service, award_service, bid_package_service, bid_revision_service, vendor_portal, and now the 23505 backstop in user_service). A single shared APIError -> HTTP translator (or a FastAPI exception handler) is deferred; consolidate when touching the error layer next.

## User Management — no durable audit log for account mutations

*Narrowed 2026-08-06: the request-logging half of this item is now built. Structured
logging with correlation IDs and actor attribution ships in
`backend/app/core/logging_config.py` + `backend/app/core/request_logging.py`, so every
mutation is now attributable in the logs to a `user_id` + `role` and a `request_id`.*

What remains is durability. Log retention is not an audit trail: user management mutates
accounts (invite / role change / deactivate / soft-delete) and only `public.users.invited_by`
persists attribution to the database. Role changes, deactivations, and soft-deletes leave no
queryable record once logs age out of CloudWatch.

The durable option is a dedicated append-only `user_audit_log` table (actor id, target id,
action, before/after role, timestamp) written from `backend/app/services/user_service.py`
alongside each mutation. Deferred because it needs a schema migration and a decision on
whether the same table should cover non-user mutations (awards, contracts) rather than being
built user-specific and then retrofitted.

## User Management UI — accept-invite "already-onboarded" detection (Phase 3 frontend)

`frontend/src/features/auth/pages/AcceptInvitePage.tsx` takes the idempotent path: whenever a live session exists it shows the set-password form, because the Supabase client `Session`/`User` exposes no reliable "has a password" signal (`user_metadata` / `app_metadata` / `identities` do not carry it). Setting a password again via `supabase.auth.updateUser` is harmless, so a user who returns to the link just re-sets it. A dedicated "you're already set up" state is deferred until a trustworthy client signal is available (e.g. a `public.users` onboarding flag surfaced through the profile, or a server endpoint that reports password status). Only the two reliably-detectable states are handled today: no session -> "invite link invalid or expired", session -> set-password form.

## User Management UI — role shown as plain text, no role-badge token convention (Phase 3 frontend)

The roster (`frontend/src/features/user-management/components/UserRosterTable.tsx`) renders `role` as plain text ("Admin" / "Project Manager") because no design-token convention exists for role pills (unlike `StatusBadge`, which owns account status). If a visual role treatment is later wanted, define a role-token mapping and a small badge, then swap the plain-text column. Kept as text for now to avoid inventing an ad hoc palette.

## User Management UI — soft-deleted users cannot be restored via the app (Phase 3 frontend / Part 2 backend)

Soft-delete is terminal in the UI: the backend `change_user` / `soft_delete_user` (`backend/app/services/user_service.py`) both call `_get_active_user_row`, which 404s when `deleted_at` is set, so no `PATCH`/`DELETE` can act on a soft-deleted row. The roster therefore only offers "Reactivate" for a deactivated row where `deleted_at IS NULL`, and hides delete/deactivate once deleted. A restore/undelete flow (a backend endpoint that clears `deleted_at` + re-activates, plus a UI action) is deferred; until then, un-deleting a user is a manual DB/dashboard operation.
