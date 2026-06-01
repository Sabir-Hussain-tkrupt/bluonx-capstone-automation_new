# Per-Vendor Bid Revision

* Document Owner: Awais Anwer (Tkrupt)
* Status: Implemented and merged to main
* Delivered Effort: ~80 hours

---

# I. Overview & Summary

This feature lets a Project Manager ask a single vendor to revise their submitted bid after the bidding round has closed, without disturbing the rest of the package. The PM sends a personalized note and a per-vendor revision deadline; the vendor receives a magic-link email and either submits a revised bid (preserved as a new submission row that supersedes the original) or declines with an optional short reason. The original bid is kept as immutable audit history regardless of outcome.

Other vendors in the same package are completely unaffected — they never know a revision request was sent. The feature is PM-initiated only, capped at 2 revision attempts per vendor per package, blocked once an award is in place, and time-bound by a PM-supplied deadline that can outlive the original bid package deadline.

**Key Objectives:**

* Recover negotiating leverage on a single vendor without rebidding the entire package
* Preserve a complete audit trail: every version of every bid is retained as an immutable record
* Keep the vendor experience simple — one click to open the portal, no portal account needed
* Prevent silent data loss or race conditions during draft, supersession, and finalize transitions
* Enforce business rules (cap, post-award guard, deadline) at the database level where possible
* Match existing system conventions for email, JWT auth, and SPA routing

---

# II. Tools & Technology Stack

The feature was built entirely within the existing BluOnX stack. No new infrastructure was added.

| Component | Used For |
| --- | --- |
| PostgreSQL via Supabase | New table, supersession columns, triggers, partial unique indexes |
| FastAPI + Python | 4 new endpoints, modified finalize and award paths, scheduled job |
| React 18 + Vite + TypeScript + TailwindCSS v4 | PM dashboard UI, vendor portal revision flow |
| Supabase Auth (PM JWT) | PM-side endpoint authentication |
| Custom HS256 JWT (vendor) | Vendor portal session, extended with revision claim |
| AWS SES | Two new transactional email templates |
| APScheduler (AsyncIOScheduler) | In-process hourly auto-expiry job |
| Jinja2 | Server-rendered HTML email templates |
| pytest + Vitest + React Testing Library | Test coverage at every layer |

---

# III. Real-Life Scenario

Sarah, a Project Manager at BluOnX Development, is reviewing bids on the Sunset Hills Phase 2 excavation task. Three vendors have submitted. ABC Excavation's bid is the most competitive overall, but their mobilization line is $2,000 higher than the others. The other elements are sound; she does not want to rebid the whole task or invite a fourth vendor for one line item.

**1. PM Requests a Revision** Sarah opens the bid package detail page, finds ABC Excavation's row, and clicks "Request Revision." A modal opens. She writes a brief note: "Your unit pricing on grading and fill is great. Could you revisit the mobilization line — I think we can sharpen by $1,500 to $2,000?" She sets a revision deadline 3 days out and submits.

**2. The Request is Created** A `bid_revision_requests` row is inserted with status `pending`. A new magic-link token is generated with the revision request id stamped on it. ABC Excavation's contact, John Smith, receives an email titled "Revision Requested: Sunset Hills Phase 2 — Excavation & Grading." The email contains Sarah's note (preserving her line breaks), the revision deadline in human-readable format, and a single CTA: "Open Bid Portal."

The other two vendors hear nothing. Their bids and their dashboard rows are unaffected.

**3. Vendor Opens the Link** John clicks the link on his phone during a break. The magic link validates against the backend, which recognizes the revision token and issues a vendor JWT carrying the revision context. He lands on a revision landing screen showing Sarah's note, the deadline, and two buttons: "Open Bid Form" and "Decline to Revise."

**4. Vendor Submits a Revised Bid** John clicks "Open Bid Form." The form loads pre-populated with his original bid's contents — every line item, his vendor notes, even his previously-uploaded files shown as read-only. He reduces the mobilization line from $7,000 to $5,500 and clicks "Submit Revised Bid." A confirmation page appears: "Revised Bid Submitted. Your revised bid has been received. The project manager has been notified, and your original bid remains in the record."

John receives a confirmation email: "Bid Revision Received: Sunset Hills Phase 2 — Excavation & Grading," showing his revised total of $48,500 and the note that his original is preserved.

**5. Sarah Sees the Update** On the bid package detail page, ABC Excavation's row now shows a "Revised" badge in green. The displayed bid amount is $48,500, not the original. A small chevron icon appears next to the badge. Sarah clicks it, and a version history table expands inline showing Version 1 ($50,500, Original, Superseded) and Version 2 ($48,500, Revised, Current) with a delta of -$2,000 between them. She can click "View Full Bid" on either version to inspect the line items.

The bid amount bar chart at the bottom of the page now shows ABC Excavation's $48,500 as the single bar for that vendor — not two bars.

**6. Sarah Awards the Contract** Sarah is satisfied with the revision. She moves to the award flow. (Note: at the time of this writing, the award flow is a backend stub pending Phase 9 — but the feature already guards against awarding a superseded version. Once Phase 9 ships, an attempted award of the superseded original would return a clear error directing Sarah to the latest version.)

**Alternative outcome — decline:** Had John instead clicked "Decline to Revise" from the revision landing screen, a confirmation dialog would have appeared with an optional reason textarea. John could have typed "Crew capacity full this quarter, no room to sharpen" and confirmed. The revision request would have closed in `declined` status, John's reason stored, his original bid still in play. Sarah would see a "Declined" badge on his row with his reason visible on hover.

**Alternative outcome — expiry:** Had John ignored the email for 3 days, the hourly scheduled job would have transitioned the request from `pending` to `expired`, revoked his magic-link token, and Sarah's dashboard would show an "Expired" badge. His original bid would remain in play.

**Alternative outcome — PM changed mind:** Had Sarah decided not to wait for John, she could have clicked Cancel on the Revision Pending badge before he responded. The request would have transitioned to `cancelled`, the link revoked, and John would never have received any cancellation notification (the spec is intentional: cancelled requests don't bother the vendor).

---

# IV. Architecture Decisions

The original Feature Proposal document described the intended behavior. During implementation, several decisions diverged from that proposal for reasons of simplicity, correctness, or fit with the existing codebase. This section documents the final state.

| Topic | Proposal | Implementation | Reason |
| --- | --- | --- | --- |
| Versioning model | `is_latest_version` boolean flag | `supersedes_submission_id` chain + `is_superseded` flag | Chain model gives a true audit history; flag model loses ordering information |
| Cancel HTTP verb | `DELETE` | `POST /{id}/cancel` | State transition, not deletion; row is preserved as audit history |
| Decline flow | Email click-through returning server-rendered HTML page | SPA-mediated `POST` with vendor JWT, returning JSON | Captures optional decline reason via textarea; one URL pattern in emails; no backend host exposed |
| Email links | Two CTAs: "Open Bid Portal" + "Decline to Revise" | One CTA: "Open Bid Portal" only | Decline happens inside the SPA after the vendor opens the portal |
| Submission endpoint for revisions | Separate `POST /submit-revision` | Existing `POST /submissions/{id}/submit` with JWT-context branch | Same end state; less code; single test path |
| Realtime updates on PM dashboard | Supabase WebSocket subscription | React Query invalidation on mutation + window-focus refresh | Matches existing app patterns; no realtime infrastructure introduced |
| Version history data source | New backend list endpoint | Client-side chain-walk via existing `GET /bid-submissions/{id}` | Cap of 2 revisions = max 2 sequential fetches; lazy per-vendor on expand; no backend scope creep |
| Scheduled expiry job | n8n cron workflow | APScheduler + AsyncIOScheduler inside FastAPI | One service to operate; version-controlled; testable; no n8n license |
| Scoring engine update | Re-score using latest version on revision finalize | Filter to current version on PM read paths only | Phase 8 scoring engine not yet built; the filter will naturally apply when scoring ships |

---

# V. Implementation Phases

## Phase A: Database Schema (12 Hours)

### Task A.1: New table and columns

* New table `bid_revision_requests` with fields for invitation reference, original submission pointer, PM note, deadline, status enum (`pending`, `submitted`, `declined`, `expired`, `cancelled`), decline reason, requested-by user, timestamps
* Added three columns to `bid_submissions`: `supersedes_submission_id` (self-FK), `is_superseded` (boolean), `revision_number` (integer, defaults to 1)
* Added `bid_revision_request_id` column to `magic_link_tokens` (nullable; discriminates initial-bid tokens from revision tokens)

### Task A.2: Triggers

Three new triggers handle atomicity:

* `fn_enforce_supersession_chain` (BEFORE INSERT OR UPDATE on `bid_submissions`): validates that revision drafts form a clean chain — same invitation as predecessor, predecessor not a draft, `revision_number` exactly predecessor + 1
* `fn_flip_superseded_on_revision_finalize` (BEFORE UPDATE OF `is_draft` on `bid_submissions`): when a revision draft finalizes, atomically flips the predecessor's `is_superseded` to TRUE inside the same statement so the partial unique index never conflicts
* `fn_close_revision_request_on_finalize` (AFTER UPDATE on `bid_submissions`): when a revision finalizes, transitions its matching `bid_revision_requests` row from `pending` to `submitted`

Existing `fn_sync_bid_invitation_on_submission` was modified to use `COALESCE(responded_at, NOW())` so that revisions preserve the original submission's `responded_at` timestamp on the invitation rather than overwriting it.

### Task A.3: Partial unique indexes

* `idx_bid_submissions_current_per_invitation` on `(bid_invitation_id) WHERE is_superseded = FALSE AND is_draft = FALSE` — guarantees exactly one current submission per invitation while allowing historical and concurrent-draft rows
* `idx_bid_revision_requests_one_pending_per_invitation` on `(bid_invitation_id) WHERE status = 'pending'` — at most one in-flight request per invitation

### Acceptance Criteria

* Migration applies cleanly in dev, staging, and production
* 10 SQL self-test scenarios pass (insert, supersession, partial unique enforcement, trigger cascading)
* No existing data corrupted; all pre-existing submissions automatically satisfy the new partial unique index

---

## Phase B: Backend API (20 Hours)

### Task B.1: Create revision request endpoint

* `POST /api/v1/bid-revision-requests` with PM authentication
* Validates: invitation exists, current submission exists (`is_superseded = FALSE AND is_draft = FALSE`), no blocking award on the task (status not in `pending_acceptance` or `accepted`), lifetime cap of 2 non-cancelled requests, deadline in the future
* On success: inserts the request, generates a new magic-link token stamped with the revision request id, queues the F.1 email

### Task B.2: Cancel revision request endpoint

* `POST /api/v1/bid-revision-requests/{id}/cancel` with PM authentication
* TOCTOU-safe: guarded UPDATE matches only if status is still `pending`; if zero rows update, returns 409 (race lost to a vendor response or expiry)
* Reuses the existing `magic_link_tokens.revoked_at` mechanism

### Task B.3: List revision requests endpoint

* `GET /api/v1/bid-revision-requests?bid_package_id={uuid}` with PM authentication
* Returns all requests for a package across statuses, sorted newest first; powers the PM dashboard's badge and history rendering

### Task B.4: Validator update for revision tokens

* Modified `POST /api/v1/vendor-auth/validate-token` to branch on the token's `bid_revision_request_id` column
* Revision tokens skip the package-status and "already submitted" checks (correctly — a revision exists precisely because the original was already submitted); instead validate that the revision request is still `pending`
* Returns vendor JWT with `bid_revision_request_id` claim baked in and a `revision_context` block on the response (PM note, deadline, original submission id)

### Task B.5: Vendor decline endpoint

* `POST /api/v1/vendor-portal/revision-requests/{id}/decline` with vendor JWT
* Validates the JWT carries the revision claim AND the claim matches the path id (prevents one vendor from declining another vendor's request)
* Optional `decline_reason` body field (max 500 chars; blank or omitted normalized to NULL)
* Transitions the request to `declined`, revokes the magic link token

### Task B.6: Auto-expiry scheduled job

* APScheduler `AsyncIOScheduler` instance lives in `backend/app/jobs/scheduler.py`, started by FastAPI's lifespan
* `expire_revision_requests` job (`backend/app/jobs/revision_expiry.py`) runs hourly UTC
* Finds pending requests past their deadline, transitions them to `expired`, revokes their tokens
* TOCTOU-guarded: UPDATE matches only if status still `pending` (handles races with vendor responses or PM cancels)
* `/api/v1/admin/scheduler-health` endpoint surfaces last-run state per registered job for external monitoring (UptimeRobot canary)
* Single ECS Fargate task with `desiredCount=1` provides the single-instance guarantee — no leader election, no advisory locks; revisit threshold documented in an ADR

### Acceptance Criteria

* All endpoints have pytest coverage for happy path, validation failures, and auth failures
* TOCTOU races between cancel, expire, and vendor response handled deterministically
* Manual curl testing on staging covers all six scenarios end-to-end

---

## Phase C: Bid Submission Flow Updates (10 Hours)

### Task C.1: Finalize endpoint revision branch

* `POST /api/v1/vendor-portal/submissions/{id}/submit` branches on the JWT's `bid_revision_request_id` claim
* Initial-bid path: existing package-status and package-deadline checks remain bit-identical
* Revision path: skips package checks; instead validates the revision request is still `pending` and its deadline hasn't passed
* UPDATE statement gains `is_draft = TRUE` to the WHERE clause as defense-in-depth against double-submits; zero rows updated returns 409

### Task C.2: Revision prefill endpoint

* `GET /api/v1/vendor-portal/submissions/{original_submission_id}/revision-prefill` with vendor JWT
* Three ordered guards: JWT must carry revision claim, submission id must match the revision request's `original_submission_id`, requesting vendor must own the submission
* Returns the original submission's line items, vendor notes, total, and attachment ids in the same shape the bid form consumes for initial-bid drafts

### Task C.3: Draft creation revision-awareness

* The existing `POST /api/v1/vendor-portal/submissions` endpoint (create draft) was made revision-aware
* For initial-bid JWTs: existing 409 "Bid already submitted" behavior preserved
* For revision JWTs: creates a new draft row with `supersedes_submission_id` set, `revision_number` calculated as predecessor + 1; idempotent (existing revision draft is resumed if found)

### Task C.4: PM-facing read-path audit

* Audited every read path that surfaces submission data to PMs
* Filtered list/aggregation paths (`_fetch_submitted_bids` for the bar chart; embedded submissions on the invitation list) to `is_superseded = FALSE AND is_draft = FALSE`
* Deliberately did NOT filter the by-id detail endpoint — superseded submissions remain inspectable as audit history
* Detail endpoint response was extended to include `is_superseded`, `revision_number`, `supersedes_submission_id`, and `is_draft` so the SPA can render "Historical version" indicators

### Task C.5: Award guard

* `POST /api/v1/awards` (currently a 501 stub pending Phase 9) gained an early-fail guard: if the chosen submission has `is_superseded = TRUE`, returns 409 with a clear error directing the PM to the latest version
* Defense-in-depth: the existing `fn_enforce_award_consistency` trigger would catch this at the database level, but the API-layer guard provides a friendly message

### Acceptance Criteria

* End-to-end revision finalize verified on staging: predecessor flips superseded, invitation `responded_at` preserved, revision request auto-closes, exactly one current submission per invitation
* Initial-bid finalize regression test passes — no behavioral change
* PM dashboard shows current version per vendor in all aggregation views; superseded versions only appear in the inline version history expander

---

## Phase D: PM Frontend (14 Hours)

### Task D.1: Request Revision action

* "Request Revision" button appears on each invitation row in the bid package detail page
* Visibility rules: current submitted bid must exist, no pending revision request, no blocking award on the task, vendor under the 2-revision cap (last is cosmetic; backend is source of truth)
* Modal opens with PM note textarea (max 2000 chars), date/time picker for the deadline, required validation before submission
* React Query invalidation on success; optimistic badge transition to "Revision Pending"

### Task D.2: Status badges

* Four states rendered on invitation rows based on the most recent non-cancelled revision request:
  * `pending` → "Revision Pending" (amber)
  * `submitted` → "Revised" (green)
  * `declined` → "Declined" (grey, hover reveals decline reason)
  * `expired` → "Expired" (grey)
* Cancelled requests show no badge (treated as if no request exists)
* Data source: `GET /api/v1/bid-revision-requests?bid_package_id=X`, fetched once per package detail view, merged with the per-row submission data already on the page
* Refresh strategy: React Query invalidation on mutation plus window-focus refresh; no WebSocket subscriptions

### Task D.3: Version history expander

* A chevron icon appears next to vendor rows that have any revision history (revision number > 1 on current submission OR at least one terminal-state revision request)
* Click expands inline (not a modal) to show a table: Version, Submitted At, Total, State (two indicators: Original/Revised + Current/Superseded), Delta vs. prior version, View Full Bid link
* Data source: client-side chain-walk starting from the invitation's current submission, walking `supersedes_submission_id` backward via `GET /api/v1/bid-submissions/{id}` (max 2 hops given the cap); React Query caches each response
* PM note from the relevant revision request rendered below the version table

### Task D.4: Cancel revision action

* Cancel button visible on rows with "Revision Pending" status (any PM or admin, no creator-only gate — backend matches)
* Confirmation dialog: "Cancel this revision request? [Vendor] will not be notified. Their original bid remains in play."
* Calls `POST /api/v1/bid-revision-requests/{id}/cancel`; on success the badge clears and React Query invalidation refetches

### Acceptance Criteria

* Smoke tests cover each new component renders without crashing, the cancel button calls the right endpoint, the request modal validates required fields
* Manual QA on the dev server covers the full PM journey across all four scenarios

---

## Phase E: Vendor Portal Frontend (14 Hours)

### Task E.1: Revision landing page

* New route `/bid/revision` rendered when a vendor opens the portal via a revision magic link
* Shows the PM's note (whitespace preserved), the revision deadline (live countdown if within 24h, relative date otherwise), and two CTAs: "Open Bid Form" and "Decline to Revise"
* Route lives inside the existing vendor portal guard so browser refresh re-hydrates the page from the session

### Task E.2: Revision form mode

* The existing bid form component was extended with a `revision` mode (gated on `bid_context.revision_context` being present); initial-bid behavior remains bit-identical
* Form pre-populates from the `revision-prefill` endpoint
* A banner at the top of the form shows the PM's note and a reminder that the original is preserved
* The countdown widget in the form now reflects the revision deadline (not the bid package deadline) in revision mode
* Step 3 (Documents) shows a read-only "Previously uploaded (original bid)" list above the new-upload area
* Step 4 (Review) finalize button reads "Submit Revised Bid"
* On submit success: navigates to a revision-specific confirmation page

### Task E.3: Decline flow inside the SPA

* "Decline to Revise" button on the landing opens a confirmation dialog with an optional reason textarea (500-char counter)
* On confirm: calls `POST /api/v1/vendor-portal/revision-requests/{id}/decline`, navigates to `/bid/revision-declined` confirmation page
* JWT expired during decline (rare — 4h JWT life vs. typically much shorter revision windows): shows inline message asking the vendor to click the email link again
* 410 response (request no longer pending): navigates to the revision-inactive error page

### Task E.4: Confirmation and error pages

* `/bid/revision-declined`: terminal page shown after a successful decline
* `/bid/revision-unavailable`: shown when the revision request is no longer pending (cancelled by PM, expired by cron, or already responded to)

### Acceptance Criteria

* Smoke tests cover landing rendering, form prefill, confirmation pages, error pages
* Manual QA on staging covers: open link → revision landing → form → submit → confirmation; open link → decline → confirmation; cancel mid-flow → revision-inactive page

---

## Phase F: Transactional Emails (4 Hours)

### Task F.1: Revision request email to vendor

* New template `bid_revision_request.html` (+ `.txt` partner) under `backend/app/templates/emails/`
* Subject: "Revision Requested: {project_name} — {task_name}"
* Contains: greeting, lead sentence identifying the project/task, PM note block (whitespace preserved), revision deadline (bold, prominent), single "Open Bid Portal" CTA button (MSO-VML + fallback per existing template pattern)
* Wired via a new `send_revision_request_email` async helper in `bid_revision_service.py`, dispatched best-effort from the create endpoint

### Task F.2: Revision confirmation email to vendor

* New template `bid_revision_submitted.html` (+ `.txt` partner)
* Subject: "Bid Revision Received: {task_name} — {project_name}"
* Contains: greeting, confirmation lead, summary card (company, project, scope, revised total, submitted-at), closing note that the original is preserved
* No CTA; receipt only
* Wired via a new `send_revision_submitted_email` async helper in `vendor_portal_service.py`; the existing finalize endpoint branches on the JWT's revision claim to choose between this template and the initial-bid confirmation template (never both)

### Acceptance Criteria

* Both templates render correctly across Gmail, Outlook, and Apple Mail
* Pytest asserts every template variable interpolates correctly and no `{{ }}` placeholders remain
* Initial-bid confirmation email path remains bit-identical (regression-locked by a pytest assertion)

---

## Phase G: End-to-End Verification (4 Hours)

After all phases merged, six manual scenarios were walked end-to-end on staging:

1. **Happy path** — PM requests revision, vendor receives email, vendor revises, PM dashboard updates, PM attempts to award the superseded version (blocked with 409)
2. **Decline with reason** — vendor declines with a typed reason, original bid stays in play, PM sees Declined badge with reason visible on hover
3. **Expiry** — PM creates request, deadline simulated in past, scheduled job runs, request transitions to expired, magic link revoked
4. **PM cancel** — PM cancels a pending request, badge clears, token revoked, vendor never notified
5. **Multi-vendor isolation** — Vendor A's revision request leaves Vendors B and C completely untouched in the same package
6. **Post-award guard** — Creating an award on a task hides the "Request Revision" button for all invitations on that task; backend rejects any attempted creation with 409

All six scenarios passed. One mid-implementation issue was caught and patched: the post-award button visibility on the PM dashboard initially didn't hide the button (the bid-package detail response didn't expose award state); the fix added an `is_awarded` field to the response, sourced from a single per-package query against the `awards` table.

---

# VI. Estimated Hours

| Phase | Description | Hours |
| --- | --- | --- |
| A | Database schema, triggers, partial unique indexes | 12 |
| B | Backend API: 4 new endpoints + validator update + scheduled job | 20 |
| C | Submission flow updates: finalize branch, prefill, read-path audit, award guard | 10 |
| D | PM frontend: request, badges, history expander, cancel | 14 |
| E | Vendor portal frontend: landing, revision form mode, decline, confirmation pages | 14 |
| F | Email templates (F.1 request, F.2 confirmation) | 4 |
| G | End-to-end verification (6 manual scenarios on staging) | 4 |
| Post-merge fix | `is_awarded` field on bid-package detail to hide button after award | 2 |
| **Total** | | **80** |

---

# VII. Out of Scope / Deferred

The following items were considered and explicitly deferred:

* **Scoring engine update** — The proposal called for re-scoring the bid package when a revision finalizes. Deferred to Phase 8 of the main project plan, where the scoring engine itself will be built. The Phase 8 implementation will naturally need to filter to `is_superseded = FALSE` on its read paths, and the supersession columns and `bid_scores` row-per-submission semantics are already in place to support this.
* **Per-revision file attachments deletion** — Vendors can add new attachments to a revision submission but cannot delete attachments inherited from the original. The originals remain linked to the original submission row (which is preserved as audit history) and are shown as read-only "previously uploaded" in the form.
* **Multi-instance scheduler deployment** — The auto-expiry job runs on a single ECS Fargate task. If horizontal scaling is needed in future, switch to PostgreSQL advisory locks for leader election. An ADR captures the decision and the revisit threshold (sustained CPU > 60% or response p95 > 500ms).
* **Sentry / Production observability** — The scheduled job currently uses structured logging only. Production observability (Sentry, alerting on missed runs) is its own dedicated work, planned but not yet implemented.
* **Mobile-native deep linking** — The magic link opens in whatever browser the vendor's email app uses. No iOS/Android native app integration; matches the broader MVP scope.

---

# VIII. Key Invariants

The feature is held together by several invariants. These are worth knowing for anyone maintaining the code.

* **Exactly one current submission per invitation:** Enforced by the partial unique index `idx_bid_submissions_current_per_invitation`. The `fn_flip_superseded_on_revision_finalize` trigger maintains this during revision finalize by flipping the predecessor's `is_superseded` to TRUE inside the same statement.
* **One pending revision request per invitation:** Enforced by the partial unique index `idx_bid_revision_requests_one_pending_per_invitation`. The API also checks before insert to give a clean 409 error.
* **Lifetime cap of 2 revision attempts:** Enforced at the API layer via count of non-cancelled revision_requests for the invitation. Cancelled requests don't count toward the cap.
* **No revisions after award:** Enforced at the API layer (create endpoint checks for `awards.status IN ('pending_acceptance', 'accepted')` on the task). Frontend hides the button via the `is_awarded` flag on the bid-package detail response.
* **Invitation `responded_at` preserved across revisions:** The `fn_sync_bid_invitation_on_submission` trigger uses `COALESCE(responded_at, NOW())` so a revision finalize never overwrites the original submission's response timestamp. The invitation's "first response" timestamp is meaningful for audit and reporting; revisions should not reset it.
* **Original bid is immutable:** Once superseded, a submission row is never modified. New attachments cannot be added to a superseded row; the row's contents reflect the bid as it was submitted at that point in time.
* **Token discrimination:** Every magic-link token is either an initial-bid token (no `bid_revision_request_id`) or a revision token (column set). The validator branches on this discriminator. The two paths never cross — a revision token cannot accidentally validate as an initial-bid invitation or vice versa.

---

# IX. Conclusion

This feature delivers a focused capability — letting a PM request a per-vendor bid revision without disturbing the rest of the package — while preserving a complete audit trail and respecting the vendor's time. The implementation spans every layer of the system (database, backend API, frontend SPA, transactional emails, scheduled jobs) but does so additively: no existing behavior was changed in a way that's visible to a vendor or PM who never uses the revision feature.

The feature is in production-ready state on `main`. The end-to-end scenario testing on staging covered all six user stories from the original proposal, with one mid-implementation gap (post-award button visibility) caught and patched. Phase 8 of the main project plan will integrate the supersession model into the scoring engine when scoring ships.
