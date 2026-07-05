# Deferred Items

Items intentionally deferred during implementation. Reference this file when moving to production or starting later phases.

---

## Task 1.9 — AWS Infrastructure
- **Blocked:** Awaiting AWS credentials from client.
- ECS task definitions / Lambda configuration
- CI/CD pipeline (GitHub Actions → AWS)
- Production environment variable management (Secrets Manager / Parameter Store)

## Task 2.6 — FastAPI Backend Scaffold

- **CORS production origin:** Currently `http://localhost:5173`. Add Vercel/production domain to `CORS_ORIGINS` in `backend/.env` before deploy.
- **Frontend type alignment:** Frontend placeholder types (`Vendor`, `Project` in `frontend/src/features/`) don't match actual DB schema columns. Update when building Phase 3 CRUD pages.
- **ECS/Lambda deployment config:** Dockerfile is ready, but no AWS-specific deployment manifests. Depends on Task 1.9.
- **Request logging middleware:** Not added to scaffold. Add structured logging (correlation IDs, request timing) during production hardening.
- **Test infrastructure:** No pytest setup, fixtures, or test database. Add in testing phase.

## Past Performance Scoring (Task 8.2 → completed in Phase 10)

`backend/app/services/bid_scoring_service.py::score_performance(vendor_id)` currently returns the module constant `NEUTRAL_PERFORMANCE_SCORE` (75.0) as a placeholder. Every vendor receives 75 because there is no on-time-completion data to derive a real score from yet — which is the intended interim behaviour (every vendor is unproven).

**Real implementation (Phase 10, once milestone data lands):**
on-time milestone completion rate (computed from the `milestones` table that ships in Phase 10) blended with `vendor_flags` history.

**Single touchpoint to change:** the body of `score_performance(vendor_id)` in `backend/app/services/bid_scoring_service.py`. The orchestrator (`score_bid_package`), `WEIGHTS`, `scoring_metadata` snapshot shape, the `POST /bid-packages/{id}/scores` endpoint, and the tests for the other four dimensions all stay as-is. The follow-up work in Phase 10 is just:

1. Replace the function body so it queries milestones + vendor_flags.
2. Update `backend/tests/scoring/test_dimension_performance.py` — replace the placeholder assertions with real on-time-rate / flag-history cases.

Anything in the engine that depends on this dimension already routes through the constant, so no other call site needs to change.

## Per-document "missing docs" warning (Task 8.4)

Task 8.4's warning-flag set ships with `onboarding_incomplete`, which covers the MVP need: a single signal that the vendor's onboarding paperwork is not fully in place. A finer-grained per-document warning ("missing W-9", "missing COI", etc.) was considered and deferred. It would require:

1. Plumbing the per-document checklist from `vendor_documents` (and the onboarding requirement table that drives it) into `scoring_metadata.inputs` so the recommendation builder can derive truthful per-doc flags.
2. UI surface in 8.3's flag-chip layer to display N codes per vendor.

`onboarding_incomplete` is intentionally labeled by the *enum status*, not by "missing docs," to stay truthful to the data the metadata snapshot actually carries today. Revisit when vendor-document plumbing reaches the scoring inputs.

## Manual score adjustment (Task 8.4)

The `bid_scores.scored_by` column was provisioned in Phase 8.2 as a dormant seam: NULL means the row is system-generated; non-NULL would mark a manual adjustment. Task 8.4 confirmed it remains dormant for MVP — manual override is **not** built.

Rationale: PM discretion is exercised at award time (Phase 9), where `awards.override_justification` captures the reason for picking against the recommendation. There is no second discretionary lever needed at scoring time, and adding one would split judgment across two surfaces.

If a manual-adjustment write path is ever added, the orchestrator at `backend/app/services/bid_scoring_service.py` already preserves manual rows on recompute (rows where `scored_by IS NOT NULL` are filtered before upsert), so no further change to scoring is required.

## Contract payment terms — placeholder text (Task 9.x)

**MUST be replaced with the client's real subcontract payment terms before production.** The contract PDF currently ships a placeholder: `DEFAULT_PAYMENT_TERMS` in `backend/app/services/contract_pdf.py` ("Net 30 days ... [Placeholder — client subcontract terms pending.]"). It fills the PAYMENT TERMS clause whenever no `payment_terms` value is supplied on the contract, which is the case today (the contract row is born with `payment_terms = NULL`), so **every generated contract renders the placeholder**. Shipping this to a real vendor would put unverified, non-authoritative payment language into a signed legal document.

**Touchpoints to finalize:**
1. `DEFAULT_PAYMENT_TERMS` in `backend/app/services/contract_pdf.py` — replace with the client-approved terms text (or remove the "[Placeholder ...]" tag once approved).
2. `backend/app/templates/contracts/firm_terms.txt.j2` — the whole terms body is the ISOLATED, SWAPPABLE template flagged for the client's own boilerplate (decision #2); swap it wholesale when the client provides subcontract language.
3. If terms should vary per contract rather than being firm-wide boilerplate, populate `contracts.payment_terms` at envelope-send in `contract_envelope_service.send_contract_envelope` (currently left NULL, which is why the default fires).

Related: the same swappable template also carries the schedule/validity clauses and the dormant "Date of signed scope of work" seam — see Task 9.8.
