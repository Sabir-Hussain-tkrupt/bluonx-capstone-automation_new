# Deployment Checklist

Go-live runbook. Steps here are required to move the system to production and are
distinct from `DEFERRED.md` (which tracks deferred code/features). Work top to
bottom; check each item in the deploy PR or release notes.

---

## User Management

The admin User Management feature (invite / list / change-role / deactivate /
resend-invite) depends on Supabase's built-in auth mailer and a correctly
configured redirect. None of these are code changes; they are environment and
dashboard configuration that must be done before the feature works in production.

- [ ] **Supabase redirect allow list.** In the Supabase dashboard, go to
  **Authentication -> URL Configuration -> Redirect URLs** and add the production
  frontend origin plus the invite landing path, e.g. `https://app.bluonx.com/accept-invite`
  (and the Site URL, e.g. `https://app.bluonx.com`). Supabase rejects any
  `redirect_to` that is not on this allow list, so invite links will silently fall
  back to the Site URL (or fail) until this is set.

- [ ] **`FRONTEND_BASE_URL` env var.** Set `FRONTEND_BASE_URL` in the backend
  environment to the production frontend origin (e.g. `https://app.bluonx.com`).
  The invite email `redirect_to` is built as `{FRONTEND_BASE_URL}/accept-invite`.
  Startup **refuses to boot** in production (`APP_ENV=production`) unless this is a
  non-localhost `https://` URL (see `backend/app/core/config.py::_validate_frontend_base_url`),
  so a missing/localhost value is caught at deploy time, not at first invite.

- [ ] **Supabase auth email is production-configured.** Invite emails are sent by
  **Supabase's built-in auth mailer, NOT by our SES `EmailService`**. Confirm the
  Supabase project's auth email is configured for a production sender and adequate
  sending volume:
    - Custom SMTP configured under **Authentication -> Emails / SMTP Settings**
      (the default Supabase mailer is rate-limited and unsuitable for production).
    - The **Invite user** email template reviewed and branded.
    - This is a separate track from the transactional SES setup (bid/milestone
      emails); exiting the SES sandbox does **not** cover Supabase auth email.

- [ ] **Bootstrap admin exists.** Ensure at least one active admin
  (`role='admin'`, `is_active=true`, `deleted_at IS NULL`) exists in
  `public.users` before go-live. The last-admin guard prevents removing the final
  admin, but it does not create the first one; seed the bootstrap admin via the
  Supabase dashboard (its `invited_by` is intentionally NULL).

### Verification after deploy

- [ ] Invite a test user from the admin UI; confirm the email arrives and its link
  lands on `{FRONTEND_BASE_URL}/accept-invite`.
- [ ] Confirm resend-invite behavior on a not-yet-confirmed user (re-send) vs an
  already-confirmed user (returns 409, nothing to resend). This path depends on the
  live Supabase project and cannot be fully verified with mocks.

---

## Transactional Email Delivery Tracking (SES / SNS)

The `email_log` delivery lifecycle (`delivered` / `bounced` / `complained`) is
driven entirely by SES event notifications delivered over SNS. Those events only
fire when each send carries a SES **configuration set**, which comes from the
`SES_CONFIGURATION_SET` env var. This var defaults to unset and is **not**
enforced at startup, so a deploy that omits it boots cleanly but every row freezes
at `sent` and no bounce/complaint is ever recorded. Full mechanics and the dev
resource ARNs are in [`ses-sns-event-tracking.md`](ses-sns-event-tracking.md).

- [ ] **Create the production SNS topic + SES event destination.** Mirror the dev
  setup for production: an SNS topic, a SES configuration set whose event
  destination routes DELIVERY / BOUNCE / COMPLAINT to that topic, and a topic
  policy allowing `ses.amazonaws.com` to publish.

- [ ] **Set `SES_CONFIGURATION_SET`** in the backend environment to the production
  configuration set name. Without it, delivery/bounce/complaint tracking silently
  no-ops (rows stay at `sent`). Treat a missing value as a failed deploy.

- [ ] **Subscribe the production webhook to the topic.** Add an HTTPS subscription
  pointing at `https://<prod-api>/api/v1/webhooks/ses-notifications`. The app
  auto-confirms the `SubscriptionConfirmation`; verify the subscription is
  `Confirmed`, not `PendingConfirmation`.

### Verification after deploy

- [ ] Send a transactional email (e.g. a bid invitation) and confirm the matching
  `email_log` row advances past `sent` to `delivered`.
- [ ] Fire a bounce via the SES simulator (`bounce@simulator.amazonses.com`) and
  confirm the row lands on `bounced` with the bounce subtype in `error_message`.

---

## Scheduler (single-instance constraint)

All eight scheduled jobs (bid reminders, insurance expiration, revision expiry,
post-deadline escalation, the two milestone jobs, the annual holiday seed, and the
self-check) run in-process via APScheduler. Every running instance runs its own
scheduler, so a second instance
double-sends every email and double-applies every state transition. There is no
distributed lock. Rationale and revisit thresholds:
[`adr/0001-scheduler-single-instance.md`](adr/0001-scheduler-single-instance.md).

- [ ] **Run exactly one instance.** ECS service `desiredCount = 1`. This is a
  correctness constraint, not a performance dial — do not scale out, and do not
  add a second instance for availability.

- [ ] **No `--workers` on the uvicorn command.** The Dockerfile `CMD` omits it
  deliberately; each worker is another scheduler. Same applies to any process
  manager that would spawn replicas.

### Verification after deploy

- [ ] `GET /api/v1/admin/scheduler-health` returns every job in `KNOWN_JOB_IDS`
  (`backend/app/jobs/scheduler.py`) with the scheduler reporting as running.
- [ ] Confirm the external canary (UptimeRobot per the ADR) is actually polling
  that endpoint and alerting to a monitored inbox. A total scheduler outage has no
  other automated catch — ECS auto-restart and Sentry are deferred infra.

---

## Holiday Calendar

Vendor responsiveness counts 3 **working** days, skipping weekends and the
org-wide `holidays` table. An empty table is not an error — the clock silently
falls back to weekends-only, and vendors start getting flagged a day early over
every holiday. Nothing alerts on this, so it has to be seeded at deploy.

- [ ] **Seed the calendar.** From `backend/`, with the venv, run as a MODULE
  (the path form puts `scripts/` on `sys.path` instead of `backend/`, so `app`
  is unimportable):

  ```bash
  python -m scripts.seed_holidays          # this year + next
  ```

  Idempotent and additive: it never touches a date already present, whatever its
  source, so re-running it cannot overwrite an admin's manual rows or renames.
  Past dates and weekends are skipped. Safe to run more than once.

### Verification after deploy

- [ ] `GET`ing the calendar as an admin at `/settings/calendar` shows ~11 rows
  for next year, all weekdays. A non-admin hitting that URL is redirected.
- [ ] The `holiday_seed` job appears in `GET /api/v1/admin/scheduler-health`.
  It fires annually on January 2 (15:00 UTC / 09:00 America/Chicago) and tops up
  the following year, so the calendar stays 12 months ahead without anyone
  remembering. It is deliberately excluded from the staleness self-check — a
  one-year interval is meaningless to that math — so the seed above is the only
  thing standing between deploy and the first January run.
