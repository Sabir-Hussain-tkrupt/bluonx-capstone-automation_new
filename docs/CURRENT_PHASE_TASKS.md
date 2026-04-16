# Current Phase Tasks — BluOnX Development Operations Platform

**Last Updated:** April 2, 2026

---

## Phase 1: Foundation & Database (60h) — ✅ COMPLETE

| Task | Status | Notes |
|------|--------|-------|
| 1.1 — Supabase project setup | ✅ | Free-tier dev account configured |
| 1.2 — Core database schema | ✅ | 28 tables — `database/bluonx_complete_schema_v2_2.sql` |
| 1.3 — Database indexes | ✅ | 49 custom indexes (Section 5 of schema) |
| 1.4 — Row Level Security | ✅ | 28 SELECT + 8 WRITE policies — `database/rls_policies.sql` |
| 1.5 — Database triggers | ✅ | 25 triggers, 11 functions (Section 6 of schema) |
| 1.6 — Storage buckets | ✅ | 3 private buckets, 12 storage RLS policies |
| 1.7 — Auth framework | ✅ | Supabase Auth configured, frontend integration done in Phase 2 |
| 1.8 — Dev/staging environments | ⏳ DEFERRED | Using free-tier dev; prod separation at deployment |
| 1.9 — AWS infrastructure | ⏳ DEFERRED | Pending client AWS credentials |

## Phase 2: Frontend Foundation, Backend API & Auth (100h) — ✅ COMPLETE

| Task | Status | Notes |
|------|--------|-------|
| 2.1 — React + Vite + TailwindCSS v4 | ✅ | Vite + TS, TW4 CSS-first `@theme`, feature-based dirs, `@/` alias |
| 2.2 — Routing (React Router v6) | ✅ | All routes defined, ProtectedRoute, navigation guards |
| 2.3 — Supabase Client + State Mgmt | ✅ | Singleton client, AuthContext/Provider, `onAuthStateChange` (sync fire-and-forget), `fetchProfile` with AbortController timeout |
| 2.4 — React Query API Layer | ✅ | Provider configured, custom hooks pattern (Supabase reads + FastAPI writes), cache invalidation |
| 2.5 — Reusable UI Component Library | ✅ | Inputs, layout, data display, navigation, form components — all TW4 |
| 2.6 — FastAPI Backend Scaffolding | ✅ | Project structure in `backend/`, single Supabase admin client via lifespan, Pydantic v2 models, JWT middleware (PyJWT HS256 audience="authenticated"), CORS, Docker, endpoint scaffolding |
| 2.7 — Authentication System | ✅ | Login/register/reset UI, email/password only, session persistence, ProtectedRoute HOC, role-based rendering |
| 2.8 — Main Dashboard Layout | ✅ | Sidebar + top header + breadcrumbs + user menu, responsive hamburger |
| 2.9 — Responsive Design | ✅ | Mobile 320px+ / tablet 768px+ / desktop 1024px+, touch targets, card views on mobile |

## Phase 3: Core Entity Management (76h) — ✅ COMPLETE

| Task | Status | Notes |
|------|--------|-------|
| 3.1 — Vendor Management Interface | ✅ | Full CRUD, CSV import, contacts, trades, documents |
| 3.2 — Project Management | ✅ | Full CRUD, budget tracking, documents |
| 3.3 — Task Management | ✅ | CRUD within projects, trade filtering by phase, sort_order, bid_type |
| 3.4 — Document Upload Functionality | ✅ | Drag-and-drop, coat-check pattern, 3 buckets, signed URLs |
| 3.5 — Google Maps Integration | ✅ | Geocoding, Haversine pre-filter, Distance Matrix for final, 75-mile default |
| 3.6 — Bid Template Management | ✅ | Template library CRUD, line item management, preview, trade association |

**Deferred from Phase 1 (to be addressed at deployment — see `docs/DEFERRED.md`):**
- Task 1.8 — Dev/staging environment separation
- Task 1.9 — AWS infrastructure setup (pending client credentials)

---

## Phase 4: Bid Invitation System (50h) — 🔄 IN PROGRESS

**Goal:** Build the complete bid invitation pipeline — from intelligent vendor filtering through email delivery and invitation tracking. After this phase, a PM can select a task, filter qualified vendors, choose a bid template, attach project documents, and send professional bid invitations via email. The system tracks invitation status in real-time on the dashboard.

**Tables touched in this phase:** `bid_packages`, `bid_package_documents`, `bid_invitations`, `magic_link_tokens`, `email_log`

**Tables read (from Phase 3):** `tasks`, `vendors`, `vendor_contacts`, `vendor_trades`, `vendor_documents`, `trades`, `projects`, `project_documents`, `vendor_flags`, `bid_templates`

### Architecture Context (carry forward from Phases 2–3)

- **Reads:** Supabase JS client (browser) → RLS policies. Authenticated users see non-deleted records automatically.
- **Writes:** All mutations go through FastAPI → single Supabase service_role admin client (bypasses RLS). Never write directly from the browser.
- **FastAPI pattern:** Admin client initialized once at startup via lifespan context manager. Endpoints get it via dependency injection. Pydantic v2 for all request/response models. `created_by` resolved server-side from JWT, never from client payload.
- **Frontend data pattern:** React Query custom hooks. `useQuery` for reads (Supabase client), `useMutation` for writes (Axios → FastAPI). `onSuccess` invalidates relevant query keys.
- **Soft deletes:** `deleted_at` TIMESTAMPTZ on vendors, projects, tasks. RLS policies already filter `deleted_at IS NULL`.
- **File uploads:** Coat-check pattern — metadata row in DB, file in Supabase Storage bucket.
- **Distance calculation:** Haversine for bulk pre-filter (~100mi generous), Google Maps Distance Matrix for final accurate set (75-mile radius). Implemented in Task 3.5.

### Key Domain Rules for Phase 4

- **One task = one trade = one award = one contract.** A bid package belongs to exactly one task.
- **Three bid types:** `competitive` (full pipeline — this is what Phase 4 handles), `direct_assign` (PM picks vendor, Phase 9), `internal` (budget line only, no bids ever). **Bid packages must NOT be created for `internal` tasks.** Enforce at API layer.
- **`direct_assign` tasks:** Phase 4 should NOT block these from having bid packages. Direct assign flows are handled in Phase 9, but the data model allows it. For Phase 4, the vendor selection UI is primarily for `competitive` tasks.
- **Bid template selection:** When creating a bid package, PM selects a bid template. Templates affiliated with the task's trade are auto-suggested, but PM can select any template (including general-purpose ones with `trade_id = NULL`). The selected `bid_template_id` is stored on `bid_packages`.
- **Round numbering:** `bid_packages.round_number` auto-incremented by trigger (`fn_set_bid_package_round_number`). Round 1 = first attempt, Round 2+ = rebid for same task.
- **75-mile vendor proximity filter** using Google Maps integration from Task 3.5.
- **Vendor qualification criteria:** trade match + distance ≤ 75mi + insurance not expired + bonding capacity ≥ task budget + capacity available (current_active_jobs < max_active_jobs) + onboarding_status = 'complete' + vendor not deleted + vendor status = 'active'.
- **Vendor flags:** Display as warnings during vendor selection, but do NOT auto-exclude flagged vendors. PM makes the final call.
- **Magic link tokens:** Generated per invitation, SHA-256 hashed, stored in `magic_link_tokens`. Raw token goes in email URL. **Token expiry is tied to the bid package deadline** — `expires_at = bid_packages.deadline`. This is critical for construction vendors who may be busy on job sites for days before responding. A vendor should be able to click their link at any point while the bid is still open. The token's `is_used` flag tracks first use (which issues a short-lived JWT session for portal access), but the token itself remains valid for re-entry if the JWT expires — vendor just clicks the link again and resumes from their saved draft. After the bid deadline passes, tokens become invalid. Token validation happens in Phase 5 (vendor portal). Phase 4 only generates and stores them.
- **Email delivery:** Phase 4 builds the AWS SES integration and email sending capability. The actual batch email orchestration uses n8n (Task 4.4), but the core SES send function lives in FastAPI for reuse.
- **`bid_package_documents`:** Junction table linking project documents to a bid package. PM selects which project docs to include with the invitation. Vendors see these docs when they access the bid portal (Phase 5).

---

### Task 4.1: Build Intelligent Vendor Filtering Algorithm (10h)

**Context:** When a PM starts bidding on a `competitive` task, the system needs to find qualified vendors automatically. The filtering algorithm is the backbone of the invitation flow — it runs all qualification checks and returns a ranked list for PM review. The PM can then override by adding/removing vendors before sending invitations.

**Backend — FastAPI endpoint:**

**`GET /v1/tasks/{task_id}/qualified-vendors`** — Returns a list of vendors qualified for this task's trade, filtered by all criteria.

Query parameters:
- `radius_miles` (optional, default: 75) — max distance from project
- `include_flagged` (optional, default: true) — include vendors with unresolved flags (shown with warning)

Response shape (per vendor):
```json
{
  "vendor_id": "uuid",
  "company_name": "ABC Excavation",
  "primary_contact": {
    "id": "uuid",
    "full_name": "John Smith",
    "email": "john@abc.fake",
    "phone": "555-1234"
  },
  "distance_miles": 42.3,
  "insurance_expiration_date": "2027-03-15",
  "insurance_days_remaining": 348,
  "bonding_capacity": 500000.00,
  "max_active_jobs": 5,
  "current_active_jobs": 3,
  "available_capacity": 2,
  "onboarding_status": "complete",
  "has_unresolved_flags": true,
  "unresolved_flag_count": 1,
  "flag_reasons": ["missed_deadline"],
  "qualification_status": "qualified",
  "disqualification_reasons": []
}
```

**Filtering pipeline (ordered for performance):**

1. **Trade match:** `vendor_trades` junction → vendors associated with `tasks.trade_id`. This is the primary filter — a vendor must have the matching trade. *SQL join, cheapest filter first.*
2. **Active & not deleted:** `vendors.status = 'active'` AND `vendors.deleted_at IS NULL`. *Already filtered by RLS for reads, but enforce explicitly in the query for service_role context.*
3. **Onboarding complete:** `vendors.onboarding_status = 'complete'`. Vendors with `pending` or `partial` status are excluded. *Simple column check.*
4. **Insurance valid:** `vendors.insurance_expiration_date > NOW()` (or `> task's project estimated_end_date` if available). Expired insurance = disqualified. NULL insurance_expiration_date = disqualified (missing data). *Column check.*
5. **Bonding capacity:** `vendors.bonding_capacity >= tasks.budget_estimate`. If task has no budget_estimate, skip this check. If vendor has NULL bonding_capacity, include with a warning flag. *Column comparison.*
6. **Capacity available:** `vendors.current_active_jobs < vendors.max_active_jobs`. If `max_active_jobs` is NULL, assume unlimited capacity (include vendor). *Column comparison.*
7. **Distance filter:** Use the `filter_vendors_by_distance` function from Task 3.5. Haversine pre-filter at ~100mi, then Google Maps Distance Matrix for the remaining set. Requires `projects.latitude`/`longitude` and `vendors.latitude`/`longitude` to be populated. If either is NULL, include vendor with `distance_miles: null` and a "distance unknown" warning. *Most expensive filter — run last.*
8. **Flags (informational, not exclusionary):** Join `vendor_flags` where `is_resolved = FALSE`. Count and list reasons. Include in response but do NOT exclude vendor.

**Disqualification tracking:** For vendors that fail any criterion, return them in a separate `disqualified_vendors` array in the response with `disqualification_reasons` populated. This lets the PM see WHY a vendor was excluded and potentially override (e.g., "their insurance renews next week").

Full response shape:
```json
{
  "task_id": "uuid",
  "task_name": "Excavation & Grading",
  "trade_name": "Excavation",
  "project_id": "uuid",
  "project_name": "Sunset Hills Phase 2",
  "filter_criteria": {
    "radius_miles": 75,
    "trade_id": "uuid",
    "min_bonding": 145000.00,
    "insurance_cutoff_date": "2026-12-31"
  },
  "qualified_vendors": [ /* array of vendor objects as above */ ],
  "disqualified_vendors": [
    {
      "vendor_id": "uuid",
      "company_name": "XYZ Corp",
      "disqualification_reasons": ["insurance_expired", "over_capacity"],
      /* ... same fields as qualified but with reasons */
    }
  ],
  "total_qualified": 7,
  "total_disqualified": 3
}
```

**Edge cases to handle:**
- Task has no trade_id → should not happen (FK required), but return 400 if encountered
- Project has no lat/lng → skip distance filter, include all with `distance_miles: null`
- No vendors match any criteria → return empty `qualified_vendors` with message
- Task `bid_type = 'internal'` → return 400 "Internal tasks do not accept bids"
- Task already has an active (non-cancelled) bid package → include warning in response but allow (rebidding scenario)

**Performance considerations:**
- The trade match + active/onboarding filters narrow the set dramatically (from ~200 vendors to ~10–20 for a given trade)
- Distance Matrix API is called only on the pre-filtered set (cost: ~$5/1000 elements)
- Cache geocoded coordinates (already done in Task 3.5)
- Entire pipeline should complete in <2 seconds for typical datasets

**No frontend in this task.** The filtering algorithm is a backend-only service. The frontend vendor selection UI is Task 4.6.

**Follows existing patterns:**
- Router file: `backend/app/routers/bid_invitations.py` (or `bid_packages.py` — group bid lifecycle routes logically)
- Pydantic v2 response models in `backend/app/models/`
- Use dependency injection for Supabase admin client and JWT auth
- Reuse the distance calculation service from Task 3.5

---

### Task 4.2: Create Bid Invitation Email Templates (6h)

**Context:** Professional HTML emails sent to vendors inviting them to bid on a task. These emails are the first impression vendors get of the system. Must render correctly across email clients (Gmail, Outlook, Apple Mail, mobile).

**Email template: Bid Invitation**

Content sections:
1. **Header:** BluOnX branding / logo placeholder
2. **Greeting:** "Dear {vendor_contact.full_name},"
3. **Introduction:** "{project.name} — {task.name} bid invitation from BluOnX Development"
4. **Project details:** Project name, location (city, state), project description (truncated), task description
5. **Bid details:** Deadline date/time, bid type (lump sum vs structured — from bid template), documents included (list of attached project document names)
6. **Call-to-action button:** "Submit Your Bid" → links to `{PORTAL_BASE_URL}/bid/{magic_link_token}`. Large, prominent, styled button.
7. **Secondary info:** Contact info for questions (PM name, email), important notes/instructions
8. **Footer:** Company info, unsubscribe note (if applicable), legal disclaimer

**Technical requirements:**
- HTML email templates stored in `backend/app/templates/emails/` (Jinja2 templates)
- Inline CSS only (no external stylesheets — email clients strip `<link>` and `<style>` tags in many cases; use inline styles for maximum compatibility, with a `<style>` block as progressive enhancement)
- Responsive: single-column layout, max-width 600px, mobile-friendly font sizes
- Test rendering in Litmus or manual testing across: Gmail (web + mobile), Outlook (desktop + web), Apple Mail
- Dark mode compatible (use background colors explicitly, don't rely on transparent)
- All images hosted externally (not inline base64 — bloats email size)
- Plain-text fallback version for email clients that don't render HTML

**Template variables (Jinja2 context):**
```python
{
    "vendor_contact_name": str,
    "vendor_company_name": str,
    "project_name": str,
    "project_location": str,  # "City, State"
    "project_description": str,  # truncated to ~200 chars
    "task_name": str,
    "task_description": str,
    "bid_deadline": str,  # formatted: "March 15, 2026 at 5:00 PM EST"
    "bid_format": str,  # "Lump Sum" or "Line-Item Breakdown"
    "document_names": list[str],  # names of attached project docs
    "magic_link_url": str,  # full URL with token
    "pm_name": str,
    "pm_email": str,
    "company_name": str,  # "BluOnX Development"
}
```

**Additional email templates to create (simpler versions):**
- **Bid Reminder — Friendly (T-7 days):** Same structure but subject = "Reminder: Bid for {task_name} due in 7 days" and softer tone
- **Bid Reminder — Urgent (T-3 days):** Subject = "Urgent: Bid deadline approaching — {task_name}" with stronger urgency
- **Bid Reminder — Final Call (T-0):** Subject = "Final Call: Bid for {task_name} due today" — last chance

> Note: Reminder emails are SENT by n8n workflows (Phase 7 Task 7.1–7.3). Phase 4 creates the templates only. However, the initial invitation email is sent as part of the bid package creation flow in this phase.

**NOT in this task:** Decline letter templates (Phase 9), award letter templates (Phase 9), milestone email templates (Phase 10).

---

### Task 4.3: Implement AWS SES Email Service Integration (8h)

**Context:** All outbound system emails go through AWS SES. This task builds the core email sending capability as a reusable service in FastAPI. n8n workflows will call this service (or use SES directly via n8n's AWS node) for batch and scheduled sends.

> **Dependency:** AWS SES access. If client AWS credentials not yet available, build the service with a mock/console-logging fallback so development can continue. Use feature flag (`EMAIL_PROVIDER=ses|mock`).

**Backend — Email service (`backend/app/services/email_service.py`):**

```python
class EmailService:
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        plain_text_body: str,
        from_email: str = "noreply@bluonx.com",
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> EmailSendResult:
        """Send a single email via AWS SES. Returns send result with message_id."""

    async def send_bulk_emails(
        self,
        emails: list[EmailPayload],
    ) -> list[EmailSendResult]:
        """Send multiple emails. Respects SES rate limits (14/sec default)."""
```

**AWS SES configuration:**
- Use `boto3` SES client (v2 API: `ses_v2_client.send_email()`)
- From address: `noreply@bluonx.com` (or configured via env var `SES_FROM_EMAIL`)
- Region: configured via `AWS_REGION` env var
- Credentials: `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` env vars (or IAM role if on EC2/ECS)
- Rate limiting: SES sandbox = 1 email/sec, production = 14 emails/sec. Implement token-bucket or simple delay between sends.

**AWS SNS bounce/delivery tracking:**
- Configure SES to publish delivery/bounce/complaint events to an SNS topic
- SNS topic → HTTPS endpoint on FastAPI: `POST /v1/webhooks/ses-notifications`
- Webhook handler parses SNS notification, updates `email_log.status`:
  - `Delivery` → status = `delivered`
  - `Bounce` → status = `bounced`, store bounce type in `error_message`
  - `Complaint` → log for review
- SNS message validation: verify SNS message signature to prevent spoofing

**Email logging (`email_log` table):**
Every email sent creates a row in `email_log`:
```python
{
    "recipient_email": "john@abc.fake",
    "recipient_type": "vendor_contact",  # or "user"
    "email_type": "bid_invitation",  # matches CHECK constraint
    "subject": "Bid Invitation: Excavation — Sunset Hills Phase 2",
    "reference_type": "bid_invitations",  # polymorphic ref
    "reference_id": "<bid_invitation_id>",
    "status": "sent",  # updated by SNS webhook later
    "sent_at": "2026-04-02T10:30:00Z",
    "retry_count": 0,
}
```

**Mock/fallback mode:**
When `EMAIL_PROVIDER=mock`:
- Log email to console with full details (to, subject, body preview)
- Insert `email_log` row with `status = 'sent'` (simulates success)
- Useful for development/testing without AWS credentials

**Retry logic:**
- On SES API failure (throttle, service unavailable): retry up to 3 times with exponential backoff (1s, 4s, 16s)
- On permanent failure (invalid address, rejected): log error, set `email_log.status = 'failed'`, store error in `email_log.error_message`
- `email_log.retry_count` incremented on each retry

**FastAPI endpoints:**

1. **`POST /v1/webhooks/ses-notifications`** — SNS webhook endpoint. Public (no auth) but validates SNS signature. Handles SubscriptionConfirmation (auto-confirms) and Notification (processes bounce/delivery).

**NOT in this task:** Actual bid invitation sending flow (that's Task 4.4 + 4.6). This task builds the infrastructure only.

---

### Task 4.4: Build Batch Email Sending Function (8h)

**Context:** When a PM confirms the vendor list and sends invitations, the system needs to: (1) create the bid package, (2) create bid invitations for each vendor, (3) generate magic link tokens, (4) render personalized email for each vendor, (5) send all emails, (6) log everything. This task builds the orchestration logic.

> **Note on n8n:** The project plan specifies n8n for batch email processing. For the initial invitation send (triggered by PM action), the orchestration runs in FastAPI as a single atomic operation. n8n handles the scheduled/recurring emails (reminders in Phase 7). If the team later decides to move invitation sending to n8n, the email service from Task 4.3 can be called by n8n's HTTP node.

**Backend — "Create Bid Package & Send Invitations" endpoint:**

**`POST /v1/tasks/{task_id}/bid-packages`** — Creates a bid package, invitations, magic links, and sends emails in one operation.

Request body:
```json
{
  "deadline": "2026-04-15T17:00:00Z",
  "bid_template_id": "uuid",  // required — PM selected template
  "project_document_ids": ["uuid", "uuid"],  // project docs to include
  "vendor_selections": [
    {
      "vendor_id": "uuid",
      "vendor_contact_id": "uuid"  // which contact to invite
    }
  ]
}
```

**Orchestration flow (inside a single FastAPI endpoint):**

1. **Validate inputs:**
   - Task exists, not deleted, `bid_type != 'internal'` (return 400)
   - Task status is `draft` or valid for bidding (not `completed`, `cancelled`)
   - Bid template exists (return 404 if not)
   - All project documents exist and belong to the task's project (return 400 if not)
   - All vendors exist, are active, not deleted (return 400 with specific vendor failures)
   - All vendor contacts exist and belong to the specified vendor (return 400)
   - Deadline is in the future (return 400)

2. **Create `bid_packages` row:**
   - `task_id`, `deadline`, `bid_template_id`, `created_by` (from JWT)
   - `round_number` auto-set by trigger
   - `status = 'open'`

3. **Create `bid_package_documents` rows:**
   - One row per selected project document

4. **For each vendor in `vendor_selections`:**
   a. Create `bid_invitations` row: `bid_package_id`, `vendor_id`, `vendor_contact_id`, `status = 'sent'`, `sent_at = NOW()`
   b. Generate magic link token:
      - Generate 32-byte secure random token (`secrets.token_urlsafe(32)`)
      - SHA-256 hash the token
      - Store hash in `magic_link_tokens`: `bid_invitation_id`, `vendor_id`, `token_hash`, `expires_at = bid_packages.deadline`, `is_used = FALSE`. Note: expires_at matches the bid deadline, NOT a fixed 24-48h window. Construction vendors may take days to respond — the link must work as long as the bid is open.
   c. Render email from Jinja2 template (Task 4.2) with all context variables
   d. Send email via EmailService (Task 4.3)
   e. Create `email_log` row

5. **Update task status** to `bidding` (if currently `draft`)

6. **Return response:**
```json
{
  "bid_package_id": "uuid",
  "round_number": 1,
  "invitations_sent": 7,
  "invitations_failed": 0,
  "failed_vendors": [],
  "deadline": "2026-04-15T17:00:00Z"
}
```

**Error handling:**
- If bid package creation fails → roll back everything, return 500
- If individual email send fails → still create the invitation and magic link (email can be resent). Mark invitation `status = 'sent'` but `email_log.status = 'failed'`. Include in `failed_vendors` response.
- Partial failure is acceptable: 6/7 emails sent = success with warning, not failure

**Magic link URL format:** `{PORTAL_BASE_URL}/bid/{raw_token}`
- `PORTAL_BASE_URL` from env var (e.g., `https://portal.bluonx.com`)
- The raw token is included in the URL and emailed. Only the hash is stored in DB.

**Rate limiting for email sends:**
- Process vendor emails sequentially with a small delay (100ms) to stay within SES limits
- For large batches (20+ vendors), consider async background processing (but MVP likely never exceeds 10–15 per task)

**Additional endpoint:**

**`POST /v1/bid-invitations/{invitation_id}/resend`** — Resend invitation email to a specific vendor.
- Generates a NEW magic link token (invalidates old tokens for this invitation by setting `is_used = TRUE` on previous tokens)
- Renders and sends email
- Logs in `email_log`
- Updates `bid_invitations.sent_at`

---

### Task 4.5: Implement Invitation Tracking (6h)

**Context:** After invitations are sent, PMs need real-time visibility into which vendors have opened, submitted, declined, or not responded. This task builds the backend tracking and query capabilities consumed by the dashboard (Task 4.6 and Phase 6).

**Backend endpoints:**

1. **`GET /v1/bid-packages/{bid_package_id}`** — Get bid package details with invitation summary.

Response:
```json
{
  "id": "uuid",
  "task_id": "uuid",
  "task_name": "Excavation & Grading",
  "round_number": 1,
  "deadline": "2026-04-15T17:00:00Z",
  "status": "open",
  "bid_template": {
    "id": "uuid",
    "name": "Excavation Standard",
    "is_lump_sum": false
  },
  "documents": [
    { "id": "uuid", "file_name": "Site Plans.pdf" }
  ],
  "invitation_summary": {
    "total": 7,
    "sent": 2,
    "opened": 1,
    "submitted": 3,
    "declined": 0,
    "expired": 0,
    "no_response": 1
  },
  "invitations": [
    {
      "id": "uuid",
      "vendor_id": "uuid",
      "vendor_company_name": "ABC Excavation",
      "vendor_contact_name": "John Smith",
      "vendor_contact_email": "john@abc.fake",
      "status": "submitted",
      "sent_at": "2026-04-01T10:00:00Z",
      "opened_at": "2026-04-01T14:30:00Z",
      "responded_at": "2026-04-03T09:15:00Z"
    }
  ]
}
```

2. **`GET /v1/bid-packages/{bid_package_id}/invitations`** — List all invitations for a bid package with vendor details. Supports filtering by status.

3. **`PUT /v1/bid-invitations/{invitation_id}/status`** — Manually update invitation status. Body: `{ "status": "declined" | "expired" | "no_response" }`. Used by PM to mark vendors who declined via phone/email outside the system.

**Invitation status lifecycle:**
```
sent → opened → submitted (via bid portal in Phase 5)
sent → declined (vendor declines via portal or PM marks manually)
sent → expired (after deadline passes — can be batch-updated)
sent → no_response (PM marks after deadline)
```

**Deadline expiration logic:**
- Build a utility function: `expire_overdue_invitations(bid_package_id)` that sets any `sent` or `opened` invitations to `expired` when the bid package deadline has passed.
- This can be called: (a) when PM views the bid package (lazy evaluation), or (b) via a scheduled job (Phase 7 n8n workflow). For Phase 4, implement the lazy approach.
- Also update `bid_packages.status` from `open` to `closed` when deadline passes.

**Email log queries:**
- `GET /v1/bid-packages/{bid_package_id}/email-log` — All emails sent for this bid package (invitations + reminders). Join `email_log` via `reference_type = 'bid_invitations'` and `reference_id`.

---

### Task 4.6: Build Vendor Selection UI (12h)

**Context:** This is the PM-facing interface for the entire bid invitation flow. The PM navigates to a task, initiates bidding, reviews the auto-filtered vendor list, selects a template, attaches documents, and sends invitations. This task also includes the bid package detail view showing invitation statuses.

**Frontend pages and components:**

#### 1. "Start Bidding" Entry Point (on Task Detail Page)

- Add a "Start Bidding" button on the Task Detail Page (from Task 3.3)
- Button visible only when: `task.bid_type = 'competitive'` AND `task.status = 'draft'`
- For tasks with existing bid packages: show "View Bid Package" or "Start New Round" instead
- Clicking "Start Bidding" navigates to the bid package creation wizard

#### 2. Bid Package Creation Wizard (`/projects/{id}/tasks/{id}/create-bid-package`)

Multi-step flow (wizard or single scrollable page with sections):

**Step 1 — Configure Bid Package:**
- Bid deadline: date/time picker (must be in future, suggest 7–14 days from now)
- Bid template selection:
  - Dropdown showing all bid templates
  - Auto-suggest: templates where `trade_id` matches the task's `trade_id` appear first, marked with a ⭐ or "Recommended" badge
  - General-purpose templates (`trade_id = NULL`) listed separately under "General Templates"
  - All other templates available under "Other Templates"
  - Selected template shows a preview (name, lump sum vs structured, item count)
- Project documents to include:
  - Checklist of all project documents (from `project_documents` for this project)
  - Pre-check all by default, PM can uncheck specific ones
  - Show file name, type, size for each

**Step 2 — Select Vendors:**
- On entering this step, auto-call `GET /v1/tasks/{task_id}/qualified-vendors` (Task 4.1)
- Show loading spinner while filtering runs
- Display results in two sections:

  **Qualified Vendors table:**
  - Columns: Checkbox (select/deselect), Company Name, Primary Contact, Email, Distance (mi), Insurance Expiry, Capacity ({current}/{max}), Flags
  - All vendors pre-checked by default
  - Flag column: warning icon with tooltip showing flag reasons (e.g., "⚠ missed_deadline")
  - Sort by: distance (default), company name, capacity
  - "Select All" / "Deselect All" toggle
  - Each row: click to expand for more vendor details (contacts list, choose which contact to invite)
  - Default contact selection: `is_primary = true` contact, PM can change

  **Disqualified Vendors section (collapsible):**
  - Collapsed by default, expandable with "Show {n} disqualified vendors"
  - Same table format but with a "Reasons" column showing disqualification reasons (chips/badges)
  - PM can manually check a disqualified vendor to include them (override) — shows confirmation warning

**Step 3 — Review & Send:**
- Summary of: deadline, template, documents count, selected vendors count
- List of selected vendors with contact emails
- "Send Invitations" button with confirmation dialog: "Send bid invitations to {n} vendors for {task_name}? This will email each vendor a unique bid portal link."
- On confirm: calls `POST /v1/tasks/{task_id}/bid-packages` (Task 4.4)
- Show progress/loading during send
- On success: navigate to bid package detail page. Show toast: "{n} invitations sent successfully"
- On partial failure: show warning with list of failed sends, option to resend

#### 3. Bid Package Detail Page (`/projects/{id}/tasks/{id}/bid-packages/{id}`)

- **Header:** Task name, bid round number, deadline (with countdown), status badge (open/closed/evaluating/cancelled)
- **Summary cards:** Total Invited | Submitted | Pending | Declined/Expired
- **Invitations table:**
  - Columns: Vendor Name, Contact, Email, Status (badge), Sent At, Opened At, Responded At, Actions
  - Status badges: color-coded (blue=sent, yellow=opened, green=submitted, red=declined, gray=expired/no_response)
  - Actions: "Resend" button (calls resend endpoint), "View Bid" (if submitted — links to Phase 6/8), "Mark Declined" / "Mark No Response"
- **Documents section:** List of attached project documents
- **Email log section (collapsible):** Shows all emails sent for this bid package with status (sent/delivered/bounced/failed)
- **Actions:**
  - "Cancel Bid Package" button (sets status to `cancelled`, marks all pending invitations as `expired`)
  - "Close Bidding" button (available when deadline passed, sets status to `closed`)

#### 4. Bid Packages List (within Task Detail Page)

- On the Task Detail Page, show a section listing all bid packages for this task
- Columns: Round #, Deadline, Status, Submitted Count / Total, Created Date
- Click row → navigates to Bid Package Detail Page

**Navigation updates:**
- Task Detail Page: add "Bid Packages" section and "Start Bidding" button
- Sidebar: no new top-level nav needed (bid packages are accessed through tasks)

**Follows existing patterns:**
- Use existing table, card, badge, modal, toast components from Task 2.5
- React Query hooks with cache invalidation on mutations
- Loading skeletons during data fetch
- Responsive design: wizard steps stack vertically on mobile, tables become cards

---

## Phase 4 Acceptance Criteria

- [ ] System accurately filters vendors by all criteria: trade match, distance (≤75mi), insurance validity, bonding capacity, job capacity, onboarding status
- [ ] Disqualified vendors shown separately with clear reasons
- [ ] PM can override and include disqualified vendors manually
- [ ] Vendor flags displayed as warnings during selection (not auto-excluding)
- [ ] Bid template selection works with auto-suggestion for trade-affiliated templates
- [ ] Professional HTML bid invitation email renders correctly across major email clients
- [ ] Unique magic link token generated per vendor, SHA-256 hashed, stored securely
- [ ] Magic link URL embedded in email correctly points to portal (even if portal not built yet)
- [ ] AWS SES integration sends emails successfully (or mock mode logs correctly)
- [ ] SNS bounce/delivery webhook updates email_log status
- [ ] Batch invitation sending handles partial failures gracefully
- [ ] Bid package creation is atomic: all-or-nothing for the package/documents/invitations
- [ ] Invitation status tracked and displayed on bid package detail page
- [ ] PM can resend invitation to individual vendors
- [ ] PM can manually update invitation status (declined, no response)
- [ ] Deadline expiration logic marks overdue invitations correctly
- [ ] Email log shows full audit trail of all emails sent per bid package
- [ ] Reminder email templates created (friendly, urgent, final call)
- [ ] All forms validate inputs (future deadline, valid vendor selections, template required)
- [ ] Task status updates to `bidding` after first bid package created

---

## Next Phase Preview

**Phase 5: Bid Collection — Custom Secure Forms (60h)** — builds directly on Phase 4:
- Custom React bid portal with magic link authentication
- Magic link token validation (consumes tokens generated in Task 4.4)
- Multi-step bid submission form (company info → pricing → documents → review)
- Bid template pre-population (structured line items from the template selected in Task 4.6)
- Draft save functionality (auto-save every 2 min)
- File upload for bid attachments (signed SOW, updated W-9)
- Submission confirmation with PDF receipt
- Creates `bid_submissions`, `bid_line_items`, `bid_attachments`

**Phase 6: Real-Time Dashboard (60h)** — Real-time submission tracking via Supabase Realtime/WebSocket, charts, live status updates.

**Phase 7: Reminder & Alert System (44h)** — n8n workflows for bid reminders (T-7, T-3, T-0) using templates from Task 4.2, document expiration monitoring.

---

## References

- Full project plan: `docs/PROJECT_PLAN.pdf` (v2.1, 12 phases, ~718h)
- Database schema: `database/bluonx_complete_schema_v2_2.sql`
- RLS policies: `database/rls_policies.sql`
- Storage policies: `database/storage_rls_policies.sql`
- Handoff document: `docs/BluOnX_Context_Handoff.md` (v3.x)
- Deferred tasks: `docs/DEFERRED.md`
