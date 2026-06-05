# Current Phase Tasks — BluOnX Development Operations Platform

**Last Updated:** June 2, 2026

---

## Phase 1: Foundation & Database (60h) — ✅ COMPLETE
## Phase 2: Frontend Foundation, Backend API & Auth (100h) — ✅ COMPLETE
## Phase 3: Core Entity Management (76h) — ✅ COMPLETE
## Phase 4: Bid Invitation System (50h) — ✅ COMPLETE
## Phase 5: Bid Collection — Custom Secure Forms (60h) — ✅ COMPLETE
## Phase 6: Real-Time Dashboard & Visibility (~30h) — ✅ COMPLETE
## Phase 7: Automated Reminder & Alert System (55h) — ✅ COMPLETE

**Deferred (see `docs/DEFERRED.md`):**
- Task 1.8 — Dev/staging environment separation
- Task 1.9 — AWS infrastructure setup (pending client credentials)

---

## Phase 8: Bid Comparison & Scoring (~40h) — 🔄 IN PROGRESS

**Goal:** Turn submitted bids into a defensible award decision. Weighted scoring (50/5/20/10/15), a side-by-side comparison surface, and a recommendation engine — all resting on the guarantee that every vendor in a package bid against the *same* frozen structure.

**Tables read:** `bid_packages`, `bid_invitations`, `bid_submissions`, `bid_line_items`, `bid_attachments`, `bid_templates`, `bid_template_items`, `tasks`, `projects`, `vendors`, `vendor_contacts`, `vendor_documents`, `vendor_flags`, `milestones`, `awards`
**Tables written:** `bid_scores` (8.2+), `bid_templates` / `bid_template_items` (8.1 — guarded writes only). No schema changes in Phase 8.

---

### Why 8.1 is NOT a normalization engine (reframe — read this first)

The original plan scoped Task 8.1 as a "bid normalization engine" that parses mixed pricing formats (one vendor lump sum, another unit price) and reconciles them into comparable totals. **That problem no longer exists.** The bid template architecture (Handoff §2.5) eliminated it upstream: the PM picks one template per bid package (`bid_packages.bid_template_id`), and every vendor fills that one structure. Description / item_type / unit_of_measure / sort_order are snapshotted into `bid_line_items` at submission time, and `line_total` is pre-computed. There is nothing left to normalize at comparison time — the comparable numbers already sit in the rows.

This is the same pattern as the dropped Phase 6 completeness checker: the form prevented incompleteness *structurally*, so the checker had no work to do. Here, the template prevents format divergence *structurally*, so the normalization engine has no work to do.

**So 8.1 is repurposed into comparability-integrity hardening** — protecting the one invariant the whole phase rests on: *all vendors in a package bid against a single, frozen structure.* Today that invariant is unprotected. A PM can edit (or empty) a template's items while vendors are mid-bid against it.

---

### Task 8.1: Comparability-Integrity Hardening — Bid Template Freeze Guards (~6–8h)

**Problem (evidence-backed, current code):**
- **Edit (PUT) has no guard.** `update_bid_template` (`backend/app/routers/bid_templates.py:308-353`) updates metadata, then unconditionally deletes every `bid_template_items` row for the template and re-inserts the new list (`_insert_items`, `bid_templates.py:167-184`). It never inspects `bid_packages`. A PM can materially alter or empty a template while vendors are bidding against it.
- **Delete has only a thin guard.** `delete_bid_template` (`bid_templates.py:356-379`) attempts the delete and catches Postgres FK error `23503` (from `bid_packages.bid_template_id ON DELETE RESTRICT`) → 409. Correct outcome, but the message is bare — it never tells the PM *which* package(s) block the delete.
- **Snapshot is real but not a freeze.** `build_line_item_rows` / `fetch_template_items_map` (`vendor_portal_service.py:498-512, 554-590`) copy template-owned fields into `bid_line_items` on every draft create *and* update. Because PUT re-snapshots from the *current* template on every auto-save, a mid-bid template edit leaks into in-progress drafts on their next save. The snapshot only fully locks once the vendor stops saving / submits. **Blocking the edit removes the source of this leak — one fix closes both holes.**

**Freeze rule (CONFIRMED: simple-and-safe):**
A template is **in use** if it is referenced by any **non-cancelled** bid package:
```sql
EXISTS (SELECT 1 FROM bid_packages
        WHERE bid_template_id = :template_id
          AND status <> 'cancelled')
```
`bid_packages.status` ∈ (`open`, `closed`, `evaluating`, `cancelled`) — there is no `draft` package status, so any non-cancelled reference means the template is committed to a live round. This intentionally locks the template even in the brief window after the PM selects it and before invitations go out. We accept that narrow over-lock in exchange for a rule that needs zero joins to `bid_invitations` and is trivial to reason about. The escape hatch (duplicate) makes the over-lock painless.

**Backend changes (all in `bid_templates.py` unless noted):**

1. **Shared helper** `_referencing_live_packages(db, template_id)` → returns the non-cancelled referencing packages (join `bid_packages` → `tasks` for `task name` + `status`, for messaging). `_is_template_in_use` = non-empty result.

2. **Edit guard** in `update_bid_template`: before any mutation, call the helper. If in use → **409** with a message naming the blocking package(s): *"This template is in use by a live bid package ({task name} — {status}) and is locked to keep all vendor bids comparable. Duplicate it to make changes."* Block the **entire PUT** when in use (metadata *and* items), not just item changes — simplest correct rule. (Name-only relaxation is a possible future tweak; out of scope here.)

3. **Delete message upgrade** in `delete_bid_template`: keep relying on FK `RESTRICT` (it blocks the delete regardless of package status — correct). Before/within the `23503` handler, run the helper-style lookup (here including cancelled refs too, since FK blocks on *any* reference) and return a **409** that lists the referencing package(s) + status. No behavior change, just a message that tells the PM why.

4. **Duplicate escape hatch** `POST /api/v1/bid-templates/{id}/duplicate` — **check whether this already exists before building.** If not: deep-copy the template (`is_lump_sum`, `trade_id`) + all `bid_template_items` (new IDs; copy `description`, `item_type`, `unit_of_measure`, `sort_order`), name = `"Copy of {original name}"` (or client-supplied), `created_by` = current user. Returns the new template. This is what makes the freeze non-blocking — the PM edits the copy, then points the *next* round at it.

5. **`is_in_use` flag on reads** — extend `GET /bid-templates/{id}` (and the list endpoint) with `is_in_use: bool` (and, on the detail endpoint, the referencing package summary) so the frontend can render the locked state without a 409 round-trip.

**Frontend changes (Task 3.6 template management UI):**
- When the open template `is_in_use`: disable Save, show a banner — *"In use by a live bid package — locked to keep bids comparable. Duplicate to change."* Surface a **Duplicate** action that calls the new endpoint and navigates into editing the copy.
- Optional/nice-to-have: an "In use" badge on rows in the template list.

**Tables:** read `bid_packages`, `tasks` (messaging + flag); guarded write `bid_templates`, `bid_template_items`. **No schema change.**

**Testing:**
- Unit: in-use helper (open/closed/evaluating → locked; cancelled-only → editable; no refs → editable); PUT returns 409 when in use and succeeds when not; delete 409 lists referencing packages; duplicate deep-copies items with fresh IDs.
- Frontend: locked-state banner renders when `is_in_use`, Save disabled, Duplicate action works.

**Out of scope for 8.1 (deferred, with rationale):**
- **Snapshot-once on draft PUT** (only copy structure when the draft has no line items yet, then touch only vendor values). Belt-and-suspenders that makes a submission immutable-by-construction even if a future code path bypasses the guard — but the edit guard already closes the realistic threat, so this is not load-bearing. Log as a separate hardening ticket if desired.
- Name-only edit relaxation for in-use templates.
- Anything touching scoring or comparison (8.2 / 8.3).

**Scoping note:** This is technically Phase-3 (template management) debt. Doing it as 8.1 is deliberate — it's the invariant Phase 8's comparison rests on, so we pay it down right before leaning on it. Equally valid to log it as a 3.x fix; either way it does not change the work.

---
### Task 8.1.5: Timeline Data — Start Dates (precursor to 8.2 scoring) (~6h)

**Why:** The 15% timeline weight (8.2), the Phase 9 start-date pre-award check, and the core "can the vendor actually start on time" promise all assume structured start-date data that was never built into the collection pipeline. This is timeline debt — paid down right before 8.2 leans on it. Free-text `instructions` is not scoreable; a scored dimension must come from a structured field.

**Schema (already applied — DB v2.32):**
- `bid_packages.desired_start_date DATE` (nullable) — PM-communicated target start for the round. NULL = flexible/none.
- `bid_submissions.proposed_start_date DATE` (nullable) — vendor's committed start date.

**Model: calendar-invite pattern.** Vendor form pre-fills `proposed_start_date` with the package's `desired_start_date`. Leaving it = "yes, I can hit your date"; changing it to a later date = "no, here's my earliest." The yes/no is *derived* (`proposed <= desired` → on time), never stored separately. "Can't do it at all" = a declined invitation, not a date.

**Locked decisions:**
- **Start date only.** No duration/end date in MVP (overlaps capacity; defer).
- **Required-when-present:** `proposed_start_date` is required on submit *when* the package has a `desired_start_date`; optional otherwise. Enforced server-side in `validate_for_submit` (applies to initial *and* revision submit branches).
- **No-desired-date scoring (8.2):** weights stay constant at 50/5/20/10/15 always; `timeline_score = 100` for every vendor when the package has no desired date (package-wide constant → cancels out of ranking, zero renormalization code). Record `basis: "no_desired_date"` in `scoring_metadata`. *(Consumed by 8.2, not built here.)*
- **Revision prefill:** carry the vendor's *prior* `proposed_start_date` forward (mirrors `vendor_notes` / `total_amount`); editable.

**Touchpoints:**
- *Backend models:* `desired_start_date` on bid-package create/update/response models; `proposed_start_date` on submission draft/response models, `PortalBidPackageModel`, and `RevisionPrefillResponse`.
- *Backend write paths:* persist `desired_start_date` in package create; persist `proposed_start_date` in submission draft create/update (initial + revision share the insert); include in `build_revision_prefill` SELECT + return; include in submission/draft read selects.
- *Validation:* required-when-desired-present in `validate_for_submit` (both submit branches).
- *Email:* desired-date row in `bid_invitation` + `bid_revision_request`; proposed-date row in `bid_revision_submitted` (mirrors initial confirmation). Revision *request* endpoint needs no change — date stays pinned to the original package.
- *Frontend:* PM package form date picker (next to deadline); display in invitation email + `ProjectContextPanel`; proposed-date picker in `Step1CompanyInfo` (pre-filled, required-when-desired-present); plumb through `useBidFormState` (`companyInfo`), `DraftPayload`, `Step4Review`, and the revision prefill path (`RevisionPrefillResponse` type, `prefillToHydration`, `HYDRATE_FROM_PREFILL`).

**Out of scope:** all scoring logic (8.2); end-date/duration; any index/trigger change (none needed).

**Acceptance:**
- [ ] PM can set an optional desired start date on a bid package; it shows in the invitation email and vendor portal.
- [ ] Vendor form pre-fills proposed start date from the desired date; editable.
- [ ] Submit rejects null `proposed_start_date` when the package has a desired date; allows null when it doesn't — initial and revision.
- [ ] Revision prefill carries the vendor's prior proposed date forward.
- [ ] Both dates round-trip through draft save, submit, and read endpoints.

---

### Task 8.2: Weighted Scoring Engine — 10h

**Objective:** Compute a 0–100 weighted score per bid submission for a competitive
bid package, persist one `bid_scores` row per submission, and expose a
compute/recompute endpoint. Scoring is the data layer for the 8.3 comparison UI.

**Engine shape (cohort scorer):**
Price is relative (needs the whole set); the other four are absolute (per-submission).
So the unit is one bid package's current submissions, scored together.
- Five PURE per-dimension functions, each returning a 0–100 float, each independently testable.
- One orchestrator `score_bid_package(bid_package_id)` that loads the cohort, calls the
  five functions, applies weights, upserts `bid_scores`, snapshots metadata, returns the set.

**Cohort selection:** submissions on the package where
`is_superseded = FALSE AND is_draft = FALSE AND status IN ('submitted','under_review')`
AND `total_amount IS NOT NULL AND total_amount > 0`. Incomplete submissions (null/zero
total) are excluded — no score row written.

**Run semantics:**
- Competitive packages ONLY. Reject direct_assign / internal (single/synthetic submission,
  no competition → meaningless price score).
- On-demand (PM triggers at/after deadline), not on every submission — each new bid changes
  every price score, so mid-round scoring is unstable.
- Idempotent recompute: overwrites system-generated rows. (Manual-adjustment preservation,
  where `scored_by` is non-NULL, is handled when that feature lands later in Phase 8 — out
  of scope here; document the seam.)

**Weights (fixed, client-confirmed):** price 0.50, compliance 0.05, performance 0.20,
capacity 0.10, timeline 0.15. `total_weighted_score = Σ(weight × dimension)`, rounded to
2 dp, fits `DECIMAL(5,2)`.

**Dimension rubrics:**

- **Price (50%):** `price_score = (lowest_valid_total / this_total) × 100`, clamp ≤ 100.
  Lone valid bid → 100.

- **Compliance (5%):** mean of two components.
  - onboarding_status: complete=100, partial=50, pending=0
  - insurance vs the package `deadline` as horizon:
    `expiration_date >= deadline + 30d` → 100; `deadline <= expiration_date < deadline + 30d`
    → 50; expired (`< deadline`) or NULL → 0
  (Low-variance dimension by design: filter 7.4 + pre-award validation already block expired
  insurance, so most of the cohort will sit at/near 100. Expected, not a bug.)

- **Performance (20%):** `score_performance(vendor_id)` returns the constant
  `NEUTRAL_PERFORMANCE_SCORE = 75.0` for now. Real calc (on-time milestone rate + flag
  history) is Phase 10 — see /docs/DEFERRED.md. Function signature and call site are final;
  only the body changes later. Today every vendor is unproven → everyone gets 75, which is
  correct intended behavior.

- **Capacity (10%):** `available = max(max_active_jobs − current_active_jobs, 0)`;
  `capacity_score = available / max_active_jobs × 100`.
  - `max_active_jobs` NULL → `NEUTRAL_CAPACITY_SCORE = 75.0` (can't penalize uncollected data)
  - `max_active_jobs = 0` → 0 (no capacity)

- **Timeline (15%):** `proposed_start_date` (submission) vs `desired_start_date` (package).
  - package `desired_start_date` NULL → constant 100 for the whole cohort (neutralized; can't
    shift relative ranking). No weight renormalization for MVP.
  - else `days_late = proposed − desired`: ≤0 → 100; 1–7 → 75; 8–14 → 50; 15–30 → 25; >30 → 0
  - desired present but proposed NULL (shouldn't occur — required on submit) → guard to 0

**`scoring_metadata` (JSONB) snapshot per row:** rubric version string, the weights dict used,
per-dimension raw inputs + computed sub-scores, cohort size, computed_at. Keeps old rows
interpretable if weights ever change and makes the future manual-adjust path auditable.

**Endpoint:** `POST /v1/bid-packages/{bid_package_id}/scores` → compute + persist + return
scored cohort. Admin-authed via existing user middleware.
404 unknown package; 400 non-competitive package; 422 no valid submissions to score.

**Files (audit before assuming):** new scoring module under `backend/app/services/`;
`bid_scores` Pydantic models under `backend/app/models/`; endpoint on
`backend/app/routers/bid_packages.py`; tests under `backend/tests/scoring/`.
Reuses `vendors.insurance_expiration_date`, `vendors.max_active_jobs`,
`vendors.current_active_jobs`, `vendors.onboarding_status`,
`bid_submissions.total_amount` / `proposed_start_date`, `bid_packages.deadline` /
`desired_start_date`.

**Acceptance:** five pure dimension fns unit-tested in isolation incl. every edge case above;
orchestrator tested for competitive-only gate, cohort filtering, weight math, upsert/recompute
idempotency, metadata snapshot; endpoint tested for the three error codes + happy path.

---

### Task 8.3: Side-by-Side Comparison UI (~12h) — 📋 PLANNED (detail in later pass)

Responsive comparison table across all submitted bids in a package, sortable by price/score/timeline, color-coded indicators, expandable line-item detail (works *because* the structure is shared — per 8.1), recommended vendor highlighted, print-friendly view, export to Excel/PDF. Builds on the Recharts foundation from Phase 6. *To be specced in detail before implementation.*

### Task 8.4: Recommendation Engine (~8h) — 📋 PLANNED (detail in later pass)

Identify the highest-scoring vendor (recommendation only — **never auto-award**, award is 100% manual per Handoff §7.5). Justification report, 2nd/3rd alternatives, warning flags (over budget, late start, missing docs, expired insurance), PM override path with required justification. *To be specced in detail before implementation.*

---

## Phase 8 Acceptance Criteria (8.1)

- [ ] In-use detection: a template referenced by any non-cancelled bid package is treated as locked; cancelled-only references and zero references remain editable
- [ ] `PUT /bid-templates/{id}` returns 409 (naming the blocking package + status) when the template is in use; succeeds otherwise
- [ ] In-use edit is blocked *before* any mutation — no partial item delete/re-insert occurs on a rejected PUT
- [ ] `DELETE /bid-templates/{id}` continues to be blocked by FK RESTRICT and now returns a 409 that lists the referencing package(s) and their status
- [ ] `POST /bid-templates/{id}/duplicate` exists (built if absent), deep-copies items with fresh IDs, sets `created_by`, returns the new template
- [ ] `GET /bid-templates/{id}` and list endpoint expose `is_in_use` so the UI renders the locked state without a 409 round-trip
- [ ] Template management UI disables Save + shows the "in use — duplicate to change" banner and a working Duplicate action when the open template is in use
- [ ] Mid-bid draft leak is closed as a consequence of the edit guard (no template-structure change can reach an in-progress draft on its next save)
- [ ] No schema change introduced; no change to scoring or comparison behavior in 8.1
- [ ] Unit tests cover the in-use helper, edit guard, delete message, and duplicate deep-copy; frontend test covers the locked-state banner + duplicate

---

## Next Phase Preview

**Phase 9: Award Decision & Contract Generation (40h)** — Pre-award validation (start-date feasibility, insurance through completion, bonding, capacity, ±5% budget variance), override workflow, DocuSign integration, award/decline emails, direct-assign synthetic submission flow.

---

## References

- Full project plan: `docs/PROJECT_PLAN.pdf` (v2.3, 12 phases)
- Database schema: `database/bluonx_complete_schema_v2_31.sql`
- RLS policies: `database/rls_policies.sql`
- Storage policies: `database/storage_rls_policies.sql`
- Handoff document: `docs/BluOnX_Context_Handoff.md`
- Deferred tasks: `docs/DEFERRED.md`
