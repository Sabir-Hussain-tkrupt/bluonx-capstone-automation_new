# BluOnX Automation: As-Built Reference

> Status: living document. Covers Phases 1 to 8. Phase 9 is in active development; Phases 10 to 12 are not yet built.
> Last updated: June 2026.

---

## A. Purpose and how to read it

This is the bid management and vendor coordination tool built to automate procurement workflow of BluOnX. The project plan describes what the tool was meant to be; this document records what the code actually is.

It serves two jobs: a starting point for navigating the real codebase, and a reference for the behaviours worth verifying during end-to-end testing before deployment.

It is not a re-statement of the plan and not a specification. Where the build matches the plan, it stays brief and points at the code. Where the build diverged, that is called out explicitly, since the divergences are what you cannot get from the plan alone.

**"Where to look" entries** name one load-bearing file or directory per layer (backend, database, frontend) plus the key endpoint, not every file involved. A single function or trigger is named directly; a standard CRUD area is named at the directory level.

**Deviations** are flagged per phase under **Differs from plan**, and collected in **Section E**.

**Companion files** (referenced, not duplicated): deferred work in `DEFERRED.md`; the per-vendor revision feature in `docs/features/per-vendor-bid-revision.md`.

---

## B. System at a glance

### Stack as built

| Layer | Technology |
| --- | --- |
| Frontend | React 18, Vite, TypeScript, Tailwind v4 |
| Backend | FastAPI, Python |
| Database | PostgreSQL via Supabase (Auth, Storage, RLS) |
| Internal auth | Supabase Auth (email/password) |
| Vendor auth | Two-token model (magic link plus short-lived vendor JWT) |
| Email | AWS SES (with a mock provider used in development) |
| Scheduling | APScheduler (AsyncIOScheduler), in-process inside FastAPI |
| Maps | Google Maps Platform (Geocoding, Routes, Maps JS) |
| E-signature | DocuSign (JWT Grant) — Phase 9, in development |

### The core access split

This is the single most important architectural fact and it repeats everywhere:

- **Reads** go directly from the frontend through the Supabase client and are protected by Row Level Security.
- **Writes** go through FastAPI using the `service_role` key, which bypasses RLS. FastAPI is the gatekeeper for every mutation.
- **Vendors never touch Supabase directly.** All vendor access is mediated by FastAPI.

RLS is therefore a safety net for direct client reads, not the primary write guard. The primary write guard is FastAPI.

### Vendor authentication (two-token model)

Vendors authenticate without accounts:

1. A **magic link token** is emailed to the vendor. Its hash is stored; the raw token is never persisted. Its expiry is tied to the bid package deadline, not an arbitrary window.
2. On a valid magic link, FastAPI issues a **short-lived vendor JWT** (a few hours). The vendor's identity is always read server-side from this JWT, never from the request body or URL.

If the JWT expires, the vendor clicks the magic link again and resumes from their saved draft.

### Repository layout

Monorepo, private, `bluonx-capstone-automation`:

```
bluonx-capstone-automation/
  backend/      FastAPI app: routers, services, business logic
  frontend/     React + Vite + TypeScript app
  database/     schema SQL and schema documentation
  docs/         specs, feature docs, this reference
```

Deeper structure is named per phase, in each phase's "Where to look" entry.

---

## C. Cross-cutting conventions

These patterns recur across phases. They are stated once here so the phase sections do not repeat them.

**Writes are single-statement Supabase table operations.** No `db.rpc()` and no explicit application-level transactions. Atomicity is handled by database triggers, not by the application wrapping multiple statements.

**Denormalized foreign keys are kept consistent by triggers.** Several tables carry a denormalized `vendor_id` or `task_id` for query performance (for example `bid_submissions.vendor_id`, `awards.task_id`). Triggers enforce that these always match their source of truth and raise an exception on mismatch. The application never trusts a client-supplied denormalized key.

**Deprecated flows are left as dormant seams, not migrated out.** When a feature is dropped from scope, its schema artefacts (enum values, columns) are left in place rather than removed, so a later revival does not require a migration. The clearest example is `direct_assign` (see Phase 1 and Section E).

**Soft deletes on core entities.** `users`, `vendors`, `projects`, and `tasks` use a `deleted_at` timestamp. Rows are never hard-deleted; RLS read policies filter out soft-deleted rows.

**Email has a mock provider for development.** `EMAIL_PROVIDER=mock` in `backend/.env` is the standing development convention. SES credentials are live, but development runs against the mock so no real email is sent during build and test.

**Scheduling is in-process.** All scheduled jobs run inside the FastAPI process via APScheduler. There is no separate orchestration service.

---

## D. Phase-by-phase status

### Phase 1: Foundation and Database

**Status: complete (Tasks 1.1 to 1.7), with Tasks 1.8 and 1.9 deferred.**

Phase 1 stands up the Supabase project, the full database (schema, indexes, RLS, triggers), the storage buckets, and the internal authentication framework. The database built here is the foundation every later phase reads from and writes to, and most of the system's correctness guarantees (capacity counts, one-active-award-per-task, denormalized consistency) live as database triggers and indexes defined in this phase, not in application code.

#### As built

The database (Tasks 1.2 to 1.5) is the foundation every later phase reads from and writes to. Most of the system's correctness guarantees (capacity counts, one-active-award-per-task, denormalized consistency) live as triggers and indexes here, not in application code. This section summarises only; the table-by-table, trigger-by-trigger detail lives in `database/bluonx_schema_documentation.md` and is not duplicated.

**Project and environment (1.1).** Supabase project created on a personal free-tier account for development. Connection keys (project URL, anon key, service_role key) are set via environment variables: anon key for the frontend Supabase client, service_role key held server-side by FastAPI. Migration to the client's own account is a production step and is deferred (see 1.8 and 1.9).

**Schema (1.2).** 29 tables across seven groups (Access Control 1, Trade and Vendor 5, Project and Task 3, Bid Lifecycle 11, Award and Contract 3, Milestone Tracking 3, Communication and Audit 3). This is one more than the plan's 28: `bid_revision_requests` was added for the per-vendor revision feature. Conventions: UUID primary keys, timezone-aware timestamps, CHECK constraints instead of enums, `ON DELETE RESTRICT` by default with `CASCADE` only on tightly-coupled children. Full table detail in the schema documentation.

**Indexes (1.3).** Foreign-key, filter, and sort indexes, plus four partial unique indexes that are the load-bearing ones for testing because they enforce one active record per scope while preserving history: `idx_awards_one_active_per_task`, `idx_contracts_one_active_per_task`, `idx_bid_submissions_current_per_invitation` (one current non-superseded non-draft submission per invitation), and `idx_bid_revision_requests_one_pending_per_invitation`.

**RLS (1.4).** Enabled on all tables. Authenticated internal users get read access filtered by active-user status; anon gets zero access. Two security-definer helpers in a non-exposed `private` schema, `is_active_user()` and `is_admin()`, back the policies. Write policies exist only where the database itself should guard: admin-only on `users` and `trades`, self-or-admin on `vendor_flags`, owner-scoped on `notifications`, admin-only read on `magic_link_tokens`. Everything else writes through FastAPI via service_role. Full policy list in `database/rls_policies.sql`.

**Triggers (1.5).** Grouped by job: updated-at maintenance; bid package round auto-increment; invitation status sync on submission; denormalized-key consistency guards (raise on mismatch); vendor capacity management (+1 on award accept, -1 on revoke or contract completion, guarded against double-decrement); and the supersession chain for the revision feature. One trigger, `fn_sync_vendor_onboarding_status`, is built but intentionally disabled (commented out) because onboarding status is managed manually by the PM. Function and trigger detail in the schema documentation; trigger bodies in Section 6 of the schema SQL.

**Storage (1.6).** Three private buckets (`vendor-documents`, `project-documents`, `bid-attachments`), twelve policies (full CRUD for authenticated across all three), zero anonymous access. Vendor uploads go through FastAPI via service_role and bypass these policies. Path conventions in the storage setup doc.

**Authentication framework (1.7).** Internal admin/PM auth only; the vendor portal uses a separate auth chain (see cross-cutting conventions and Phase 5). No standalone doc exists for this task, so it is detailed here.

- *Database side:* the `fn_handle_new_auth_user` trigger mirrors each new Supabase Auth user into `public.users`, taking `full_name` and `role` from signup metadata.
- *Auth context:* `contexts/AuthContext.tsx` exposes `AuthProvider` and a `useAuth` hook holding `session`, `user`, `profile` (the `public.users` row including `role`), and `isLoading`. It derives `isAuthenticated = !!session && !!profile`, subscribes to `onAuthStateChange`, fetches the profile with a 10-second abort timeout, and auto-signs-out deactivated users. Exposes `refreshProfile()` and `signOut()`.
- *Auth service:* `services/auth.service.ts` wraps `supabase.auth` with `signUp`, `signIn`, `signOut`, `requestPasswordReset`, `updatePassword`, `updateUserMetadata`, `getCurrentSession`, and `getAccessToken` (returns the JWT or null).
- *Route gating:* `components/auth/ProtectedRoute.tsx` shows a loading screen while `isLoading`, redirects unauthenticated users to the login route (preserving intended destination via `state.from`), and on a `requiredRole` mismatch silently redirects to the dashboard (no information leak).
- *Token to backend:* the Axios instance in `lib/api.ts` (base URL `${VITE_API_BASE_URL}/api/v1`) attaches `Authorization: Bearer <token>` via a request interceptor calling `getAccessToken()`; a response interceptor normalises errors (401 maps to "session expired"). The Supabase client in `lib/supabase.ts` is configured with `persistSession`, `autoRefreshToken`, `detectSessionInUrl`, and `storageKey: 'bluonx-auth'`, so the interceptor always reads a fresh JWT.
- *Email verification:* not enforced in code; it is a Supabase dashboard toggle. `signUp` passes `emailRedirectTo`, so confirmation works if "Confirm Email" is enabled, but the frontend never blocks unverified users and there is no `/auth/callback` enforcement. Development runs with Confirm Email off (session created immediately).

#### Differs from plan

- **29 tables, not 28.** `bid_revision_requests` was added for the per-vendor revision feature.
- **`direct_assign` is a dormant seam.** The schema still carries `tasks.bid_type = 'direct_assign'` in its CHECK constraint and `bid_submissions.is_direct_assign`, but `direct_assign` was dropped from product scope; only `internal` and `competitive` remain in use, and awards are restricted to competitive bids. The seam is left in the schema deliberately, not migrated out.
- **Onboarding sync trigger disabled.** Built per the plan's intent but commented out in favour of manual PM control.
- **n8n references in RLS comments are stale.** The Phase 1 RLS file's comments still mention n8n as a write path. n8n was removed from the system entirely and replaced by APScheduler (this surfaces properly in Phase 7). The comments are historical only; there is no n8n.
- **Tasks 1.8 and 1.9 deferred.** Separate dev/staging/prod Supabase projects and all AWS infrastructure (ECS task definitions, CI/CD, production secrets) were not feasible at the time. See `DEFERRED.md`.

#### Where to look

- Database schema: `database/bluonx_complete_schema.sql` (triggers and functions in Section 6).
- Schema documentation: `database/bluonx_schema_documentation.md`.
- RLS policies: `database/rls_policies.sql` (table RLS) and the storage RLS policy file (bucket RLS).
- Storage bucket setup: `docs/task_1.6_storage_bucket_setup.md`.
- Auth trigger: `fn_handle_new_auth_user` in the schema file.
- Frontend auth: `frontend/src/contexts/AuthContext.tsx`, `frontend/src/services/auth.service.ts`, `frontend/src/components/auth/ProtectedRoute.tsx`, `frontend/src/lib/api.ts` (Axios token interceptor), `frontend/src/lib/supabase.ts`.

---

### Phase 2: Frontend Foundation, Backend API, and Authentication

**Status: complete, with deferred backend-scaffold items.**

Phase 2 stands up the React app, the FastAPI backend, the shared data layer, and the internal authentication system. It produces the chrome and plumbing every feature phase builds on: the route trees, the UI component library, the React Query conventions, and the backend's router/service/core structure.

#### As built

**Frontend app and routing (2.1, 2.6, 2.8).** React 18 with Vite and TypeScript. Tailwind v4 is set up the CSS-first way: no `tailwind.config` or `postcss.config` files, just `@import "tailwindcss"` plus an `@theme` block of custom color tokens in `src/index.css`, driven by the `@tailwindcss/vite` plugin. Routing (React Router v6) is defined in one route tree (`src/routes/index.tsx`) with all path strings centralised in `src/constants/routes.ts`. The provider stack is `BrowserRouter` to `QueryClientProvider` to `AuthProvider` to `ToastProvider` to `GoogleMapsProvider`. There are three isolated route groups: public auth (login, forgot-password, plus bare `/auth/callback` and `/auth/reset-password`), protected dashboard (all internal pages, with `/settings` nested behind an admin-only guard), and the vendor portal (its own provider and layout, custom-JWT, no Supabase). The dashboard chrome lives in `src/components/layout/DashboardLayout.tsx` (sidebar plus header shell rendering pages via `<Outlet />`, role-based sidebar sections, sidebar collapse persisted to localStorage). Breadcrumbs are derived from the URL path.

**UI component library (2.2).** Roughly 25 components under `src/components/ui/`, each in its own subfolder, all hand-built with Tailwind and a local `cn()` helper. No third-party UI kit (no shadcn/ui, Radix, or headless-ui); modals, tabs, dropdowns, and toasts implement their own focus, escape, and outside-click handling. Covers inputs, form field wrappers, layout (Card, Modal, Alert, Tabs, Accordion), data display (Table, StatusBadge, EmptyState, Skeleton, StatCard), navigation, and a custom toast system. A barrel `index.ts` re-exports most of them.

**Data layer (2.4, 2.5).** A singleton React Query client (`src/lib/queryClient.ts`) sets the global defaults: queries use a 2-minute stale time, 10-minute gc time, 2 retries, and refetch on window focus, mount, and reconnect; mutations never auto-retry (to avoid duplicate side effects). Data hooks live per feature under `features/<feature>/hooks/`, query keys are centralised in `src/lib/queryKeys.ts`, and the mutation pattern is invalidate-by-query-key in `onSuccess` (not optimistic cache writes). The Supabase client config is documented in Phase 1.7. Supabase Realtime is plumbed at the infrastructure level (`src/lib/realtime.ts` and two hooks) but not consumed by any feature; the app relies on React Query refetch and invalidation instead (see Differs from plan).

**Backend scaffold (2.3).** Layered FastAPI app under `backend/app/` with the entry point at `app/main.py`. Structure: `routers/` (one module per domain), `services/` (business logic), `models/` (Pydantic request/response schemas), `core/` (cross-cutting infra: config, Supabase client, auth, vendor auth, storage, file validation, rate limit), and `jobs/` (APScheduler scheduler and scheduled jobs, relevant from Phase 7). The Supabase service-role client is a module-level singleton created once in the `lifespan` context manager and stored on `app.state`, with a request-dependency accessor and a separate accessor for non-request job contexts. Config is a pydantic-settings `Settings` object loading `.env`; required vars are `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, and `VENDOR_JWT_SECRET`, with `API_V1_PREFIX` defaulting to `/api/v1`. All domain routers mount under that prefix; the health router mounts at root. CORS defaults to the Vite dev origin only. Packaged via a multi-stage Dockerfile (python:3.11-slim, non-root user, uvicorn on port 8000); `requirements.txt` is the manifest (no pyproject). Deferred scaffold items (production CORS origin, request logging, test infrastructure, frontend type alignment) are tracked in `DEFERRED.md`.

**Authentication system (2.7).** The context, service layer, ProtectedRoute, token interceptor, and Supabase client are all documented in Phase 1.7 and not repeated here. Phase 2 adds the auth pages under `features/auth/pages/`: `LoginPage`, `ForgotPasswordPage`, `ResetPasswordPage`, and a single `AuthCallbackPage` that handles all Supabase auth redirects (routes to the dashboard on sign-in, forwards to the reset page on password recovery). On the backend, the JWT dependency in `app/core/auth.py` auto-detects the token algorithm: `ES256` verified against Supabase's JWKS endpoint, or legacy `HS256` verified with the JWT secret, both requiring audience `authenticated`. It exposes a three-tier chain: current user (JWT only), current active user (with a `public.users` lookup and role/active/deleted checks), and an admin-only guard. The vendor portal has its own separate JWT chain in `app/core/vendor_auth.py`.

**Responsive design (2.9).** Implemented as a Tailwind convention across the component library and layouts (mobile, tablet, desktop breakpoints; the dashboard layout carries mobile menu state and a hamburger in the top header) rather than as a discrete module.

#### Differs from plan

- **No registration page; account creation is invite-only.** The plan's Task 2.7 lists register and email verification flows. The app has no signup page or register route. The `signUp` service function exists but is not surfaced in the UI, consistent with internal accounts being provisioned outside the app.
- **JWT verification is broader than specified.** The plan specified PyJWT with HS256. The backend auto-detects and verifies `ES256` (via Supabase JWKS) as well as legacy `HS256`, both with audience `authenticated`.
- **Supabase Realtime is built but dormant.** The plan's Task 2.4 includes real-time subscription setup. The infrastructure exists (`src/lib/realtime.ts` and subscription/invalidation hooks) but no feature subscribes; the app uses React Query window-focus refetch and mutation invalidation instead. Left as a dormant seam for possible later use.
- **Backend scaffold items deferred.** Production CORS origin, structured request logging, and test infrastructure are not in the scaffold. See `DEFERRED.md`.

#### Where to look

- Frontend entry and providers: `frontend/src/App.tsx`; routes in `frontend/src/routes/index.tsx`, paths in `frontend/src/constants/routes.ts`.
- Tailwind setup: `frontend/vite.config.ts` and `frontend/src/index.css`.
- UI components: `frontend/src/components/ui/`.
- Layout chrome: `frontend/src/components/layout/DashboardLayout.tsx`.
- Data layer: `frontend/src/lib/queryClient.ts`, `frontend/src/lib/queryKeys.ts`, feature hooks under `frontend/src/features/<feature>/hooks/`; Realtime seam in `frontend/src/lib/realtime.ts`.
- Backend entry and wiring: `backend/app/main.py`; structure under `backend/app/` (`routers/`, `services/`, `models/`, `core/`, `jobs/`).
- Backend auth and config: `backend/app/core/auth.py`, `backend/app/core/vendor_auth.py`, `backend/app/core/config.py`.
- Auth pages: `frontend/src/features/auth/pages/`.

---

### Phase 3: Core Entity Management

**Status: complete.**

Phase 3 is the CRUD backbone: vendors, projects, tasks, their documents, the bid template builder, and the Google Maps location layer that powers vendor proximity. Most logic lives inline in the routers (the services layer is used selectively for the heavier pieces).

#### As built

**Vendor, project, task CRUD (3.1, 3.2, 3.3).** Each domain has a feature folder under `frontend/src/features/` with a list page, a modal create/edit form, and a detail page. The three backend routers (`vendors.py`, `projects.py`, `tasks.py`) hold most logic inline; heavier work is extracted to services (vendor insurance recompute, qualified-vendor filtering). Tasks are nested under projects in the API (`/projects/{id}/tasks`) and the task form filters the trade dropdown by the selected phase, with the same rule re-enforced server-side. Soft delete applies only to the top-level entities (`deleted_at` set, reads filter it out); child records like contacts, trades, and documents are hard-deleted. Deletes are blocked with a clear error when active engagements exist: a vendor with live work returns 409, a task with bid packages, awards, or contracts returns 422. Projects additionally have an archive/unarchive state separate from soft delete. Vendor CSV import is a three-step modal that parses client-side with PapaParse and posts already-parsed JSON rows to `POST /vendors/import`; the backend does not parse CSV, it runs each row through the same create path and returns per-row errors with partial success.

**Document upload (3.4).** One shared `FileUpload` dropzone in the UI library, wrapped per feature (vendor docs carry type and expiration, project docs are plainer). Three buckets are fed by multipart endpoints: vendor docs to `vendor-documents` (path `{vendor_id}/{document_type}/{filename}`), project docs to `project-documents` (`{project_id}/{filename}`), and bid attachments to `bid-attachments` (`{submission_id}/{filename}`, collision-deduped). The authoritative validation is server-side in `core/file_validation.py`: a 50 MB dev cap, an allow-list of PDF, JPEG, PNG (project docs also allow TIFF), and a five-step check that ends with a magic-byte signature match, returning 422 on any failure. Bid attachments carry an extra hard 10 MB router cap. Downloads use private Supabase signed URLs (one-hour expiry) via `core/storage.py`. The coat-check split is followed throughout: bytes in the bucket, metadata row in the DB linked by `file_path`, with orphan cleanup if either side fails.

**Google Maps (3.5).** The frontend wraps the app in a `GoogleMapsProvider` (using `@vis.gl/react-google-maps`) that degrades gracefully to plain UI when no key is present; `AddressAutocomplete` uses the Places library purely as input assistance. The system of record for coordinates is the backend: `services/geocoding.py` calls Google's Geocoding REST API on vendor and project create, update, and import. Proximity is exposed through a single route, `GET /projects/{project_id}/nearby-vendors`. Distance logic in `services/distance.py` supports both Google Routes API driving distance and a local haversine calculation, preferring the API with a haversine fallback, but the bulk vendor radius filter uses haversine (straight-line) only, narrowing in SQL by coordinates and trade first, then applying the radius in Python. The 75-mile radius is a default parameter value repeated in three call sites rather than one named constant (worth knowing if it ever needs to change). The Maps key is split across two env vars, `GOOGLE_MAPS_API_KEY` server-side and `VITE_GOOGLE_MAPS_API_KEY` client-side.

**Bid template builder (3.6).** `features/bid-templates/` has a list page, a single form page serving both create and edit, a line-items editor, and a live read-only preview that renders exactly the vendor-facing form (a single total field for lump-sum templates, otherwise the line-item table). The backend (`routers/bid_templates.py`) has no per-item endpoints: items are always sent inline with the parent, and an update deletes and re-inserts the full item list. Validation runs on both layers (Zod and Pydantic): template name and item description required, unit of measure required when an item is unit-priced, at least one line item when not lump sum. Two referential guards matter: deletion is blocked (409) when any bid package references the template, backed by the `ON DELETE RESTRICT` foreign key; and editing is frozen (409) once a live, non-cancelled package references it, so already-issued bids stay comparable. Duplicate-template is the deliberate escape hatch from the edit freeze.

#### Differs from plan

- **`direct_assign` is still selectable in the task form.** The form offers all three bid types (competitive, direct_assign, internal) and the backend accepts them, even though `direct_assign` was dropped from product scope and its downstream award flow was never built. It is a live loose end to be removed later, not yet a dormant seam at the application layer (refines register entry 2).
- **Vendor distance filtering is straight-line, not driving distance.** The plan implied Google Distance Matrix driving distance. The bulk 75-mile filter uses haversine (straight-line) in Python; the Google Routes API path exists but is used only for on-demand single-pair distance, not the bulk filter.
- **Bid templates freeze on edit when a live package references them.** Beyond the plan's delete-only guard, editing is also blocked once a non-cancelled package uses the template (to keep issued bids comparable), with template duplication as the escape hatch.

#### Where to look

- Vendor, project, task features: `frontend/src/features/vendors/`, `frontend/src/features/projects/`, `frontend/src/features/tasks/` (note task pages live under `features/projects/pages/`, task components under `features/tasks/components/`).
- Entity routers: `backend/app/routers/vendors.py`, `projects.py`, `tasks.py`; CSV ingest at `POST /vendors/import`.
- Documents: `frontend/src/components/ui/FileUpload/`, backend `core/file_validation.py` and `core/storage.py`.
- Maps: `frontend/src/providers/GoogleMapsProvider.tsx`; backend `services/geocoding.py`, `services/distance.py`, `services/vendor_filtering.py`; route `GET /projects/{id}/nearby-vendors`.
- Bid templates: `frontend/src/features/bid-templates/`; backend `routers/bid_templates.py`, `models/bid_templates.py`.

---

### Phase 4: Bid Invitation System

**Status: complete, with two known gaps (see below).**

Phase 4 is the invitation pipeline: filter qualified vendors for a competitive task, configure a bid package (deadline, template, documents), select vendors, and send invitation emails with per-vendor magic links, then track invitation status. This is the first phase that writes across several tables in one user action, and it is where the email subsystem and SES/SNS plumbing land.

#### As built

**Vendor filtering (4.1).** `GET /tasks/{task_id}/qualified-vendors` (in the tasks router) delegates to `services/vendor_filtering.py`. It returns two arrays, qualified and disqualified, each with per-vendor detail; disqualified vendors carry their specific `disqualification_reasons` so a PM can see why and override. Flags are informational only and never auto-exclude. The distance leg uses straight-line haversine, not driving distance (register entry 10).

**Email subsystem (4.2, 4.3).** `services/email_service.py` exposes a single send and a bulk send. The provider is chosen by `EMAIL_PROVIDER`: `ses` uses an SES provider (needs AWS keys), anything else falls back to a mock provider that logs the email and returns a synthetic message id. Mock is the default and the standing dev convention. Single send writes an `email_log` row (queued, then sent or failed) and retries transient failures up to three times with exponential backoff; bulk send paces at 0.1s between messages. Templates live in `templates/emails/` rendered with Jinja2, each shipping a paired HTML and plain-text body. The template library already contains more than Phase 4 needs: the bid invitation plus the three reminder tiers (Phase 7), submission and revision confirmations, and several digest and alert templates. The SES bounce and delivery webhook is `POST /api/v1/webhooks/ses-notifications` (public, always returns 200, with SNS signature verification implemented), mapping delivery, bounce, and complaint notifications onto `email_log` status.

**Bid package creation and tokens (4.4).** `POST /tasks/{task_id}/bid-packages` delegates to `services/bid_package_service.py` (a bare `POST /bid-packages` exists but is a 501 stub). All validation runs up front, then the writes happen as a sequence of independent statements: insert the package, loop the document links, then per vendor insert the invitation, insert the magic link token, render and send the email, and log it. The magic link token is a 32-byte url-safe random value, SHA-256 hashed (only the hash stored), with `expires_at` set to the bid package deadline so the link works for the whole bid window. Resend (`POST /bid-invitations/{invitation_id}/resend-link`) hard-revokes the prior tokens (sets `is_used` and `revoked_at`) and issues a fresh one; the vendor-portal validator later rejects a revoked token with HTTP 410.

**Invitation tracking (4.5).** The bid package detail endpoint returns summary counts, invitations, documents, and submitted bids; a separate endpoint lists invitations filterable by status, and a manual status update lets a PM mark a vendor declined, expired, or no-response (submitted invitations are terminal, and a manual change also revokes that invitation's tokens). Overdue expiry is lazy, computed on the detail view: when the deadline has passed and the package is still open, sent and opened invitations flip to expired and the package closes. There is no scheduled job for this transition.

**Vendor selection UI and detail page (4.6).** The flow lives in `features/bids/`. A "Start Bidding" button on the task detail page opens a three-step wizard (configure, select vendors, review and send), all steps implemented; the create page gates on `bid_type === 'competitive'` and shows a not-eligible state otherwise. The vendor selection step renders qualified vendors in a sortable, pre-checked table with a flags column (warning icon, count, tooltip) and a collapsible disqualified section whose rows show reason chips; checking a disqualified vendor opens an override confirmation, and deselect-all deliberately preserves overridden vendors. The bid package detail page shows summary cards, a submission status pie, an invitations table (resend, mark declined, view bid, request or cancel revision), and a lazily loaded email log.

#### Differs from plan

- **Bid package creation is not atomic.** The plan's acceptance criterion called for all-or-nothing creation. The Supabase REST client has no multi-statement transaction, so creation is a sequence of independent writes with accepted partial success: if a vendor's email send fails, that invitation and token row remain in place (status still `sent`), the failure is reported in the response, and the batch continues. There is no rollback and no cleanup of the orphaned invitation. This is consistent with the single-statement write convention, but it means a "sent" invitation does not guarantee an email actually went out.
- **SES/SNS status updates likely do not land (known issue).** The webhook matches `email_log` rows by `id` using the SES message id, but the email service stores a database-generated UUID and never persists the SES message id onto the row. As written, delivery and bounce notifications will not find a matching row, so `email_log` status is effectively not updated from SNS. Worth verifying and fixing before relying on bounce tracking in production.
- **No n8n; scheduling is APScheduler.** The spec still referenced n8n for batch and reminder sends. There is no n8n anywhere; the in-phase batch send is sequential in FastAPI and the reminder jobs are APScheduler (register entry 3).

Minor: bulk send does not write `email_log` rows (only single send does), so any future use of bulk send would bypass the email audit trail. The Phase 4 invitation flow uses single sends in a loop, so it is unaffected.

#### Where to look

- Vendor filtering: `backend/app/services/vendor_filtering.py`; route `GET /tasks/{id}/qualified-vendors`.
- Bid package and invitation backend: `backend/app/routers/bid_packages.py`, `routers/bid_invitations.py`; `services/bid_package_service.py`, `services/invitation_tracking_service.py`.
- Email subsystem: `backend/app/services/email_service.py`, `services/email_providers/`, templates in `backend/app/templates/emails/`, webhook in `routers/webhooks.py`.
- Bid invitation UI: `frontend/src/features/bids/` (wizard under `components/BidPackageWizard/`, detail page `pages/BidPackageDetailPage.tsx`).

---

### Phase 5: Bid Collection (Vendor Portal)

**Status: complete.**

Phase 5 is the vendor-facing portal: a vendor clicks the magic link from their invitation, the backend validates the token and issues a short-lived vendor JWT, and the vendor submits a bid through a multi-step form whose structure comes from the bid template. This is the one path in the system that is reached without a real account, so its isolation from the admin/Supabase auth world is the thing to understand.

#### As built

**Token validation and vendor JWT (5.2).** `POST /vendor-auth/validate-token` is public and returns precise status codes in short-circuit order: 404 unknown token, 410 revoked (checked before expiry), 410 expired, 404 orphaned invitation, 423 package not open, 409 already submitted. On success it returns the vendor JWT and the full bid context (vendor, project, task, instructions, template with items, project documents, existing draft) in one response, so the form needs no follow-up call to render. First use marks the token used and advances the invitation from sent to opened (both non-fatal side effects). The vendor JWT (`core/vendor_auth.py`) is HS256 signed with a dedicated `VENDOR_JWT_SECRET`, carries `type: "vendor_portal"` plus the vendor, contact, invitation, package, and task ids, and expires after `VENDOR_JWT_EXPIRY_HOURS` (default 4). The guard dependency uses its own bearer scheme, decodes only with the vendor secret, and asserts the type claim, so an admin/Supabase token can never satisfy a vendor route and vice versa.

**Portal API and submit validation (5.3, 5.4, 5.5).** All routes live under `/vendor-portal` and depend on the vendor guard: get bid context, create draft (409 if one exists), update draft (replaces line items), submit, get submission, attachment upload/list/delete, and project-document download (one-hour signed URL). `vendor_id` is always taken from the JWT, never the body; ownership checks filter by both invitation and vendor and return 404 rather than 403 to avoid leaking whether a submission exists, with the database consistency trigger as a backstop. Submit re-reads state and runs full server-side validation in `services/vendor_portal_submit_validator.py`: notes within 2000 chars, total greater than zero, and for structured templates the line count must match the template, each line total must equal its own math, and the grand total must equal the sum of lines (lump-sum templates skip the breakdown). It also requires a proposed start date when the package carries a desired start date (the timeline rule that feeds Phase 8 scoring). The final update is guarded with `is_draft = TRUE` to catch a submit-after-submit race, returning 409. Validation failures return 422 with field-level errors.

**Draft and auto-save (5.6).** Auto-save fires every two minutes when the form is dirty, and also on window blur, alongside a manual save. The POST-then-PUT switch keys off whether a submission id exists yet; a draft-conflict error (the unique constraint per invitation) adopts the existing id and retries as an update, and a ref dedupes the case where an attachment upload races the auto-save create.

**Form UI and routing (5.1, 5.8).** The portal is a separate route tree under `features/vendor-portal/` with its own layout (no admin sidebar) and never imports the Supabase client; it uses a dedicated Axios instance with a vendor-JWT interceptor. The form is four steps (company info, pricing, notes and uploads, review), with state held in a `useReducer` store rather than React Hook Form. `portalApi` is a thin router that switches between a real Axios implementation and an in-memory mock based on the `VITE_DEMO_MODE` flag, both implementing a shared interface so they cannot drift; a demo-mode banner shows when the mock is active. The `VendorPortalGuard` sends a vendor with no JWT or context to the expired page (which tells them to re-click the magic link), which is how re-entry after JWT expiry is handled.

**Confirmation (5.7).** The submit flow sends a best-effort confirmation email (a provider failure still returns 200, with a `confirmation_email_sent` flag for the UI). The confirmation page shows a summary card (project, task, submitted-at, bid total) and a next-steps note. There is no PDF receipt; the email plus on-screen summary is the receipt.

#### Differs from plan

- **No PDF receipt.** The plan and the phase acceptance checklist both expected a PDF receipt. The build intentionally produces none; the confirmation email and on-screen summary serve as the record. 
- **Client validation is server-driven, not React Hook Form.** The plan specified per-step React Hook Form validation. The form uses a `useReducer` store with no RHF or Zod; validation is enforced server-side on submit and the field-level errors are mapped back to the relevant step.

Rate limiting on token validation (10 requests per IP per minute, in-memory per worker) and the magic-link IP capture are in place as specified.

#### Where to look

- Vendor auth: `backend/app/routers/vendor_auth.py`, `core/vendor_auth.py`; route `POST /vendor-auth/validate-token`.
- Portal API and validation: `backend/app/routers/vendor_portal.py`, `services/vendor_portal_submit_validator.py`, `core/rate_limit.py`.
- Portal frontend: `frontend/src/features/vendor-portal/` (steps in `components/`, form state in `hooks/useBidFormState.ts`, auto-save in `hooks/useAutoSave.ts`, API split in `services/portalApi.ts`, guard in `context/VendorPortalGuard.tsx`).

---

### Phase 6: Dashboard and Bid Visibility

**Status: complete.**

Phase 6 adds PM visibility surfaces with no new write paths: real dashboard counts, single-bid inspection, a cross-task bid package list, and the first charts. It is additive UI on top of the established read model and introduced no architectural change.

#### As built

**Dashboard counts (6.1).** The dashboard shows four stat cards (Active Projects, Open Tasks, Pending Bids, Active Vendors), each a direct Supabase count query (count helpers in `features/dashboard/api/dashboard.queries.ts`), with the standard skeleton-then-value loading. The optional "Awards This Month" card was dropped. Below the stats are three static quick-access nav cards.

**Single bid detail (6.2).** The previously stubbed `GET /bid-submissions/{submission_id}` is implemented (admin-authed; the other verbs on that router remain stubs) and returns the full submission: line items sorted by order, and attachments with one-hour signed download URLs, alongside vendor and total metadata. The PM views it through a read-only modal (`BidSubmissionDetailModal`) opened from the "View" action on submitted invitation rows, not a separate route.

**Bid package list (6.3).** `GET /bid-packages` lists packages across all tasks with status, project, and sort parameters; submission counts are computed in SQL via embedded aggregates rather than on the client (project-name sort is the one ordering done in memory). The page is `features/bids/pages/BidPackageListPage.tsx` at `/bid-packages`, reached from a new top-level sidebar item labeled "Bids."

**Charts (6.4).** The submission status pie shipped on the bid package detail page. The "Submitted Bid Amounts" comparison bar chart did not land on the detail page as the spec described; it lives on the bid package compare page (which belongs to Phase 8's comparison work). Recharts is the only charting library.

**Refresh model and lifecycle cleanup.** No `refetchInterval` and no Realtime subscriptions were added; the dormant Realtime hooks remain unused (register entry 9), and the app continues to refresh on window focus and mutation invalidation. The pre-phase invitation lifecycle cleanup is in place: "Mark No Response" is gone from the invitations table (only Mark Declined remains), a status update on a submitted invitation returns 409, and resend on a non-open (past-deadline) package returns 400.


#### Where to look

- Dashboard: `frontend/src/features/dashboard/` (counts in `api/dashboard.queries.ts`).
- Single bid detail: backend `routers/bid_submissions.py` (`GET /bid-submissions/{id}`), `services/bid_submission_detail_service.py`; frontend `features/bids/components/BidSubmissionDetailModal.tsx`.
- Bid package list: backend `routers/bid_packages.py` (`GET /bid-packages`), `services/bid_package_list_service.py`; frontend `features/bids/pages/BidPackageListPage.tsx`.
- Charts: `frontend/src/features/bids/components/SubmissionStatusPie.tsx` and `BidAmountBarChart.tsx`.

---

### Phase 7: Automated Reminders and Alerts

**Status: complete.**

Phase 7 adds the scheduled-work and alerting layer: daily bid reminders to vendors, insurance-expiration and post-deadline monitoring for staff, an in-app notification subsystem, and a scheduler self-check. Its defining decision is a clean split by recipient type: external vendors receive email, internal staff receive in-app notifications rather than email. All scheduled work runs in-process via APScheduler; there is no n8n (register entry 3).

#### As built

**Scheduler foundation and jobs (7.1, 7.3, 7.5, 7.6, 7.8).** Five jobs run under `backend/app/jobs/`, each in its own module exposing a `register(scheduler)` and decorated with `@tracked_job`, which logs start and finish, records last-run success or failure, and prevents a job exception from crashing the scheduler. The five are `daily_bid_reminders`, `daily_insurance_expiration`, `post_deadline_escalation`, `scheduler_self_check`, and the pre-existing `revision_expiry`. All use UTC cron triggers (staggered through the morning) with local-time intent in code comments, and all surface their last run and result on `GET /api/v1/admin/scheduler-health`.

- *Bid reminders* fire at T-7, T-3, and T-0 relative to the package deadline, skipping vendors who already submitted, declined, expired, or were marked no-response, with per-day dedup via `email_log` and a status re-check inside each send to catch vendors who submit between query and send. Sends fan out through `asyncio.gather` with a concurrency semaphore. Notably, reminders carry no magic link; they tell the vendor to use the link from their original invitation email, which preserves the one-token-per-invitation model.
- *Insurance expiration* notifies admins at exact T-30 and T-7 dates and daily once expired until acknowledged (admin marks the underlying certificate expired, which recomputes the vendor's date and stops the match). Deep-links to the vendor.
- *Post-deadline escalation* finds packages whose deadline passed in the last 24 hours with still-pending invitations, notifies the package creator, and then flips those invitations to no-response, but only for a package where at least one notification actually reached someone.
- *Scheduler self-check* compares each watched job's last run against a configured interval plus a two-hour grace window and sends admins one consolidated alert listing stale jobs. Jobs are watched only if explicitly listed in its interval map (fail-closed), and the self-check deliberately does not watch itself.

**Notification infrastructure (7.4).** `services/notification_service.py` is the single writer to the `notifications` table; `create_notification` validates the type against a controlled vocabulary (`insurance_expiring`, `insurance_expired`, `post_deadline_non_responders`, `scheduler_alert`) and dedupes against existing unread rows for the same user, type, and reference. Four admin-authed endpoints back the UI: list (paginated), unread count, mark-one-read, and mark-all-read, with per-user isolation enforced by the Phase 1 RLS policies. The frontend adds a bell icon and badge to the header, a dropdown of recent unread plus some read for context, deep-link navigation that marks read in the same action, and a full `/notifications` page. The unread count refreshes on window focus and polls every 60 seconds (no Realtime).

**Insurance sync hardening (7.4.5).** `recompute_vendor_insurance_expiration` makes `vendors.insurance_expiration_date` a reliable mirror of the latest valid insurance certificate (the max expiration across valid certs, or null). It is called after insurance-certificate upload and delete, and now surfaces a 500 if the recompute fails rather than swallowing the error, so drift is visible. As elsewhere, there is no transaction around the certificate write and the recompute (a documented PostgREST limitation).

**Communication history (7.7).** The bid package email-log endpoint was broadened: because `email_log` has no `vendor_id` and vendor-facing emails are written under three reference types (`bid_invitations`, `bid_revision_requests`, `bid_submissions`), a complete history is assembled by walking the package to its invitations, deriving the related revision-request and submission ids, running one query per type, and merging in Python. A new vendor-level endpoint (`GET /vendors/{id}/email-log`) does the same across all of a vendor's invitations and feeds a new Communication tab on the vendor detail page, reusing the existing email-log table component. A known limitation: emails written under reference types outside those three (a future award or milestone email) will not appear until the filter is extended.

#### Differs from plan

- **Internal alerts are in-app notifications, not email.** The plan built Phase 7 around n8n email workflows and included PM/admin email digests (an escalation digest and an insurance digest). The build routes all staff alerts through the in-app notification subsystem and ships only the three vendor-facing bid-reminder templates; the two admin digest email templates were dropped as unnecessary. Vendors still receive email.
- **There is no assigned-PM concept.** The plan's language implies a project manager per project. Ownership is implicit via `created_by`, so "the PM" for an alert is `bid_packages.created_by`.
- **Self-check safety net leans on deferred infra.** The self-check covers stale individual jobs, but its fallback for the whole scheduler being down (Sentry plus ECS auto-restart) depends on production infrastructure that is deferred (register entries 6 and the 1.9 deferral). In the current dev environment, a total scheduler outage has no automated catch beyond the health endpoint.

#### Where to look

- Scheduler and jobs: `backend/app/jobs/` (`scheduler.py` with `@tracked_job` and `KNOWN_JOB_IDS`; one module per job); health at `GET /api/v1/admin/scheduler-health`.
- Notifications: backend `services/notification_service.py`, `routers/notifications.py`; frontend `features/notifications/` (bell, dropdown, `useUnreadCount`).
- Insurance sync: `backend/app/services/vendor_service.py` (`recompute_vendor_insurance_expiration`); badge endpoint `GET /vendors/insurance-expiring-count`.
- Communication history: `backend/app/services/invitation_tracking_service.py`; vendor tab via `useVendorEmailLog` on `VendorDetailPage`.

---

### Phase 8: Bid Comparison and Scoring

**Status: complete.**

Phase 8 turns submitted bids into a defensible award recommendation: a weighted score per bid, a side-by-side compare workspace, and a recommendation engine. The whole phase rests on one invariant, that every vendor in a package bid against the same frozen template structure, so the phase opens by hardening that invariant rather than by building the normalization engine the original plan called for.

#### As built

**Comparability hardening (8.1).** The plan scoped 8.1 as a bid normalization engine to reconcile mixed pricing formats. That engine was not built and is not needed: because the PM picks one template per package and the template fields are snapshotted into `bid_line_items` at submission time with `line_total` precomputed, the comparable numbers already sit in the rows. 8.1 was repurposed into the template freeze guards already described under Phase 3 (register entry 11): a non-cancelled package reference locks the template against edit and delete, with duplicate-template as the escape hatch. Blocking the edit also closes a subtler hole, that a mid-bid template edit could otherwise leak into an in-progress draft on its next auto-save.

**Timeline data (8.1.5).** Scoring's 15% timeline weight needed structured dates that the collection pipeline did not originally capture. Two nullable fields (`bid_packages.desired_start_date`, `bid_submissions.proposed_start_date`) were added, on a calendar-invite model: the vendor form pre-fills the proposed date with the package's desired date, leaving it means "I can hit your date," and a later date means "here is my earliest." On-time is derived (`proposed <= desired`), never stored. The proposed date is required on submit only when the package carries a desired date (the rule already noted in Phase 5).

**Scoring engine (8.2).** `services/bid_scoring_service.py` scores a competitive package's current cohort (non-superseded, non-draft, submitted, with a positive total) as a unit, since price is relative to the set. Five pure per-dimension functions feed an orchestrator (`score_bid_package`) that applies the fixed weights (price 0.50, compliance 0.05, performance 0.20, capacity 0.10, timeline 0.15), upserts one `bid_scores` row per submission, and snapshots the inputs and weights into `scoring_metadata`. It runs on demand (a PM triggers it at or after the deadline, since every new bid shifts every price score) and recompute overwrites system-generated rows. Price is lowest-over-this times 100 (lone bid scores 100); compliance blends onboarding status and insurance horizon; capacity is available over max (neutral 75 when max is unknown); timeline buckets days-late, or is a cohort-wide constant 100 when the package has no desired date (so it cancels out of ranking with no weight renormalization). Performance returns a constant 75 placeholder until milestone data exists in Phase 10 (the single touchpoint to change is documented in `DEFERRED.md`). The endpoint is `POST /bid-packages/{id}/scores` (404 unknown, 400 non-competitive, 422 no valid submissions).

**Compare workspace and recommendation (8.3, 8.4).** A read endpoint (`GET /bid-packages/{id}/scores`) returns the persisted scores joined to the live non-superseded cohort, so stale score rows for superseded submissions are simply not selected (no cleanup job needed); the payload is enriched with vendor company name and the task budget estimate so the recommendation layer needs no client-side joins, and an empty result returns 200 with an empty list rather than 404. `POST` remains the deliberate compute or recompute lever. The recommendation builder is a pure function over that cohort: it ranks by total weighted score (tie-break to lower price), generates a plain-language justification for the top pick, and derives four warning flags (over budget, late start, insurance window, onboarding incomplete). It is recommendation only and never auto-awards. The frontend is a dedicated compare route off the bid package detail page (a "Compare Bids" button in the header) showing the recommendation panel, a sortable color-coded comparison table with expandable line items, and the Recharts visualization; the "Submitted Bid Amounts" bar chart lives here (register entry 16). The compare entry appears for a competitive package with at least one valid submitted bid, regardless of status or deadline, with a non-blocking banner when the round is still open.

#### Differs from plan

- **No normalization engine.** The planned Task 8.1 normalization engine was unnecessary and not built; the single-template-per-package architecture makes bids structurally comparable, and 8.1 became the freeze guards instead (register entry 18, and the mechanism in entry 11).
- **Manual score adjustment not built.** The plan's "PM can manually adjust individual scores with justification" was not implemented. PM discretion lives at award time (Phase 9 override justification), and `bid_scores.scored_by` remains a dormant seam (register entry 19; see `DEFERRED.md`).
- **Export is browser print-to-PDF, not Excel.** The plan listed Excel and PDF export. The compare route ships a print-friendly stylesheet for browser print-to-PDF; there is no export library and no Excel output.
- **Performance scoring is a placeholder.** Every vendor scores a constant 75 on the 20% performance dimension until Phase 10 milestone data lands. This is the intended interim behavior (every vendor is unproven), documented in `DEFERRED.md`; the function signature and call site are final.

#### Where to look

- Freeze guards: `backend/app/routers/bid_templates.py` (see Phase 3 entry).
- Scoring engine: `backend/app/services/bid_scoring_service.py` (`score_bid_package`); endpoints on `routers/bid_packages.py` (`POST` and `GET .../scores`).
- Recommendation: the pure recommendation module under `backend/app/services/`; models under `backend/app/models/`.
- Compare UI: the compare route page under `frontend/src/features/bids/` (`BidPackageComparePage`), reusing `BidSubmissionDetailModal` and the Recharts components.

---

## E. Deviations register

Consolidated list of where the build diverged from the plan. This grows as later phases are documented; entries below cover Phase 1 and structural decisions visible so far.

| # | Plan said | As built | Why / notes |
| --- | --- | --- | --- |
| 1 | 28 tables | 29 tables | `bid_revision_requests` added for per-vendor revision feature. |
| 2 | `direct_assign` is a supported bid type | Dropped from product scope, but still selectable in the task form and accepted by the backend; downstream award flow never built | Only `internal` and `competitive` are real flows; awards are restricted to competitive. A live loose end to remove later, plus a dormant schema seam (`is_direct_assign`). |
| 3 | n8n for scheduling and outbound email orchestration | APScheduler in-process inside FastAPI; n8n removed entirely | Scheduled work is a handful of daily jobs, well within Python's reach; avoids running a second service. Surfaces fully in Phase 7. |
| 4 | Per-vendor bid revision was a post-MVP idea | Built and shipped | Full design in `docs/features/per-vendor-bid-revision.md`. Summarised when its phase is documented. |
| 5 | Onboarding status auto-synced from documents | Manual PM control; sync trigger disabled | PM may verify beyond document presence. Trigger preserved, commented out. |
| 6 | Separate dev/staging/prod and AWS infra in Phase 1 | Deferred | See `DEFERRED.md` (Tasks 1.8, 1.9). |
| 7 | Register and email-verification flows (Task 2.7) | No registration page; accounts are invite-only, provisioned outside the app | `signUp` service exists but is not surfaced in the UI. |
| 8 | JWT validation via PyJWT HS256 (Task 2.3) | Backend auto-detects and verifies ES256 (Supabase JWKS) or legacy HS256, audience `authenticated` | Broader than specified; accommodates Supabase's current signing keys. |
| 9 | Supabase Realtime subscriptions (Task 2.4) | Realtime infrastructure built but dormant; no feature subscribes | App uses React Query window-focus refetch and mutation invalidation instead. Left as a seam. |
| 10 | Vendor proximity via Google Distance Matrix (driving distance) | Bulk 75-mile filter uses straight-line haversine in Python; Google Routes API exists but only for on-demand single-pair distance | Radius is a repeated default value (three call sites), not one named constant. |
| 11 | Bid template guarded on delete only | Also frozen on edit once a live (non-cancelled) package references it; duplicate-template is the escape hatch | Keeps already-issued bids comparable. |
| 12 | Bid package creation atomic, all-or-nothing (Task 4.4) | Sequence of independent writes, accepted partial success, no rollback or cleanup | Supabase REST client has no transaction. A `sent` invitation does not guarantee the email was delivered. |
| 13 | SNS bounce/delivery webhook updates `email_log` (Task 4.3) | Webhook matches rows by SES message id, but the email service never stores that id on the row; updates likely match nothing | Known issue. Bounce tracking effectively inert until fixed. |
| 14 | Vendor submission PDF receipt (Phase 5 plan and acceptance) | No PDF generated; confirmation email plus on-screen summary is the receipt | No PDF library in use. No separate confirmation number; submission id is the reference. |
| 15 | Per-step client validation via React Hook Form (Task 5.4) | Vendor form uses a `useReducer` store, no RHF/Zod; validation is server-driven with field errors mapped back to steps | Server-side submit validation is the authority. |
| 16 | Bid amount bar chart on the detail page with a budget reference line (Task 6.4) | Detail page has the pie only; the comparison bar chart lives on the Phase 8 compare page and draws no budget line | `tasks.budget_estimate` is not read by the chart. |
| 17 | Staff alerts via n8n email workflows and PM/admin email digests (Phase 7) | Staff alerts are in-app notifications via the `notifications` table; only the three vendor bid-reminder email templates ship; the two admin digest templates were dropped | Vendors still receive email; internal users use the bell/notification UI. Channel split by recipient type. |
| 18 | Bid normalization engine (Task 8.1) | Not built; unnecessary because one template per package makes bids structurally comparable. 8.1 became template freeze guards | Comparable numbers are already snapshotted into `bid_line_items` at submission. See entry 11 for the freeze mechanism. |
| 19 | PM can manually adjust individual scores (Task 8.4) | Not built; `bid_scores.scored_by` stays a dormant seam | PM discretion is exercised at award time via override justification (Phase 9). See `DEFERRED.md`. |
