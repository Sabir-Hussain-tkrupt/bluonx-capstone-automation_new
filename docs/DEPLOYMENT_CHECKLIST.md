# Deployment Checklist

Go-live runbook. Steps here are required to move the system to production and are
distinct from `DEFERRED.md` (which tracks deferred code/features). Work top to
bottom; check each item in the deploy PR or release notes.

---

## Environment Variables

Vars whose absence or wrong value breaks production. Two of the three now refuse
to boot rather than failing quietly at first use.

- [ ] **`CORS_ORIGINS`** set to the production frontend origin(s), e.g.
  `["https://app.bluonx.com"]`. Startup **refuses to boot** under `APP_ENV=production`
  on an empty list, `"*"`, a localhost/127.0.0.1 origin, or a non-https origin
  (`backend/app/core/config.py::_validate_cors_origins`). One origin is enough while the
  vendor portal is served by the same Vite app as the staff dashboard (`/bid/*` routes);
  add a second only if the portal gets its own domain.

- [ ] **`LOG_LEVEL`** (default `INFO`) and **`LOG_FORMAT`**. Leave `LOG_FORMAT` unset:
  it resolves to `json` under `APP_ENV=production` and `console` elsewhere, so structured
  logs are automatic. Set it explicitly only to override.

- [ ] **`SES_CONFIGURATION_SET`**, **`FRONTEND_BASE_URL`** — covered in their own sections
  below.

---

## Container Image and ECS Service

The Dockerfile is production-shaped (multi-stage, non-root, single worker) but there are
no deployment manifests. Nothing below is code; it is all infra to stand up.

- [ ] **Run on ECS Fargate with `desiredCount = 1`.** Lambda is **not** a viable target:
  APScheduler runs in-process and needs a long-lived process, so all eight scheduled jobs
  would simply never fire. See the Scheduler section below.

- [ ] **Set the deployment strategy to `minimumHealthyPercent = 0` /
  `maximumPercent = 100`.** The default ECS rolling deploy briefly runs the old and new
  task together, which means two APScheduler instances, which double-sends every email in
  that window. The Scheduler section covers steady state; this covers the deploy
  transient.

- [ ] **Ship the DocuSign private key into the container.** `DOCUSIGN_PRIVATE_KEY_PATH`
  defaults to `secrets/docusign_private_key.pem`, but `backend/secrets/` is gitignored and
  the Dockerfile copies only `app/`, so the key is **not** in the image and JWT mint will
  fail at runtime. Either inject the PEM from Secrets Manager to that path at task start,
  or change the config to accept the key material directly from an env var.

- [ ] **ALB target group health check to `/health`.** Unauthenticated, returns 200, and is
  logged at DEBUG so continuous polling does not bury real traffic.

- [ ] **Create the CloudWatch log group.** The app writes JSON (one object per line) to
  **stdout**, with `request_id`, `method`, `path`, `route`, `status`, `duration_ms`, and
  the acting `user_id`/`role` (or `vendor_id`) as top-level fields, queryable directly in
  Logs Insights.

- [ ] **Push the image to ECR** and wire the task definition secrets (Supabase keys, both
  JWT secrets, AWS creds, DocuSign creds) through Secrets Manager rather than plain env.

### Verification after deploy

- [ ] `curl -i https://<prod-api>/health` returns 200 and an `X-Request-ID` response
  header.
- [ ] A CloudWatch Logs Insights query on `status >= 500` parses cleanly as JSON, and one
  known request can be traced end to end by its `request_id`.

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

## Storage Buckets

All three buckets are private and every upload goes through FastAPI on the `service_role`
key. Bucket **configuration** is not code and does not travel with the image, so it has to
be applied per environment or uploads fail at the storage layer with the app none the wiser.

- [ ] **Create the three private buckets** (`vendor-documents`, `project-documents`,
  `bid-attachments`) in **Supabase Dashboard -> Storage**, with the **default** settings.
  Leave the "Allowed MIME types" field and the file size limit alone; the script below sets
  both.

- [ ] **Run `database/storage_rls_policies.sql`** in the production SQL Editor. It applies
  the BUCKET CONFIGURATION block (sets `allowed_mime_types` and `file_size_limit`) and then
  creates the 12 RLS policies (4 ops x 3 buckets). For production, run the **PRODUCTION**
  `UPDATE storage.buckets` pair commented near the top of that file *instead of* the DEV
  pair, after raising the global limit in **Storage -> Settings** (the free tier caps files
  at 50 MB).

- [ ] **Leave `allowed_mime_types` NULL.** MIME/extension validation is application-layer,
  in `BUCKET_CONFIGS[...]["allowed_extensions"]`
  (`backend/app/core/file_validation.py`), because CAD (`.dwg/.dxf/.dwf/.dgn`) and some
  Office files arrive as `application/octet-stream` and no bucket-level list can express
  that. A bucket list narrower than the app's allow-list is the original defect: DOCX / XLSX
  / CAD uploads pass validation and then fail at storage. Do not set one in the Dashboard.

### Verification after deploy

- [ ] ```sql
      SELECT id, file_size_limit, allowed_mime_types
        FROM storage.buckets
       WHERE id IN ('vendor-documents','project-documents','bid-attachments');
      ```
      Expect 3 rows, `allowed_mime_types` **NULL** on all three, and `bid-attachments` at
      `10485760` (10 MB, matching `MAX_ATTACHMENT_BYTES`).

- [ ] Upload a `.docx` and a `.dwg` to a project through the app, and a `.pdf` attachment
  through the vendor portal. All three should return 201, not 500.

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

---

## Frontend Build

- [ ] **`VITE_DEMO_MODE=false`.** Already the value in `frontend/.env.production`; confirm
  the production build actually picks that file up, because demo mode serves an in-memory
  mock portal API and would put mock data in front of real vendors.

- [ ] **`VITE_API_BASE_URL`** points at the production API origin, and
  **`VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`** at the production project.

- [ ] **Regenerate `frontend/src/types/database.types.ts`.** It is still the placeholder
  whose `Tables` carries `[key: string]: any`, so every direct Supabase read outside
  `users` is typed `any` and the read half of the hybrid data-access pattern has no type
  safety. Run
  `npx supabase gen types typescript --project-id <id> > src/types/database.types.ts`.
  Expect this to surface type errors that `any` was masking, so do it in its own PR rather
  than on deploy day.

---

## CI

- [ ] **Add a GitHub Actions workflow.** `.github/` does not exist, so the backend suite
  (160 test files) and the frontend typecheck only run when someone remembers. At minimum:
  `pytest` for the backend and `tsc --noEmit` plus `vitest` for the frontend, on every PR.
  Note the backend suite currently requires live Supabase credentials and a
  `TEST_ADMIN_EMAIL` / `TEST_ADMIN_PASSWORD` pair (see `backend/tests/conftest.py`), so CI
  needs either those secrets or a dedicated test project.



## Contract payment terms — placeholder text (Task 9.x)

**MUST be replaced with the client's real subcontract payment terms before production.** The contract PDF currently ships a placeholder: `DEFAULT_PAYMENT_TERMS` in `backend/app/services/contract_pdf.py` ("Net 30 days ... [Placeholder — client subcontract terms pending.]"). It fills the PAYMENT TERMS clause whenever no `payment_terms` value is supplied on the contract, which is the case today (the contract row is born with `payment_terms = NULL`), so **every generated contract renders the placeholder**. Shipping this to a real vendor would put unverified, non-authoritative payment language into a signed legal document.

**Touchpoints to finalize:**
1. `DEFAULT_PAYMENT_TERMS` in `backend/app/services/contract_pdf.py` — replace with the client-approved terms text (or remove the "[Placeholder ...]" tag once approved).
2. `backend/app/templates/contracts/firm_terms.txt.j2` — the whole terms body is the ISOLATED, SWAPPABLE template flagged for the client's own boilerplate (decision #2); swap it wholesale when the client provides subcontract language.
3. If terms should vary per contract rather than being firm-wide boilerplate, populate `contracts.payment_terms` at envelope-send in `contract_envelope_service.send_contract_envelope` (currently left NULL, which is why the default fires).

Related: the same swappable template also carries the schedule/validity clauses and the dormant "Date of signed scope of work" seam — see Task 9.8.
