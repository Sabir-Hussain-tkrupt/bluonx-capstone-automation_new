## Phase 7: Automated Reminder & Alert System (55 Hours)

Module 7: Deadline Reminders, Insurance Expiration Monitoring, Escalation & In-App Notifications

**Architecture note:** Phase 7 separates communication channels by recipient type. Vendors (external, not in the portal) receive **email** via the existing `EmailService`. Admins and PMs (authenticated portal users) receive **in-app notifications** via the `notifications` table — built in Phase 1 but unused until this phase. All scheduled workflows run inside the existing FastAPI process via APScheduler (AsyncIOScheduler) on a single ECS Fargate task (`desiredCount=1`) with ECS auto-restart on health-check failure. There is no separate orchestration service.

---

### Implementation notes (evidence-backed, derived from existing code)

These notes capture conventions that already exist in the codebase. New jobs must follow them.

**Channel routing (Phase 7 split):**
- External recipients (vendors) → email via `EmailService.send_email()` → audit in `email_log`
- Internal recipients (admin, PM) → in-app notification via `NotificationService.create_notification()` → record in `notifications` table (built in Phase 7 Task 7.4)

**Notification type vocabulary (controlled — do not invent new values):**
- `insurance_expiring` — insurance certificate or vendor record expiring in 30 or 7 days
- `insurance_expired` — expiration date has passed and the underlying record is still in `valid` / unupdated state (admin hasn't acknowledged)
- `post_deadline_non_responders` — bid package deadline passed with non-responding vendors
- `scheduler_alert` — one or more scheduled jobs are stale per the self-check

**Deep-link mapping (`reference_type` → frontend route):**
- `vendors` → vendor detail page (`/vendors/{id}`)
- `bid_packages` → bid package detail page (`/bid-packages/{id}`)
- `NULL` → no deep link (e.g., scheduler alerts)

**Scheduler integration pattern (matches existing `revision_expiry` job):**
- Each job lives in its own module under `backend/app/jobs/` and exposes a `register(scheduler)` function.
- Each job function is decorated with `@tracked_job(job_id)` from `backend/app/jobs/scheduler.py` (line 67). The decorator handles start/complete logging, success/failure recording into `_last_run`, and prevents exceptions from crashing the scheduler.
- `register()` calls `scheduler.add_job(..., id=..., replace_existing=True, **DEFAULT_JOB_KWARGS)` where `DEFAULT_JOB_KWARGS = {"coalesce": True, "misfire_grace_time": 300, "max_instances": 1}`.
- Each new job ID must be added to the `KNOWN_JOB_IDS` tuple in `scheduler.py`.
- Each new job must be wired into `start_scheduler()` with a deferred import and an explicit `register(scheduler)` call.
- Timezone: all new jobs use UTC (consistent with existing `revision_expiry` which uses `CronTrigger(minute=0)`). Cron expressions documented in code comments with the equivalent local time for the BluOnX team.

**Email sending pattern (matches existing callers like `bid_package_service`):**
- All sends go through `EmailService.send_email()` — never `send_bulk_emails()`, which bypasses `email_log` entirely.
- For batch sends, loop over recipients calling `send_email()` per recipient, wrapped in `asyncio.gather` with a semaphore (concurrency limit 10) for SES rate control.
- `email_log` writes are handled internally by `EmailService` — callers do not touch `email_log` directly except for dedup-lookup reads.
- `send_email()` returns an `EmailSendResult` (does not raise) — per-recipient failures are logged to `email_log` with `status='failed'` and `error_message` populated. The job logs the failure and continues processing remaining recipients.

**Notification sending pattern (introduced by Task 7.4):**
- All admin/PM notifications go through `NotificationService.create_notification(db, user_id, notification_type, title, message, reference_type, reference_id, dedupe=True)`.
- The default `dedupe=True` prevents stacking duplicate unread notifications for the same `(user_id, notification_type, reference_id)` triple — if an unread one already exists, the service returns it without inserting a new row.
- Jobs do not write to the `notifications` table directly; the service is the single source of truth for inserts and validates `notification_type` against the controlled vocabulary above.

**Template loading pattern (matches `backend/app/services/template_renderer.py`):**
- Templates live in `backend/app/templates/emails/` as paired `<name>.html` and `<name>.txt` files. A shared `base.html` provides layout.
- Loaded via the module-level singleton `template_renderer` (Jinja2 with HTML autoescape on `.html`, off on `.txt`).
- Phase 7 only adds vendor-facing email templates (the three `bid_reminder_*` pairs already in place). Admin/PM communications use in-app notifications, not emails, so no admin digest templates are built.

**Recipient resolution pattern (no PM concept exists):**
- There is no "assigned PM" or `get_project_pm()` helper in the codebase. Ownership is implicit via `created_by` columns.
- For bid-related notifications, "the PM" is `bid_packages.created_by` looked up in `users` (matches existing inline pattern at `bid_package_service.py:277, 532` and `vendor_portal.py:925-942`).
- For admin notifications, query `users WHERE role='admin' AND is_active=TRUE AND deleted_at IS NULL`.

**Dedup pattern for bid reminders (no schema change required):**
- `email_log` has no tier discriminator. Each tier (T-7 / T-3 / T-0) only matches today's date once in an invitation's lifecycle because the threshold is anchored to `bid_packages.deadline` (e.g., T-7 only matches when `deadline = today + 7 days`).
- Dedup query: `SELECT 1 FROM email_log WHERE email_type='bid_reminder' AND reference_id = :invitation_id AND created_at::date = CURRENT_DATE`.

**Existing notification infrastructure (built but unused before Phase 7):**
- `notifications` table exists with columns: `id`, `user_id`, `title`, `message`, `notification_type`, `reference_type`, `reference_id`, `is_read`, `created_at`.
- RLS policies in place: `notifications_select_own` (users see only their own) and `notifications_update_own` (users can mark their own as read).
- Partial index `idx_notifications_user_unread ON notifications (user_id, is_read) WHERE is_read = FALSE` already exists and covers badge-count and dropdown queries.

---

### Task 7.1: Establish scheduler foundation and conventions for Phase 7 jobs - 4h

* Add the four new Phase 7 job IDs (`daily_bid_reminders`, `daily_insurance_expiration`, `post_deadline_escalation`, `scheduler_self_check`) to the `KNOWN_JOB_IDS` tuple in `backend/app/jobs/scheduler.py`
* Wire each new job's `register(scheduler)` call into `start_scheduler()` with a deferred import (matching the existing `revision_expiry` pattern)
* Create `backend/app/jobs/README.md` documenting the job-authoring contract: must use `@tracked_job`, must include `id` and `replace_existing=True` and `**DEFAULT_JOB_KWARGS` in `add_job`, must wrap heavy work in `asyncio.gather` with a semaphore, must use UTC cron expressions with local-time comments, must return a JSON-serializable dict for the health endpoint
* Verify `GET /api/v1/admin/scheduler-health` surfaces all new job IDs (null last-run records until first execution)
* Tools: APScheduler, FastAPI lifespan hooks, Python logging

### Task 7.2: Build tiered email templates - 3h

*(Scope reduced from the originally-planned 6h. The three `bid_reminder_*` template pairs are the only Phase 7 templates needed because admin/PM communications use in-app notifications instead of email digests. The originally-planned post-deadline escalation digest template and insurance expiration digest template are no longer required.)*

* Verify and finalize the existing `bid_reminder_*` template trio in `backend/app/templates/emails/` for T-7 friendly reminder, T-3 urgent reminder, T-0 final call (Claude Code confirmed these files exist but were never wired up); update copy and styling as needed
* Both `.html` and `.txt` versions required for each tier (the existing `EmailService` requires both bodies as positional arguments to `send_email()`)
* All templates use the shared `base.html` layout, mobile-responsive HTML, BluOnX branding, and dynamic content placeholders rendered via the `template_renderer` singleton
* Tools: Jinja2, HTML/CSS email design

### Task 7.3: Implement bid reminder scheduling job - 10h

* New module `backend/app/jobs/bid_reminders.py` with `register(scheduler)` exposing job ID `daily_bid_reminders`
* APScheduler `CronTrigger` set to UTC, fires once daily at the UTC equivalent of 8:00 AM local time for the BluOnX team (document the exact UTC hour and local-time intent in a code comment)
* SQL query identifies bid invitations needing a reminder today:
  * Join `bid_invitations → bid_packages` on `bid_package_id`
  * `bid_packages.status = 'open'`
  * `bid_invitations.status NOT IN ('submitted', 'declined', 'expired', 'no_response')`
  * `bid_packages.deadline::date IN (CURRENT_DATE + 7, CURRENT_DATE + 3, CURRENT_DATE)` to match T-7, T-3, T-0 thresholds
  * Tier is derived from the day difference: T-7 → friendly template, T-3 → urgent template, T-0 → final call template
* Per-invitation dedup before sending: `SELECT 1 FROM email_log WHERE email_type='bid_reminder' AND reference_id = :invitation_id AND created_at::date = CURRENT_DATE` — skip if any row found
* Resolve recipient: `bid_invitations.vendor_contact_id → vendor_contacts.email, full_name`
* **Auth/magic link decision:** reminders do NOT include a magic link. The reminder email references the vendor's original invitation email (sender, date, subject) and instructs them to use the magic link from that original message. This preserves the existing one-token-per-invitation auth model — no token rotation, no raw-token storage, no schema change.
* Send via `EmailService.send_email(...)` with `email_type='bid_reminder'`, `recipient_type='vendor_contact'`, `reference_type='bid_invitations'`, `reference_id=invitation.id`
* All sends dispatched via `asyncio.gather` with `asyncio.Semaphore(10)` to respect SES rate limits and keep the event loop responsive
* Re-check `bid_invitations.status` inside each per-invitation coroutine to skip vendors who submitted between query time and send time
* Job returns a JSON-serializable dict: `{"t_minus_7_sent": N, "t_minus_3_sent": N, "t_minus_0_sent": N, "failed": N, "skipped_already_sent": N, "skipped_status_changed": N, "duration_seconds": float}`
* Tools: APScheduler, asyncio, EmailService, Supabase Python client

### Task 7.4: Build in-app notification infrastructure - 12h

This task establishes the notification subsystem that Tasks 7.5, 7.6, and 7.8 depend on. It must land before any of them.

**Backend — notification service:**
* New module `backend/app/services/notification_service.py` exposing:
  * `create_notification(db, *, user_id, notification_type, title, message, reference_type=None, reference_id=None, dedupe=True) -> dict` — inserts a row into `notifications`. If `dedupe=True` (default), first checks whether an unread notification already exists for the same `(user_id, notification_type, reference_id)` triple and returns it without inserting a duplicate.
  * `create_notifications_bulk(db, *, notifications: list[dict]) -> list[dict]` — batch helper for jobs notifying multiple admins/PMs at once; applies the same dedupe rule per row.
* All `notification_type` values must be from the controlled vocabulary documented in the Implementation Notes (validate at the service layer; raise `ValueError` on unknown values).
* No exception raised on duplicate-skip — the service returns the existing notification's id. Callers can ignore the return value if they don't need it.

**Backend — REST endpoints (all admin-authed via existing `get_current_active_user`):**
* `GET /api/v1/notifications?unread_only=false&limit=50&offset=0` — paginated list of the current user's notifications, newest first. Default page size 50.
* `GET /api/v1/notifications/unread-count` — returns `{"count": int}` of unread notifications for the current user. Backed by the existing `idx_notifications_user_unread` partial index.
* `PATCH /api/v1/notifications/{notification_id}/read` — marks a single notification as read. Returns 404 if not owned by current user (RLS enforces; endpoint surfaces clean response).
* `PATCH /api/v1/notifications/mark-all-read` — bulk update setting `is_read=TRUE` for all of current user's unread notifications. Returns `{"updated_count": int}`.

**Frontend — notification panel:**
* Add a bell icon to the existing top header component (Claude Code will locate the exact file during implementation — search for the header component used across authenticated pages).
* Bell icon shows a numeric badge with unread count when count > 0. Hidden when count is 0.
* Click opens a dropdown panel showing the 10 most recent unread notifications + 5 most recent read for context. Each notification card shows: title, message, relative timestamp ("2 hours ago"), and a "Mark as read" button (only on unread items).
* Notifications with non-null `reference_type` + `reference_id` render as clickable links that navigate to the deep-link target (per the mapping in Implementation Notes) and mark the notification as read in the same action.
* "View all" footer link at the bottom of the dropdown navigates to a full-page `/notifications` view with pagination, filter toggle (all / unread only), and a "Mark all as read" action.
* React Query handles the unread-count fetch with: refetch on window focus (default), polling interval of 60 seconds. No Supabase Realtime subscription for MVP — polling is sufficient at internal-tool scale.

**Tests:**
* Backend: `backend/tests/services/test_notification_service.py` — covers `create_notification`, dedupe behavior, `create_notifications_bulk`, unknown notification_type rejection.
* Backend: `backend/tests/routers/test_notifications.py` — covers all four endpoints, RLS isolation (user A cannot see/modify user B's notifications), pagination, mark-all-read.
* Frontend: component tests for the bell badge (renders count when > 0, hidden at 0), dropdown rendering, mark-as-read interaction, deep-link navigation.

* Tools: FastAPI, Supabase Python client, React, React Query


### Task 7.4.5: Insurance sync hardening - 2h

Foundation refactor for Task 7.5. Makes `vendors.insurance_expiration_date` a reliably-computed mirror of the latest valid insurance certificate, so Task 7.5 can trust a single field as the source of truth.

* New helper `recompute_vendor_insurance_expiration(db, vendor_id)` in `backend/app/services/vendor_service.py`. Computes `MAX(expiration_date)` across `vendor_documents` rows where `vendor_id` matches AND `document_type='insurance_certificate'` AND `status='valid'`. Writes that value (or `NULL` if none exist) to `vendors.insurance_expiration_date`. Single source of truth for this field.
* Refactor `upload_vendor_document` (insurance certs only): replace the inline swallowed-exception mirror with a call to the helper. Re-raise on failure as `HTTPException(500, "Document saved, but the vendor's insurance date may not have updated. Please refresh and check the vendor record.")` so operators see drift instead of discovering it weeks later.
* Refactor `delete_vendor_document` (insurance certs only): pre-delete fetch grabs `document_type` alongside `file_path`. After successful delete, call the helper for insurance cert deletions. Same error-handling posture as upload.
* No transaction wrapping is possible via PostgREST/supabase-py; the trade-off (cert row committed before recompute) is documented inline in the router.
* Frontend soft-rule hint: when uploading an `insurance_certificate` AND the vendor already has at least one valid insurance cert, show an inline note ("This will become the active certificate. The previous one will remain on file as a historical record."). `VendorDetailPage` passes `vendor_documents` as an `existingDocuments` prop to `VendorDocumentUpload`; no new hook.
* Tests: 5 service-level tests covering MAX semantics (null, multiple, ignores expired-status rows, ignores non-insurance document types, returns persisted value). 6 router tests covering upload-triggers-recompute, upload-of-non-insurance-does-not, upload-recompute-failure-surfaces-500, delete-triggers-recompute, delete-of-non-insurance-does-not, delete-recompute-failure-surfaces-500. 4 frontend hint-visibility tests.
* Tools: FastAPI, Supabase Python client, React

### Task 7.5: Implement insurance expiration monitoring job - 6h

Replaces the no-op stub in `backend/app/jobs/insurance_expiration.py` with full implementation. Sends in-app notifications to admins via `NotificationService` (no email). Relies on the hardened sync from Task 7.4.5 — `vendors.insurance_expiration_date` is the trusted single source of truth.

**Trigger:** APScheduler `CronTrigger` in UTC, fires once daily at 15:15 UTC (≈ 8:15 AM Mountain Time, offset 15 minutes from bid reminders to spread DB/network load and isolate logs).

**Query — one query, three tiers derived in Python:**

* `vendors` where `deleted_at IS NULL` AND `insurance_expiration_date IS NOT NULL` AND `insurance_expiration_date <= CURRENT_DATE + 30`
* In Python, derive the tier per row:
  * `expiration_date = CURRENT_DATE + 30` → `insurance_expiring` (T-30)
  * `expiration_date = CURRENT_DATE + 7` → `insurance_expiring` (T-7)
  * `expiration_date < CURRENT_DATE` → `insurance_expired`
  * Any other date in the window → skip (no notification today; will match exactly on a future T-7 or T-30 day)

**Per-target dedup:**

* For `insurance_expiring`: lead-up tier only matches on exact T-30 and T-7 dates, firing at most twice per vendor per cycle. `NotificationService.create_notification(dedupe=True)` guards against same-day duplicates if the job re-runs.
* For `insurance_expired`: `dedupe=True` prevents stacking duplicate unread notifications. As long as the admin hasn't read or acted on the prior notification, no new one is created. Once read, a new daily notification appears.
* **Acknowledgment to silence:** admin updates `vendor_documents.status='expired'` for the underlying cert (triggering the Task 7.4.5 recompute, which sets `vendors.insurance_expiration_date` to the next-latest valid cert or NULL) → the next day's query no longer matches.

**Recipients:** All active admins (`users WHERE role='admin' AND is_active=TRUE AND deleted_at IS NULL`).

**Notification fields per recipient (one notification per affected vendor per admin):**

* `notification_type` — `insurance_expiring` or `insurance_expired`
* `title` — e.g., "Insurance expiring in 7 days: ABC Excavation" or "Insurance expired: ABC Excavation"
* `message` — Vendor company name, expiration date (formatted), days until/past expiration
* `reference_type='vendors'`, `reference_id=vendor.id` (deep-links to vendor detail page where admin can review and update the underlying cert)

**Frontend addition — dashboard badge:**

* Vendor list view shows a count badge for vendors with insurance expiring within 30 days OR already expired. Backed by a new FastAPI endpoint `GET /api/v1/vendors/insurance-expiring-count` returning `{"count": int}`. Same single-query approach against `vendors.insurance_expiration_date`.

**Job return value:**
{
"expiring_30day_notified": N,
"expiring_7day_notified": N,
"expired_notified": N,
"deduplicated_skipped": N,
"duration_seconds": float
}

* Tools: APScheduler, NotificationService, Supabase Python client, React for dashboard badge

### Task 7.6: Implement post-deadline escalation job - 6h

Replaces the no-op stub in `backend/app/jobs/post_deadline_escalation.py` with full implementation. Sends in-app notifications to the PM who created each affected bid package via `NotificationService` (no email).

**Trigger:** APScheduler `CronTrigger` in UTC, fires once daily at 16:00 UTC (≈ 9:00 AM Mountain Time).

**Query:** bid packages whose `deadline` fell within the last 24 hours AND have at least one `bid_invitations.status IN ('sent', 'opened')` (no submission, no decline). Enrich each affected package with task and project context via PostgREST embedded resource select (`tasks(name, project_id, projects(name))`).

**Logic:**

* Group affected packages by `bid_packages.created_by` (the user who originated the bid round — matches the existing "the PM" pattern at `bid_package_service.py:277, 532`).
* Look up each recipient in `users WHERE id=:created_by AND is_active=TRUE AND deleted_at IS NULL`. Skip with `skipped_inactive_creator` counter increment if recipient is inactive or deleted (rare edge case for archived users; distinct from dedupe-skip for observability).
* **Pre-query dedupe** (matches Task 7.5 pattern): before fan-out, query `notifications` for unread rows with `notification_type='post_deadline_non_responders'` AND `reference_id IN (affected_package_ids)`. Build a set of `(user_id, bid_package_id)` pairs that already have an unread notification. Skip those during dispatch (count toward `deduplicated_skipped`). All `create_notification(...)` calls pass `dedupe=False` — the in-job pre-query is the source of truth for the counter.
* For each affected package, create one notification for the package creator:
  * `notification_type='post_deadline_non_responders'`
  * `title` — e.g., "3 vendors did not respond: Sunset Hills / Excavation"
  * `message` — Lists non-responding vendor company names and contact details (newline-separated, max 5 listed; if more, append "...and N more."). Recommended actions live on the bid package detail page, not in the notification body.
  * `reference_type='bid_packages'`, `reference_id=bid_package.id` (deep-links to bid package detail page; the deep-link helper joins `bid_packages → tasks → projects` to build the nested route)
* Sequential fan-out with per-recipient try/except.
* **Status transition is per-package and gated:** after notifications dispatch for a given package, IF at least one notification succeeded (not necessarily all admins), bulk-UPDATE that package's affected `bid_invitations` from status `sent`/`opened` → `no_response`. If notification dispatch failed for ALL recipients on a package, skip that package's status update — the escalation didn't actually reach anyone, so the invitations shouldn't be flipped.

**Job return value:**

```
{
"packages_affected": int,
"notifications_created": int,
"invitations_marked_no_response": int,
"deduplicated_skipped": int,
"skipped_inactive_creator": int,
"duration_seconds": float
}
```

* Tools: APScheduler, NotificationService, Supabase Python client

### Task 7.7: Build reminder/communication history view - 6h

Read-only `email_log`-backed view scoped to either a bid package or a vendor. Two pieces of work shipped together: a fix to broaden the existing bid-package Email Log filter (which previously missed three flows), and a new vendor-level endpoint plus Communication tab on the vendor detail page.

**Broader filter — used by both endpoints:**

The `email_log` table has no `vendor_id` column, and Phase 7 vendor-facing flows write rows under three distinct `reference_type` values: `bid_invitations`, `bid_revision_requests`, `bid_submissions`. A complete history must union across all three. The shipped implementation runs three small queries (one per `reference_type`) and merges the results in Python sorted by `created_at DESC` — cleaner than a single `.or_()` call with nested IN clauses, and skips empty branches when an ID list would be empty.

**Bid-package side (fix to existing endpoint):**

* Existing endpoint `GET /api/v1/bid-packages/{bid_package_id}/email-log` (`invitation_tracking_service.py:get_bid_package_email_log`) previously filtered only `reference_type='bid_invitations'`, missing PM revision requests, initial bid receipts, and revision receipts.
* Updated logic: walk `bid_package → invitations`, then derive `revision_request_ids` (tied to those invitations) and `submission_ids` (tied to those invitations). Run three `email_log` queries with the respective ID lists, merge and sort.
* No frontend change required — `BidPackageDetailPage`'s existing `EmailLogTable` already renders whatever rows the endpoint returns.

**Vendor side (new endpoint):**

* New endpoint `GET /api/v1/vendors/{vendor_id}/email-log`, admin-authed via existing `get_current_active_user`.
* Backed by a new function in `invitation_tracking_service.py`. Walks `vendor → invitations` (all invitations for this vendor across every bid package), then derives revision and submission IDs the same way. Same three-query merge.
* Response shape matches the bid-package endpoint exactly so the same `EmailLogTable` component renders both.

**No pagination** in either endpoint — matches the existing pattern; volume is bounded for an internal tool.

**Frontend — Vendor detail page (`VendorDetailPage.tsx`, tabbed layout):**

* Add `{ id: 'communication', label: \`Communication (${count})\` }` to the `tabDefs` array (matches the existing label-with-count pattern used by Contacts/Trades/Documents/Flags).
* Conditional render block uses the existing `EmailLogTable` component as-is — no duplication, no new table component.
* New `useVendorEmailLog(vendorId)` hook follows the existing pattern of the bid-package email log hook.

**Out of scope (acknowledged limitations):**

* Future email flows that write to `email_log` with a `reference_type` outside the three handled here (e.g., a hypothetical `awards` or `milestones` reference) will be invisible to these endpoints. When new types are added, the filter is extended at that time.
* No manual resend action — automatic next-tier retry handles repeated outreach; manual resend creates duplicate-email risk.

* Tools: React, FastAPI, Supabase Python client, React Query

### Task 7.8: Build scheduler self-check job - 4h

Replaces the no-op stub in `backend/app/jobs/scheduler_self_check.py` with full implementation. Sends in-app notifications to admins via `NotificationService` (no email).

**Trigger:** APScheduler `CronTrigger` in UTC, fires once daily at 15:45 UTC (≈ 8:45 AM Mountain Time, after all primary jobs have had a chance to run).

**Scheduler module addition:** `backend/app/jobs/scheduler.py` exposes `_started_at: datetime | None` alongside `_last_run`. Set to `datetime.now(timezone.utc)` in `start_scheduler()` and to `None` in `stop_scheduler()`. Read by the self-check via `get_scheduler_started_at()` for cold-start grace.

**Expected intervals (configured constant at top of the job module — opt-in by inclusion):**

EXPECTED_INTERVALS = {
"revision_expiry": timedelta(hours=1),
"daily_bid_reminders": timedelta(days=1),
"daily_insurance_expiration": timedelta(days=1),
"post_deadline_escalation": timedelta(days=1),
}

GRACE_WINDOW = timedelta(hours=2)

`scheduler_self_check` is intentionally excluded — it can't usefully self-evaluate, and that's an accepted blind spot covered by Sentry + ECS health checks. Future jobs added to `KNOWN_JOB_IDS` are NOT auto-watched; they must be added to `EXPECTED_INTERVALS` explicitly. This is intentional: the watcher fails closed (silent non-watching) rather than open (false positives on unconfigured jobs).

**Staleness logic per job:**

* If `last_run_at is None`:
  * If the scheduler has been running for less than `expected_interval + GRACE_WINDOW`, skip this job (cold-start grace — it hasn't had a chance to fire yet).
  * Otherwise, flag as stale with "last ran: never".
* If `last_run_at is not None` and `last_run_at < now - (expected_interval + GRACE_WINDOW)`, flag as stale.

**Dedupe** (pre-query, matches Tasks 7.5 / 7.6 pattern):

* Pre-query `notifications` for unread `scheduler_alert` rows for the candidate admin set. Build a set of `user_ids` to skip.
* All `create_notification(...)` calls pass `dedupe=False`; the in-job pre-query is the source of truth for `deduplicated_skipped`.
* Consequence: a persistent scheduler problem produces one alert per admin until they read it, not one per day.

**Recipients:** All active admins (`users WHERE role='admin' AND is_active=TRUE AND deleted_at IS NULL`). Skip the entire dispatch if either the stale list is empty (no notification, healthy state is silence) or no active admins exist (log a warning; nothing actionable).

**Notification content — one consolidated notification per admin, not one per stale job:**

* `notification_type='scheduler_alert'`
* `title` — "Scheduler alert: 1 job stale" or "Scheduler alert: {N} jobs stale"
* `message` — Newline-separated list, one line per stale job: `"{job_id}: expected every {interval}, last ran {last_run_or_never}"`. Final line: `"Check /api/v1/admin/scheduler-health for current state."`
* `reference_type=NULL`, `reference_id=NULL` — no deep-link target (the admin opens the health endpoint or Sentry directly).

This job's own failure is the only observability blind spot. Sentry + ECS auto-restart + the `scheduler_running` flag on `/admin/scheduler-health` cover the case where the entire scheduler is down.

**Job return value:**
{
"stale_jobs": [list of stale job_id strings],
"admins_notified": int,
"deduplicated_skipped": int,
"duration_seconds": float
}

* Tools: APScheduler, NotificationService, Python logging

---

### Acceptance Criteria

* APScheduler runs as a single in-process scheduler on a single ECS Fargate task; no external orchestration service introduced
* All four Phase 7 jobs (`daily_bid_reminders`, `daily_insurance_expiration`, `post_deadline_escalation`, `scheduler_self_check`) registered with explicit IDs, `replace_existing=True`, and the existing `DEFAULT_JOB_KWARGS` (`coalesce=True`, `misfire_grace_time=300`, `max_instances=1`)
* All five jobs (the four above + the existing `revision_expiry`) appear in `KNOWN_JOB_IDS`; `GET /api/v1/admin/scheduler-health` surfaces last-run timestamps and statuses for every job
* All jobs decorated with `@tracked_job` and return JSON-serializable result dicts surfaced in the health endpoint
* All jobs use UTC `CronTrigger` expressions (matching the existing `revision_expiry` job) with code comments documenting the equivalent local fire times
* Bid reminders (Task 7.3) sent automatically at T-7, T-3, and T-0 thresholds; vendors with status `submitted`, `declined`, `expired`, or `no_response` excluded; per-day dedup via `email_log` prevents duplicate sends; vendor emails route through `EmailService.send_email()` only (never `send_bulk_emails`)
* Bid reminder emails do not include a magic link; they reference the vendor's original invitation email — preserving the existing one-token-per-invitation auth model
* `NotificationService.create_notification()` validates `notification_type` against the controlled vocabulary (`insurance_expiring`, `insurance_expired`, `post_deadline_non_responders`, `scheduler_alert`) and rejects unknown values
* Default dedupe behavior prevents duplicate unread notifications for the same `(user_id, notification_type, reference_id)` triple
* Frontend bell icon visible in the top header on authenticated pages, with badge showing unread notification count; badge hidden at zero
* Notification dropdown shows recent unread + recent read context; clicking a notification with deep-link navigates to the target page and marks the notification as read in one action
* Unread count refreshes on window focus and every 60 seconds via React Query polling (no Supabase Realtime for MVP)
* Insurance expiration job (Task 7.5): lead-up notifications fire on exact T-30 and T-7 dates; expired-but-unacknowledged notifications fire daily until the admin updates the document status to `expired` or refreshes the vendor's `insurance_expiration_date`; dedupe prevents stacking unread duplicates
* Vendor list dashboard shows count badge for vendors with insurance expiring within 30 days OR expired, backed by `GET /api/v1/vendors/insurance-expiring-count`
* Post-deadline escalation job (Task 7.6): notifications reach the bid package creator (`bid_packages.created_by`) the morning after their packages closed with non-responders; one notification per affected package per recipient; affected `bid_invitations.status` transitions `sent`/`opened` → `no_response` after notifications are created
* Communication history visible from vendor detail page (as new Communication tab) and from the existing bid-package detail page Email Log (filter broadened in-place to include `bid_invitations`, `bid_revision_requests`, and `bid_submissions` reference types). Both endpoints return the same response shape; the existing `EmailLogTable` component renders both. Color-coded by `email_log.status`; not paginated (bounded volume for an internal tool); no manual resend action exposed.
* Scheduler self-check (Task 7.8) creates one consolidated `scheduler_alert` notification per admin listing every stale job, when any tracked job is stale beyond its configured `EXPECTED_INTERVALS` entry + 2-hour grace window. Cold-start grace is honored via `get_scheduler_started_at()`. Pre-query dedupe prevents stacking unread alerts; admins receive a fresh alert only after reading or acting on the prior one. Jobs not present in `EXPECTED_INTERVALS` are intentionally not watched (fail-closed semantics).
* RLS policies on `notifications` enforce per-user isolation: `notifications_select_own` and `notifications_update_own` prevent users from seeing or modifying other users' notifications
* Per-recipient failures are isolated: one failed send/notification-create never crashes the parent job
* Graceful shutdown via FastAPI lifespan (`scheduler.shutdown(wait=True)`) so in-flight job runs finish during deploys
* Unit tests for each new job body using the established `FakeSupabase` pattern from `backend/tests/jobs/conftest.py`; integration tests for `NotificationService` and the notification REST endpoints; frontend component tests for the bell badge, dropdown, and mark-as-read interaction
* Sentry captures any unhandled exceptions; structured logs record job start, end, duration, and per-job result counts via the existing `@tracked_job` decorator
