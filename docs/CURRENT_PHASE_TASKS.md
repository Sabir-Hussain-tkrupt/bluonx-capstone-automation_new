# Current Phase Tasks — BluOnX Development Operations Platform

**Last Updated:** June 9, 2026

---

## Phase 1–7 — ✅ COMPLETE
## Phase 8: Bid Comparison & Scoring (~40h) — ✅ COMPLETE

**Deferred (see `docs/DEFERRED.md`):**
- Task 1.8 — Dev/staging environment separation
- Task 1.9 — AWS infrastructure setup (pending client credentials)
- Real performance scoring (milestone on-time rate + flag history) — Phase 10
- Manual score adjustment (`scored_by` dormant seam) — PM discretion lives at award override

---

## Phase 9: Award Decision & Contract Generation (~40h) — 🔄 IN PROGRESS

**Goal:** Turn the PM's award decision into a validated, audit-safe contract. Automatic pre-award validation gates the decision; an override workflow lets the PM proceed past soft warnings with documented justification; DocuSign executes the signature; and award/decline emails close the loop. Awards apply to **competitive bids only** — the task model is now just `internal` (no bidding) and `competitive` (bidding); `direct_assign` is excluded from the product. Award stays **100% manual** (Handoff §7.5) — the system validates, recommends, and executes, but never auto-awards.

**Tables read:** `bid_submissions`, `bid_invitations`, `bid_packages`, `tasks`, `projects`, `vendors`, `vendor_contacts`, `bid_scores`, `awards`, `contracts`
**Tables written:** `awards`, `contracts`, `docusign_envelopes`, `email_log` (via EmailService). No schema changes in Phase 9 — `awards`, `contracts`, `docusign_envelopes` were all built in Phase 1.

---

### Implementation notes (evidence-backed, current code)

These capture conventions Phase 9 must follow. Verified against the code-state snapshot (June 9).

**Greenfield surface — what does NOT exist yet:**
- `awards.py` router has CRUD route shells; every handler is a stub (`list_awards` → `[]`, others raise `501`). The **only** real logic is a superseded pre-award guard in `create_award` (`routers/awards.py:48-63`, returns `409` if the candidate submission is a revised/superseded row).
- No `award_service.py`. `has_override` / `override_justification` exist only as fields on `AwardCreate` (`models/awards.py:25-32`) — nothing validates or enforces them.
- `contracts.py` router is entirely stubs. No DocuSign client, JWT-grant, RSA-key, or envelope code anywhere. DocuSign exists only as Pydantic models (`models/awards.py:98-128`). `routers/webhooks.py` is SES/SNS only — **not** a DocuSign webhook.
- **`direct_assign` is excluded from the product.** The task model is now `internal` (no bidding) and `competitive` (bidding) only. Awards run for competitive bids exclusively. The `direct_assign` value remains in the `tasks.bid_type` CHECK constraint as a dormant enum (no migration — matches the dormant-seam pattern used elsewhere); it is simply never offered in task creation and never reached by the award pipeline. The read-side `is_direct_assign` flag (`vendor_portal.py:315` etc.) stays hard-coded `False` and untouched. *(If you'd rather tighten the CHECK to drop the value outright, that's a separate small migration — flagged, not assumed.)*
- **No** award/decline/contract email templates exist under `backend/app/templates/emails/` — all greenfield.

**Email (provider-abstracted, live):** `EmailService.send_email()` is the only send path (Phase 7 convention — never `send_bulk_emails`, which bypasses `email_log`). `EMAIL_PROVIDER` (`core/config.py:40`) is a real runtime switch defaulting to `"ses"`, and **SES creds are present** → the backend sends real emails right now.
- **Dev convention for Phase 9:** set `EMAIL_PROVIDER=mock` in `backend/.env` while building 9.4/9.6. Mock logs To/From/Subject/Body-preview to console, returns the same `EmailSendResult` shape, writes `email_log` identically — no AWS call. Flip back to `ses` by removing the line. Leaving it on `ses` sends live mail to whatever recipient is on the bid/award record. (Note: mock truncates the plain-text body preview to 80 chars — read the rendered template or the `email_log` row to eyeball full bodies.)

**Scheduling:** single in-process `AsyncIOScheduler` singleton (`jobs/scheduler.py`) with `@tracked_job` + `KNOWN_JOB_IDS`, started by the FastAPI lifespan. **No n8n anywhere** — the plan's references to "batch sending via n8n" (Task 9.6) are stale and reframed to `EmailService` below.

**Validation discipline (mirrors 8.2 / 8.4):** pre-award validation is a **pure, server-side-loaded** function — vendor/award context is resolved server-side from the candidate `bid_submission_id`, never passed in the request body. Deterministic and independently unit-testable, like the scoring dimensions.

**Award gate semantics (defined in 9.1, enforced at award-create in 9.2/9.5):**
- any **`block`** check → `can_award = false`; award-create hard-rejects (422), not overridable.
- any **`warn`** check (no blocks) → `requires_override = true`; award-create allowed only when `has_override = true` + non-empty `override_justification`.
- all `pass` / `skipped` → clean award, no override needed.

**Pre-existing partial unique indexes (already enforce "one active per task"):** `idx_awards_one_active_per_task` (status NOT IN declined/cancelled) and `idx_contracts_one_active_per_task` (status NOT IN terminated). The award/contract write paths must surface the resulting unique-violation as a clean 409, not a 500.

**Vendor capacity triggers (already live — do NOT double-handle in app code):** `+1` on award `→ accepted`, `-1` on accepted-award revoked / contract completed-or-terminated (with double-decrement guard). Phase 9 app code never touches `vendors.current_active_jobs` directly.

---

### Reframe — "prior performance" and "conflict detection" are not real checks yet (read this first)

The plan's Task 9.1 lists seven checks including **prior performance validation** and **conflict detection (scheduling, resources)**. Two of those are not honestly backable by the current schema, and faking them would put a meaningless green check in front of a real award decision:

- **Prior performance** — there is no performance data until Phase 10 builds milestone on-time tracking. This is the exact reason 8.2 scores performance with a neutral constant. 9.1 does **not** gate on performance; the seam is documented and picked up in Phase 10.
- **Conflict detection (scheduling/resources)** — there is no per-vendor job *calendar* in the schema. The only schedule signals that exist are (a) capacity (`current_active_jobs` vs `max_active_jobs`) and (b) the start-date comparison (`proposed_start_date` vs `desired_start_date`, built in 8.1.5). "Conflict detection" therefore reduces to those two checks — there is no third hidden calendar to consult. We do not invent one.

So 9.1 validates **five real checks** over data that genuinely exists: submission eligibility, insurance, bonding, capacity, budget variance, plus the start-date check. Everything else is deferred with rationale, not stubbed green.

---

### Task 9.1: Comprehensive Pre-Award Validation (~8h)

**Objective:** A pure function that, given a candidate winning `bid_submission`, returns a structured pass/warn/block validation result — plus a read-only preview endpoint so the PM sees exactly what awarding this submission would flag *before* committing. The result object is the same shape that gets snapshotted into `awards.validation_results` (JSONB) at award time (9.5) and read by the override workflow (9.2).

**Shape (pure validator + loader + preview endpoint):**
- **Loader** resolves context server-side from `bid_submission_id`:
  `bid_submissions` (`total_amount`, `proposed_start_date`, `vendor_id`, `is_draft`, `is_superseded`, `status`, `is_direct_assign`)
  → `bid_invitations` → `bid_packages` (`desired_start_date`, `deadline`, `status`)
  → `tasks` (`budget_estimate`, `project_id`)
  → `projects` (`estimated_end_date`)
  → `vendors` (`insurance_expiration_date`, `bonding_capacity`, `max_active_jobs`, `current_active_jobs`, `onboarding_status`).
- **Pure validator** `validate_pre_award(context) -> PreAwardValidationResult` — no I/O, fully unit-testable.
- **`award_amount`** for budget/bonding comparisons = the candidate submission's `total_amount`.

**Cohort-free (important):** the validator operates on a **single** submission + its vendor — no cohort, no price-relative math. It just needs one competitive winning submission row to point at. (This is also why it has no dependency on anything else in Phase 9 — it reads data that already exists.)

**The checks (each emits a `{check, severity, status, message, inputs}` entry):**

1. **submission_eligibility** — the candidate must be live: `is_superseded = FALSE AND is_draft = FALSE AND status IN ('submitted','under_review','accepted')`. Superseded / draft / wrong-status → **BLOCK**. (This subsumes the existing `awards.py:48-63` superseded guard into the validator; keep a hard guard at award-create too for defense-in-depth.)

2. **insurance_validity** — `vendors.insurance_expiration_date` vs today and vs `projects.estimated_end_date`:
   - expired (`expiration < today`) → **BLOCK** *(per plan "block if expired" — awarding to a vendor with no active insurance is uninsurable liability; not overridable)*.
   - valid today but `expiration < projects.estimated_end_date` (lapses before the work is done) → **WARN** (overridable — PM may have a renewal in hand).
   - `estimated_end_date` NULL (can't compute the window) → compare to today only; valid-today → **PASS**.
   - `insurance_expiration_date` NULL → **WARN** (data gap; PM chases the cert).
   > ⚠️ **Locked decision (default — flag if you want it flipped):** expired insurance is the **one hard BLOCK** among the data-quality checks. Everything else is an overridable WARN. If the client wants even expired insurance to be PM-overridable, this is the single line to change.

3. **bonding_capacity** — `vendors.bonding_capacity` vs `award_amount`:
   - `bonding_capacity < award_amount` → **WARN** (insufficient bonding for this contract value).
   - `bonding_capacity` NULL → **WARN** (data gap).
   - else **PASS**.

4. **vendor_capacity** — `vendors.current_active_jobs` vs `max_active_jobs`:
   - `max_active_jobs` NULL → **SKIPPED** (can't evaluate uncollected data — matches 8.2's neutral capacity handling; do not penalize).
   - `current_active_jobs >= max_active_jobs` → **WARN** (at/over capacity; accepting would push past max).
   - else **PASS**.
   - *(App code never mutates capacity here — the +1 is the trigger's job, on `→ accepted`.)*

5. **budget_variance** — `award_amount` vs `tasks.budget_estimate`, ±5% band:
   - `budget_estimate` NULL → **SKIPPED**.
   - `abs(award_amount − budget_estimate) / budget_estimate > 0.05` → **WARN**, with direction (`over` / `under`) and the computed variance % in `inputs`.
   - else **PASS**.

6. **start_date_feasibility** — `bid_submissions.proposed_start_date` vs `bid_packages.desired_start_date` (the 8.1.5 calendar-invite data):
   - `desired_start_date` NULL → **SKIPPED** (no target to hit).
   - `proposed_start_date` NULL while desired present (shouldn't occur — 8.1.5 made it required-when-desired) → **WARN** (guard the gap).
   - `proposed_start_date > desired_start_date` → **WARN**, with `days_late` in `inputs`.
   - else **PASS**.

**Result object:**
```jsonc
{
  "rubric_version": "preaward-v1",
  "can_award": false,            // false iff any check severity == "block"
  "has_blocking": true,
  "has_warnings": true,
  "requires_override": false,    // true iff has_warnings && !has_blocking
  "validated_at": "<iso8601>",
  "award_amount": 145000.00,
  "checks": [ { "check": "...", "severity": "block|warn|pass|skipped",
                "status": "pass|fail|skipped", "message": "...", "inputs": { } } ]
}
```
This is exactly what `awards.validation_results` stores at award time and what 9.2's override UI renders. Keep it self-describing (raw `inputs` per check) so a stored snapshot stays interpretable later, same principle as `bid_scores.scoring_metadata`.

**Endpoint (read-only preview / dry-run):** a GET keyed by the candidate submission, e.g. `GET /api/v1/awards/validate?bid_submission_id={id}` *(audit the existing `awards.py` / `ROUTES` nesting convention before fixing the path — match the Phase 8 pattern of confirming routing against actual code)*. No side effects, no write. `404` unknown submission. A blocking result returns **200 with the block detail** (so the UI can render *why* it's blocked) — the 422 hard-reject belongs to award-create (9.2/9.5), not the preview.

**Files (audit before assuming):** new pure module `backend/app/services/pre_award_validation_service.py`; extend `PreAwardValidationResult` / per-check models in `backend/app/models/awards.py`; preview endpoint in `backend/app/routers/awards.py`; tests under `backend/tests/awards/` (match existing test layout). Reuses `vendors.*`, `bid_submissions.total_amount` / `proposed_start_date`, `bid_packages.desired_start_date` / `deadline`, `tasks.budget_estimate`, `projects.estimated_end_date`.

**Out of scope / deferred (with rationale):**
- **Performance gate** — no data until Phase 10. Documented seam, not stubbed green. (DEFERRED.md.)
- **Scheduling/resource conflict beyond capacity + start-date** — no vendor calendar exists. (DEFERRED.md.)
- **Unresolved `vendor_flags` surfacing at award** — genuinely useful and cheap, but folds into the deferred performance/flag-history work; revisit with Phase 10. (DEFERRED.md.)
- **Override enforcement / `validation_results` persistence** — that's the *write* side; the gate logic is defined here but enforced at award-create in 9.2/9.5.
- **Anything DocuSign, decline, or acceptance** — 9.3+.

**Acceptance (9.1):**
- [ ] Pure `validate_pre_award` unit-tested per check at every boundary: insurance expired/within-window/valid/NULL; bonding below/above/NULL; capacity at/under/NULL-max; budget over/under/within-5%/NULL-estimate; start on-time/late/NULL-desired/NULL-proposed; eligibility live/superseded/draft/wrong-status.
- [ ] Severity classification correct: only insurance-expired and ineligible-submission are `block`; the rest are `warn`; capacity-NULL-max and budget-NULL-estimate and desired-NULL are `skipped`; performance and conflict are **not** emitted as checks at all.
- [ ] `can_award` / `has_blocking` / `has_warnings` / `requires_override` derived correctly from the check set.
- [ ] Validator is cohort-free and runs on a single competitive winning submission — no dependency on any other Phase 9 task.
- [ ] Preview endpoint returns the structured result (200 even when blocking), `404` on unknown submission; no write occurs; path matches the audited routing convention.
- [ ] Result object shape is byte-compatible with what `awards.validation_results` will store (self-describing `inputs` per check).
- [ ] No schema change; no email; no capacity mutation in app code; existing superseded guard reconciled with the new eligibility check.

---

### Task 9.2: Award-Create + Validation Override Gate (~4h)

**Objective:** Build the real award-create write path (the first writer to `awards`) with the 9.1 validation result as its gate. The PM may proceed past `warn`-severity checks with a required justification; `block`-severity checks are never overridable. This task writes the award row at `pending_acceptance` and stops — no DocuSign envelope, no email, no contract (those are 9.3–9.6). **9.2 does not depend on any of the open DocuSign decisions and is shippable now.**

> **Locked decision — `has_override` means *validation* override only.** Awarding a vendor who isn't the top-scored recommendation (8.4) is a free PM choice: it sets nothing, requires no justification, and is recorded only implicitly by which `bid_submission_id` won. `has_override = TRUE` means exactly one thing: *the PM knowingly accepted a flagged validation `warn`.* Rationale: the recommendation is a **ranking**, validation is a **risk gate** — conflating them would muddy the audit signal. (8.4 persists nothing — verified — so there is no collision; 9.2 is the clean first writer to `awards`.)

**Backend — award-create write path (makes the `create_award` 501 stub real, `routers/awards.py:37-89`):**

Request payload (extends existing `AwardCreate`): `{ bid_submission_id, has_override?, override_justification? }`. Everything else is **server-derived, never trusted from the client**:
- `award_amount` = the candidate submission's `total_amount`
- `task_id` / `vendor_id` = resolved from the submission chain (the existing consistency triggers enforce this anyway)
- `awarded_by` = authenticated user; `status` = `pending_acceptance`

Gate logic (server is the final truth — **re-runs 9.1 fresh**, never trusts a client-supplied validation snapshot):
```
result = validate_pre_award(load_context(bid_submission_id))   # recompute server-side
if result.has_blocking:                       → 422, return the block detail (not overridable)
if result.has_warnings:
    if not has_override or not override_justification.strip():
                                              → 422, return the full result (forces the dialog)
    has_override_final = TRUE
else:
    has_override_final = FALSE                # no warnings ⇒ override is a no-op even if client sent it
INSERT award( status=pending_acceptance, award_amount=<submission.total_amount>,
              has_override=has_override_final,
              override_justification = <justification if has_override_final else NULL>,
              validation_results = <result snapshot>, awarded_by=<user> )
UPDATE tasks SET status='awarded' WHERE id=<task_id>
```
- **`has_override` is never TRUE when no warnings existed**, regardless of what the client sent — the server decides.
- `validation_results` (JSONB) is snapshotted on **every** award, clean or not, so the audit record always shows the state at award time (self-describing per-check `inputs`, same principle as `bid_scores.scoring_metadata`).
- **Atomic:** award INSERT + task status update in one transaction.

Preconditions (structural, before the gate):
- submission not found → `404`.
- the submission's bid package status must be `closed` or `evaluating` — awarding from an `open` package (bidding still live) or `cancelled` → `422`. *(Sensible default; drop if you don't want a package-status gate.)*
- second active award on the same task → the partial unique index `idx_awards_one_active_per_task` fires; **surface it as a clean `409`, not a `500`.**
- ineligible submission (superseded/draft/wrong-status) needs no separate guard — it already returns via `result.has_blocking` (the 9.1 `submission_eligibility` block). This **subsumes** the old `awards.py:48-63` superseded `409` guard; replace it with the validator-driven path (keep a hard transaction-level guard for defense-in-depth).

**Frontend — award action + override dialog:**
- An **Award** action per vendor in the comparison UI (`RecommendationPanel.tsx` / the comparison table row in `BidPackageComparePage.tsx`). Wire up the unused `AWARDS` / `AWARD(id)` constants (`constants/api.ts:67-69`).
- On click → fetch `GET /awards/validate/{bid_submission_id}` (the 9.1 preview) and render the dialog:
  - `block` checks → red, **confirm disabled** (cannot award).
  - `warn` checks → amber, with a **required justification textarea** (confirm disabled until non-empty).
  - `pass` / `skipped` → muted.
  - all clean → confirm enabled, no justification field.
- Confirm → `POST /awards` → on success, **invalidate** the package scores / package / task React Query keys (mutation-invalidation convention — no polling). The existing `is_awarded` read flag (`types.ts:90`, `InvitationsTable.tsx:145`) already hides "Request Revision" once awarded, so that surface updates for free.
- Reuse existing modal/dialog + form components (Phase 2 library).

**Audit trail (reframe — no separate table):** the plan says "override history logging for audit trail." There is **no separate override-history table** and we add none. The award row *is* the immutable audit record: `has_override`, `override_justification`, the `validation_results` JSONB snapshot, `awarded_by`, `awarded_at`. Re-awards (after a cancel/decline) leave the prior award row in place — the partial unique index permits historical `declined_by_vendor`/`cancelled` rows — so the table naturally carries award history.

**Vendor-facing gap (expected, not a bug):** between 9.2 and 9.3/9.4 an awarded vendor receives no notification — award-create only writes the internal row. The signing link + award email are 9.3/9.4.

**Files (audit before assuming):** make `create_award` real in `backend/app/routers/awards.py`; new `backend/app/services/award_service.py` (write path + gate, calls the 9.1 validator); reuse `PreAwardValidationResult`; frontend award button + dialog under `frontend/src/features/bids/`; tests under `backend/tests/awards/`.

**Out of scope:** DocuSign/envelope (9.3), award email (9.4), contract row (9.5), declines (9.6), acceptance transition (`pending_acceptance → accepted`, which is driven by the signing webhook per open decision #1). No schema change.

**Acceptance (9.2):**
- [ ] `create_award` writes a real award row; server recomputes 9.1 validation and **never** trusts a client-supplied `validation_results`.
- [ ] `block` → 422 (non-overridable, returns block detail); `warn` without justification → 422 (returns full result); `warn` + non-empty justification → award written with `has_override=TRUE` + justification + snapshot; all-clean → award written with `has_override=FALSE` + snapshot.
- [ ] `has_override` is never TRUE when no warnings existed, regardless of client input.
- [ ] Award status = `pending_acceptance`; `tasks.status → 'awarded'`; both in one transaction.
- [ ] `award_amount` derived server-side from the submission; `awarded_by` = authenticated user.
- [ ] Second active award on the same task → clean `409` (not 500); package-status precondition enforced.
- [ ] Old superseded `409` guard reconciled into the validator's eligibility block.
- [ ] Awarding a non-top-ranked vendor requires nothing extra and sets no override fields.
- [ ] Frontend: award button + dialog renders the validation result; justification required **only** when warnings present; confirm disabled on blocks; success invalidates the relevant React Query keys.
- [ ] No envelope, email, or contract created; no schema change.

### Task 9.3a: DocuSign Auth + Client Foundation (~4h)

**Objective:** Stand up the DocuSign client and **JWT Grant** authentication so the rest of Phase 9 has an authenticated `ApiClient` to build on. This layer is **decision-independent** — it doesn't care who signs or what the document is — so it ships now while 9.3b waits on decisions #1–#3.

> **Locked decision — JWT Grant (impersonation), not Authorization Code.** BluOnX is an unattended service integration: the *sender* is the organization (BluOnX/Capstone), envelopes are sent by backend automation with no human at a consent screen, and vendors sign by email without DocuSign logins. DocuSign's own rule: a single app-wide DocuSign login ⇒ JWT Grant; per-user interactive logins ⇒ Auth Code. The "DocuSign recommends Auth Code" line is scoped to *user-present* apps and doesn't apply here. (Full reasoning in chat, June 9.)

**SDK:** the official `docusign-esign` Python client. Its calls are **synchronous** (blocking `requests` under the hood) — wrap token mint and all later envelope calls in a threadpool (`anyio.to_thread.run_sync` / `run_in_executor`) so they don't block the FastAPI event loop. Add `docusign-esign` to backend deps.

**Two hosts (don't conflate):**
- **OAuth host** (token mint + consent) — sandbox constant `account-d.docusign.com`. New env: `DOCUSIGN_OAUTH_BASE_URL`.
- **REST base** (API calls) — `{DOCUSIGN_ACCOUNT_BASE_URL}/restapi` (e.g. `https://demo.docusign.net/restapi`).

**Config additions (`core/config.py`)** — existing: `DOCUSIGN_ACCOUNT_ID`, `DOCUSIGN_USER_ID`, `DOCUSIGN_ACCOUNT_BASE_URL`, `DOCUSIGN_INTEGRATION_KEY`, `DOCUSIGN_PRIVATE_KEY_PATH`. Add: `DOCUSIGN_OAUTH_BASE_URL` (default `account-d.docusign.com`), `DOCUSIGN_JWT_SCOPES` (default `signature impersonation`), `DOCUSIGN_REDIRECT_URI` (any URI registered on the integration key — used only for the one-time consent URL), `DOCUSIGN_TOKEN_EXPIRES_IN` (default `3600`), and a **`DOCUSIGN_PROVIDER` mock toggle** (`sandbox` | `mock`) mirroring the `EMAIL_PROVIDER` pattern.

**Provider abstraction (mirror EmailService):**
- `sandbox` provider → real JWT mint against the developer sandbox.
- `mock` provider → returns a synthetic token without any network call, so unit tests and local dev run without consent or creds (same role `EMAIL_PROVIDER=mock` plays for email). This is the safe default when creds/consent aren't in place.

**Client responsibilities (`backend/app/services/docusign_client.py` or similar — audit existing service layout first):**
- Mint a JWT user token via the SDK (`request_jwt_user_token` / `configure_jwt_authorization_flow`) using the impersonated user (`DOCUSIGN_USER_ID` as `sub`), integration key as `client_id`, RSA key from `DOCUSIGN_PRIVATE_KEY_PATH`, scopes `signature impersonation`.
- **Cache the token in-process with its expiry** and re-mint on demand with a safety margin (tokens are 1-hour, **no refresh token** — DocuSign issues none for JWT). In-process cache fits the single-Fargate-task, no-Redis model; no token persistence.
- On `consent_required`, **construct and surface the one-time consent URL**: `https://{DOCUSIGN_OAUTH_BASE_URL}/oauth/auth?response_type=code&scope=signature%20impersonation&client_id={integration_key}&redirect_uri={redirect_uri}` — caller visits once in a browser as the impersonated user, clicks allow (the returned code is ignored), then retries. Consent persists server-side until revoked.
- Expose an authenticated `ApiClient` / `EnvelopesApi` factory for 9.3b.

**Diagnostic endpoint:** `GET /admin/docusign-health` (mirrors the Phase 7 `/admin/scheduler-health` convention) — attempts a token mint and returns `{ ok: true }`, or, on `consent_required`, returns the consent URL so the one-time grant is self-service. Authenticated (internal users) only.

**Impersonated user = a dedicated *system* user** (e.g. "BluOnX Automation"), not a personal employee account, so audit trails aren't tied to someone who may leave. Note: the impersonated *sender* is a different concept from the internal *signatory* in decision #3 — they needn't be the same identity.

**Secrets hygiene:** confirm `backend/secrets/` is gitignored before first commit (the `.pem` is a private key — leaking it = indefinite impersonation, since there's no short-lived refresh token to revoke). Production key storage is AWS Secrets Manager (Phase 12 seam).

**Files (audit before assuming):** `core/config.py` (settings); new `backend/app/services/docusign_client.py` (provider abstraction + token cache); `/admin/docusign-health` route (reuse the scheduler-health router pattern); deps file; `.gitignore`; tests under `backend/tests/`.

**Out of scope (9.3b and later):** envelope creation, signer/tab config, the Connect status webhook + HMAC verification, any award/contract mutation. No schema change.

**Acceptance (9.3a):**
- [ ] `docusign-esign` added; all blocking SDK calls run in a threadpool (event loop never blocked).
- [ ] `DOCUSIGN_PROVIDER=mock` returns a synthetic token with no network call (tests/dev run without consent or creds); `sandbox` mints a real token.
- [ ] Token is cached in-process and re-minted on expiry with a safety margin; no refresh-token logic; no token persisted.
- [ ] `consent_required` is caught and the correct consent URL is constructed and surfaced.
- [ ] `GET /admin/docusign-health` returns ok on success or the consent URL when consent is missing; internal-auth only.
- [ ] OAuth host vs REST base kept distinct; config loads cleanly; `backend/secrets/` gitignored.
- [ ] Unit tests cover token-cache re-mint, consent-URL construction, mock provider, and config loading; a real-mint integration test is marked/skipped without creds (test-discipline convention).
- [ ] No envelope, webhook, award, or contract code; no schema change.

### Contract lifecycle reframe (read before 9.3b / 9.5)

The plan and our earlier notes said "contract created on acceptance." **The schema overrides that.** `docusign_envelopes.contract_id` is `NOT NULL`, and `contracts.status` runs `draft → sent_for_signature → executed → active → completed/terminated`. Both mean the contract row must exist **at envelope-send time**, not at signature. Corrected lifecycle:

| Moment | `awards.status` | `contracts.status` | `docusign_envelopes.status` | Side effects |
|---|---|---|---|---|
| Award (9.2) | `pending_acceptance` | — | — | task → `awarded` |
| Envelope send (9.3b+9.5) | `pending_acceptance` | `sent_for_signature` | `sent` | award email sent |
| Both sign (Connect `completed`) | `accepted` | `executed` | `completed` | **+1 capacity (trigger)**, declines fire (9.6) |
| Vendor declines / voided | `declined_by_vendor` | `terminated` | `declined`/`voided` | task freed to re-award |

Capacity still bumps only on `award → accepted` — unchanged. What changed: the contract row is **born at send in `sent_for_signature`**, not at acceptance. 9.5 owns that row's full lifecycle; 9.3b calls into it so the envelope FK is satisfiable.

### Task 9.3b: DocuSign Envelope + Connect Webhook (~6h)

**Objective:** On top of 9.3a's authenticated client, send the contract envelope when an award is created, and consume DocuSign's status callbacks to drive the acceptance lifecycle above. Built on the resolved-by-assumption decisions (see the confirmation table below) — all of which land on config or one swappable document template, never the architecture.

**Resolved assumptions baked in:**
- **Acceptance = full envelope completion** (both signers), via the Connect `envelope-completed` event. Not the vendor's signature alone.
- **Document = in-app-generated contract PDF** (firm standard terms, populated with award data) + the vendor's **signed SOW attached as an exhibit** when one is on file; sent as inline document(s) with anchor-string `SignHere` tabs. Terms template isolated for one-line swap if the client supplies their own.
- **Signers = sequential: vendor contact `routingOrder` 1, internal BluOnX signer `routingOrder` 2** (`CONTRACT_OWNER_SIGNER_NAME` / `_EMAIL` config; sandbox = your own email).

**Part A — Envelope send (`send_contract_envelope(award_id)` in the DocuSign service):**
- Triggered **post-commit from `award_service`** after award-create (9.2), best-effort: a send failure does **not** roll back the award (it stays `pending_acceptance` with no envelope) and is retryable via a resend path. Also exposed for manual resend.
- Load context: award → submission → vendor + invited contact, task, project. Vendor signer = the invited `vendor_contacts` row; internal signer = config.
- **Create the `contracts` row first** (9.5 path) in `sent_for_signature` so the envelope FK holds; generate the contract PDF from award data (vendor, `award_amount`, start/end dates, project/task, terms template), attaching the signed SOW exhibit if present. *(contract_number assignment + date/terms population are 9.5's detail.)*
- Build the `EnvelopeDefinition`: document(s) base64, two `Signer` recipients with `routingOrder` + `SignHere` anchor tabs (`/vendor_sig/`, `/owner_sig/`), an **envelope-level `eventNotification`** pointing at our webhook (self-contained — no account-level Connect config), `status="sent"`. All SDK calls in a threadpool (9.3a rule).
- Persist the `docusign_envelopes` row (`envelope_id`, `status='sent'`, `contract_id`); set contract → `sent_for_signature`.

**Part B — Connect status webhook (the acceptance hub):**
- A **new** route, separate from the SES/SNS `webhooks.py`. **HMAC-verify the raw body** before parsing: SHA-256 over the exact request bytes, base64, constant-time compare against `x-docusign-signature` (read `await request.body()` *before* JSON). Reject on mismatch. New env: `DOCUSIGN_CONNECT_HMAC_KEY`.
- **Idempotent:** Connect retries up to 5× over 72h — key on `envelope_id` + event/status and no-op if already applied (a duplicate `completed` must never double-create a contract, double-bump capacity, or double-send declines).
- Update `docusign_envelopes.status` + store the full `webhook_payload` (JSONB, for audit/debug) on every event.
- **Dispatch on event** (the transition handlers themselves live in award/contract/decline services — 9.5/9.6 — the webhook just routes to them):
  - `completed` → `on_envelope_completed`: contract → `executed`, award → `accepted` (fires the +1 capacity trigger), trigger declines to the other vendors (9.6).
  - `declined` / `voided` → contract → `terminated`, award → `declined_by_vendor`.
  - `delivered` / `sent` → status update only.

**Dev note — local webhook testing:** DocuSign Connect must reach a **public URL**, so testing the webhook locally needs a tunnel (e.g. ngrok) pointed at the backend; set the envelope `eventNotification` URL accordingly. The `DOCUSIGN_PROVIDER=mock` path (9.3a) lets you build/test the *send* and *handler* logic without live envelopes; the real Connect round-trip needs the tunnel + sandbox consent.

**Co-dependency:** 9.3b, 9.5 (contract row), and 9.4 (award email) are sent together at award time and are naturally built in one pass. The webhook's completion handler needs 9.5's contract transitions and 9.6's decline send to exist.

**Files (audit before assuming):** extend `backend/app/services/docusign_client.py` (envelope build/send) + a new `contract_service.py` if not already present (9.5); new Connect webhook route (do **not** fold into `webhooks.py`); extend `award_service` with the post-commit send hook + resend; config (`DOCUSIGN_CONNECT_HMAC_KEY`, `CONTRACT_OWNER_SIGNER_NAME/_EMAIL`, webhook URL); tests under `backend/tests/`.

**Out of scope:** award email body (9.4), contract_number/terms text detail (9.5), decline email body (9.6). No schema change.

**Acceptance (9.3b):**
- [ ] `send_contract_envelope` creates the `contracts` row (`sent_for_signature`), generates the contract PDF (+ SOW exhibit if present), sends a real sandbox envelope with two sequential signers + anchor tabs, persists `docusign_envelopes`; all SDK calls off the event loop.
- [ ] Send is post-commit best-effort — a DocuSign failure leaves the award at `pending_acceptance` (not rolled back) and is resendable.
- [ ] Webhook HMAC-verifies the raw body and rejects bad signatures; idempotent across Connect retries (duplicate `completed` is a no-op).
- [ ] `completed` → contract `executed` + award `accepted` (+1 capacity via trigger) + declines dispatched; `declined`/`voided` → contract `terminated` + award `declined_by_vendor`; every event updates status + stores `webhook_payload`.
- [ ] Acceptance fires only on **full** completion (both signers), not the vendor's signature alone.
- [ ] No schema change.

### Task 9.4: Award Letter Email Template (~3h) — summary

HTML + plain-text pair under `backend/app/templates/emails/` (`base.html` layout, `template_renderer` singleton, Phase 7 convention). Congratulations + project/task details + mobilization info + embedded DocuSign signing link. **No milestone list** (milestones don't exist until Phase 10 — confirmed). Sent via `EmailService.send_email()` (mock in dev) at envelope-send time. Built alongside 9.3b.

### Task 9.5: Contract Record Lifecycle (~6h) — summary

Owns the `contracts` row across its full lifecycle (per the reframe above): **created at envelope-send in `sent_for_signature`** (auto `contract_number`, start/end dates, `contract_amount`, payment terms), linked to the `docusign_envelopes` row; **`executed` on Connect `completed`** (the moment award → `accepted` fires the +1 capacity trigger); **`terminated` on decline/void** (frees the task to re-award). Surface the partial-unique violation (`idx_contracts_one_active_per_task`) as a clean 409. Competitive awards only. Built together with 9.3b (the envelope-send path calls contract-create so the FK holds). `payment_terms` content is a placeholder until the client provides boilerplate.

### Task 9.6: Decline Notifications (~7h) — summary

Professional decline email (HTML + text pair) to the **other** invited vendors on the package, **fired on acceptance** (Connect `completed`), not at award creation — so we don't decline the backup pool before the winner signs. **Reframe:** plan says "batch sending via n8n" — n8n is gone; this loops over recipients through `EmailService.send_email()` with the Phase 7 semaphore/`asyncio.gather` concurrency pattern, each logged to `email_log`. Dispatched from the 9.3b webhook completion handler.

---

## Decisions — resolved-by-assumption (build now, confirm with client later)

Client is unreachable for a few days; rather than block, we adopt the highest-probability answer for a real construction firm and **isolate each assumption to config or one swappable document template** so a client deviation never touches the architecture or schema. All of 9.3b–9.6 build on these.

| # | Question | Options | **Our pick (resolved June 9)** | Blast radius if client differs |
|---|---|---|---|---|
| 1 | Acceptance trigger | (a) signing = acceptance · (b) separate accept step | **(a)** the contract signature *is* acceptance (industry-standard; no separate step exists in construction) | Low — would add an accept step; `pending_acceptance` already models it |
| 1b | Acceptance = whose signature | vendor-only · both signers | **full envelope completion (both signers)** — firm countersigns last | Low — Connect event filter |
| 2 | Contract document source | (a) our generated terms PDF + SOW exhibit · (b) client's own subcontract template · (c) DocuSign console template | **(a)** generated PDF, signed SOW as exhibit, terms template isolated for one-line swap | Low–med — swap one template, or flip envelope builder to template+roles; flow untouched |
| 2b | SOW relationship to contract | reference · attach-as-exhibit · combined single doc | **attach signed SOW as exhibit** (scope ≠ terms; SOW binds price-to-scope at bid, contract carries legal terms) | Low — document-assembly detail |
| 3 | Signing order | (a) vendor → firm · (b) firm → vendor · (c) vendor only | **(a)** vendor `routingOrder` 1, firm countersigns `routingOrder` 2 | Low — `routingOrder` change |
| 3b | Internal signatory identity | specific name/email | **config value** (`CONTRACT_OWNER_SIGNER_NAME/_EMAIL`); sandbox = your email | None — pure config |
| 4 | DocuSign env / auth | JWT sandbox · auth-code · prod now | **JWT Grant, developer sandbox; prod at go-live** (spec'd in 9.3a) | n/a — locked |
| 5 | Decline-email timing | on award creation · on acceptance | **on acceptance** (Connect `completed`) — don't burn the backup pool before the winner signs | Low — webhook trigger point |

**Also flagged to the client (not Phase 9 work, log in `DEFERRED.md`):**
- **Mandatory signed SOW at bid time** — the client stated "sign a SOW for each job, submit with each bid," but Task 5.5 left it optional/unenforced. Assume they want it mandatory; this is a **Phase 5 (bidding) enforcement gap**, and could later become a pre-award compliance check ("no signed SOW on file → block/warn"). Does not block Phase 9.
- **Contract `payment_terms` / terms-template text** — placeholder until the client supplies their subcontract boilerplate. The *plumbing* is template-agnostic.
- **Legal weight of the bid-time SOW signature** (binding sub-agreement vs acknowledgment; whether the contract must re-incorporate it) — a legal-structure question for the client's contracts people. Determines what the DocuSign contract document must contain (decision #2).

---

## Phase 9 Acceptance (full phase — for reference; 9.1 criteria above are the active set)

- [ ] All pre-award checks execute automatically before an award is written (9.1 + enforcement in 9.2/9.5)
- [ ] PM can override `warn`s with documented justification; `block`s are never overridable; `validation_results` snapshot stored
- [ ] DocuSign envelope created/sent on award; status webhook updates `docusign_envelopes` and drives contract status
- [ ] Award letter email sent with signing link; decline letters sent to non-selected vendors via `EmailService` (no n8n)
- [ ] Contract record created on acceptance with complete details; capacity updated via the existing trigger (not app code)
- [ ] Complete audit trail (`validation_results`, `override_justification`, `email_log`, `docusign_envelopes.webhook_payload`)
- [ ] No schema change introduced in Phase 9

---

## Next Phase Preview

**Phase 10: Vendor Commitment & Performance Tracking (48h)** — email-based milestone check-ins, PM dashboard widgets, vendor flagging. Closes the performance/flag seams that 8.2 and 9.1 deliberately left neutral.

---

## References

- Full project plan: `docs/PROJECT_PLAN.pdf` (v2.3, 12 phases)
- Database schema: `database/bluonx_complete_schema_v2_31.sql`
- RLS policies: `database/rls_policies.sql`
- Handoff document: `docs/BluOnX_Context_Handoff.md`
- Deferred tasks: `docs/DEFERRED.md`
