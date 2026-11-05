# BluOnX Security Remediation Plan (October 2026 advisories)

Status: **PLAN ONLY, nothing changed yet.** Prepared 2026-10-23 for review.

Evidence used: `pip-audit` against the exact versions `backend/requirements.txt` resolves to today, `npm audit` on `frontend/package-lock.json`, and a read of the code paths each advisory needs before it can be exploited.

---

## 1. Verdict per advisory

| Advisory | In BluOnX? | Real risk to us | Action |
|---|---|---|---|
| Next.js / React Server Components RCE | **No.** Frontend is Vite + React 19 SPA (`BrowserRouter`), no Next.js, no RSC, no SSR | None | None |
| PHP libraries | **No.** Zero PHP | None | None |
| Python 3.11 runtime | **Yes**, `python:3.11-slim` (floating tag) in `backend/Dockerfile` | Depends on the image ECS last pulled | Pin `python:3.11.17-slim-bookworm` and rebuild |
| **Starlette (under FastAPI)** | **Yes**, 0.46.2 (held there by `fastapi<0.116`) | **HIGH**: unauthenticated DoS of the single production container | Upgrade FastAPI to 0.161 / Starlette 1.9, plus body-size limits |
| cryptography | **Yes**, 44.0.3 (capped by `<45.0`) | Medium: bundled OpenSSL is old; other CVEs are in features we don't use | Upgrade to 50.x |
| Pillow | **Yes, indirectly** (reportlab dependency). Resolves to 13.0.0 today, but an old image may have older | Low: we never open user images with Pillow | Pin `pillow>=13.0` for traceability |
| pytest | Yes, **and it ships in the production image** (it's in `requirements.txt`) | Low | Move to `requirements-dev.txt` |
| Frontend npm (axios, react-router, form-data…) | Yes | Low: SSR/Node-only bugs don't apply to a browser SPA | `npm audit fix` (non-breaking) |
| Frontend build tools (vite, vitest, rollup, esbuild, postcss) | Yes, build/dev only | Low for prod; **medium for devs on Windows** (vite/esbuild dev-server file read) | `npm audit fix` |
| Node.js | Build only (Amplify + local) | Low, no Node server in production | Node 22.23.4 / 24.22.1 on Amplify and locally |
| Supabase | Managed service | No advisory hits our client libs | Dashboard checks (section 6) |

---

## 2. Findings, highest priority first

### P0. Starlette: unauthenticated DoS on `api.bluonx.com` (7 CVEs, 4 apply)

Installed: starlette **0.46.2**. Cause: `fastapi>=0.115,<0.116` requires `starlette<0.47`.

| CVE (fix version) | Applies? | Why |
|---|---|---|
| PYSEC-2026-1941, large multipart files block the event loop on spool rollover (0.47.2) | **Yes** | 3 upload endpoints: `projects.py:505`, `vendors.py:951`, `vendor_portal.py:887` |
| PYSEC-2026-249, `max_fields` / `max_part_size` skipped for urlencoded forms (1.3.1) | **Yes** | Every endpoint with `Form(...)` also accepts `application/x-www-form-urlencoded` |
| PYSEC-2026-161 / -248, unvalidated Host header and path used to rebuild `request.url` (1.0.1 / 1.3.0) | Partial | FastAPI's trailing-slash redirect builds its URL from `request.url`, so Host-header poisoning or open redirect is possible |
| PYSEC-2026-1942, Range header quadratic time (0.49.1) | No | We serve no `FileResponse` / `StaticFiles` |
| PYSEC-2026-2280 / -2281, HTTPEndpoint / Windows StaticFiles (1.1.0) | No | Not used |

**Why "logged-in only" endpoints don't protect us:** FastAPI parses the request body **before** it runs `Depends(get_current_active_user)` / `get_vendor_context`. An anonymous attacker can send a huge multipart or urlencoded body to an upload URL, and the parser does all the expensive work before the 401.

**Why the impact is total:** ECS runs `desiredCount = 1` by design (APScheduler must not run twice). One hung event loop means the whole API is down for everyone.

**Related weaknesses in our own code that make this worse** (fixed in the same phase):
1. **No request-size cap anywhere.** The ALB doesn't limit body size, and neither do uvicorn or the app. The webhook routes (`/webhooks/ses-notifications`, `/webhooks/docusign-connect`) read unbounded bodies before checking any signature.
2. **Uploads load the whole file into RAM** (`await file.read()`, up to 50 MB). On a 1 GB task, about 15-20 concurrent 50 MB uploads cause an out-of-memory kill.
3. **The SNS webhook blocks the event loop.** `webhooks.py:101` makes a synchronous `httpx.get(cert_url, timeout=10)` inside an `async def`. Anyone can POST an SNS-shaped body pointing at a real AWS cert URL with a garbage signature, and each request freezes the server for the length of the download. It's unauthenticated and cheap to send. It also doesn't pin `TopicArn`, so any AWS account's SNS topic gets auto-confirmed.
4. **The rate limiter trusts the first `X-Forwarded-For` hop** (`rate_limit.py:31`), which the client controls. An attacker can rotate fake IPs and never hit the 429. Behind an ALB, the trustworthy value is the **last** hop.

### P1. cryptography 44.0.3 (6 CVEs)

| CVE | Applies? |
|---|---|
| GHSA-537c-gmf6-5ccf, statically bundled OpenSSL is outdated (fix 48.0.1) | **Yes.** It's the OpenSSL behind JWT ES256 verification (PyJWT), the DocuSign RSA signing, and SNS cert parsing |
| PYSEC-2026-35 / -3553 / -3554, X.509 name-constraint and chain-building issues | No. We don't build or verify certificate chains, we only load a single SNS cert |
| PYSEC-2026-2141, EC public key from numbers | No direct use |
| PYSEC-2026-3552, PKCS7 decrypt | Not used |

Fix: `cryptography>=50.0,<51.0`. Check that `docusign-esign` and PyJWT resolve cleanly with it.

### P2. Docker base image / OS packages

- `FROM python:3.11-slim` floats. Whatever was cached when the ECS image was last built is what's running now. 3.11.17 is the current 3.11 release, published 2026-10-01; 3.11 is security-only until 2027-10.
- No ECR image scanning is mentioned in the deploy docs.

### P3. Frontend (24 npm findings: 1 critical, 16 high)

Shipped to browsers: **axios 1.13.5** (needs ≥1.20.0), **react-router(-dom) 7.13.0** (needs ≥7.18.2), follow-redirects, form-data.
- react-router's RCE, CSRF, and DoS findings are all **SSR / framework-mode / RSC** bugs. We use declarative `BrowserRouter` only, so they don't apply. The `<Link>` / `useNavigate` backslash open-redirect is client-side, but no code feeds user-controlled paths into `navigate()`.
- axios's SSRF, proxy, and stream findings are **Node HTTP adapter** bugs. In the browser, axios uses XHR/fetch. The prototype-pollution gadgets need a separate pollution bug first.

Build/dev only: vitest (critical), vite, rollup, esbuild, postcss, ws, etc. They aren't in `dist/`, but **vite/esbuild dev-server arbitrary file read on Windows** matters because the team develops on Windows.

`tailwindcss` and `@tailwindcss/vite` are in `dependencies` but are build-only, which is why build tools show up as "production" in audits.

### P4. pytest in the production image

`requirements.txt` mixes runtime and test dependencies, so pytest and pytest-asyncio are installed in the Fargate image. PYSEC-2026-1845 is a `/tmp` race that only matters when pytest runs. It's low risk, but test tools shouldn't ship to production.

---

## 3. Implementation plan

### Phase 1: Backend dependency upgrade (P0 + P1 + P4), about half a day including tests

1. **`backend/requirements.txt`** (runtime only):
   ```
   fastapi>=0.161,<0.162
   starlette>=1.9,<2.0          # explicit, so the CVE floor is visible
   uvicorn[standard]>=0.54,<0.55
   python-multipart>=0.0.32,<1.0
   cryptography>=50.0,<51.0
   pillow>=13.0,<14.0           # transitive via reportlab; pinned for audit traceability
   reportlab>=4.5,<5.0
   ```
   (other lines unchanged; pytest lines removed)
2. **New `backend/requirements-dev.txt`**: `-r requirements.txt`, `pytest>=9.0.3,<10`, `pytest-asyncio` (bump to a version compatible with pytest 9).
3. Update the `api-test` service in `docker-compose.yml` to install the dev requirements (a small `test` build stage or `pip install -r requirements-dev.txt` at run).
4. **Optional but recommended:** generate a lock file (`pip-compile` → `requirements.lock`) so the image is reproducible and auditable. Right now each `--no-cache` build can pull different transitive versions.
5. **Compatibility fixes for FastAPI 0.115 → 0.161 / Starlette 0.46 → 1.9** (verified locally, the imports we use still exist):
   - `status.HTTP_422_UNPROCESSABLE_ENTITY` (about 40 call sites) still works but now emits `StarletteDeprecationWarning`. Rename to `HTTP_422_UNPROCESSABLE_CONTENT`; it's the same value and purely mechanical.
   - `starlette.concurrency.run_in_threadpool`, the pure-ASGI `RequestLoggingMiddleware`, `lifespan=`, and `TestClient` are all still supported.
   - Run the full hermetic suite (`pytest`) and then `pytest -m requires_db` against the dev Supabase project.

### Phase 2: DoS hardening in our own code (P0 related), about half a day

1. **Body-size limit middleware** (pure ASGI, next to `RequestLoggingMiddleware`). It rejects with 413 when `Content-Length` exceeds the limit, and counts streamed bytes for chunked bodies. Limits: about 52 MB for the 2 document-upload routes, 11 MB for the vendor attachment route, 1 MB for everything else (JSON APIs and webhooks).
2. **Starlette form limits.** With Starlette ≥1.3.1, `max_part_size` and `max_fields` now also cover urlencoded bodies. Keep the defaults or set them explicitly.
3. **Uploads:** read in chunks with a running cap instead of `await file.read()` of the whole stream, and run the synchronous Supabase storage upload in `run_in_threadpool` so a 50 MB push to Supabase doesn't block the event loop.
4. **SNS webhook:**
   - Check `TopicArn` against a new `SES_SNS_TOPIC_ARN` setting **before** any network call.
   - Fetch the signing cert with the async httpx client in a threadpool and **cache it by URL** (AWS reuses it).
   - Only auto-confirm subscriptions for the pinned topic.
5. **Rate limiter / client IP:** use the **right-most** `X-Forwarded-For` entry (the one the ALB appends), or run uvicorn with `--proxy-headers --forwarded-allow-ips=<VPC CIDR>` and read `request.client.host`.
6. **Uvicorn flags** in the Dockerfile `CMD`: `--proxy-headers --forwarded-allow-ips=<VPC CIDR> --limit-concurrency 200 --timeout-keep-alive 5`.
7. **Host header:** add `TrustedHostMiddleware(allowed_hosts=[api domain, dev api domain, localhost])` driven by settings, like `CORS_ORIGINS`.
8. Add tests: 413 on an oversized body to each upload route **without** auth, SNS wrong-topic rejection, and XFF spoofing.

### Phase 3: Docker image + AWS ECS / ECR / ALB, about 2 hours

1. **Dockerfile:** `FROM python:3.11.17-slim-bookworm` in **both** stages (ideally pinned by `@sha256:` digest), and in the runtime stage add `apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*` to pick up Debian security fixes. Remove the dead `scripts/entrypoint.sh` or wire it in (the `CMD` duplicates it).
2. Build with `--no-cache --pull`. Tag `latest` **plus** an immutable tag (date or commit) so rollback is possible.
3. **ECR:** turn on *scan on push* (or Inspector enhanced scanning) and set tag immutability for release tags.
4. **ECS:** force a new deployment. Keep `desiredCount = 1` (APScheduler). Make sure the ALB health check on `/health` plus ECS auto-restart is on, and add the CloudWatch alarms from the Technical Overview (§ monitoring): running tasks < 1, ALB 5xx, unhealthy targets.
5. **ALB:**
   - Attach **AWS WAF**: a rate-based rule per IP (for example 1000 requests / 5 min overall, tighter on `POST /api/v1/*/documents` and `/attachments`) plus the AWS Managed Core Rule Set (`SizeRestrictions_BODY` set to *count* on upload paths so legitimate uploads still pass).
   - Turn on `routing.http.drop_invalid_header_fields` and desync mitigation mode **defensive** (or strictest).
   - Add a listener rule that forwards only when `Host` is the API domain and returns a fixed 404 otherwise, as an extra Host-header guard.
6. Verify the security group allows port 8000 **only** from the ALB SG (as documented).

### Phase 4: Frontend + AWS Amplify, about 1 hour

1. In `frontend/`: `npm audit fix` (all 24 fixes are within the current semver ranges, so no `--force` is needed). Then confirm `axios ≥ 1.20.0`, `react-router-dom ≥ 7.18.2`, `vite ≥ 7.3.7`, `vitest` latest 4.x.
2. Move `tailwindcss` and `@tailwindcss/vite` to `devDependencies`, so `npm audit --omit=dev` shows only what actually ships.
3. Run `npm run lint`, `npm test`, `npm run build`, then smoke-test login, vendor portal upload, and milestone links in the dev Amplify app.
4. **Amplify console:** set the build image's Node to **22.23.4 or 24.22.1** (Build settings → Build image settings → Live package updates → Node.js), or pin it in a committed `amplify.yml` (`nvm install 22`). The build spec isn't in the repo today, so committing `amplify.yml` makes it reviewable.
5. Optional hardening: Amplify **custom headers** (`Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options: DENY`, a CSP allowing self + Supabase + API domain + Google Maps).
6. **Local dev machines:** update Node to the latest 22/24 patch, and don't run `vite --host` on shared networks until vite is updated (Windows file-read bug).

### Phase 5: Supabase (no code change expected), about 30 minutes in the dashboard

The advisories don't hit our Supabase client libraries (`supabase` py 2.33.0, `supabase-js` 2.97.0; neither shows up in either audit). The backend talks to Supabase only over HTTPS (PostgREST / Storage / Auth), not direct Postgres connections. Checklist for **both** dev and prod projects:
1. **Settings → Infrastructure:** apply any pending Postgres version / security upgrade (it causes a short restart, so schedule it).
2. **Advisors → Security Advisor:** fix any "RLS disabled", "function search_path mutable", or "security definer view" warnings.
3. **Database → Network Restrictions:** since we never connect directly to Postgres from ECS, restrict direct DB access to the team's IPs only. SSL enforcement should be on.
4. **Storage:** confirm all 3 buckets are still private with the 50 MB / 10 MB `file_size_limit` from `database/storage_rls_policies.sql`.
5. **Keys:** service-role key only in ECS Secrets Manager; only the anon key in Amplify env vars. There's no sign of compromise, so **rotation isn't required**.
6. **Auth → Rate limits:** review the defaults for sign-in and password reset.

### Phase 6: Rollout order and verification

1. Dev first: deploy backend (Phases 1-3) to `dev.api`, frontend (Phase 4) to the dev Amplify branch. Run full tests plus a manual smoke test (staff login, create bid package with SoW upload, vendor magic link with attachment, DocuSign send, SES webhook test notification).
2. Re-run `pip-audit` inside the built image (`docker run --rm <image> pip-audit`) and `npm audit --omit=dev`. Both should be clean or show only accepted, non-applicable items.
3. Verify the DoS fix: an anonymous `curl` with a 100 MB body to `/api/v1/projects/<id>/documents` should get **413 immediately**, while `/health` keeps responding during the test.
4. Production: same image digest promoted to the prod ECR repo, deployed with force-new-deployment in a low-traffic window. With min healthy 0% there's a few seconds of downtime, so announce it.
5. Rollback: the previous immutable image tag (ECS) / the previous Amplify build.

---

## 4. Effort summary

| Phase | What | Effort | Risk of change |
|---|---|---|---|
| 1 | FastAPI/Starlette/cryptography upgrade, split dev deps | ~4 h | Medium (big version jump, covered by test suite) |
| 2 | Size limits, chunked uploads, SNS fix, XFF, uvicorn flags, TrustedHost | ~4 h | Low-medium |
| 3 | Docker pin + ECR scan + WAF + ALB settings | ~2 h | Low |
| 4 | npm audit fix + Amplify Node version | ~1 h | Low |
| 5 | Supabase dashboard checks | ~30 min | Low |
| 6 | Dev → prod rollout and verification | ~2 h | — |


Koi breaking change na ho
keep also this in mind 
do also keep this in mind