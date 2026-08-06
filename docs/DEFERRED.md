# Deferred Items

Items intentionally deferred during implementation. Reference this file when moving to production or starting later phases.


## User Management — invite rate limiter is per-process (Phase 3 / user management)

`POST /api/v1/users/invite` reuses the in-memory sliding-window limiter in `backend/app/core/rate_limit.py` (`validate_token_rate_limit`, 10 req / 60s / IP). State is per worker process, not cluster-wide. This is acceptable today because production runs a single Fargate task (desiredCount=1), so per-process is effectively cluster-wide. Before scaling horizontally past one instance, move the limiter to a shared store (Redis or a DB-backed counter) so the bound holds across workers. Touchpoint: `backend/app/core/rate_limit.py` (swap the module-level `_buckets` dict for a shared backend); the invite endpoint dependency wiring stays the same.

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

## User Management UI — soft-deleted users cannot be restored via the app (Phase 3 frontend / Part 2 backend)

Soft-delete is terminal in the UI: the backend `change_user` / `soft_delete_user` (`backend/app/services/user_service.py`) both call `_get_active_user_row`, which 404s when `deleted_at` is set, so no `PATCH`/`DELETE` can act on a soft-deleted row. The roster therefore only offers "Reactivate" for a deactivated row where `deleted_at IS NULL`, and hides delete/deactivate once deleted. A restore/undelete flow (a backend endpoint that clears `deleted_at` + re-activates, plus a UI action) is deferred; until then, un-deleting a user is a manual DB/dashboard operation.
