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
