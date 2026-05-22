## Phase 7: Automated Reminder & Alert System (44 Hours)

Module 7: Deadline Reminders, Insurance Expiration Monitoring & Escalation

**Architecture note:** All scheduled workflows in this phase run inside the existing FastAPI process via APScheduler (AsyncIOScheduler), using the in-process scheduler foundation established during the bid revision feature. There is no separate orchestration service. The system deploys as a single ECS Fargate task (`desiredCount=1`) with ECS auto-restart on health-check failure. All emails route through the existing `EmailService` (`backend/app/services/email_service.py`) which already owns `email_log` writes and SES retries.

---

### Implementation notes (evidence-backed, derived from existing code)

These notes capture conventions that already exist in the codebase. New jobs must follow them.

**Scheduler integration pattern (matches existing `revision_expiry` job):**
- Each job lives in its own module under `backend/app/jobs/` and exposes a `register(scheduler)` function.
- Each job function is decorated with `@tracked_job(job_id)` from `backend/app/jobs/scheduler.py` (line 67). The decorator handles start/complete logging, success/failure recording into `_last_run`, and prevents exceptions from crashing the scheduler.
- `register()` calls `scheduler.add_job(..., id=..., replace_existing=True, **DEFAULT_JOB_KWARGS)` where `DEFAULT_JOB_KWARGS = {"coalesce": True, "misfire_grace_time": 300, "max_instances": 1}`.
- Each new job ID must be added to the `KNOWN_JOB_IDS` tuple in `scheduler.py` (currently `("revision_expiry",)`).
- Each new job must be wired into `start_scheduler()` with a deferred import and an explicit `register(scheduler)` call.
- Timezone: all new jobs use UTC (consistent with existing `revision_expiry` which uses `CronTrigger(minute=0)`). Cron expressions documented in code comments with the equivalent local time for the BluOnX team.

**Email sending pattern (matches existing callers like `bid_package_service`):**
- All sends go through `EmailService.send_email()` — never `send_bulk_emails()`, which bypasses `email_log` entirely.
- For batch sends, loop over recipients calling `send_email()` per recipient, wrapped in `asyncio.gather` with a semaphore (concurrency limit 10) for SES rate control.
- `email_log` writes are handled internally by `EmailService` — callers do not touch `email_log` directly except for dedup-lookup reads.
- `send_email()` returns an `EmailSendResult` (does not raise) — per-recipient failures are logged to `email_log` with `status='failed'` and `error_message` populated. The job logs the failure and continues processing remaining recipients.

**Template loading pattern (matches `backend/app/services/template_renderer.py`):**
- Templates live in `backend/app/templates/emails/` as paired `<name>.html` and `<name>.txt` files. A shared `base.html` provides layout.
- Loaded via the module-level singleton `template_renderer` (Jinja2 with HTML autoescape on `.html`, off on `.txt`).
- **Pre-existing templates Claude Code found:** three `bid_reminder_*` template files already exist in the templates directory (built but never wired up — `EMAIL_TYPES` enum has `bid_reminder` but no caller sends with it yet). Verify these match the T-7 / T-3 / T-0 tier needs and reuse them where they fit.

**Recipient resolution pattern (no PM concept exists):**
- There is no "assigned PM" or `get_project_pm()` helper in the codebase. Ownership is implicit via `created_by` columns.
- For bid-related notifications, "the PM" is `bid_packages.created_by` looked up in `users` (matches existing inline pattern at `bid_package_service.py:277, 532` and `vendor_portal.py:925-942`).
- For admin notifications, query `users WHERE role='admin' AND is_active=TRUE AND deleted_at IS NULL`.

**Dedup pattern for bid reminders (no schema change required):**
- `email_log` has no tier discriminator. Each tier (T-7 / T-3 / T-0) only matches today's date once in an invitation's lifecycle because the threshold is anchored to `bid_packages.deadline` (e.g., T-7 only matches when `deadline = today + 7 days`).
- Dedup query: `SELECT 1 FROM email_log WHERE email_type='bid_reminder' AND reference_id = :invitation_id AND created_at::date = CURRENT_DATE`.

---

### Task 7.1: Establish scheduler foundation and conventions for Phase 7 jobs - 4h

* Add the four new Phase 7 job IDs (`daily_bid_reminders`, `daily_insurance_expiration`, `post_deadline_escalation`, `scheduler_self_check`) to the `KNOWN_JOB_IDS` tuple in `backend/app/jobs/scheduler.py`
* Wire each new job's `register(scheduler)` call into `start_scheduler()` with a deferred import (matching the existing `revision_expiry` pattern)
* Create `backend/app/jobs/README.md` documenting the job-authoring contract: must use `@tracked_job`, must include `id` and `replace_existing=True` and `**DEFAULT_JOB_KWARGS` in `add_job`, must wrap heavy work in `asyncio.gather` with a semaphore, must use UTC cron expressions with local-time comments, must return a JSON-serializable dict for the health endpoint
* Verify `GET /api/v1/admin/scheduler-health` surfaces all new job IDs (null last-run records until first execution)
* Tools: APScheduler, FastAPI lifespan hooks, Python logging

### Task 7.2: Build tiered email templates - 6h

* Verify and finalize the existing `bid_reminder_*` template trio in `backend/app/templates/emails/` for T-7 friendly reminder, T-3 urgent reminder, T-0 final call (Claude Code confirmed these files exist but were never wired up); update copy and styling as needed
* Build the post-deadline admin escalation digest template (new): consolidated list of bid packages whose deadline passed in the last 24 hours, with non-responding vendors grouped by package, plus recommended actions
* Build the insurance expiration admin digest template (new): consolidated list of vendors and `vendor_documents` insurance certificates expiring at T-30 and T-7, grouped by expiration tier
* Every template requires both `.html` and `.txt` versions (the existing `EmailService` requires both bodies as positional arguments to `send_email()`)
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
* Send via `EmailService.send_email(...)` with `email_type='bid_reminder'`, `recipient_type='vendor_contact'`, `reference_type='bid_invitations'`, `reference_id=invitation.id`
* All sends dispatched via `asyncio.gather` with `asyncio.Semaphore(10)` to respect SES rate limits and keep the event loop responsive
* Re-check `bid_invitations.status` inside each per-invitation coroutine to skip vendors who submitted between query time and send time
* Job returns a JSON-serializable dict: `{"t_minus_7_sent": N, "t_minus_3_sent": N, "t_minus_0_sent": N, "failed": N, "skipped_already_sent": N}`
* Tools: APScheduler, asyncio, EmailService, Supabase Python client

### Task 7.4: Implement insurance expiration monitoring job - 8h

* New module `backend/app/jobs/insurance_expiration.py` with `register(scheduler)` exposing job ID `daily_insurance_expiration`
* APScheduler `CronTrigger` set to UTC, fires once daily at the UTC equivalent of 8:15 AM local time (offset from bid reminders to spread SES load and isolate logs)
* **Scope: insurance only.** Two SQL queries unioned (or run sequentially) into one result set:
  * `vendor_documents` where `document_type = 'insurance_certificate'` AND `status = 'valid'` AND `expiration_date IN (CURRENT_DATE + 30, CURRENT_DATE + 7)`
  * `vendors` where `deleted_at IS NULL` AND `insurance_expiration_date IN (CURRENT_DATE + 30, CURRENT_DATE + 7)`
* Resolve recipients: query `users WHERE role = 'admin' AND is_active = TRUE AND deleted_at IS NULL`
* Build one consolidated digest per admin listing every expiring insurance item (T-30 and T-7 tiers grouped, with vendor name, company name, certificate expiration date, days remaining)
* Skip the digest entirely if no items match (no empty emails)
* Weekly dedup: `SELECT 1 FROM email_log WHERE email_type='general' AND recipient_type='user' AND reference_type='insurance_expiration_digest' AND created_at >= CURRENT_DATE - INTERVAL '6 days'` — if the same admin already received a digest this week, skip them (prevents daily spam when the same items keep matching the T-30 window for several days)
* Send via `EmailService.send_email(...)` with `email_type='general'`, `recipient_type='user'`, `reference_type='insurance_expiration_digest'` (synthetic discriminator since no real source table — documented in the job comment), `reference_id=user.id`
* **Frontend: dashboard badge.** Add an indicator to the vendor list view showing the count of vendors with insurance (from either `vendors.insurance_expiration_date` or matching `vendor_documents`) expiring within 30 days. Backed by a new FastAPI endpoint `GET /api/v1/vendors/insurance-expiring-count` returning a single integer count.
* Job returns a JSON-serializable dict: `{"items_found": N, "admins_notified": N, "admins_skipped_weekly_dedup": N, "failed": N}`
* Tools: APScheduler, EmailService, Supabase Python client, React for dashboard badge

### Task 7.5: Implement post-deadline admin escalation job - 6h

* New module `backend/app/jobs/post_deadline_escalation.py` with `register(scheduler)` exposing job ID `post_deadline_escalation`
* APScheduler `CronTrigger` set to UTC, fires once daily at the UTC equivalent of 9:00 AM local time
* SQL query identifies bid packages whose `deadline` fell within the last 24 hours and have at least one `bid_invitations.status IN ('sent', 'opened')` (no submission, no decline)
* Group affected packages by `bid_packages.created_by` (the user who originated the bid round — matches the existing "the PM" pattern at `bid_package_service.py:277, 532`)
* Look up each recipient in `users WHERE id = :created_by AND is_active = TRUE AND deleted_at IS NULL` — skip if user is inactive or deleted
* Build one consolidated digest per recipient listing all their affected packages: project name (`projects.name`), task name (`tasks.name`), deadline, and a row per non-responding vendor (`vendors.company_name`, `vendor_contacts.full_name`, `vendor_contacts.email`, `vendor_contacts.phone`)
* Body includes recommended actions ("Contact vendor directly", "Extend deadline and resend invitations via the existing Bid Revision flow", "Award based on submitted bids")
* Skip the digest entirely if a recipient has no affected packages
* Send via `EmailService.send_email(...)` with `email_type='general'`, `recipient_type='user'`, `reference_type='post_deadline_escalation'` (synthetic discriminator), `reference_id=recipient_user.id`
* After successful digest delivery, update affected `bid_invitations.status` from `sent`/`opened` to `no_response` for cleaner dashboard reporting (one bulk UPDATE per package using the partial unique index on bid_package_id + vendor_id)
* Job returns a JSON-serializable dict: `{"packages_affected": N, "recipients_notified": N, "invitations_marked_no_response": N, "failed": N}`
* Tools: APScheduler, EmailService, Supabase Python client

### Task 7.6: Build reminder/communication history view - 6h

* New FastAPI endpoints:
  * `GET /api/v1/vendors/{vendor_id}/email-history` — paginated (default page size 50), returns `email_log` rows where `recipient_type='vendor_contact'` AND the recipient_email matches any `vendor_contacts.email` for this vendor, OR where `reference_type='bid_invitations'` AND `reference_id IN (SELECT id FROM bid_invitations WHERE vendor_id = :vendor_id)`
  * `GET /api/v1/bid-packages/{bid_package_id}/email-history` — paginated, returns `email_log` rows where `reference_type='bid_invitations'` AND `reference_id IN (SELECT id FROM bid_invitations WHERE bid_package_id = :bid_package_id)`
* Both endpoints admin-authed via existing `get_current_active_user` dependency
* **Frontend — Vendor detail page (`VendorDetailPage.tsx`, tabbed layout):**
  * Add `{ id: 'communication', label: \`Communication (${count})\` }` to the `tabDefs` array (matches the existing pattern at lines 120-126)
  * Add a conditional block `{activeTab === 'communication' && (...)}` inside the `<Tabs>` children (matches lines 172-420)
  * Render a paginated list with columns: timestamp (formatted), email type, subject, recipient email, status (color-coded badge)
* **Frontend — Bid package detail page (`BidPackageDetailPage.tsx`, stacked-cards layout):**
  * Add another `<Card>` inside the root `<div className="space-y-6">` (matches lines 143-326)
  * Use the existing collapsible-section pattern from the Email Log card (lines 294-326): a header `<button>` toggling a `showCommunicationHistory` boolean to lazy-render its body
  * Same column layout as the vendor view, scoped to this package's invitations
* Status badge colors: green = `delivered`, blue = `sent`, amber = `queued`, red = `bounced` or `failed`
* No manual resend action — automatic next-tier retry handles repeated outreach; manual resend creates duplicate-email risk
* Tools: React, FastAPI, Supabase Python client, React Query

### Task 7.7: Build scheduler self-check job - 4h

* New module `backend/app/jobs/scheduler_self_check.py` with `register(scheduler)` exposing job ID `scheduler_self_check`
* APScheduler `CronTrigger` set to UTC, fires once daily at the UTC equivalent of 8:45 AM local time (after all primary jobs have had a chance to run)
* Reads the in-memory last-run state via `get_last_run(job_id)` from `scheduler.py` for every entry in `KNOWN_JOB_IDS` except `scheduler_self_check` itself
* For each tracked job: define an expected interval (hourly for `revision_expiry`, daily for the four new jobs) and a 2-hour grace window. If `last_run_at` is `None` or older than `now - (expected_interval + grace)`, append the job to the failure summary with its job ID, expected interval, and last-run timestamp
* If the failure summary is non-empty, resolve admin recipients (same query as Task 7.4: `users WHERE role = 'admin' AND is_active = TRUE AND deleted_at IS NULL`) and send one alert email per admin
* Email body lists every stale job and links to `/api/v1/admin/scheduler-health` for inspection
* Send via `EmailService.send_email(...)` with `email_type='general'`, `recipient_type='user'`, `reference_type='scheduler_self_check'` (synthetic discriminator), `reference_id=recipient_user.id`
* This job's own failure is the only observability blind spot; that's acceptable because Sentry exception capture + ECS auto-restart + the `scheduler_running` flag on `/admin/scheduler-health` cover the case where the entire scheduler is down
* Job returns a JSON-serializable dict: `{"stale_jobs": [...], "admins_notified": N}`
* Tools: APScheduler, EmailService, Python logging

### Acceptance Criteria

* APScheduler runs as a single in-process scheduler on a single ECS Fargate task; no external orchestration service introduced
* All four new jobs (`daily_bid_reminders`, `daily_insurance_expiration`, `post_deadline_escalation`, `scheduler_self_check`) registered with explicit IDs, `replace_existing=True`, and the existing `DEFAULT_JOB_KWARGS` (`coalesce=True`, `misfire_grace_time=300`, `max_instances=1`)
* All new job IDs added to `KNOWN_JOB_IDS`; `GET /api/v1/admin/scheduler-health` surfaces last-run timestamps and statuses for every job
* All jobs decorated with `@tracked_job` and return JSON-serializable result dicts surfaced in the health endpoint
* All jobs use UTC `CronTrigger` expressions (matching the existing `revision_expiry` job) with code comments documenting the equivalent local fire times
* All email sends use `EmailService.send_email()` (never `send_bulk_emails`); `email_log` writes happen automatically inside the service
* Per-recipient failures are isolated: one failed send never crashes the parent job; the job records the failure via the existing `EmailService` retry/log path and continues processing remaining recipients
* Bid reminders sent automatically at T-7, T-3, and T-0 thresholds; vendors with status `submitted`, `declined`, `expired`, or `no_response` are excluded; the same tier is never sent twice for the same invitation (per-day dedup via `email_log` lookup)
* Insurance expiration alerts cover both `vendor_documents` rows where `document_type='insurance_certificate'` AND `status='valid'` AND `expiration_date IN (CURRENT_DATE + 30, CURRENT_DATE + 7)`, and `vendors.insurance_expiration_date IN (CURRENT_DATE + 30, CURRENT_DATE + 7)`
* Insurance digest delivered to all active admin users; weekly dedup prevents the same admin receiving multiple digests within a 7-day window for the same matched items
* Vendor list dashboard shows a count badge for vendors with insurance expiring within 30 days, backed by `GET /api/v1/vendors/insurance-expiring-count`
* Post-deadline escalation digest reaches each bid package creator (`bid_packages.created_by`) the morning after their packages closed with non-responders; one consolidated email per recipient, not one per package
* After the post-deadline digest sends, affected `bid_invitations.status` is updated from `sent`/`opened` to `no_response`
* Communication history visible from the vendor detail page (as a new tab) and the bid package detail page (as a new collapsible Card section), paginated, color-coded by `email_log.status`; no manual resend action exposed
* Self-check job emails admins when any tracked job is stale beyond its expected interval + 2-hour grace window
* Graceful shutdown via FastAPI lifespan (`scheduler.shutdown(wait=True)` in the existing pattern) so in-flight email batches finish during deploys
* Unit tests for each job body using the established `FakeSupabase` pattern from `backend/tests/jobs/conftest.py`; integration test confirms the full pipeline (job runs → `EmailService.send_email` invoked → `email_log` row written)
* Sentry captures any unhandled exceptions; structured logs record job start, end, duration, and per-job result counts via the existing `@tracked_job` decorator
