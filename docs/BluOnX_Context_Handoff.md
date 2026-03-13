# BluOnX Development Operations Platform -- Project Context Handoff
**Date:** March 6, 2026
**Version:** 3.1
**Purpose:** Complete project context for continuing development across conversation threads.

---

## 1. System Overview

Building a **Bid Management & Vendor Coordination System** for **BluOnX Development** (land/horizontal) and **Capstone LLC** (vertical construction). The system manages the complete vendor lifecycle: bid invitation, bid collection, comparison/scoring, contract award, and milestone tracking.

**Tech Stack:** React 18 + Vite + TypeScript + TailwindCSS v4 (frontend), FastAPI (backend), PostgreSQL via Supabase (database), Supabase Storage (files), Supabase Auth (email/password only, no OAuth).

**Email & Automation Stack:** AWS SES (transactional email), AWS SNS (bounce/delivery notifications), n8n Pro (workflow scheduling and orchestration).

**Full 12-phase project plan (~707 hours, 11 weeks) is attached to the Claude project as PROJECT_PLAN_v2.1.md.**


## 2. Core Business Rules

### 2.1 Foundational Principle
**One Task = One Trade = One Award = One Contract.** Each task belongs to exactly one trade/scope. Vendor filtering, bid comparison, award, contract, and milestones all operate at the task level.

**Multi-trade scenarios:** PM creates separate tasks per trade (e.g., "Erosion Control - Wood Chips" under Mass Grading, "Erosion Control - Maintenance" under Erosion Control). Each goes through its own independent lifecycle.

### 2.2 Three Task Bid Types
- **competitive** -- full pipeline: auto-filter vendors, invitations, collection, comparison, award
- **direct_assign** -- PM picks a vendor directly. Backend creates a synthetic bid_submission (with `is_direct_assign = TRUE`) so the full downstream chain (award, contract, milestones) works identically. No schema exceptions.
- **internal** -- budget line item only, no vendor involvement. Cannot have bid_packages, awards, contracts, or milestones (enforced at application layer, documented in schema comments).

### 2.3 Project Phases
- **Due Diligence** -- investigation tasks (geotech, surveys, environmental). Bid out first.
- **Development** -- construction tasks (grading, utilities, paving). Proceeds only if DD passes.

Both phases use the same bid workflow and unified vendor pool. Phase is for **task grouping/display only**, not workflow enforcement. The `trades` table has a `phase` field (`due_diligence`, `development`, `both`) that controls which trades appear in the dropdown based on the task's phase.

### 2.4 Re-Award / Re-Bid Scenarios
- **Rebidding:** `bid_packages` has a `round_number` (auto-incremented by trigger). New round = new bid_package for the same task. Full history preserved.
- **Re-award:** Partial unique indexes on `awards` and `contracts` tables allow one active record per task while preserving declined/cancelled history. A vendor can decline, the old award moves to `declined_by_vendor`, and a new award is created.

### 2.5 Bid Templates
Steve confirmed some trades use lump sum and others need structured line-item templates. `bid_templates` + `bid_template_items` tables define per-trade bid formats. When a vendor opens the bid form, the system checks if the task's trade has a template. If yes, it pre-populates line items. If no, it shows a simple lump sum field.

A **bid template management UI** is scoped as Task 3.6. Admin can create/edit templates per trade, manage line items, and preview the template structure.

### 2.6 Document Sharing with Bid Invitations
Documents are uploaded at **project level** (`project_documents`). When setting up a bid package, the PM selects which project documents to include via `bid_package_documents` junction table. Actual files stay in Supabase Storage, no duplication.

### 2.7 Vendor Onboarding Status
Managed **manually by PM**, not auto-synced from documents. The PM may need to verify details beyond document presence (confirm insurance with carrier, review W-9 for corrections). The auto-sync trigger exists in the schema but is intentionally disabled (commented out with rationale).

### 2.8 Document Expiration Monitoring
Vendor documents with expiration dates (primarily insurance certificates) are monitored by an n8n daily workflow. The system sends automated reminder emails at T-30 days and T-7 days before expiration. The vendor filtering algorithm blocks vendors with expired insurance from being invited to bid or awarded a contract. Expiration dates are entered by admin when uploading documents. All reminder emails are logged in `email_log`.

---

## 3. Key Schema Design Decisions

> **Note:** Full schema details are in the attached SQL files. This section covers the *reasoning* behind non-obvious decisions.

### 3.1 Denormalized Fields with Consistency Triggers
Several tables have denormalized FKs for query performance (avoiding expensive JOINs on high-traffic queries). Each is enforced by a BEFORE INSERT/UPDATE trigger:

| Table | Denormalized Field | Validated Against |
|-------|-------------------|-------------------|
| `bid_submissions` | `vendor_id` | `bid_invitations.vendor_id` |
| `awards` | `vendor_id` | `bid_submissions.vendor_id` |
| `awards` | `task_id` | Chain: submission, invitation, package, task |
| `contracts` | `vendor_id`, `task_id` | `awards.vendor_id`, `awards.task_id` |
| `milestones` | `task_id` | `contracts.task_id` |

### 3.2 Cascade Strategy
- **RESTRICT** (39 FKs) -- audit-safe, prevents accidental data loss on core entities
- **CASCADE** (8 FKs) -- only on tightly-coupled children (line items, attachments, template items, magic link tokens, junction tables, notifications)
- **SET NULL** (5 FKs) -- on optional/advisory references (scored_by, resolved_by, milestone_id on flags, email_log_id on alerts)

### 3.3 Soft Deletes
`deleted_at` TIMESTAMPTZ on: `users`, `vendors`, `projects`, `tasks`. Core entities are never hard-deleted. RLS policies filter out soft-deleted records automatically.

### 3.4 Status Fields as CHECK Constraints
All status fields use CHECK constraints (not PostgreSQL enums). Easier to extend without ALTER TYPE migrations.

### 3.5 Vendor Capacity Management
Two triggers maintain `vendors.current_active_jobs`:
- Award accepted: +1. Award revoked after acceptance: -1 (with double-decrement prevention checking if contract already handled it)
- Contract completed/terminated: -1

### 3.6 RLS Architecture
- **Authenticated users (admin/PM):** RLS policies govern all reads via Supabase client
- **All writes:** Go through FastAPI using `service_role` key (bypasses RLS). FastAPI is the primary gatekeeper.
- **n8n automation writes:** n8n uses Supabase nodes with service_role credentials for direct DB access (milestone token storage, email_log inserts). This is a deliberate exception to the "all writes through FastAPI" rule. n8n is a trusted server-side system, and its writes are limited to simple inserts into `milestone_alerts` and `email_log`.
- **Vendors:** Never access Supabase directly. FastAPI mediates all access using `service_role`.
- **Anonymous:** Zero access (revoked on all 28 tables + private schema)
- **Admin-only at DB level:** `users` (write), `trades` (write), `magic_link_tokens` (read)
- **User-scoped:** `notifications` (users see only their own)
- Helper functions (`private.is_active_user()`, `private.is_admin()`) use SECURITY DEFINER in a `private` schema not exposed via PostgREST

### 3.7 Storage Architecture
Three private buckets with "coat check" pattern (metadata in DB, files in storage):

| Bucket | Path Pattern | DB Table |
|--------|-------------|----------|
| `vendor-documents` | `{vendor_id}/{document_type}/{filename}` | `vendor_documents` |
| `project-documents` | `{project_id}/{filename}` | `project_documents` |
| `bid-attachments` | `{bid_submission_id}/{filename}` | `bid_attachments` |

---

## 4. Vendor Information

### 4.1 Structure
- A **vendor is a company**, not an individual
- Multiple contacts per vendor (confirmed: Kolb Grading has two)
- Bid invitations target contacts, not the company directly
- Lat/long stored on vendors and projects for Google Maps distance filtering (geocoded on create/update via backend)

### 4.2 Required Onboarding Documents (uploaded by admin)
1. W-9
2. Insurance Certificate (has expiration date, monitored by automated reminders)
3. Executed Master Trade Agreement

### 4.3 Data Still Missing from Client
Phone numbers, addresses, insurance details per vendor, W-9 status. The ScopeContracter spreadsheet provides ~25+ vendors with company name, contact, and email organized by scope.

---

## 5. Trade/Scope Categories (~27 from client spreadsheet)

**Due Diligence:** Engineering, Phase 1/Phase 2, Title, Traffic Study, Ecological Study, Geo Tech, Legal, Manual Entry (Self Perform)

**Development:** Engineering, Mass Grading, Underground Utilities, Electric Conduit/Crossings, Paving, Blasting, Demo, Erosion Control, Retaining Walls, Site Final Grading, Common Ground Electric, Common Ground Flatwork, Common Ground Amenities, Street Signs, Landscaping, Irrigation, Fencing, Sod, Monuments, Foundations and Aeration, Mailboxes, Manual Entry

**Notes:** Engineering and Manual Entry appear in both phases (`phase = 'both'`). "Common Ground Amenities" can include 40+ sub-tasks. PM creates only what is needed per project as freeform tasks.

---

## 6. Users, Auth & Roles

- **Authentication:** Supabase Auth, email/password only. No OAuth/Google Sign-In for MVP.
- **Auth to Profile:** Trigger on `auth.users` INSERT auto-creates `public.users` row with matching UUID. Signup passes `full_name` and `role` via `raw_user_meta_data`; trigger reads them with fallbacks (email prefix for name, `project_manager` for role).
- **Frontend auth framework (Task 1.7):** Supabase client singleton, AuthContext/Provider (session + profile state), auth service layer (signUp, signIn, signOut, resetPassword, getAccessToken), ProtectedRoute shell. Session persists in localStorage under `bluonx-auth` key. Auto token refresh handled by Supabase client.
- **Key auth lesson:** `onAuthStateChange` callback must be synchronous (fire-and-forget pattern); async/await blocks Supabase's internal event listener. `fetchProfile` needs timeout protection (AbortController) to prevent indefinite hangs.
- **Roles:** `admin` (full access, manages vendors/trades/users) and `project_manager` (manages projects, tasks, bid process, awards).
- All projects visible to all users for MVP (no project-level access restriction).
- No executive approval workflow for MVP.
- **Remaining auth work:** Login/signup UI pages (Task 2.7), dashboard layout with user menu (Task 2.8), FastAPI JWT validation middleware (Task 2.3).

---

## 7. Bid Process Details

### 7.1 Bid Format
Hybrid: lump sum for simple scopes, structured line items for complex trades. Both supported in same submission via `bid_line_items` table (supports `lump_sum` and `unit_price` item types simultaneously).

### 7.2 Scoring Weights (Client-Confirmed, Fixed for MVP)
- 50% Price (inverse curve, lowest price scores highest)
- 5% Compliance (insurance validity, required documents, onboarding status)
- 20% Past Performance (milestone on-time completion rate + vendor flag history; new vendors get neutral/baseline score)
- 10% Capacity (available jobs vs maximum)
- 15% Timeline Alignment (can start on required date, schedule fit)

`bid_scores.scored_by` is nullable: NULL = system-generated score, non-NULL = manually adjusted by a user.

### 7.3 Bid Deadline
Same deadline for all vendors on a given task. Stored on `bid_packages.deadline`.

### 7.4 Vendor Filtering
Auto-filters vendors from the system database (not external search) by: trade match, geographic distance within 75 miles (Google Maps Distance Matrix API), valid insurance (blocks expired), bonding capacity, current capacity (active jobs vs max), and vendor flag warnings. PM reviews the filtered list, can manually add/remove vendors, then confirms before invitations go out.

### 7.5 Award Process
100% manual. The system scores, ranks, and recommends, but never auto-awards. The PM always reviews the comparison, makes the final call, and clicks "Award Contract." Pre-award validation checks run automatically (start date feasibility, insurance validity, bonding, capacity, budget variance). PM can override warnings with documented justification (stored in awards.has_override and awards.override_justification).

---

## 8. Email Architecture

### 8.1 Service Stack
- **AWS SES:** Transactional email sending for all system emails (bid invitations, reminders, milestone check-ins, award/decline letters, document expiration alerts)
- **AWS SNS:** Receives bounce and delivery notifications from SES, pushes to webhook endpoint for email_log updates
- **n8n Pro:** Orchestrates all time-triggered outbound workflows (bid reminders, milestone check-in scheduling, document expiration monitoring, escalation alerts)

### 8.2 Email Tracking Scope (MVP)
The `email_log` table tracks: `sent_at` (recorded on successful SES send), `status` (queued/sent/delivered/bounced/failed), and `error_message` (on failure). Bounce notifications arrive via SNS webhook and update status to `bounced`.

**Deferred to post-MVP:** `opened_at` and `clicked_at` columns exist in the schema but will not be populated. Open tracking (tracking pixel) and click tracking (link wrapping) require significant custom infrastructure. Action tracking via dedicated tables (`bid_submissions`, `milestone_responses`) is sufficient. If the vendor submitted a bid or clicked a milestone response, the system knows without needing email-level tracking.

---

## 9. Contracts & Milestones

### 9.1 Contracts
One per accepted award. DocuSign integration for e-signatures. Partial unique index allows re-contracting if previous contract terminated. Direct assign flow creates a synthetic bid_submission (is_direct_assign = TRUE) so the downstream chain (award, contract, milestones) works identically to competitive bids.

### 9.2 Milestone Tracking Architecture

**Overview:** Simple email-driven milestone tracking. No vendor portal. Automated check-ins via styled HTML emails with Yes/No button links. PM alerted only when intervention is needed.

**Milestones are optional and PM-controlled.** Short-duration tasks (quick surveys, legal reviews) can skip milestones entirely or use a single completion milestone. Typically 2-5 milestones per awarded task. Statuses: scheduled, started, on_track, delayed, completed.

**Responsibility Split:**

| Side | Owner | What it does |
|------|-------|-------------|
| Outbound (scheduling, tokens, emails) | n8n (fully) | Reads milestones from Supabase, generates tokens, stores hashes directly in Supabase via Supabase nodes, sends HTML emails through AWS SES |
| Inbound (vendor click responses) | FastAPI (fully) | Validates tokens, records responses in milestone_responses, updates milestone status, returns styled HTML confirmation pages, fires async webhook to n8n for follow-up |
| Follow-up (PM alerts, notifications) | n8n (triggered by FastAPI webhook) | Sends PM alert emails on delay, completion notifications, escalation alerts |
| PM actions (date updates, overrides) | React dashboard via FastAPI | Deep links from PM alert emails into the dashboard milestone detail view |

**Check-in Schedule (per milestone):**
- T-5 before start (only if milestone duration > 7 days): informational reminder to vendor + PM
- Start date: "Did you start?" with Yes/No buttons to vendor
- T-5 before end (only if milestone duration > 7 days): "Will you finish on time?" with Yes/No buttons to vendor
- End date: "Did you complete?" with Yes/No buttons to vendor
- No response for 2 days: escalation alert to PM (once per check-in, not repeated)

**Token Design:**
- n8n generates a random token per email, hashes it with SHA-256, stores the hash in `milestone_alerts.response_token_hash` via Supabase node
- Raw token embedded in email button links pointing to FastAPI: `https://api.bluonx.com/v1/milestones/respond/{token}?response=yes|no`
- Tokens are time-limited (7 days) with **first-response-wins** logic. First click records the official response. Subsequent clicks (including email scanner pre-fetches or accidental double-clicks) show a friendly page: "You already responded [Yes] on [date]"

**Delay Handling:**
- Vendor clicks "No" on any check: milestone status set to `delayed`, PM gets immediate alert email with vendor contact info and deep link to dashboard
- Automated check cycle **pauses** after a "No" response. PM must either update the end date (resets status to on_track, restarts the cycle with new dates) or manually mark the milestone as complete from the dashboard
- PM can also manually "Mark as started" or "Mark as completed" with manual date entry for cases where vendors respond outside of the email flow

**PM Date-Update Flow:**
PM alert emails contain a deep link to the dashboard milestone detail view (e.g., `https://app.bluonx.com/projects/{id}/tasks/{id}/milestones/{id}`). PM is already authenticated via session. Date fields are editable. After update, status resets and n8n's next daily run picks up the new dates.

**Milestone alerts** reference `email_log` for delivery details, no data duplication. Milestone-specific context (alert_type, response_token_hash) lives on `milestone_alerts`; delivery tracking lives on `email_log`.

---

## 10. Out of MVP Scope

- Mobile native apps (iOS/Android)
- Advanced analytics and reporting dashboards
- Automated payment processing and invoicing
- Contingency budget tracking with variance workflow (Steve requested; Fatima flagged out of scope)
- Multi-user granular permissions
- Change order management
- SMS notifications via Twilio
- Photo uploads for milestone completion
- Complex vendor portal for milestone tracking (keeping it email-based)
- Google Sign-In / OAuth authentication
- Vendor self-service onboarding portal
- Email open tracking and click tracking (email_log.opened_at and clicked_at deferred; action tracking via dedicated tables is sufficient)
- Budget forecasting and variance analysis
- Weather delay tracking
- Equipment scheduling and management