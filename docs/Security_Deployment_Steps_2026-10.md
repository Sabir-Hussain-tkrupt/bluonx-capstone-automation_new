# Security Fix: Deployment Steps (October 2026)

Everything below is already changed in the code. These are the steps **you** run to ship it. Do them in order, **dev first, then production**.

Verified locally before handing over:
- Backend: 1469 tests pass, 0 fail (Python 3.11.17, new packages). `pip-audit` reports no known vulnerabilities.
- Frontend: 578 tests pass, production build succeeds, `npm audit` reports 0 vulnerabilities.
- Real API started locally with the new packages: health, auth, Supabase connection, webhooks, and the new 413 limits all behave correctly.

---

## Step 0: Commit

Commit the working tree. New files to include:
`backend/app/core/body_limit.py`, `backend/app/core/host_validation.py`, `backend/tests/security/`, and the two `docs/Security_*` files.

---

## Step 1: Local check on your machine (optional, about 5 minutes)

```bash
cd backend
pip install -r requirements.txt
pytest
```
Expected: `1469 passed`. You need Python 3.11.

```bash
cd frontend
npm ci
npm test
npm run build
```
Expected: all tests pass and the build finishes.

---

## Step 2: Two new environment variables (do this BEFORE deploying the backend)

Add them to the ECS task definition (environment, or Secrets Manager / SSM), **for both dev and prod**:

| Variable | Dev value | Prod value | What happens if missing |
|---|---|---|---|
| `SES_SNS_TOPIC_ARN` | ARN of the dev SES events topic, e.g. `arn:aws:sns:us-east-1:314727362874:bluonx-ses-events-dev` | ARN of the prod SES events topic | **The SES webhook rejects everything, so delivery, bounce and complaint statuses stop updating.** Required. |
| `ALLOWED_HOSTS` | `["dev.api.bluonx.com"]` | `["api.bluonx.com"]` | Host check stays off (safe, just not hardened) |

To find the topic ARN: **AWS Console → SNS → Topics**, the topic your SES configuration set publishes to. Copy the ARN.

`ALLOWED_HOSTS` must be a JSON array, with the brackets and quotes. `/health` stays reachable by IP, so ALB health checks are not affected.

How to add them: **ECS → Task definitions → (backend task) → Create new revision → Container → Environment variables → Add**. Save the revision; the service update in Step 3 uses it.

---

## Step 3: Backend, build and deploy the Docker image (dev first)

The Dockerfile now pins `python:3.11.17-slim-trixie` and applies Debian security updates during the build. Run from the repo root, with Docker Desktop running:

```bash
docker build --no-cache --pull -t bluonx-backend:sec-2026-10 ./backend
```

Optional quick check that the image starts:
```bash
docker run --rm --env-file backend/.env -p 8000:8000 bluonx-backend:sec-2026-10
```
Then open http://localhost:8000/health. It should return `{"status":"healthy"...}`. Stop it with Ctrl+C.
*(Note: with your local `.env` this connects to Supabase and starts the scheduler, as the app normally does.)*

Push to ECR (replace `<ACCOUNT>`, `<REGION>` and the repo name with yours, e.g. `bluonx-backend-dev`):
```bash
aws ecr get-login-password --region <REGION> | docker login --username AWS --password-stdin <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com
```
```bash
docker tag bluonx-backend:sec-2026-10 <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/bluonx-backend-dev:latest
```
```bash
docker tag bluonx-backend:sec-2026-10 <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/bluonx-backend-dev:sec-2026-10
```
```bash
docker push --all-tags <ACCOUNT>.dkr.ecr.<REGION>.amazonaws.com/bluonx-backend-dev
```

Deploy: **ECS → Cluster → backend service → Update → select the new task definition revision from Step 2 → check "Force new deployment" → Update**.
Because the service runs 1 task with minimum healthy 0%, expect a few seconds of downtime.

---

## Step 4: Verify the backend on dev

```bash
curl https://dev.api.bluonx.com/health
```
Expect: `200 {"status":"healthy",...}`

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://dev.api.bluonx.com/api/v1/users/me
```
Expect: `401` (was 403 before; this is the new FastAPI behavior and the frontend already handles it).

Oversized-upload protection (the main fix). Run from Git Bash or Linux/macOS:
```bash
head -c 60000000 /dev/zero > big.bin
```
```bash
curl -s -w "\n%{http_code}\n" -X POST -H "content-type: multipart/form-data; boundary=x" --data-binary @big.bin https://dev.api.bluonx.com/api/v1/projects/00000000-0000-0000-0000-000000000000/documents
```
Expect: `413` with "Request body exceeds the 51MB limit".

Then click through the app on the dev Amplify site:
1. Staff login works.
2. Upload a project document (PDF) and a vendor document.
3. Open a vendor bid link, upload an attachment, and submit.
4. Send a test email (e.g. resend a bid invite). Then in **CloudWatch Logs** check for `SNS event received: type=Delivery`, and make sure you **don't** see `Unexpected SNS topic`. If you do see it, the `SES_SNS_TOPIC_ARN` value is wrong.
5. In CloudWatch, the startup logs show no errors.

---

## Step 5: Frontend (AWS Amplify)

Only `package.json` / `package-lock.json` and 3 test files changed. Amplify rebuilds automatically when you push to the connected branch.

1. Push to the dev branch, then wait for the Amplify build to go green.
2. Set the Node version Amplify builds with (one time): **Amplify Console → App → Hosting → Build settings → Build image settings → Edit → Live package updates → add "Node.js" version `22`** (or `24`). Save and redeploy.
3. Open the dev site and repeat the click-through from Step 4.

---

## Step 6: Production

Only after dev looks good:
1. Make sure the prod ECS task definition has `SES_SNS_TOPIC_ARN` (prod topic) and `ALLOWED_HOSTS=["api.bluonx.com"]` (Step 2).
2. Tag and push the **same image** you tested on dev to the prod ECR repo (Step 3 commands, prod repo name), then **Force new deployment** in a quiet hour.
3. Merge/push the frontend to the prod branch for Amplify.
4. Repeat the Step 4 checks against `api.bluonx.com` and the prod app.

**Rollback if needed:** ECS → update service → choose the previous task definition revision (old image) → Force new deployment. Amplify → redeploy the previous build.

---

## Step 7: AWS hardening (recommended, no code needed)

These are console settings. They add protection on top of the code fixes.

1. **ECR → repository → Edit → Scan on push: ON.**
2. **EC2 → Load Balancers → (API ALB) → Attributes:**
   - "Drop invalid header fields": **On**
   - "Desync mitigation mode": **Defensive**
3. **AWS WAF → Create web ACL → attach to the API ALB:**
   - Rate-based rule: block an IP above ~1000 requests per 5 minutes.
   - Add the AWS managed rule group "Core rule set". Set its `SizeRestrictions_BODY` rule to **Count** (not Block), or it will block normal file uploads.
4. **CloudWatch alarms:** ECS running task count < 1, ALB 5xx count, unhealthy target count.

---

## Step 8: Supabase checks (dashboard, both projects)

No code changes are needed for Supabase.
1. **Project Settings → Infrastructure:** if a Postgres upgrade is offered, schedule it (short restart).
2. **Advisors → Security Advisor:** fix any red items (RLS disabled, mutable search_path, etc.).
3. **Storage:** confirm the 3 buckets are **private**.
4. Keys do **not** need rotating. There's no sign of exposure.

---

## What changed, in one list (for the commit message / PR)

**Security fixes**
- FastAPI 0.115 → 0.161, Starlette 0.46 → 1.9 (7 CVEs; unauthenticated DoS through uploads and forms), cryptography 44 → 50 (bundled OpenSSL), uvicorn 0.54, python-multipart 0.0.32, Pillow ≥ 13, pytest 9.0.3.
- Request body size limits (413) before any parsing or auth: 51 MB for document uploads, 11 MB for vendor attachments, 2 MB for everything else.
- Uploads are read in 1 MB chunks and stop at the limit; Supabase storage uploads run off the event loop.
- SES/SNS webhook: accepts only our topic (`SES_SNS_TOPIC_ARN`), caches the signing certificate, and no longer blocks the server while fetching it.
- Rate limiter uses the ALB-appended client IP, so it can't be bypassed with a fake `X-Forwarded-For`.
- Optional Host header allow list (`ALLOWED_HOSTS`).
- uvicorn: `--limit-concurrency 200`, `--timeout-keep-alive 65` (above the ALB's 60s idle timeout).
- Docker base image pinned to `python:3.11.17-slim-trixie`, plus Debian security updates.
- Frontend: axios 1.20, react-router-dom 7.18.4, vite 7.3.7, vitest 4.1.12, plus transitive fixes (0 npm audit findings).

**Behavior change to know about**
- A request with **no** `Authorization` header now gets **401** instead of 403 (FastAPI change). The frontend already treats 401 as "session expired".

**Tests**
- 9 long-failing backend tests and 3 frontend tests updated to match deliberate earlier changes (DocuSign health is admin-only, the "BluOnX" sender name, wider allowed file types, the W-9/MTA onboarding rule, the invite duplicate check).
- 30+ new tests for the security fixes.
