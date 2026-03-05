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
