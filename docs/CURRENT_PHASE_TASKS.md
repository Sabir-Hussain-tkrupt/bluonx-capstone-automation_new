# Current Phase Tasks — BluOnX Development Operations Platform

**Last Updated:** April 15, 2026

---

## Phase 1: Foundation & Database (60h) — ✅ COMPLETE
## Phase 2: Frontend Foundation, Backend API & Auth (100h) — ✅ COMPLETE
## Phase 3: Core Entity Management (76h) — ✅ COMPLETE
## Phase 4: Bid Invitation System (50h) — ✅ COMPLETE

**Deferred from Phase 1 (see `docs/DEFERRED.md`):**
- Task 1.8 — Dev/staging environment separation
- Task 1.9 — AWS infrastructure setup (pending client credentials)

---

## Phase 5: Bid Collection — Custom Secure Forms (60h) — 🔄 IN PROGRESS

**Goal:** Build the vendor-facing bid submission portal. Vendors click a magic link from their invitation email (Phase 4), authenticate via token → JWT, and submit their bid through a multi-step form. Form structure comes from the bid template selected during bid package creation. Vendors can save drafts, upload documents, and receive a submission confirmation with PDF receipt.

**Tables written:** `bid_submissions`, `bid_line_items`, `bid_attachments`, `magic_link_tokens` (update `is_used`/`used_at`), `bid_invitations` (status sync via existing trigger)

**Tables read:** `bid_packages`, `bid_package_documents`, `bid_invitations`, `magic_link_tokens`, `bid_templates`, `bid_template_items`, `vendors`, `vendor_contacts`, `projects`, `project_documents`, `tasks`, `trades`

### Key Domain Rules for Phase 5

- **Vendors NEVER access Supabase directly.** All vendor interactions go through FastAPI exclusively. The portal does NOT use the Supabase JS client. RLS has no anon policies.
- **Magic link auth flow:** Vendor clicks URL → FastAPI validates token hash → issues short-lived vendor JWT (2–4 hours) → vendor uses JWT for all portal API calls. If JWT expires, vendor clicks magic link again and resumes from draft.
- **Token lifecycle (from Phase 4):** Raw token in URL, SHA-256 hash stored in `magic_link_tokens`. `expires_at` matches `bid_packages.deadline` (NOT fixed 24-48h). `is_used` tracks first click but token remains valid for re-entry until deadline passes or bid package cancelled.
- **One submission per invitation:** `bid_submissions.bid_invitation_id` has UNIQUE constraint.
- **Draft auto-save:** Submissions start as drafts (`is_draft = TRUE`). Auto-save every 2 min. On final submit: `is_draft = FALSE`, `status = 'submitted'`, `submitted_at = NOW()`. Trigger `fn_sync_bid_invitation_on_submission` auto-updates invitation status.
- **Template determines form:** `is_lump_sum = TRUE` → single total field. `is_lump_sum = FALSE` → pre-populated line items from `bid_template_items`.
- **File uploads:** `bid-attachments` bucket, path `{bid_submission_id}/{filename}`. FastAPI service_role. PDF/JPEG/PNG, max 10MB.
- **Denormalized consistency:** `bid_submissions.vendor_id` enforced by trigger — must match `bid_invitations.vendor_id`. API resolves from invitation, never trusts client.
- **No Supabase Auth for vendors.** Vendor JWT is custom (PyJWT), NOT Supabase JWT. Contains: `vendor_id`, `bid_invitation_id`, `bid_package_id`, `vendor_contact_id`, `task_id`, `exp`. Signed with `VENDOR_JWT_SECRET` (separate from Supabase secret).
- **Synthetic submissions** (`is_direct_assign = TRUE`) are Phase 9. Phase 5 only handles competitive bids.

---

### Task 5.1: Design Custom Bid Submission UI (12h) — ✅ COMPLETE

**This is a SEPARATE route tree and layout from the admin dashboard.** Same React+Vite project but different layout (no sidebar), different auth (vendor JWT, not Supabase Auth). Vendors may fill this on a phone from a job site — mobile-first.

**Portal layout:** Clean header (BluOnX logo + project name + vendor name), progress stepper, footer ("Powered by BluOnX"). No sidebar. Mobile-first 320px+.

**Multi-step form — 4 steps:**

**Step 1 — Info & Docs:** Pre-filled read-only vendor fields (company, contact name/email/phone). Read-only project context panel (project name, location, task name/description, deadline countdown, and **PM-supplied bid instructions** if present — sourced from `bid_packages.instructions`, optional, displayed in a callout box only when non-empty). **Project Documents card** — read-only list of project docs attached to this bid package, with download links (signed URLs from FastAPI). Documents are placed here intentionally so vendors can review plans/specs/drawings BEFORE deciding to bid and BEFORE entering pricing.

**Step 2 — Pricing:**
- Lump sum: single "Total Bid Amount" currency input → `bid_submissions.total_amount`
- Structured: table from `bid_template_items` — Description (read-only), Type badge, UoM (read-only), Qty input (unit_price only), Unit Price input (unit_price only), Lump Sum Amount input (lump_sum only), auto-calculated Line Total. Grand total at bottom → `bid_submissions.total_amount`. All amounts required, ≥ 0, total > 0.
- The bid template is selected by the PM during bid package creation (Phase 4 — Task 4.4). The template ID is stored in `bid_packages.bid_template_id`. Template items (`bid_template_items`) are used ONLY to populate the form structure. The actual vendor input is stored in `bid_submissions` + `bid_line_items` (description, item_type, unit_of_measure, sort_order are copied from the template into `bid_line_items` to decouple submissions from future template edits).

**Step 3 — Notes & Uploads:** Editable `vendor_notes` textarea (max 2000 chars) — labeled "Notes to Owner". Vendor upload section (drag-and-drop, multiple files, PDF/JPEG/PNG, ≤10MB, immediate upload, progress bar, delete). Notes and uploads are grouped together since both are vendor-supplied additions to their bid.

**Step 4 — Review & Submit:** Full summary with "Edit" links per section (Info, Pricing, Notes & Attachments). "Save Draft" + "Submit Bid" buttons. Confirmation dialog on submit (centered vertically on mobile via shared `Modal` `mobileCenter` prop, NOT bottom-sheet). On success → confirmation page.

**Progress stepper:** 4 steps labeled "Info & Docs / Pricing / Notes & Uploads / Review". Clickable completed steps, no skip ahead. Horizontal desktop, compact mobile.

**Draft indicator:** "Last saved at {time}", "Unsaved changes" when dirty, amber draft badge.

**Auto-save:** `useAutoSave` hook — 2-min interval, saves if dirty, updates lastSavedAt. Also saves on page blur.

**State management:** useReducer for form state across steps. On load: if draft exists in bid_context, pre-populate. Validate current step before allowing next.

**Suggested file structure:**
```
frontend/src/features/vendor-portal/
├── components/       # PortalLayout, ProgressStepper, each Step component, LineItemsTable, DraftIndicator, BidDeadlineCountdown, ConfirmSubmitDialog
├── hooks/            # useBidSubmission, useBidContext, useAutoSave
├── pages/            # MagicLinkLandingPage, BidFormPage, SubmissionConfirmation, error pages
├── services/         # portalApi.ts (Axios instance with vendor JWT)
└── types/            # portal.ts
```

**Vendor JWT handling:** Stored in React state/context. Axios interceptor adds Bearer header. On 401 → redirect to session expired page.

**Implementation status:** Frontend shell is complete with mock data (Summit Earthworks vendor, Phoenix Logistics Park project). All 4 steps render correctly across mobile/tablet/desktop. Real backend wiring happens in Tasks 5.2–5.5. The shared `Modal` component now supports a `mobileCenter` prop for centered mobile dialogs.

---

### Task 5.2: Build Magic Link Authentication System (12h)

**Frontend — Landing Page (`/bid/{token}`):** Show spinner, call validate endpoint, on success store JWT + redirect to form. Handle error states: 410 expired, 404 invalid, 409 already submitted, 423 bid closed.

**Backend — `POST /v1/vendor-auth/validate-token`:**
1. SHA-256 hash the raw token from request body
2. Look up in `magic_link_tokens` → 404 if not found
3. Check `expires_at > NOW()` → 410 if expired
4. Check `bid_packages.status = 'open'` → 423 if cancelled/closed
5. Check if `bid_submission` with `status = 'submitted'` exists for this invitation → 409
6. If `is_used = FALSE`: set `TRUE`, record `used_at`, `ip_address`
7. Issue vendor JWT (HS256, `VENDOR_JWT_SECRET`, 4h expiry) with `vendor_id`, `vendor_contact_id`, `bid_invitation_id`, `bid_package_id`, `task_id`, `type: "vendor_portal"`
8. Return JWT + full `bid_context`: vendor info, project/task info, **`bid_packages.instructions`** (PM-supplied bid guidance, optional), bid template with items, project documents list, existing draft (if any) — everything the form needs in ONE call

**Backend — Vendor JWT middleware (`get_vendor_context`):** FastAPI dependency for all `/v1/vendor-portal/*` endpoints. Extracts Bearer token, validates signature + expiration, returns `VendorContext` dataclass. Separate from admin JWT middleware.

**Rate limiting:** 10 req/IP/min on token validation. IP logged in `magic_link_tokens`.

---

### Task 5.3: Implement Form Backend API (8h)

**Base path:** `/v1/vendor-portal` — all endpoints use vendor JWT middleware.

1. **`GET /v1/vendor-portal/bid-context`** — Re-fetch bid context (same shape as token validation response).

2. **`POST /v1/vendor-portal/submissions`** — Create draft. Resolve `vendor_id` from JWT (never from body). Check bid package open + deadline. 409 if submission already exists. Create `bid_submissions` (`is_draft=TRUE`) + `bid_line_items`.

3. **`PUT /v1/vendor-portal/submissions/{id}`** — Update draft. Validate belongs to vendor, `is_draft=TRUE`, deadline not passed. Update fields. Replace all line items (delete + re-insert).

4. **`POST /v1/vendor-portal/submissions/{id}/submit`** — Finalize. Run validation (Task 5.4). Set `is_draft=FALSE`, `status='submitted'`, `submitted_at=NOW()`. Send confirmation email + generate PDF. Return confirmation.

5. **`GET /v1/vendor-portal/submissions/{id}`** — Get submission details.

6. **`GET /v1/vendor-portal/documents/{project_document_id}/download`** — Signed URL for project doc. Validate doc is part of this bid package.

**Error patterns:** 401 invalid JWT, 409 conflict, 422 validation, 423 deadline passed/closed.

---

### Task 5.4: Build Form Validation Logic (6h)

**Client-side (React Hook Form):** Per-step validation. Step 2 (Pricing): all pricing fields required, ≥ 0, total > 0. Step 3 (Notes & Uploads): notes ≤ 2000 chars, file type/size on drop. Step 4: re-validate all before submit.

**Server-side (submit endpoint):** Total > 0, all line items valid, item count matches template, line totals correctly calculated, grand total = sum of lines, notes ≤ 2000, bid package open + deadline not passed. Return 422 with field-level error array on failure.

**Template pre-population:** Description, item_type, unit_of_measure, sort_order copied from template INTO `bid_line_items`. Decouples submission from future template edits.

---

### Task 5.5: Implement File Upload for Vendors (6h)

**`POST /v1/vendor-portal/submissions/{id}/attachments`** — Upload. Vendor JWT auth. Validate draft state, MIME (PDF/JPEG/PNG), size ≤ 10MB. Upload to `bid-attachments` bucket: `{bid_submission_id}/{filename}`. Create `bid_attachments` row.

**`DELETE /v1/vendor-portal/submissions/{id}/attachments/{attachment_id}`** — Remove. Validate draft. Delete from storage + DB.

**`GET /v1/vendor-portal/submissions/{id}/attachments`** — List.

Sanitize filenames, handle collisions with suffix.

---

### Task 5.6: Build Draft Save Functionality (6h)

**Auto-save (frontend):** `useAutoSave` hook — 2-min interval, saves if dirty. Save on page blur. Retry on failure.

**Draft flow:** First save → POST creates draft → subsequent saves → PUT updates. Returning vendor: `existing_draft` in bid_context pre-populates form, all saves use PUT.

**Deadline during session:** Next save gets 423 → modal "Deadline passed." Disable submit.

**Race condition:** Concurrent POST returns 409 with existing draft ID → switch to PUT.

---

### Task 5.7: Create Submission Confirmation Flow (6h)

**Confirmation page:** Success message, summary (vendor company, project name, task name, total bid amount, submission timestamp), email notice. No confirmation number — `bid_submissions.id` is sufficient as a unique reference. No PDF receipt — confirmation email serves as the receipt.

**Confirmation email:** Jinja2 template — greeting ("Your bid for {task_name} on {project_name} has been received"), submission summary (total amount, submission timestamp, documents uploaded count), general next steps ("You will be notified of the award decision" — no deadline mention). Send via EmailService, log in `email_log`.

---

### Task 5.8: Implement Vendor Portal Routing (4h)

**Routes:**
```
/bid/:token              → MagicLinkLandingPage (validate + redirect)
/bid/form                → BidFormPage (requires vendor JWT)
/bid/submitted/:id       → SubmissionConfirmation
/bid/expired             → TokenExpiredPage
/bid/invalid             → InvalidTokenPage
/bid/closed              → BiddingClosedPage
/bid/already-submitted   → AlreadySubmittedPage
```

**`VendorPortalGuard`:** Checks vendor JWT in context → redirects to `/bid/expired` if missing. Wraps `/bid/form` and `/bid/submitted/*`.

Portal routes use `PortalLayout`, admin routes use existing dashboard layout. Both coexist, differentiated by route prefix. Portal routes are PUBLIC (no Supabase auth).

---

## Phase 5 Acceptance Criteria

- [ ] Magic link validates token, issues vendor JWT, handles expired/invalid/submitted/closed
- [ ] Re-entry works: vendor clicks magic link again after JWT expiry, resumes from draft
- [ ] Vendor JWT separate from Supabase JWT, dedicated secret, rate-limited
- [ ] Multi-step form works on mobile 320px+, tablet, desktop
- [ ] Step 2 renders lump sum OR structured line items from bid template
- [ ] Line totals and grand total auto-calculate
- [ ] File uploads validate type/size, upload immediately, show progress
- [ ] Auto-save every 2 min, manual save, draft indicator
- [ ] Returning vendor resumes from draft
- [ ] Submit requires confirmation, submitted bid locked (409 on updates)
- [ ] Invitation status auto-updated via trigger
- [ ] Confirmation page + email + PDF receipt
- [ ] Portal layout professional, distinct from admin
- [ ] All vendor calls through FastAPI, zero direct Supabase
- [ ] Server-side validation on submit, consistency trigger passes
- [ ] Deadline expiration during session gracefully handled

---

## Next Phase Preview

**Phase 6: Real-Time Dashboard (60h)** — Supabase Realtime, live bid status, charts, completeness checker.
**Phase 7: Reminder & Alert System (44h)** — n8n bid reminders (T-7/T-3/T-0), doc expiration monitoring.
**Phase 8: Bid Comparison & Scoring (40h)** — Normalization, weighted scoring, comparison UI.

---

## References

- Full project plan: `docs/PROJECT_PLAN.pdf` (v2.1, 12 phases, ~718h)
- Database schema: `database/bluonx_complete_schema_v2_2.sql`
- Handoff document: `docs/BluOnX_Context_Handoff.md`
- Deferred tasks: `docs/DEFERRED.md`
