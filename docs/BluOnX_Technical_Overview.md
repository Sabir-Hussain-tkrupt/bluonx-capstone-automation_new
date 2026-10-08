# BluOnX Bid Management Platform — Technical Overview & Production Operations Guide

| Item | Detail |
|------|--------|
| **System** | BluOnX Bid Management & Vendor Coordination System (MVP) |
| **Document type** | Technical architecture, engineering reference and production operations guide |
| **Audience** | Software engineers, DevOps / cloud engineers, technical administrators, and any technical person taking ownership of the system |
| **Document owner** | Awais Anwer (Tkrupt) |
| **Version** | 1.0 — Final MVP Handoff |
| **Date** | October 8, 2026 |
| **Companion documents** | `docs/BluOnX_Context_Handoff.md` (business context, rules, phase record), `docs/DEPLOYMENT_CHECKLIST.md` (go-live runbook), `database/bluonx_schema_documentation.md` (table reference), `docs/ses-sns-event-tracking.md`, `docs/adr/0001-scheduler-single-instance.md`, `docs/features/per-vendor-bid-revision.md`, `backend/app/jobs/README.md`, `SETUP.md` (local set-up) |

---

## Table of Contents

1. Purpose and How to Use This Guide
2. System Architecture
3. Technology Stack and Versions
4. Repository Structure
5. Backend Architecture
6. Frontend Architecture
7. Data Architecture
8. Security Model
9. Core Business Engines
10. External Integrations
11. Background Jobs and Scheduling
12. Environments
13. Production Infrastructure on AWS
14. Build, Release and Rollback Procedures
15. Configuration Reference
16. Production Operations Runbook
17. Troubleshooting Guide
18. Testing and Quality
19. Extending and Customising the System
20. Known Limitations and Technical Debt
21. Appendix A — API Endpoint Catalogue
22. Appendix B — Status Vocabularies
23. Appendix C — Glossary

---

## 1. Purpose and How to Use This Guide

This guide explains the BluOnX platform from a technical point of view: how it is built, how the pieces fit together, why the main design decisions were made, and how to run, deploy, monitor, troubleshoot and extend it in production. It is written so that an engineer who has never seen the codebase can become productive, and so that an operator can keep the production system healthy without needing to read the code.

**Recommended reading paths**

| If you are… | Read first | Then |
|-------------|-----------|------|
| A new engineer | Sections 2, 4, 5, 6, 7 | 8, 9, 19 |
| A DevOps / cloud engineer | Sections 2, 12, 13, 14, 15 | 16, 17 |
| A technical administrator | Sections 16, 17 | 11, 15 |
| Planning new features | Sections 9, 19, 20 | Context Handoff, Section 15 (out of scope) |

**Conventions used in this guide**

- File and folder paths are relative to the repository root.
- "Staff" means internal users (admins and project managers). "Vendor" means an external company contact who never has an account.
- "Service role" means the Supabase key that bypasses Row Level Security; it is held only by the backend.
- Times for scheduled jobs are given in UTC with the US Central equivalent, because the scheduler runs in UTC and the business operates in Central time.

---

## 2. System Architecture

### 2.1 Architectural Style

The platform is a **three-tier web application** with a **hybrid data-access pattern**:

- A **single-page React application** serves two audiences from one build: the staff dashboard and the vendor portal.
- A **FastAPI backend** is the single gatekeeper for every write, every vendor interaction, every email, every scheduled job, and every third-party integration.
- **Supabase** provides PostgreSQL, authentication for staff, and private file storage.

The defining rule of the system: **staff reads go directly from the browser to Supabase under Row Level Security; every write goes through FastAPI using the service role.** Vendors never touch Supabase at all.

### 2.2 Component Map

| Component | Runs on | Responsibility |
|-----------|---------|----------------|
| Staff dashboard (React) | AWS Amplify (static hosting + CDN) | All internal screens: projects, tasks, vendors, bids, compare, awards, milestones, settings |
| Vendor portal (React, same build) | AWS Amplify | Account-free bid submission, revisions and milestone check-ins under `/bid/*` and `/milestone/*` routes |
| FastAPI backend | AWS ECS Fargate (single task) behind an Application Load Balancer | REST API, business rules, vendor authentication, scheduled jobs, email, DocuSign, webhooks |
| Container registry | Amazon ECR | Backend images |
| Database | Supabase PostgreSQL | All business data, triggers, stored procedures, views, RLS |
| Staff authentication | Supabase Auth | Login, invitations, password reset, JWT issuance |
| File storage | Supabase Storage | Three private buckets for vendor documents, project documents and bid attachments |
| Transactional email | AWS SES | All system emails |
| Email events | AWS SNS | Delivery, bounce and complaint notifications to the backend webhook |
| E-signature | DocuSign eSignature + Connect | Contract envelopes and signing status callbacks |
| Location services | Google Maps Platform | Geocoding, address autocomplete, maps, on-demand route distance |
| Logs | Amazon CloudWatch Logs | Structured JSON logs from the backend container |

### 2.3 Principal Request Flows

**Staff read (for example, the project list)**
1. The browser holds a Supabase session (JWT) for the signed-in user.
2. The React Query hook queries Supabase directly with the anon key plus the user's JWT.
3. PostgreSQL applies Row Level Security: the user must be active; soft-deleted rows are filtered out.

**Staff write (for example, creating a task)**
1. The browser sends the request to FastAPI with `Authorization: Bearer <Supabase JWT>`.
2. FastAPI verifies the JWT (ES256 via Supabase's public keys, or legacy HS256 via the shared secret) and loads the user's active profile and role.
3. The router validates the payload (Pydantic), applies business rules, and writes with the service-role client.
4. Database triggers and constraints act as the final integrity backstop.
5. The frontend invalidates the related React Query keys and re-reads.

**Vendor bid submission**
1. The vendor clicks the emailed magic link (`/bid/<token>`).
2. The portal posts the token to FastAPI, which hashes it, validates it, marks it used, and returns a short-lived **vendor JWT** plus the complete bid context.
3. Every subsequent portal call carries the vendor JWT; the backend derives the vendor's identity from the token, never from the request body.
4. FastAPI reads and writes Supabase with the service role on the vendor's behalf.

**Scheduled work**
1. APScheduler, started in the FastAPI lifespan, fires a job on its cron trigger.
2. The job reads and writes through the same server-side Supabase client and sends email through the email service.
3. The job records its last-run outcome in memory for the scheduler-health endpoint.

**Inbound webhooks**
- SES → SNS → `POST /api/v1/webhooks/ses-notifications` (SNS signature verified) → `email_log` status update.
- DocuSign Connect → `POST /api/v1/webhooks/docusign-connect` (HMAC verified) → contract, award, envelope and capacity updates, decline emails.

### 2.4 Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| Hybrid access (reads via Supabase, writes via FastAPI) | Fast, cacheable reads with database-enforced visibility; all business rules in one auditable place |
| Service-role writes with triggers as backstop | Application owns validation and messages; the database guarantees invariants even if code is wrong |
| Stored procedures only for multi-row atomic writes | Supabase's Python client has no transactions; RPCs give all-or-nothing behaviour where it matters |
| In-process scheduler, single instance | Simple, version-controlled, testable; avoids an extra service (n8n). Requires exactly one backend instance |
| Separate vendor auth chain | Vendors cannot obtain staff privileges, and staff tokens cannot be used in the portal |
| One SPA for staff and vendors | One build and one hosting target; route trees and API clients are isolated |
| Mock providers for email and DocuSign by default | A fresh checkout never sends real email or envelopes; production refuses to start with the mock email provider |

---

## 3. Technology Stack and Versions

### 3.1 Backend

| Concern | Library / tool | Version range |
|---------|---------------|---------------|
| Language runtime | Python | 3.11 (container base `python:3.11-slim`) |
| Web framework | FastAPI | 0.115.x |
| ASGI server | Uvicorn (standard extras) | 0.34.x |
| Validation | Pydantic v2, pydantic-settings v2, email-validator | 2.x |
| Database client | supabase-py (PostgREST, Storage, Auth admin) | 2.x |
| JWT | PyJWT | 2.x |
| HTTP | httpx | 0.27–0.28 |
| Uploads | python-multipart | ≥0.0.18 |
| Templates | Jinja2 | 3.x |
| Scheduling | APScheduler (AsyncIOScheduler) | 3.10+ (below 4.0) |
| Holidays | holidays | 0.102+ |
| AWS | boto3, cryptography | boto3 1.35+ |
| DocuSign | docusign-esign | 6.x |
| PDF | ReportLab | 4.x |
| Caching | async-lru | 2.x |
| Tests | pytest 8, pytest-asyncio 0.25 | |

### 3.2 Frontend

| Concern | Library / tool | Version range |
|---------|---------------|---------------|
| UI library | React, React DOM | 19.2 |
| Build tool | Vite (with `@vitejs/plugin-react`) | 7.3 |
| Language | TypeScript | 5.9 |
| Styling | TailwindCSS v4 via `@tailwindcss/vite` (CSS-first, no config file) | 4.1 |
| Routing | React Router DOM | 7.x |
| Server state | TanStack React Query (+ devtools) | 5.x |
| HTTP | Axios | 1.13 |
| Supabase | supabase-js | 2.97+ |
| Forms | React Hook Form, Zod, hookform resolvers | RHF 7, Zod 4 |
| Charts | Recharts | 2.15 |
| Drag and drop | dnd-kit (core, sortable, utilities) | |
| CSV | PapaParse | 5.5 |
| Icons | lucide-react | |
| Maps | `@vis.gl/react-google-maps` (Places / Maps JS) | |
| Tests | Vitest, React Testing Library, jsdom | Vitest 4 |
| Lint | ESLint 9 with typescript-eslint and React hooks rules | |

### 3.3 Platform Services

| Service | Plan / mode |
|---------|-------------|
| Supabase | Separate development and production projects |
| AWS | ECS Fargate, ECR, ALB, ACM, CloudWatch, SES, SNS, Amplify, IAM, Secrets Manager (recommended). Basic (free) support plan is sufficient |
| DocuSign | Developer sandbox (development); production account required for go-live |
| Google Maps Platform | Geocoding API, Places API, Maps JavaScript API, Routes API |
| GitHub | Source control; branches `main` and `dev`; Amplify connected for frontend builds |

---

## 4. Repository Structure

### 4.1 Top Level

| Path | Purpose |
|------|---------|
| `backend/` | FastAPI service, its Dockerfile, tests, operational scripts |
| `frontend/` | React SPA, environment files, tests |
| `database/` | Authoritative SQL: complete schema, RLS policies, storage policies, schema documentation, development seed data |
| `docs/` | Handoff, this guide, deployment checklist, feature specs, ADRs, integration notes |
| `docker-compose.yml` | Local backend (`api`) and test runner (`api-test`) services |
| `SETUP.md` | Step-by-step local environment set-up |

### 4.2 Backend (`backend/`)

| Path | Contents |
|------|----------|
| `app/main.py` | Application factory: logging set-up, lifespan (Supabase client + scheduler), CORS and request-logging middleware, global database-error handler, router registration |
| `app/core/` | Cross-cutting infrastructure: `config.py` (settings and production guards), `supabase_client.py` (singleton client), `auth.py` (staff JWT and role dependencies), `vendor_auth.py` (vendor JWT), `storage.py` (uploads, signed URLs), `file_validation.py` (per-bucket rules, file signatures), `rate_limit.py`, `request_logging.py`, `logging_config.py`, `db_errors.py` (PostgREST error mapping), `query_filters.py`, `time.py` (business clock and working-day calendar access) |
| `app/routers/` | One module per API domain (see Appendix A) |
| `app/services/` | Business logic: vendor filtering, bid package creation, invitation tracking, vendor portal, submission validation, revisions, scoring, recommendation, pre-award validation, awards, contracts, contract PDF, envelope orchestration, DocuSign client, decline letters, milestones (service, tokens, portal, responses, email, notifications), reviews, holidays, users, contract signers, notifications, email service and providers, geocoding, distance, insurance rules |
| `app/models/` | Pydantic request/response schemas per domain |
| `app/jobs/` | Scheduler (`scheduler.py`) and one module per scheduled job, with an authoring contract in `README.md` |
| `app/templates/emails/` | Jinja2 email templates, each with an HTML and a plain-text version, sharing a branded `base.html` |
| `app/templates/contracts/` | `firm_terms.txt.j2` — the swappable contract terms body |
| `scripts/` | `seed_holidays.py` (calendar seed), `entrypoint.sh`, `mint_checkin.py` and `preview_milestone_emails.py` (developer utilities) |
| `tests/` | pytest suites organised by domain, shared fakes, `conftest.py` |
| `secrets/` | Local-only location for the DocuSign private key (git-ignored) |
| `Dockerfile` | Multi-stage, non-root production image |
| `requirements.txt` | Python dependency manifest |
| `pytest.ini` | Test configuration; live-database tests are deselected by default |

### 4.3 Frontend (`frontend/src/`)

| Path | Contents |
|------|----------|
| `main.tsx`, `App.tsx` | Entry point and provider stack |
| `routes/` | The single route tree (public, protected dashboard, admin settings, vendor portal) |
| `constants/` | Route paths and API endpoint paths in one place each |
| `contexts/` | Authentication context (session, profile, role) |
| `services/` | Auth service wrapper around Supabase Auth |
| `lib/` | Axios instance with token interceptor, Supabase client, React Query client, query keys, formatting, breadcrumbs, dormant Realtime helpers |
| `components/ui/` | In-house component library (about 30 components: Button, TextInput, Select, DatePicker, Modal, ConfirmDialog, Table, Tabs, Accordion, Toast, StatusBadge, StatCard, StarRating, FileUpload, DocumentList, Sidebar, TopHeader, UserMenu and others) |
| `components/layout/`, `components/auth/`, `components/shared/` | Dashboard shell, route guards, shared pieces |
| `features/` | One folder per domain, each with `api/` (queries and mutations), `hooks/`, `components/`, `pages/`, and tests |
| `types/` | Shared types, including the Supabase database types placeholder |
| `test/` | Test set-up |

**Feature folders:** `auth`, `dashboard`, `projects` (project and task pages), `tasks` (task list, form, default-task seeding), `vendors`, `trades`, `bid-templates`, `bids` (wizard, package detail, compare, revisions), `vendor-portal`, `contracts`, `contract-signers`, `milestones`, `notifications`, `holidays`, `user-management`.

### 4.4 Database (`database/`)

| File | Purpose |
|------|---------|
| `bluonx_complete_schema.sql` | Tables, constraints, indexes, functions, triggers, stored procedures, views, grants — the single authoritative schema |
| `rls_policies.sql` | Row Level Security policies for every table |
| `storage_rls_policies.sql` | Bucket configuration (size limits) and storage RLS policies |
| `bluonx_schema_documentation.md` | Human-readable table and trigger reference |
| `seed_data/` | Development seed and demo data |

---

## 5. Backend Architecture

### 5.1 Application Lifecycle

1. **Configuration load.** `Settings` reads environment variables (and `backend/.env` locally). Validators run immediately and **refuse to start** the application on unsafe production configuration (see Section 15.3).
2. **Logging.** Root logging is configured before anything else logs: human-readable console format in development, one-JSON-object-per-line in production.
3. **Lifespan start.** A single Supabase service-role client is created and stored on application state. The active email provider is logged prominently (a warning if it is the mock). The scheduler is started and all jobs registered.
4. **Serving.** Uvicorn serves on port 8000 with a **single worker** (no worker flag — each worker would be another scheduler).
5. **Lifespan stop.** The scheduler is shut down cleanly.

### 5.2 Layering

| Layer | Responsibility | Rules |
|-------|---------------|-------|
| Routers | HTTP surface: path, method, auth dependency, request/response models, HTTP error mapping | Thin; simple CRUD may live here, anything substantial is delegated |
| Services | Business rules, orchestration, I/O | Raise domain errors carrying a status and message; routers translate them |
| Pure logic modules | Scoring, recommendation, pre-award checks, insurance classification | No database or network access; fully unit-testable |
| Models | Pydantic schemas, literal vocabularies | Server derives sensitive fields (ids, amounts, vendor) rather than trusting the client |
| Core | Infrastructure shared by all | Single source for config, auth, storage, logging |
| Jobs | Scheduled entry points | Follow the job-authoring contract (Section 11) |

### 5.3 Middleware and Cross-Cutting Behaviour

- **CORS.** Origins come from `CORS_ORIGINS`. Methods allowed: GET, POST, PUT, PATCH, DELETE, OPTIONS. Credentialed CORS is not used — both auth schemes are bearer tokens.
- **Request logging.** The outermost middleware assigns a correlation id to every request (returned as the `X-Request-ID` header) and logs method, path, matched route, status, duration and the acting user id and role (or vendor id). Health checks log at DEBUG to avoid noise.
- **Global database-error handler.** Any PostgREST error not caught locally is mapped centrally: a unique-constraint violation (SQLSTATE 23505) becomes **409 Conflict** with a readable message; anything else becomes a generic **500** with the full error logged but nothing leaked to the client.
- **Not-found handling.** Single-row lookups use "maybe single" semantics so a missing row returns a proper 404 or 422 rather than a 500.
- **Custom SQLSTATEs.** Stored procedures raise `PT404`, `PT409` and `PT422`; services map them to 404, 409/410 and 422 with the database's human-written message where appropriate.

### 5.4 Authentication Dependencies

| Dependency | Grants access when |
|------------|-------------------|
| Current user | A valid Supabase JWT with audience `authenticated` is presented |
| Current active user | As above, plus a `public.users` row that is active and not soft-deleted |
| Require admin | Active user with role `admin` |
| Vendor (bid) | A valid vendor JWT of type `vendor_portal`, signed with `VENDOR_JWT_SECRET` |
| Vendor (milestone) | A valid milestone-scoped vendor JWT issued from a milestone check-in token |

### 5.5 Route Ordering and Path Parameters

FastAPI matches routes in registration order. A **static path segment must always be registered before a parameterised one at the same position**, and identifier parameters should be typed as UUIDs. In the tasks router this is why the default-task seeding route (`/projects/{project_id}/tasks/default`) and the reorder route (`/projects/{project_id}/tasks/reorder`) are declared before the single-task routes, and the single-task routes use a UUID path converter. If this ordering is broken, a request for the static path is captured by the parameterised route and fails with **405 Method Not Allowed** (or 422). Any new static sub-path under an existing collection must follow the same rule.

### 5.6 Error and Status-Code Conventions

| Status | Used for |
|--------|---------|
| 400 | Request not valid for the current state (for example, non-competitive task in the bid pipeline, archived project) |
| 401 | Missing or invalid token; failed webhook signature |
| 403 | Authenticated but wrong role |
| 404 | Unknown or soft-deleted resource; unknown magic link |
| 409 | Conflict with existing state (duplicate, already submitted, one-active-record rules, delete blocked) |
| 410 | Link revoked, expired, or no longer current (portal) |
| 422 | Validation failure, illegal transition, blocked pre-award |
| 423 | Bid package not open (portal) |
| 429 | Rate limit exceeded on magic-link validation |
| 501 | Deliberate stub (a few legacy CRUD verbs not used by the product) |

---

## 6. Frontend Architecture

### 6.1 Provider Stack and Route Areas

The application wraps the router in React Query, authentication, toast and Google Maps providers. Routes fall into four isolated areas:

| Area | Paths | Guard |
|------|-------|-------|
| Public authentication | `/login`, `/forgot-password`, `/auth/callback`, `/auth/reset-password`, `/accept-invite` | None |
| Staff dashboard | `/dashboard`, `/projects`, `/projects/:id`, `/projects/:id/tasks/:taskId`, bid package, compare and milestone pages, `/vendors`, `/bid-packages`, `/bid-templates`, `/milestones`, `/notifications` | Authenticated, active profile |
| Admin settings | `/settings/trades`, `/settings/users`, `/settings/calendar`, `/settings/contract-signers` | Role `admin` (non-admins are silently redirected) |
| Vendor portal | `/bid/:token`, `/bid/form`, `/bid/revision`, `/bid/submitted/:id`, `/bid/expired`, `/bid/invalid`, `/bid/closed`, `/bid/already-submitted`, `/milestone/:token`, `/milestone/respond`, `/milestone/recorded`, `/milestone/unavailable` | Vendor JWT held in portal context; never uses Supabase |

All path strings live in `frontend/src/constants/routes.ts`; all API paths in `frontend/src/constants/api.ts`.

### 6.2 Data Layer

- **Reads** use React Query hooks calling Supabase directly (or FastAPI where the read needs server logic, such as scores or qualified vendors).
- **Writes** use Axios against FastAPI. The Axios instance prefixes `VITE_API_BASE_URL` + `/api/v1`, attaches the current Supabase access token on every request, and normalises errors (401 becomes "session expired").
- **Caching policy:** queries are fresh for 2 minutes, garbage-collected after 10, retried twice, and refetched on window focus, mount and reconnect. Mutations never auto-retry (to avoid duplicate side effects) and invalidate the affected query keys on success.
- **Query keys** are centralised in `lib/queryKeys.ts` so invalidation is consistent.
- **Realtime:** Supabase Realtime helpers exist but are not subscribed by any feature; refresh-on-focus and invalidation provide freshness.

### 6.3 Vendor Portal Isolation

- The portal has its own layout, its own Axios instance with a vendor-JWT interceptor, and its own context and guard. It never imports the Supabase client.
- Form state is held in a reducer store; validation is authoritative on the server and errors are mapped back to the relevant step.
- **Demo mode** (`VITE_DEMO_MODE=true`) swaps the portal API for an in-memory mock with a visible banner. It must be `false` in production (the production environment file sets it so).

### 6.4 UI and Styling

- TailwindCSS v4 is configured CSS-first: theme tokens are declared in `src/index.css`; there is no Tailwind or PostCSS config file.
- Components are hand-built and accessible (focus handling, escape and outside-click on overlays, keyboard-safe mobile table cards).
- Responsive breakpoints cover phone, tablet and desktop; the sidebar collapses (state remembered in local storage) and becomes a mobile menu.

### 6.5 Notable Feature Implementations

| Feature | Implementation notes |
|---------|---------------------|
| Task list | Drag-and-drop ordering (dnd-kit) persisted through the reorder endpoint; **Add Default Tasks** button calls the seeding endpoint and shows a toast with created / skipped counts |
| Bid package wizard | Three steps; vendor selection preserves PM overrides; Scope of Work upload required |
| Compare page | Recommendation panel, sortable colour-coded table, expandable line items, Recharts bar chart, print stylesheet |
| Notifications | Bell with unread count polled every 60 seconds and refreshed on focus; mark-as-read on navigation |
| Milestones | Detail page with actions and activity timeline; global list; dashboard attention card |
| Contracts | Contract panel with status, "contract not sent" recovery alert, completion and review panel with star rating |

---

## 7. Data Architecture

### 7.1 Schema Overview

PostgreSQL on Supabase with **34 tables, 3 views**, and a set of PL/pgSQL functions, triggers and stored procedures. Conventions: UUID primary keys, `TIMESTAMPTZ` timestamps, CHECK-constrained status columns, ON DELETE RESTRICT by default, comments on every table and key column.

| Group | Tables |
|-------|--------|
| Access control | `users` |
| Trade & vendor | `trades`, `vendors`, `vendor_contacts`, `vendor_trades`, `vendor_documents` |
| Project & task | `projects`, `project_documents`, `tasks` |
| Bid lifecycle | `bid_templates`, `bid_template_items`, `bid_packages`, `bid_package_documents`, `bid_invitations`, `bid_submissions`, `bid_line_items`, `bid_attachments`, `bid_scores`, `bid_revision_requests`, `magic_link_tokens` |
| Award & contract | `awards`, `contracts`, `docusign_envelopes`, `contract_signers` |
| Milestones & performance | `milestones`, `milestone_alerts`, `milestone_responses`, `milestone_events`, `milestone_checkin_tokens`, `vendor_performance_reviews` |
| Communication & audit | `email_log`, `notifications`, `vendor_flags` |
| System configuration | `holidays` |

### 7.2 Integrity Mechanisms

| Mechanism | Examples |
|-----------|---------|
| Partial unique indexes | One active award per task; one active (non-terminated) contract per task; one current non-superseded, non-draft submission per invitation; one pending revision request per invitation |
| Unique constraints | One response per milestone alert (first response wins); one check-in token per alert; one review per contract; unique holiday date; unique signer email; unique contract number and envelope id |
| Consistency triggers | Denormalized `vendor_id` / `task_id` must match their source chain (submissions, awards, contracts, milestones, reviews) |
| Lifecycle triggers | `updated_at` maintenance; bid round auto-numbering; invitation status sync on submission; revision supersession chain; vendor capacity +1 / −1; milestone date guards (start date immutable once live); immutable milestone event ledger; holiday guardrails (no past edits, 25 per year, 14 consecutive) |
| Auth trigger | New Supabase Auth user creates the matching `public.users` profile from invitation metadata |
| Disabled trigger | Vendor onboarding status sync (manual control by design) |

### 7.3 Stored Procedures (Atomic Writes)

| Procedure | Purpose |
|-----------|---------|
| `fn_create_bid_package_with_invitations` | Package, document links, invitations (status `pending_send`), token hashes and the draft-to-bidding task flip in one transaction |
| `fn_create_milestone` | Milestone and its opening event |
| `transition_milestone` | The only writer of milestone status; validates the transition table under a row lock, applies dates, bumps the cycle on reschedule, writes the event |
| `fn_record_milestone_response` | Records the vendor's answer, transitions the milestone and spends the token atomically |
| `fn_mark_contract_complete` | Completes a contract; refuses while any milestone is open |
| `fn_is_business_day`, `fn_add_business_days`, `fn_business_days_between` | Working-day arithmetic against the holiday calendar — the single implementation used by the backend |

### 7.4 Views

| View | Purpose |
|------|---------|
| `v_vendor_performance` | Review count, average rating and 0–100 performance score per vendor (security invoker) |
| `v_milestone_overview` | Read model for milestone list, dashboard attention card and detail pages |
| `v_vendor_email_log` | Vendor-level communication history |

### 7.5 Row Level Security

- RLS is enabled on every table. Anonymous users have no access.
- Authenticated users can read when `private.is_active_user()` is true; soft-deleted rows are filtered.
- Database-level write policies exist only where the database should guard independently: admin-only on `users`, `trades` and `holidays`; owner-scoped `notifications`; admin-only read on `magic_link_tokens`.
- All other writes are performed by FastAPI with the service role and therefore bypass RLS. **FastAPI authorization is the real gate for writes** — keep this in mind when adding endpoints.

### 7.6 Storage

| Bucket | Allowed types | Size limit |
|--------|---------------|-----------|
| `vendor-documents` | PDF, common images (PNG, JPG/JPEG, GIF, WEBP, BMP, SVG, TIF/TIFF), TXT, Word, Excel, PowerPoint (legacy and OOXML) | 50 MB (raise for production per checklist) |
| `project-documents` | As above plus CAD (DWG, DXF, DWF, DGN) | 50 MB |
| `bid-attachments` | As vendor documents | 10 MB |

- Validation is in the application (extension allow-list, size, and file-signature match). Bucket-level MIME lists must be left empty because CAD and some Office files arrive as generic binary.
- Paths: `{vendor_id}/{document_type}/{filename}`, `{project_id}/{filename}`, `{bid_submission_id}/{filename}`.
- Downloads are one-hour signed URLs. If the database write fails after upload (or vice versa), the orphan is cleaned up.

### 7.7 Schema Change Management

There is no migration framework. The SQL files in `database/` are the source of truth and are applied through the Supabase SQL editor.

- For a new environment: run `bluonx_complete_schema.sql`, then `rls_policies.sql`, then `storage_rls_policies.sql`, after creating the three buckets.
- For a change to an existing environment: write an idempotent change script, apply it to development, verify, then apply to production **before** deploying code that depends on it; update `bluonx_complete_schema.sql` (and the schema documentation) so the files remain authoritative.
- Prefer additive changes (new nullable columns, new CHECK values). Status values are CHECK constraints, so adding one means replacing the constraint.

---

## 8. Security Model

### 8.1 Staff Authentication

- Supabase Auth, email and password. Accounts are created only by admin invitation through the Supabase admin API; there is no self-registration.
- The backend verifies JWTs with audience `authenticated`, supporting both the current asymmetric signing (ES256, verified against Supabase's published keys) and legacy HS256 (shared `SUPABASE_JWT_SECRET`).
- Role and active status are checked against `public.users` on every protected call.
- User-management guards: no self role change, self deactivation or self deletion; the last active admin can never be removed.

### 8.2 Vendor Authentication (Bids)

| Element | Design |
|---------|--------|
| Magic-link token | 32 random bytes, URL-safe; only the SHA-256 hash is stored |
| Validity | Until the bid package deadline (revision tokens: until the revision deadline) |
| Re-send | Revokes previous tokens and issues a new one |
| Validation order | Unknown (404) → revoked (410) → expired (410) → orphaned (404) → package not open (423) → already submitted (409) |
| Session | HS256 vendor JWT signed with `VENDOR_JWT_SECRET` (must differ from the Supabase secret), type `vendor_portal`, carrying vendor, contact, invitation, package and task ids; default lifetime 4 hours |
| Identity | Always taken from the JWT; ownership checks return 404 rather than 403 to avoid leaking existence |
| Rate limiting | 10 validation requests per IP per minute (in-memory, per process) |
| Audit | First use and client IP recorded |

### 8.3 Vendor Authentication (Milestone Check-ins)

- Separate token table (`milestone_checkin_tokens`), one token per check-in, hashed, 7-day hard expiry, stamped with the milestone cycle.
- Opening the link only validates and issues a milestone-scoped JWT; **the answer is recorded only by an explicit Yes/No POST**, so link-prefetching email scanners cannot answer.
- A reschedule bumps the milestone cycle, making every older token stale without any clean-up job.
- First response wins at the database level; repeat clicks see "already answered."

### 8.4 Webhook Security

| Webhook | Verification |
|---------|-------------|
| SES via SNS | SNS message signature verified (including the subscription-confirmation token field); subscriptions auto-confirm; always returns 200 to SNS |
| DocuSign Connect | HMAC-SHA256 of the raw body compared in constant time with `X-DocuSign-Signature-1`; requests are rejected if no key is configured (fail-closed); processing is idempotent across Connect retries |

### 8.5 Secrets and Configuration Hygiene

- Secrets are never committed: `backend/.env`, `frontend/.env` and `backend/secrets/` are git-ignored.
- In AWS, inject secrets into the ECS task definition from **Secrets Manager** (or SSM Parameter Store) rather than plain environment values.
- The DocuSign private key is supplied at runtime through the `DOCUSIGN_PRIVATE_KEY_SECRET` environment variable; the container start command writes it to `/app/secrets/docusign_private_key.pem`, which `DOCUSIGN_PRIVATE_KEY_PATH` should reference.
- The frontend only ever receives the Supabase **anon** key and public configuration. The service-role key must never appear in frontend configuration.
- Production start-up guards reject wildcard, localhost or non-HTTPS CORS origins and non-HTTPS frontend URLs.

### 8.6 Upload Security

Server-side validation of extension, size and file signature ("magic bytes"), private buckets, signed short-lived download URLs, and service-role mediated vendor uploads. Antivirus scanning is not implemented (Section 20).

---

## 9. Core Business Engines

### 9.1 Task Template Library and Default-Task Seeding

**What it is.** A standard library of 58 activity-coded task templates (B0010–B0760; 14 Due Diligence, 44 Development; 43 competitive, 15 internal), defined in the tasks router alongside a small trade-alias map. The full list is in Appendix A of the Context Handoff.

**Endpoint.** `POST /api/v1/projects/{project_id}/tasks/default` (any active staff user). Returns 201 with a message plus `created_count` and `skipped_count`.

**Algorithm.**
1. Load the project; reject if missing (404) or archived (400).
2. Load all **active** trades and index them by lower-cased name.
3. Load the names of the project's existing non-deleted tasks.
4. Find the project's current highest sort order.
5. For each template in activity-code order: build the name "*Code* - *Name*"; skip it if that name already exists; resolve the trade by exact name, then through the alias map ("Geotechnical Engineering" ↔ "Geo Tech"); assign the next sort order; create a draft task with the template's description, phase and bid type, and the calling user as creator.
6. Insert all new tasks in one bulk insert. Report created and skipped counts.

**Operational notes.**
- Idempotent by name: repeating the action fills gaps only.
- **Trade dependency:** if a template's trade cannot be resolved, the current implementation falls back to the first active trade it finds rather than failing. Before using the feature in a new environment, confirm that every trade named in the library exists, is active, and has a phase compatible with the template (Context Handoff, Section 5). A misspelt or inactive trade is the only realistic way to get a wrongly classified seeded task.
- The bulk insert bypasses the per-task trade-phase check used by the single-task form, so trade phases must be configured correctly.
- Seeded tasks have no budget; PMs fill budgets per project.
- Route ordering matters (Section 5.5): this static route must remain above the UUID-typed single-task routes.

**Changing the library** is described in Section 19.2.

### 9.2 Vendor Filtering

`GET /api/v1/tasks/{task_id}/qualified-vendors` (default radius 75 miles, range 1–500; flagged vendors included by default). Only `competitive` tasks are accepted.

Pipeline: load task and project → candidate vendors linked to the task's trade → status active → onboarding → insurance classification (shared with pre-award) → bonding against task budget → capacity → straight-line distance from project coordinates → flags (informational only). The response returns **qualified** and **disqualified** vendors, each disqualified vendor with its reasons, so the PM can override knowingly. If the project has no coordinates, the distance stage is skipped and a warning is returned with the results so the PM knows the radius was not applied.

### 9.3 Bid Package Creation

`POST /api/v1/tasks/{task_id}/bid-packages` validates everything first (competitive task, deadline in the future, template, Scope of Work present, documents belong to the project, vendors and contacts valid), generates one token per vendor (hash only sent to the database), and calls the atomic creation procedure. Emails are then sent one by one; each invitation is reconciled to `sent` (with `sent_at`) or `send_failed`. Failed sends are recoverable from the package page, which mints a new token and labels the email correctly as a first send.

Packages can be **closed** early or **cancelled**; cancelling the last live round resets the task to draft. Overdue packages are closed lazily when viewed, and open invitations are marked expired (never-delivered invitations keep their status).

### 9.4 Vendor Portal Submission Validation

On final submit the server re-reads state and checks: notes within 2,000 characters; total greater than zero; for structured templates, line count equals the template, each line total equals quantity × unit price, and the grand total equals the sum of lines; a proposed start date when the package has a desired start date; and the Scope of Work attestation (vendor-typed company name). The final update is guarded on the draft flag so a double submit returns 409. Failures return 422 with field-level errors.

Drafts: one per invitation; the portal auto-saves every two minutes and on blur, and handles the race between the first auto-save and an attachment upload.

### 9.5 Per-Vendor Revision

PM-initiated, one vendor at a time, capped at two per vendor per package, one pending at a time, blocked after award. A revision-scoped token and vendor JWT drive the revision landing page; the vendor submits through the normal finalise path, creating a new submission that supersedes the original (enforced by triggers and the current-submission partial unique index). The hourly expiry job moves overdue requests to `expired` and revokes their tokens. Full design: `docs/features/per-vendor-bid-revision.md`.

### 9.6 Scoring Engine

`POST /api/v1/bid-packages/{id}/scores` computes; `GET` reads. The cohort is the package's current, non-superseded, non-draft, submitted bids with a positive total. Five pure functions feed an orchestrator that upserts one score row per submission with a snapshot of inputs and weights.

| Dimension | Weight | Formula |
|-----------|--------|---------|
| Price | 0.50 | (lowest total in cohort ÷ this total) × 100 |
| Compliance | 0.05 | Mean of onboarding (complete 100 / partial 50 / pending 0) and insurance (expiry ≥ deadline + 30 days → 100; ≥ deadline → 50; otherwise or missing → 0) |
| Performance | 0.20 | Vendor's average rating ÷ 5 × 100 from `v_vendor_performance`; 75 when the vendor has no reviews |
| Capacity | 0.10 | (max − current) ÷ max × 100; 75 when max unknown; 0 when max is 0 |
| Timeline | 0.15 | No desired start → 100 for all; missing proposed start → 0; days late ≤0 → 100, ≤7 → 75, ≤14 → 50, ≤30 → 25, otherwise 0 |

Total = weighted sum on a 0–100 scale. Weights and constants are defined at the top of the scoring service (Section 19.4).

### 9.7 Recommendation

A pure function over the scored cohort and the task budget: rank by total score (tie → lower price), produce a plain-language justification for the top vendor, and attach warning flags — over budget, late start, insurance window, onboarding incomplete. It never awards.

### 9.8 Pre-Award Validation

Six pure checks (submission eligibility, insurance validity, bonding capacity, vendor capacity, budget variance ±5%, start-date feasibility) each return a severity of pass, warn, block or skipped plus the raw inputs. The result (`can_award`, `requires_override`, check list, rubric version, timestamp) is previewed through `GET /api/v1/awards/validate/{bid_submission_id}` and recomputed server-side at award time. Blocks are not overridable; warnings require a justification. The full result is stored on the award as a JSON snapshot.

### 9.9 Award, Contract and DocuSign Lifecycle

| Step | Trigger | Effect |
|------|---------|--------|
| 1 | PM posts `POST /awards` with submission, signer, optional instructions, validity days, work duration, and justification if needed | Validation re-run; award written at `pending_acceptance` with derived amount, task and vendor; task → `awarded`. One-active-award index surfaces as 409 |
| 2 | Post-commit hook (best effort) | Contract row created at `sent_for_signature` with a generated contract number |
| 3 | Envelope orchestration | Retry-safe check for an existing envelope (local, then DocuSign by contract id) → contract PDF generated (firm terms template, dates, amount, SoW signed date, SoW exhibit) → two-signer envelope sent (BluOnX signer routing order 1, vendor routing order 2, Connect notification attached when configured) → envelope row stored → award notification email sent |
| 4 | Failure at any point in 3 | Award stands; UI shows "Contract not sent"; `POST /awards/{id}/send-contract` re-runs idempotently |
| 5 | Connect `completed` | Contract → `executed` (signed date, `valid_until` = signed date + validity days); award → `accepted` (capacity +1 by trigger); decline letters to every other invited contact; envelope payload stored |
| 6 | Connect `declined` / `voided` | Contract → `terminated`; award → `declined_by_vendor`; PM may award again |
| 7 | Connect `sent` / `delivered` | Envelope status update only |
| 8 | PM marks contract complete | `fn_mark_contract_complete` (refused while milestones are open); capacity −1 by trigger |
| 9 | PM rates vendor | One 1–5 review per completed contract; editable |

### 9.10 Milestone Engine

**State machine** (enforced only by `transition_milestone`):

| Action | Allowed from | Result |
|--------|-------------|--------|
| PM mark started | scheduled | in_progress |
| PM mark completed | scheduled, in_progress, delayed, unresponsive | completed |
| PM reschedule (new end date) | in_progress, delayed, unresponsive | in_progress (new cycle) |
| PM cancel | scheduled, in_progress, delayed, unresponsive | cancelled |
| Vendor start — yes / no | scheduled, unresponsive | in_progress / delayed |
| Vendor progress — yes / no | in_progress, unresponsive | in_progress / delayed |
| Vendor completion — yes / no | in_progress, unresponsive | completed / delayed |
| System no-response | scheduled, in_progress | unresponsive |

**Dates.** `start_date` is editable only while scheduled and before any check-in has been sent. `baseline_end_date` freezes the originally committed finish; reschedules move only `end_date`. On-time means actual end ≤ baseline end. Actual dates are write-once.

**Check-in schedule** (daily job): start check on the start date; completion check on the end date; progress check 5 days before the end date only if that is at least 3 days after the start. Past check dates are never back-filled. Only `scheduled` and `in_progress` milestones receive checks; `delayed` and `unresponsive` pause the cycle until the PM acts.

**Idempotency.** The alert row is written before the email is sent and serves as the de-duplication marker (milestone, alert type, cycle). Each check-in links its `email_log` row so the no-response job can distinguish a bounce from silence.

**Escalation.** After 3 working days without an answer (database business-day functions, holiday-aware), the milestone becomes `unresponsive`, the owning PM (`milestones.created_by`) receives an email and an in-app notification, once per cycle. A bounced, complained or failed check-in instead produces a delivery-failure notification.

**PM fan-out on vendor answers.** Handled in Python after the transaction (a stored procedure cannot send email): delay → PM email and notification; completion → PM notification.

### 9.11 Notification Service

A single writer to `notifications` with a controlled vocabulary of types, de-duplicated against existing unread notifications for the same user, type and reference. Endpoints: list (paginated), unread count, mark one read, mark all read. Per-user isolation is enforced by RLS.

### 9.12 Insurance Rules

One pure classifier (`valid`, `lapses_before_end`, `expired`, `missing`) shared by the vendor filter (disqualify on expired / missing) and pre-award validation (block on expired, warn otherwise), so the two stages can never disagree. The vendor's insurance expiration is recomputed from its valid certificates on every certificate upload and deletion.

---

## 10. External Integrations

### 10.1 AWS SES and SNS

| Aspect | Detail |
|--------|-------|
| Provider selection | `EMAIL_PROVIDER` = `mock` (default) or `ses`. Production requires `ses` and AWS credentials |
| Sender | `SES_FROM_EMAIL` must be a verified identity (domain verification with SPF, DKIM and DMARC recommended for production) |
| Region | `AWS_REGION` (default `us-east-1`) |
| Sending behaviour | Each send writes an `email_log` row (queued → sent / failed), retries transient failures up to three times with exponential backoff, and stores the SES MessageId |
| Event tracking | Requires `SES_CONFIGURATION_SET` naming a configuration set whose event destination publishes DELIVERY, BOUNCE and COMPLAINT to an SNS topic; the topic has an HTTPS subscription to `/api/v1/webhooks/ses-notifications` |
| Status updates | Delivery advances only `queued`/`sent` rows (never overwrites a terminal status); bounces set `bounced` with subtype; complaints set `complained` |
| Sandbox | A new SES account can only send to verified addresses until production access is granted |
| Concurrency | Batch sends use `asyncio.gather` with a semaphore of 10 |

Details and development ARNs: `docs/ses-sns-event-tracking.md`.

### 10.2 DocuSign

| Aspect | Detail |
|--------|-------|
| Provider selection | `DOCUSIGN_PROVIDER` = `mock` (default; no network) or `sandbox` (real calls to the demo environment). Production requires moving to production hosts and a production-approved integration key |
| Auth | JWT Grant (impersonation) with an RSA private key; 1-hour tokens cached in process and re-minted with a safety margin; no refresh tokens stored |
| Hosts | OAuth host (`DOCUSIGN_OAUTH_BASE_URL`, e.g. `account-d.docusign.com` for demo, `account.docusign.com` for production) is distinct from the REST base (`DOCUSIGN_ACCOUNT_BASE_URL`, e.g. `https://demo.docusign.net`) |
| Consent | The impersonated user must grant consent once; the DocuSign health endpoint reports `consent_required` with the consent URL |
| Envelope | Generated contract PDF (+ SoW exhibit), two signers in routing order, anchor-based signing fields, custom field carrying the BluOnX contract id for reconciliation |
| Connect | `DOCUSIGN_CONNECT_WEBHOOK_URL` placed on each envelope; `DOCUSIGN_CONNECT_HMAC_KEY` must match the key configured in DocuSign Connect |
| Health | `GET /api/v1/admin/docusign-health` (admin) attempts a token mint and reports status |

### 10.3 Google Maps Platform

| Usage | Where | Key |
|-------|-------|-----|
| Geocoding of vendor and project addresses (system of record for coordinates) | Backend on create, update, import | `GOOGLE_MAPS_API_KEY` |
| Driving distance for a single pair (on demand) | Backend Routes API, with straight-line fallback | `GOOGLE_MAPS_API_KEY` |
| Address autocomplete and maps | Browser | `VITE_GOOGLE_MAPS_API_KEY` (restrict by HTTP referrer) |

Without a key, the frontend degrades to plain inputs and the backend falls back to straight-line distance. The bulk qualification radius always uses straight-line distance.

### 10.4 Supabase Auth Mailer

Invitation and password-reset emails are sent by Supabase, not SES. Production needs custom SMTP in Supabase, a branded invite template, the production Site URL, and the redirect allow list including `{FRONTEND_BASE_URL}/accept-invite`, `/auth/callback` and `/auth/reset-password`.

---

## 11. Background Jobs and Scheduling

### 11.1 Scheduler Model

- One `AsyncIOScheduler` in UTC, created at module level, started and stopped by the FastAPI lifespan.
- Default job options: coalesce missed runs, 300-second misfire grace, maximum one concurrent instance per job.
- Each job is wrapped by a tracking decorator that logs start and finish with a per-run correlation id, records the last outcome in memory, and never lets an exception crash the scheduler.
- No persistent job store: jobs are defined in code and registered on start-up.
- **Single-instance constraint:** exactly one backend process may run. Two instances would double-send every email and double-apply transitions. See ADR 0001.

### 11.2 Job Catalogue

| Job id | Schedule (UTC) | US Central (CDT) | Purpose |
|--------|----------------|------------------|---------|
| `revision_expiry` | Every hour at :00 | Hourly | Expire overdue revision requests; revoke their tokens |
| `daily_bid_reminders` | 15:00 daily | 10:00 | T-7 / T-3 / T-0 vendor reminders with per-day de-duplication and a status re-check before each send |
| `daily_insurance_expiration` | 15:15 daily | 10:15 | Admin notifications at T-30, T-7 and daily while expired |
| `scheduler_self_check` | 15:45 daily | 10:45 | Alert admins about any watched job that has not run within its interval plus a 2-hour grace |
| `post_deadline_escalation` | 16:00 daily | 11:00 | Notify package creators of non-responders from the last 24 hours, then mark them no-response |
| `milestone_daily_checkin` | 16:15 daily | 11:15 | Send start, progress and completion check-ins |
| `milestone_no_response` | 16:30 daily | 11:30 | Escalate check-ins unanswered for 3 working days |
| `holiday_seed` | January 2, 15:00 | 09:00 (CST) | Top up federal holidays for the following year |

(Central times shift by one hour during standard time because the triggers are fixed in UTC.)

### 11.3 Scheduler Health

`GET /api/v1/admin/scheduler-health` (admin) returns whether the scheduler is running and, for every known job, its last run time, status, result and error. Because state is in memory, it is reset when the container restarts — a job shows "never run" until its next trigger. An external uptime monitor polling this endpoint is the recommended catch for a complete scheduler outage.

---

## 12. Environments

| Environment | Frontend | Backend | Supabase | Email | DocuSign |
|-------------|----------|---------|----------|-------|----------|
| Local | Vite dev server, `http://localhost:5173` | Docker Compose service `api`, `http://localhost:8000` (live code mount) | Development project | `mock` by default; `ses` to send real email | `mock` by default |
| AWS development | Amplify, `dev.app.bluonx.com` | ECS Fargate behind ALB, `dev.api.bluonx.com` | Development project | SES | Sandbox |
| Production | Amplify, production app domain (e.g. `app.bluonx.com`) | ECS Fargate behind ALB, production API domain (e.g. `api.bluonx.com`) | Production project | SES (production access) | Production account |

**Environment parity rules**

- Frontend `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` and backend `SUPABASE_*` must point to the **same** Supabase project in each environment.
- `VITE_API_BASE_URL` must point to that environment's API; `CORS_ORIGINS` must include that environment's app origin.
- `PORTAL_BASE_URL` and `FRONTEND_BASE_URL` must be the environment's app origin (the portal and the dashboard are served by the same SPA).
- Reference data (trades, vendors, templates) is per environment; use the data-copy procedure in Section 16.7.

---

## 13. Production Infrastructure on AWS

### 13.1 Backend

| Resource | Configuration |
|----------|--------------|
| Amazon ECR | Repository per environment (e.g. `bluonx-backend-dev`); images tagged `latest` plus an immutable tag (date or commit) recommended for rollback |
| ECS cluster and service | Fargate launch type; **desired count 1**; deployment configuration **minimum healthy 0%, maximum 100%** so old and new tasks never run together (avoids a second scheduler during deploys) |
| Task definition | Container port 8000; CPU/memory sized for a single process (0.5 vCPU / 1 GB is a reasonable starting point); environment and secrets from Secrets Manager; log driver `awslogs` to a dedicated log group |
| Application Load Balancer | HTTPS listener with an ACM certificate for the API domain; HTTP → HTTPS redirect; target group health check path `/health` |
| Networking | Tasks in subnets with outbound internet (NAT or public IP) to reach Supabase, SES, DocuSign and Google; security group allowing inbound 8000 only from the ALB |
| IAM | Task execution role (ECR pull, CloudWatch logs, secrets read); SES sending via an IAM user's keys today — a task role with `ses:SendEmail` is the recommended improvement |
| CloudWatch | JSON logs queryable in Logs Insights by `request_id`, `status`, `route`, `user_id`, `job_id`; set retention (e.g. 30–90 days) |
| DNS | API domain (CNAME/alias) to the ALB |

### 13.2 Frontend

| Resource | Configuration |
|----------|--------------|
| AWS Amplify app | Connected to the GitHub repository; one branch per environment; build command `npm ci` then `npm run build` in `frontend/`; artefact directory `frontend/dist` |
| SPA routing | Rewrite rule sending all non-file paths to `/index.html` (required for deep links such as `/bid/<token>` and `/projects/...`) |
| Environment variables | `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_GOOGLE_MAPS_API_KEY`, `VITE_DEMO_MODE=false` — set in Amplify (build-time values) |
| Domain | App domain with Amplify-managed certificate |

### 13.3 Email

SES verified domain and sender, production access (out of sandbox), configuration set with SNS event destination, SNS topic with policy allowing SES to publish, HTTPS subscription to the API webhook in `Confirmed` state.

### 13.4 Cost Profile

Indicative monthly running cost at MVP volume: ECS Fargate single task + ALB + Amplify + SES + CloudWatch on AWS in the order of tens of dollars; Supabase Pro; DocuSign plan; Google Maps usage within free credit at current volume. AWS **Basic Support (free)** is sufficient; paid AWS support plans are not required for the services to work. Keep a valid payment method on the AWS account once promotional credits expire.

---

## 14. Build, Release and Rollback Procedures

### 14.1 Source Control Flow

1. Develop on a feature branch; open a pull request into `dev`.
2. Before pushing, run the backend test container, the frontend type-check / lint / tests, and resolve any remote changes by pulling with rebase. **A rejected push means the code never reached GitHub** — always confirm the push succeeded before deploying.
3. Merge `dev` to `main` for production releases.

### 14.2 Backend Release

1. Ensure the target commit is on the branch you are releasing and your working copy matches it.
2. Apply any required database changes to the target Supabase project first (Section 7.7).
3. Build the image from `backend/` **without the Docker layer cache** (`docker build --no-cache`). Building with cache has, in practice, produced an image identical to the previous one, so ECS kept running old code.
4. Tag the image for the environment's ECR repository (both `latest` and an immutable release tag) and authenticate Docker to ECR.
5. Push the image to ECR and note the new image digest.
6. In ECS, update the service with **Force new deployment** (or register a new task-definition revision pointing to the immutable tag). Wait for the new task to pass health checks; with minimum healthy 0% the old task stops first, giving a brief interruption of a few seconds to a minute.
7. **Verify:** `/health` returns 200 with an `X-Request-ID` header; the interactive API docs (`/docs` or `/openapi.json`) list any new endpoints; `/api/v1/admin/scheduler-health` shows the scheduler running with all jobs; CloudWatch shows clean start-up lines including the active email provider.

### 14.3 Frontend Release

1. Push to the branch connected to Amplify; the build starts automatically.
2. Confirm the build succeeded in the Amplify console and the environment variables are correct (they are baked in at build time — changing a variable requires a rebuild).
3. Hard-refresh the app and verify the change. If the new UI calls a new API endpoint, release the backend first; otherwise users will see the new button but get errors (for example 405 or 404).

### 14.4 Database Release

1. Write an idempotent SQL change script.
2. Apply to development; run the live-database test selection if affected; exercise the feature.
3. Apply to production in a quiet period; then deploy dependent code.
4. Update `database/bluonx_complete_schema.sql` and the schema documentation in the same pull request.

### 14.5 Rollback

| Layer | Rollback method |
|-------|----------------|
| Backend | Redeploy the previous immutable image tag (or previous task-definition revision) with force new deployment |
| Frontend | Redeploy the previous successful build from the Amplify console, or revert the commit and push |
| Database | Apply a compensating script. Prefer additive changes so code rollbacks never require schema rollbacks. Supabase point-in-time recovery / daily backups for disasters |

### 14.6 Release Verification Checklist

- Login, dashboard counts and project list load.
- Create a task and use **Add Default Tasks** on a test project (expect created / skipped counts).
- Open a bid package page; send a test invitation to a controlled address; confirm `email_log` advances to `delivered`.
- Open the vendor link and save a draft.
- Scheduler health shows all eight jobs.
- DocuSign health reports a valid token (when DocuSign is configured).

---

## 15. Configuration Reference

### 15.1 Backend Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SUPABASE_URL` | Yes | — | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | — | Service-role key (secret) |
| `SUPABASE_JWT_SECRET` | Yes | — | Legacy HS256 verification secret (secret) |
| `VENDOR_JWT_SECRET` | Yes | — | Vendor portal JWT signing secret; long random value, different from the Supabase secret (secret) |
| `VENDOR_JWT_EXPIRY_HOURS` | No | 4 | Vendor session lifetime |
| `APP_ENV` | No | development | `production` enables start-up guards and JSON logs |
| `DEBUG` | No | true | Set false in production |
| `API_V1_PREFIX` | No | `/api/v1` | API prefix |
| `BUSINESS_TIMEZONE` | No | America/Chicago | Business "today" for milestones and jobs |
| `CORS_ORIGINS` | Prod | `["http://localhost:5173"]` | JSON list of allowed browser origins |
| `LOG_LEVEL` | No | INFO | Root log level |
| `LOG_FORMAT` | No | json in production, console otherwise | Log format override |
| `FRONTEND_BASE_URL` | Prod | `http://localhost:5173` | Staff app origin; invite redirect `/accept-invite` |
| `PORTAL_BASE_URL` | Prod | `http://localhost:5173` | Origin used in vendor magic links and milestone links |
| `EMAIL_PROVIDER` | Prod | mock | `mock` or `ses` |
| `SES_FROM_EMAIL` | With SES | noreply@bluonx.com | Verified sender |
| `SES_CONFIGURATION_SET` | Prod | — | Enables delivery/bounce/complaint tracking |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | With SES | — | SES credentials (secret) |
| `AWS_REGION` | No | us-east-1 | SES region |
| `GOOGLE_MAPS_API_KEY` | Recommended | — | Geocoding and Routes |
| `DOCUSIGN_PROVIDER` | No | mock | `mock` or `sandbox` (real API) |
| `DOCUSIGN_ACCOUNT_ID`, `DOCUSIGN_USER_ID`, `DOCUSIGN_INTEGRATION_KEY` | With DocuSign | — | Account, impersonated user, client id |
| `DOCUSIGN_PRIVATE_KEY_PATH` | With DocuSign | — | Path to the RSA key inside the container (e.g. `secrets/docusign_private_key.pem`) |
| `DOCUSIGN_PRIVATE_KEY_SECRET` | With DocuSign in AWS | — | PEM content written to the key path at container start (secret) |
| `DOCUSIGN_ACCOUNT_BASE_URL` | With DocuSign | — | REST base host |
| `DOCUSIGN_OAUTH_BASE_URL` | No | account-d.docusign.com | OAuth host (no scheme) |
| `DOCUSIGN_JWT_SCOPES` | No | signature impersonation | Token scopes |
| `DOCUSIGN_REDIRECT_URI` | No | local health URL | Used only to build the consent URL |
| `DOCUSIGN_TOKEN_EXPIRES_IN` | No | 3600 | Assertion lifetime |
| `DOCUSIGN_CONNECT_HMAC_KEY` | With Connect | — | Webhook HMAC key (secret) |
| `DOCUSIGN_CONNECT_WEBHOOK_URL` | With Connect | — | Public URL of `/api/v1/webhooks/docusign-connect` |
| `CONTRACT_OWNER_SIGNER_NAME`, `CONTRACT_OWNER_SIGNER_EMAIL` | No | — | Fallback signer for awards created before the signer roster |
| `CONTRACT_FIRM_NAME` | No | BluOnX Development LLC | Contract PDF firm name |
| `CONTRACT_FIRM_CONTACT_EMAIL`, `_PHONE`, `_ADDRESS` | No | — | Contract PDF contact block |
| `TEST_ADMIN_EMAIL`, `TEST_ADMIN_PASSWORD` | Tests only | — | Live-database test login |

### 15.2 Frontend Environment Variables (build time)

| Variable | Purpose |
|----------|---------|
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon key (public, RLS-protected) |
| `VITE_API_BASE_URL` | Backend origin (without `/api/v1`) |
| `VITE_GOOGLE_MAPS_API_KEY` | Browser Maps key (referrer-restricted) |
| `VITE_DEMO_MODE` | `true` only for demos; `false` in production |

Per-environment defaults live in `frontend/.env.development` and `frontend/.env.production`; local secrets in `frontend/.env`.

### 15.3 Production Start-up Guards

With `APP_ENV=production` the backend refuses to start if: `EMAIL_PROVIDER` is not `ses`; SES is selected without AWS keys; `FRONTEND_BASE_URL` is not a non-localhost HTTPS URL; `CORS_ORIGINS` is empty, contains `*`, a localhost origin, or a non-HTTPS origin; or the log settings are invalid. A failing guard prints the reason in the container log and the ECS task stops — check CloudWatch first when a deploy will not stay up.

---

## 16. Production Operations Runbook

### 16.1 Health Endpoints

| Endpoint | Auth | Meaning |
|----------|------|---------|
| `GET /health` | None | Process up (ALB health check) |
| `GET /api/v1/admin/scheduler-health` | Admin | Scheduler running; last run of each job |
| `GET /api/v1/admin/docusign-health` | Admin | DocuSign token mint works; consent status |
| `GET /docs`, `/openapi.json` | None | Live API surface — confirms which code version is running |

### 16.2 Monitoring Recommendations

- **Uptime:** external monitor on `/health` and on the scheduler-health endpoint (with an admin token or a dedicated check), alerting a monitored inbox.
- **Logs:** CloudWatch Logs Insights saved queries for `status >= 500`, slow requests (`duration_ms`), and job failures (`job_id` with error level).
- **Alarms:** ECS running-task count < 1; ALB 5xx rate; target unhealthy count.
- **Email:** periodic review of `email_log` rows in `bounced`, `complained` or `failed`; SES reputation dashboard (bounce and complaint rates).
- **Errors:** Sentry (or equivalent) is recommended but not yet integrated.

### 16.3 Daily / Weekly / Annual Routines

| Frequency | Task |
|-----------|------|
| Daily (automatic) | Scheduler jobs; review in-app notifications (insurance, escalations, scheduler alerts) |
| Weekly | Check scheduler health; scan error logs; review bounced emails and correct vendor addresses |
| Monthly | Review AWS and Supabase usage and billing; rotate any expiring credentials; confirm backups |
| Annually (January) | Confirm the holiday seed ran and review next year's calendar; review DocuSign key and certificate validity |

### 16.4 Administrative Tasks in the Application

| Task | Where |
|------|-------|
| Invite, re-invite, change role, deactivate, delete, restore users | Settings → Users |
| Maintain trades and their phases | Settings → Trades |
| Maintain holiday calendar | Settings → Calendar |
| Maintain contract signers | Settings → Contract Signers |
| Bid templates | Bid Templates page |
| Seed standard tasks into a project | Project → Tasks → Add Default Tasks |

### 16.5 Bootstrapping a New Environment

1. Create the Supabase project; create the three private storage buckets with default settings.
2. Run the schema, RLS and storage SQL files in order.
3. Configure Supabase Auth: Site URL, redirect allow list, SMTP, invite template; disable public sign-ups.
4. Create the first admin in Supabase Auth with role metadata `admin` (or update the `public.users` role after creation).
5. Load trades (all trades required by the Task Template Library), optionally vendors and bid templates (Section 16.7).
6. Seed the holiday calendar by running the seed script as a module from `backend/` (`python -m scripts.seed_holidays`).
7. Add at least one contract signer.
8. Configure SES, SNS, DocuSign and Google keys; deploy backend and frontend; run the release verification checklist.

### 16.6 Backups and Recovery

- Supabase Pro provides daily backups (and optional point-in-time recovery); confirm retention in the dashboard.
- Storage buckets are not covered by database backups — schedule a periodic export of the buckets for critical documents (signed contracts are also retained in DocuSign).
- Code and SQL are in GitHub; container images are in ECR.

### 16.7 Copying Reference Data Between Environments

When populating development from production (or vice versa) with trades, vendors and templates, copy in dependency order so foreign keys resolve:

1. `trades`
2. `vendors`
3. `vendor_contacts` (needs vendors)
4. `vendor_trades` (needs vendors and trades)
5. `vendor_documents` (needs vendors; replace `uploaded_by` with a valid user id from the target environment)
6. `bid_templates` (needs trades; replace `created_by` with a valid target user id)
7. `bid_template_items` (needs bid templates)

Export from the source with a SELECT (choosing only the columns and rows needed), insert into the target with "on conflict do nothing," then compare row counts per table. Storage files referenced by `vendor_documents` must be copied separately if downloads are needed in the target.

### 16.8 Credential Rotation

| Credential | Rotation steps |
|------------|---------------|
| Supabase service-role / JWT secret | Rotate in Supabase; update Secrets Manager; force new ECS deployment; staff sessions refresh automatically |
| `VENDOR_JWT_SECRET` | Update secret and redeploy; active vendor sessions end and vendors simply click their link again |
| AWS SES keys | Create new keys, update secret, redeploy, then delete old keys |
| DocuSign RSA key | Add new key to the integration, update `DOCUSIGN_PRIVATE_KEY_SECRET`, redeploy, verify health, remove old key |
| DocuSign Connect HMAC | Add new key in Connect, update the variable, redeploy, then remove the old key |
| Google Maps keys | Create restricted replacement keys, update backend secret and Amplify variable (rebuild), then delete old keys |

---

## 17. Troubleshooting Guide

| Symptom | Likely cause | Resolution |
|---------|-------------|------------|
| New button works locally but returns **405 Method Not Allowed** in AWS (response header `server: uvicorn`, `allow: GET`) | The running container is an older build without the new route (or a static route is registered after a parameterised one) | Confirm the commit is pushed; rebuild without cache; push to ECR; force new deployment; check `/openapi.json` lists the route; verify route order (Section 5.5) |
| Endpoint missing from `/docs` after deploy | Old image still running, or route excluded from the schema | As above; confirm the image digest ECS is running matches the pushed digest |
| Every browser call fails with a CORS error | `CORS_ORIGINS` does not contain the app origin, or wrong `VITE_API_BASE_URL` | Fix the variable and redeploy (frontend variables need a rebuild) |
| Backend task stops immediately after deploy | A production start-up guard failed or a required variable is missing | Read the CloudWatch log for the reason (Section 15.3) |
| Emails stay at `sent`, never `delivered` | `SES_CONFIGURATION_SET` missing, or SNS subscription not confirmed | Set the variable; confirm the subscription; test with the SES simulator |
| Emails not received at all | Mock provider active, SES sandbox, unverified sender | Check start-up log for the provider; request SES production access; verify the identity |
| Invite link lands on the wrong page or fails | Redirect not in Supabase allow list; wrong `FRONTEND_BASE_URL` | Add `{FRONTEND_BASE_URL}/accept-invite` to the allow list; correct the variable |
| Contract not sent after award | DocuSign misconfiguration, consent not granted, missing private key in container | Check DocuSign health; grant consent; confirm key injection; use the re-send action |
| Connect webhook returns 401 | HMAC key mismatch or not configured | Align `DOCUSIGN_CONNECT_HMAC_KEY` with the DocuSign Connect key |
| Uploads fail with 500 at storage | Bucket MIME restrictions or size limit narrower than the app allow-list | Leave bucket MIME list empty; apply the storage SQL; raise size limits |
| Vendor link says expired or revoked | Deadline passed, link re-sent, or package closed | PM re-sends the link (if the package is open) or extends via a revision request |
| Milestone shows unresponsive but vendor says they replied | Vendor opened the link but did not press Yes/No, or answered after a reschedule (stale cycle) | PM updates the status manually from the milestone page |
| Duplicate emails | More than one backend instance or worker running | Ensure ECS desired count 1, min healthy 0%, no `--workers` |
| Scheduler health shows jobs "never run" | Container recently restarted (in-memory state) or scheduler stopped | Wait for the next trigger; if the scheduler is not running, redeploy and investigate logs |
| Add Default Tasks adds nothing | All template task names already exist in the project | Expected; the response reports them as skipped |
| Seeded tasks show an unexpected trade | A template's trade is missing or inactive in this environment | Create/activate the trade with the correct phase; correct affected tasks |
| Holiday-sensitive escalations fire a day early | Holiday calendar empty | Run the holiday seed script |
| 409 when deleting a task, project or template | Live bids, awards, contracts or references exist | Cancel or archive instead (by design) |

---

## 18. Testing and Quality

### 18.1 Backend

- Run the hermetic suite in Docker with `docker compose run --rm api-test` (no database, network or credentials required).
- Live-database tests (triggers, business-day functions, RPC grants) are marked `requires_db` and run with the marker selection; they need `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and `TEST_ADMIN_*`. They write and clean up real rows — coordinate before running against a shared project.
- Test layout mirrors the domains: awards, bid package creation and status, revisions, templates and freeze, contracts, contract signers, DocuSign client and envelopes, email and templates, holidays, invitation tracking, jobs (with an in-memory Supabase double), milestones and milestone portal, recommendation, reviews, routers, scope of work, scoring, services, auth, distance, file validation, logging, config.

### 18.2 Frontend

- `npm run test` (Vitest + React Testing Library + jsdom), `npm run lint`, and `npm run build` (which includes the TypeScript build check).
- Tests cover pages, forms, the vendor portal, notifications, milestones, contracts, task list (including the default-task button) and the holiday form.

### 18.3 Quality Gates (recommended CI)

On every pull request: backend hermetic tests; frontend type-check, lint and tests; Docker image build. A GitHub Actions workflow does not yet exist (Section 20).

---

## 19. Extending and Customising the System

### 19.1 Adding a New API Endpoint

1. Add Pydantic models in `app/models/`.
2. Put business logic in a service in `app/services/` that raises a domain error with status and message.
3. Add the route in the relevant router with the right auth dependency (`get_current_active_user` or `require_admin`); keep static paths above parameterised ones and type ids as UUIDs.
4. If the operation writes several rows that must succeed together, implement a stored procedure and call it from the service.
5. Add the path to `frontend/src/constants/api.ts`, a mutation or query in the feature's `api/`, a hook in `hooks/`, and invalidate the right query keys.
6. Add backend and frontend tests.

### 19.2 Changing the Task Template Library

The library is defined centrally in the backend tasks router (the default-task list and the trade-alias map).

1. Edit, add or remove template entries (activity code, name, phase, trade, bid type). Keep entries in activity-code order — that becomes the task order in projects.
2. Ensure each trade name exists and is active in **every** environment with a compatible phase, or add an alias.
3. Remember that existing projects are not changed; renamed templates will be seen as new by the duplicate check (it matches on the full task name).
4. Update the endpoint summary if the count changes, update tests, and update Appendix A of the Context Handoff.
5. Release the backend (Section 14.2).

A future enhancement can move the library into database tables with an admin editor, mirroring the bid-template feature (template table + items, management page, and the seeding endpoint reading from the table).

### 19.3 Adding a Trade

Admins add trades in Settings → Trades with the right phase. Then link vendors to the trade, optionally create a trade-affiliated bid template, and if it should appear in the default library, follow Section 19.2.

### 19.4 Changing Scoring Weights or Rules

Weights, neutral scores, insurance horizon and timeline buckets are named constants at the top of the scoring service. Change them, update the scoring tests, and note that existing score rows keep their snapshot until a PM recomputes. If weights should become per-project, add columns to `bid_packages` and pass them into the orchestrator.

### 19.5 Changing Pre-Award Rules

Each check is a pure function returning a self-describing result. Add a new function, include it in the validator, decide its severity (block vs warn vs skipped), bump the rubric version, and add tests. The UI renders checks generically from the result.

### 19.6 Adding or Editing an Email

1. Create `name.html` (extending `base.html`) and `name.txt` in `app/templates/emails/`.
2. Render and send through the email service's single-send function (never the bulk helper, which bypasses `email_log`).
3. If the email belongs to a new category, extend the `email_log.email_type` CHECK constraint and the vendor communication-history filter.
4. Use the milestone email preview script as a pattern for visual review.

### 19.7 Adding a Scheduled Job

Follow `backend/app/jobs/README.md`: one module with a `register(scheduler)` function; a tracked entry point returning a JSON-serialisable result; UTC cron trigger with a Central-time comment; default job options; add the id to the known-jobs list and register it in the start function; optionally add it to the self-check interval map; test the job body against the in-memory database double.

### 19.8 Contract Terms

Replace the firm terms template (`app/templates/contracts/firm_terms.txt.j2`) and the default payment terms in the contract PDF service with client-approved language. For per-contract terms, populate `contracts.payment_terms` at envelope send.

### 19.9 Re-enabling Dormant Capabilities

| Capability | What remains | What is needed |
|------------|-------------|----------------|
| Direct assignment | Schema value and submission flag; display labels | Allow the value in the task models; build the synthetic-submission award path |
| Live dashboard updates | Realtime helpers in `lib/realtime.ts` | Enable Realtime on tables; subscribe in features |
| Manual score adjustment | `bid_scores.scored_by` | Endpoint and UI with justification |
| Email open/click tracking | `email_log.opened_at`, `clicked_at` | SES open/click events and handler mapping |
| Vendor flag creation | `vendor_flags` table and read-only tab | Create/resolve endpoints and UI |

---

## 20. Known Limitations and Technical Debt

| Area | Limitation | Recommendation |
|------|-----------|----------------|
| Contract payment terms | Placeholder text in every generated contract | Replace before production contracts (blocking) |
| Scaling | Single backend instance because of the in-process scheduler | Move jobs to a separate worker or add database advisory locks before scaling out |
| Scheduler state | Last-run state is in memory; resets on restart | Persist if historical job reporting is needed |
| Rate limiting | In-memory, per process | Adequate at one instance; use a shared store if scaled |
| Monitoring | No Sentry or uptime monitor yet | Add both |
| CI | No GitHub Actions workflow | Add the gates in Section 18.3 |
| Frontend DB types | Placeholder types make direct reads loosely typed | Regenerate from the live schema |
| Task Template Library | Defined in code; unresolved trade falls back to the first active trade | Move to database tables with an admin editor; fail or warn on unresolved trades |
| Default-task seeding | Bulk insert skips the per-task trade-phase validation | Validate phase compatibility during seeding |
| Distance | Bulk radius is straight-line | Acceptable; switch to Routes matrix if driving distance is needed |
| Upload scanning | No antivirus | Add scanning (e.g. ClamAV or a managed service) if vendor uploads become higher risk |
| Email bulk helper | Bypasses `email_log` | Do not use; or add logging |
| Communication history | Covers bid, revision and submission email references | Extend filters when new reference types are added |
| Schema management | Manual SQL application | Consider Supabase CLI migrations |
| Milestone "starting soon" reminder | Supported in the data model, not sent | Add to the daily job if requested |

---

## 21. Appendix A — API Endpoint Catalogue

All paths are prefixed with `/api/v1` except `/health`. "Staff" = active admin or PM; "Admin" = admin only; "Vendor" = vendor JWT; "Public" = no auth (signature-verified where noted).

### Health and administration

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | Public | Liveness |
| GET | `/admin/scheduler-health` | Admin | Scheduler and job status |
| GET | `/admin/docusign-health` | Admin | DocuSign token and consent status |

### Users, trades, holidays, signers

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/users/me` | Staff | Current profile |
| POST | `/users/invite` | Admin | Invite a user |
| GET | `/users`, `/users/{id}` | Admin | List / get users |
| PATCH | `/users/{id}` | Admin | Change role or active status |
| DELETE | `/users/{id}` | Admin | Soft delete |
| POST | `/users/{id}/restore` | Admin | Restore |
| POST | `/users/{id}/resend-invite` | Admin | Resend invitation |
| GET / POST / PATCH / DELETE | `/trades`, `/trades/{id}` | Staff read, Admin write | Trade management |
| POST | `/holidays`, `/holidays/range` | Admin | Add holiday(s) |
| PATCH / DELETE | `/holidays/{id}` | Admin | Edit / remove |
| POST | `/contract-signers` | Admin | Add signer |
| PATCH | `/contract-signers/{id}` | Admin | Edit / deactivate signer |

### Vendors

| Method | Path | Purpose |
|--------|------|---------|
| GET / POST | `/vendors` | List / create |
| GET | `/vendors/insurance-expiring-count` | Sidebar badge count |
| GET / PATCH / DELETE | `/vendors/{id}` | Read / update / soft delete (blocked with live work) |
| GET / POST | `/vendors/{id}/contacts` | Contacts |
| PATCH / DELETE | `/vendors/{id}/contacts/{contact_id}` | Contact edit / delete |
| GET / POST | `/vendors/{id}/trades` | Trade links |
| DELETE | `/vendors/{id}/trades/{trade_id}` | Remove trade link |
| GET / POST | `/vendors/{id}/documents` | Documents (upload multipart) |
| GET | `/vendors/{id}/documents/{doc_id}/url` | Signed download URL |
| DELETE | `/vendors/{id}/documents/{doc_id}` | Remove document |
| GET | `/vendors/{id}/email-log` | Communication history |
| POST | `/vendors/import` | CSV import (parsed rows) |

### Projects and tasks

| Method | Path | Purpose |
|--------|------|---------|
| GET / POST | `/projects` | List / create |
| GET / PATCH / DELETE | `/projects/{id}` | Read / update / soft delete |
| POST | `/projects/{id}/archive`, `/projects/{id}/unarchive` | Archive state |
| GET / POST | `/projects/{id}/documents` | Project documents |
| GET | `/projects/{id}/documents/{doc_id}/url` | Signed URL |
| DELETE | `/projects/{id}/documents/{doc_id}` | Remove |
| GET / POST | `/projects/{id}/tasks` | List / create task |
| POST | `/projects/{id}/tasks/default` | **Seed the Task Template Library** |
| PUT | `/projects/{id}/tasks/reorder` | Bulk sort order |
| GET / PATCH / DELETE | `/projects/{id}/tasks/{task_id}` | Read / update / soft delete (UUID-typed) |
| GET | `/tasks/{task_id}/qualified-vendors` | Vendor filtering |

### Bidding

| Method | Path | Purpose |
|--------|------|---------|
| GET / POST / PUT / DELETE | `/bid-templates`, `/bid-templates/{id}` | Template library |
| POST | `/bid-templates/{id}/duplicate` | Duplicate |
| POST | `/tasks/{task_id}/bid-packages` | Create package with invitations |
| GET | `/bid-packages` | Cross-task list |
| GET / PATCH | `/bid-packages/{id}` | Detail / update |
| POST | `/bid-packages/{id}/close`, `/bid-packages/{id}/cancel` | Close / cancel round |
| GET | `/bid-packages/{id}/invitations`, `/bid-packages/{id}/email-log` | Tracking |
| POST / GET | `/bid-packages/{id}/scores` | Compute / read scores |
| POST / DELETE | `/bid-packages/{id}/documents[/{doc_id}]` | Package documents |
| POST | `/bid-invitations/{id}/resend-link` | Send / re-send link |
| PUT | `/bid-invitations/{id}/status` | Manual status (e.g. declined) |
| GET | `/bid-invitations/{id}` | Invitation detail |
| GET | `/bid-submissions/{id}` | Full submission with signed attachment URLs |
| POST / GET | `/bid-revision-requests` | Create / list revision requests |
| POST | `/bid-revision-requests/{id}/cancel` | Cancel revision |

### Awards, contracts, reviews, milestones

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/awards/validate/{bid_submission_id}` | Pre-award preview |
| POST | `/awards` | Create award (+ contract send) |
| GET / PATCH | `/awards/{id}` | Read / update |
| POST | `/awards/{id}/send-contract` | Re-send contract envelope |
| POST | `/contracts/{id}/mark-complete` | Complete contract |
| POST | `/contracts/{id}/review` | Create PM review |
| PATCH | `/reviews/{id}` | Edit review |
| GET / POST | `/milestones` | List / create |
| GET / PATCH | `/milestones/{id}` | Read / edit |
| POST | `/milestones/{id}/mark-started`, `/mark-completed`, `/reschedule`, `/cancel` | PM transitions |

### Notifications

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/notifications` | Paginated list |
| GET | `/notifications/unread-count` | Badge |
| PATCH | `/notifications/{id}/read`, `/notifications/mark-all-read` | Mark read |

### Vendor authentication and portal

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/vendor-auth/validate-token` | Public (rate-limited) | Bid / revision magic link → vendor JWT + context |
| POST | `/vendor-auth/validate-milestone-token` | Public | Milestone link → milestone JWT + question |
| GET | `/vendor-portal/bid-context` | Vendor | Bid context |
| POST | `/vendor-portal/submissions` | Vendor | Create draft |
| PUT | `/vendor-portal/submissions/{id}` | Vendor | Update draft |
| POST | `/vendor-portal/submissions/{id}/submit` | Vendor | Final submit |
| GET | `/vendor-portal/submissions/{id}` | Vendor | Read own submission |
| GET | `/vendor-portal/submissions/{id}/revision-prefill` | Vendor | Revision pre-fill |
| POST | `/vendor-portal/revision-requests/{id}/decline` | Vendor | Decline revision |
| POST / GET / DELETE | `/vendor-portal/submissions/{id}/attachments[/{attachment_id}]` | Vendor | Attachments |
| GET | `/vendor-portal/documents/{project_document_id}/download` | Vendor | Package document download |
| POST | `/vendor-portal/milestones/{milestone_alert_id}/respond` | Milestone JWT | Record Yes/No |

### Webhooks

| Method | Path | Verification |
|--------|------|-------------|
| POST | `/webhooks/ses-notifications` | SNS signature |
| POST | `/webhooks/docusign-connect` | HMAC-SHA256 |

---

## 22. Appendix B — Status Vocabularies

| Entity | Statuses |
|--------|---------|
| User role | admin, project_manager |
| Trade phase | due_diligence, development, both |
| Vendor status | active, inactive, suspended |
| Vendor onboarding | pending, partial, complete |
| Vendor document type / status | w9, insurance_certificate, master_trade_agreement / valid, expired, pending_review |
| Project | planning, active, on_hold, completed, cancelled (plus archived flag) |
| Project document kind | reference, scope_of_work |
| Task phase / bid type | due_diligence, development / competitive, internal (direct_assign dormant) |
| Task | draft, bidding, evaluating, awarded, in_progress, completed, cancelled |
| Bid template item type | lump_sum, unit_price |
| Bid package | open, closed, evaluating, cancelled |
| Bid invitation | pending_send, sent, send_failed, opened, submitted, declined, expired, no_response |
| Bid submission | draft, submitted, under_review, accepted, rejected (plus superseded flag) |
| Revision request | pending, submitted, declined, expired, cancelled |
| Award | pending_acceptance, accepted, declined_by_vendor, cancelled |
| Contract | draft, sent_for_signature, executed, active, completed, terminated |
| DocuSign envelope | sent, delivered, signed, completed, declined, voided |
| Milestone | scheduled, in_progress, delayed, unresponsive, completed, cancelled |
| Milestone alert type | starting_soon, start_check, progress_check, completion_check, delay_alert, no_response_alert, completion_notification |
| Milestone event trigger | creation, vendor_response, pm_action, system_no_response |
| Email type | bid_invitation, bid_reminder, award_notification, decline_notification, milestone_alert, general |
| Email status | queued, sent, delivered, bounced, failed, complained |
| Holiday source | seeded, manual |

---

## 23. Appendix C — Glossary

| Term | Definition |
|------|-----------|
| ALB | AWS Application Load Balancer in front of the ECS service |
| Amplify | AWS service hosting the built React application |
| Anon key | Public Supabase key used by the browser; access governed by RLS |
| APScheduler | Python scheduler running background jobs inside the API process |
| Coat-check pattern | File bytes in storage, metadata row in the database |
| Cycle | Milestone check-in generation; reschedule increments it |
| ECR / ECS / Fargate | AWS container registry / container service / serverless compute for containers |
| Force new deployment | ECS action that replaces running tasks with fresh ones pulling the current image |
| JWT Grant | DocuSign server-to-server authentication using a signed assertion |
| Magic link | Emailed one-per-invitation link that authenticates a vendor without an account |
| Partial unique index | Unique index applied only to rows matching a condition (e.g. active records) |
| RLS | PostgreSQL Row Level Security |
| RPC | A PostgreSQL function called through Supabase as a single transaction |
| Service role | Supabase key that bypasses RLS; backend only |
| Supersession | Replacing a bid with a revision while keeping the original |
| Task Template Library | The 58 standard activity-coded task definitions seeded by Add Default Tasks |
| Working day | Weekday not on the holiday calendar |

---

*End of Technical Overview & Production Operations Guide — Version 1.0*
