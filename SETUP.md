# BluOnX — Local Setup Guide

Get the app running on a fresh machine. Three moving parts:

| Part | Runs where | How you start it |
|------|-----------|------------------|
| **Backend** (FastAPI) | Docker container | `docker compose up` |
| **Frontend** (React + Vite) | Node dev server | `npm run dev` |
| **Database + Auth** (Postgres) | **Supabase (cloud)** | nothing to run — you connect to it |

> **The one thing to understand first:** the database and auth are **not** local. They live in Supabase. So "running locally" means the frontend and backend on your machine talk to a Supabase project in the cloud. You need credentials for that project (see Step 2).

---

## 1. Prerequisites

Install these once:

- **Docker Desktop** (runs the backend — no Python/venv needed) — https://www.docker.com/products/docker-desktop
- **Node.js 18+** and npm (runs the frontend) — https://nodejs.org
- **Git**

Verify:

```bash
docker --version      # 24+ recommended
node --version        # v18 or newer
```

---

## 2. Get the credentials

You need secrets from the project owner. **Ask them for a filled-in `backend/.env` and `frontend/.env`, or the individual values below.** These are secrets — share them privately (password manager / DM), never commit them.

**Backend needs:**

| Variable | What it is |
|----------|-----------|
| `SUPABASE_URL` | The Supabase project URL (`https://<ref>.supabase.co`) |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role key (backend bypasses RLS with this — keep secret) |
| `SUPABASE_JWT_SECRET` | Supabase JWT signing secret (validates admin/PM logins) |
| `VENDOR_JWT_SECRET` | Separate secret for vendor-portal tokens (**must differ** from the one above) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | AWS keys for sending email via SES (see Step 4) |
| `SES_FROM_EMAIL` | A sender address **verified in AWS SES** |

**Frontend needs:**

| Variable | What it is |
|----------|-----------|
| `VITE_SUPABASE_URL` | Same Supabase URL as above |
| `VITE_SUPABASE_ANON_KEY` | The Supabase **anon** key (safe for the browser; RLS protects it) |
| `VITE_API_BASE_URL` | Backend URL — leave the default `http://localhost:8000` |

> **Alternative — your own Supabase project:** If you want a fully isolated database instead of sharing the owner's, create a free project at supabase.com, then run these SQL files in the Supabase SQL editor **in order**: [`database/bluonx_complete_schema.sql`](database/bluonx_complete_schema.sql) → [`database/rls_policies.sql`](database/rls_policies.sql) → [`database/storage_rls_policies.sql`](database/storage_rls_policies.sql). Then use *your* project's URL/keys above. This takes ~20 min and you start with an empty database.

---

## 3. Clone and configure

```bash
git clone https://github.com/awais-anwer/bluonx-capstone-automation.git
cd bluonx-capstone-automation

# Backend env
cp backend/.env.example backend/.env
#   → open backend/.env and fill in the values from Step 2

# Frontend env
cp frontend/.env.example frontend/.env
#   → open frontend/.env and fill in the values from Step 2
```

Both `.env` files are gitignored — they never get committed.

---

## 4. Email configuration (real sending)

This project sends **real email** through AWS SES (bid invitations, reminders, award notices, milestone alerts). In `backend/.env`:

```ini
EMAIL_PROVIDER=ses
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
SES_FROM_EMAIL=verified-sender@yourdomain.com
```

> ⚠️ **Real emails go out.** With `EMAIL_PROVIDER=ses`, actions like sending a bid invitation will actually email real vendors/contacts. When experimenting, use test addresses you control.
>
> - The backend **refuses to start** if `EMAIL_PROVIDER=ses` but the AWS keys are missing.
> - `SES_FROM_EMAIL` must be a **verified identity** in the SES account, or sends fail.
> - Keep `APP_ENV=development` for local work. (Setting `APP_ENV=production` forces `ses` and adds other prod guards you don't want locally.)
> - Want to avoid sending anything while you poke around? Set `EMAIL_PROVIDER=mock` — no email leaves your machine.

---

## 5. Run it

**Backend** (from the repo root):

```bash
docker compose up --build      # first run builds the image; later runs: docker compose up
```

The API comes up on **http://localhost:8000**. Check it: open http://localhost:8000/health (should return `{"status":"ok"}`) or the interactive docs at http://localhost:8000/docs.

**Frontend** (in a second terminal):

```bash
cd frontend
npm install
npm run dev
```

The app opens on **http://localhost:5173**. Log in with a Supabase user for the project (ask the owner to invite you, or create one in Supabase Auth).

---

## 6. Day-to-day

| Task | Command |
|------|---------|
| Start backend | `docker compose up` (root) |
| Stop backend | `docker compose down` (or Ctrl-C) |
| Rebuild backend after dependency changes | `docker compose up --build` |
| View backend logs | `docker compose logs -f api` |
| Start frontend | `cd frontend && npm run dev` |
| Frontend production build | `cd frontend && npm run build` |
| Run backend tests | `docker compose run --rm api-test` |

### Backend tests

```bash
docker compose run --rm api-test
```

That runs the hermetic suite: no database, no credentials, no network. It is the
default and it is what you should get green before pushing. (Note: the command
this file used to document, `docker compose run --rm api pytest`, collected
**zero** tests and exited without an error, which looked exactly like a pass.
The `api` image does not contain `tests/`. The `api-test` service mounts them.)

A small number of tests exercise SQL triggers, business-day functions and RPC
grants, which cannot be meaningfully mocked. They are marked `requires_db` and
are **deselected by default**:

| Command | Runs |
|---------|------|
| `docker compose run --rm api-test` | the hermetic suite (default) |
| `docker compose run --rm api-test pytest -m requires_db` | only the live-database tests |
| `docker compose run --rm api-test pytest -m ""` | everything |

Working in a local virtualenv instead of Docker? Drop the prefix and run
`pytest`, `pytest -m requires_db` or `pytest -m ""` from `backend/`.

The `requires_db` set talks to a real Supabase project, so it needs live
credentials in `backend/.env`: `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`
(already there if the app runs at all), plus `TEST_ADMIN_EMAIL` and
`TEST_ADMIN_PASSWORD` (see `backend/.env.example`) pointing at an admin user in
that same project. Leave the two `TEST_ADMIN_*` blank and the tests that need a
signed-in admin skip rather than fail.

Two cautions while the team shares one Supabase project: these tests write real
rows (they clean up after themselves), and two people running `-m requires_db`
at the same time can collide over the same calendar dates. Coordinate before
running them, or leave them to one person.

---

## Troubleshooting

- **Backend container exits immediately / "Settings validation error"** → a required env var is missing in `backend/.env`. The message names it. Most common: `EMAIL_PROVIDER=ses` without the AWS keys, or a missing `VENDOR_JWT_SECRET`.
- **Frontend loads but every request fails / CORS error** → check `VITE_API_BASE_URL` points at `http://localhost:8000`, and the backend's `CORS_ORIGINS` includes `http://localhost:5173` (it does by default).
- **Login fails** → the frontend's `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` and the backend's `SUPABASE_*` must all point at the **same** Supabase project. A user must exist in that project's Auth.
- **`docker compose` not found** → you have an old Docker; use `docker-compose` (with hyphen) or update Docker Desktop.
- **Port already in use (8000 or 5173)** → stop whatever else is using it, or change the port mapping in `docker-compose.yml` / pass `--port` to Vite.

---

## What's NOT covered here (optional integrations)

These default to safe **mock** modes and aren't needed to run the app locally. Configure them only if you're working on those features (see [`docs/DEPLOYMENT_CHECKLIST.md`](docs/DEPLOYMENT_CHECKLIST.md)):

- **DocuSign** (`DOCUSIGN_PROVIDER`, defaults to `mock`) — contract e-signature.
- **Google Maps** (`GOOGLE_MAPS_API_KEY`) — vendor distance ranking falls back to Haversine when absent.
