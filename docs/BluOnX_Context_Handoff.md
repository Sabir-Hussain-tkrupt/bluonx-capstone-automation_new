# BluOnX Development Operations Platform — Project Context Handoff

| Item | Detail |
|------|--------|
| **System** | Bid Management & Vendor Coordination System (MVP) |
| **Prepared for** | BluOnX Development (land / horizontal) and Capstone LLC (vertical construction) |
| **Document owner** | Awais Anwer (Tkrupt) |
| **Version** | 4.0 — Final MVP Handoff |
| **Date** | October 8, 2026 |
| **Supersedes** | Version 3.1 (March 6, 2026) |
| **Status** | All 12 planned phases delivered; post-plan client enhancements included |
| **Companion documents** | `docs/BluOnX_Technical_Overview.md` (engineering and production operations), `docs/DEPLOYMENT_CHECKLIST.md` (go-live runbook), `database/bluonx_schema_documentation.md` (table-level schema reference), `docs/features/per-vendor-bid-revision.md` (revision feature specification), `docs/ses-sns-event-tracking.md` (email delivery tracking), `docs/adr/0001-scheduler-single-instance.md` (scheduler architecture decision) |

---

## 0. About This Document

### 0.1 Purpose

This document is the single source of project context for the BluOnX Bid Management & Vendor Coordination System. It explains **what the system is, the business rules it enforces, why the key design decisions were made, what was delivered in each of the twelve planned phases, and what was added at the client's request after the original project plan was approved.**

Version 3.1 of this document was written mid-build (March 2026) as a working context file. Version 4.0 completes it as the final handoff record: the original sections have been retained and brought in line with the system as it was actually built, and new sections cover the remaining phases, the post-plan enhancements, the deviations from the plan, and the open items that remain before full production use.

### 0.2 Intended Readers

| Reader | What they should take from this document |
|--------|------------------------------------------|
| Client stakeholders and project sponsors | What was delivered, how it maps to the approved plan, and what remains open |
| Project managers and administrators | The business rules the system enforces and why it behaves the way it does |
| Incoming engineers and maintainers | The design reasoning behind the data model and workflows (with the technical detail in the companion Technical Overview) |
| Future scoping and Phase 2 planning | The out-of-scope list, deferred items, and dormant extension points left in the schema |

### 0.3 How to Read It

- **Sections 1 through 9** describe the system and its rules. Where the build changed an earlier assumption, the section has been updated to describe the system as built.
- **Section 10** is the phase-by-phase completion record against the original 12-phase project plan.
- **Section 11** documents the features added beyond the original plan at the client's request, led by the **Task Template Library and Add Default Tasks** capability.
- **Section 12** is the consolidated register of deviations from the plan, with the reason for each.
- **Sections 13 and 14** summarise environments, deployment, and the open items that must be closed before or shortly after go-live.
- **Appendix A** lists the full standard task template library (58 activity-coded tasks).

---

## 1. System Overview

### 1.1 What the System Does

The platform is a **Bid Management & Vendor Coordination System** for **BluOnX Development** (land / horizontal development) and **Capstone LLC** (vertical construction). It manages the complete vendor lifecycle for every unit of work on a project:

1. **Project and task set-up** — projects with budgets, locations and documents; tasks organised by phase and trade, either created individually or seeded from the standard Task Template Library.
2. **Bid invitation** — automatic filtering of qualified vendors, a configurable bid package (deadline, desired start date, bid template, scope of work, documents), and personalised invitation emails carrying secure magic links.
3. **Bid collection** — a dedicated, account-free vendor portal where vendors build, save and submit structured bids.
4. **Tracking and reminders** — live invitation status, automated reminders at T-7, T-3 and T-0, and post-deadline escalation.
5. **Comparison and scoring** — side-by-side comparison, a five-dimension weighted score, and a plain-language recommendation.
6. **Award and contract** — pre-award validation, PM override with recorded justification, a generated contract PDF, two-party DocuSign signature, and automatic decline letters to unsuccessful vendors.
7. **Milestone tracking** — email-driven vendor check-ins, automatic escalation of delays and silence, and a PM activity timeline.
8. **Close-out** — contract completion and a PM performance rating that feeds future bid scoring.

### 1.2 Technology Stack (As Built)

| Layer | Technology |
|-------|-----------|
| Frontend (staff dashboard and vendor portal) | React 19, Vite 7, TypeScript 5.9, TailwindCSS v4 (CSS-first configuration), React Router 7, TanStack React Query 5, React Hook Form with Zod, Recharts, dnd-kit (drag-and-drop ordering), PapaParse (CSV import) |
| Backend API | FastAPI on Python 3.11, Uvicorn, Pydantic v2, pydantic-settings |
| Database | PostgreSQL hosted on Supabase (Row Level Security, triggers, stored procedures, views) |
| File storage | Supabase Storage — three private buckets |
| Staff authentication | Supabase Auth, email and password, invite-only account provisioning |
| Vendor authentication | Account-free magic links plus short-lived, purpose-scoped vendor JWTs |
| Transactional email | AWS SES, with delivery, bounce and complaint events returned through AWS SNS |
| Scheduling and automation | APScheduler running in-process inside the FastAPI application (replaced n8n — see Section 12) |
| E-signature | DocuSign eSignature REST API (JWT Grant / impersonation) with DocuSign Connect status webhooks |
| Contract documents | Server-generated PDF (ReportLab) with a swappable terms template |
| Location services | Google Maps Platform — Geocoding (server side), Places autocomplete and Maps JavaScript (browser), Routes (on-demand distance) |
| Backend hosting | AWS ECS Fargate behind an Application Load Balancer, container images in Amazon ECR |
| Frontend hosting | AWS Amplify, connected to the GitHub repository |
| Testing | pytest (backend, ~170 test modules), Vitest with React Testing Library (frontend, ~100 test files) |
| Version control | Git and GitHub (`main` and `dev` branches) |

> The original plan specified Vercel Pro for frontend hosting, n8n Pro for automation, and Google Sign-In. As built, the frontend is hosted on AWS Amplify, automation runs inside the backend on APScheduler, and authentication is email and password only. These and all other plan changes are recorded in Section 12.

### 1.3 Delivery Summary

| Phase | Module | Planned hours | Status |
|-------|--------|---------------|--------|
| 1 | Foundation & Database | 60 | Delivered |
| 2 | Frontend, Backend API & Authentication | 100 | Delivered |
| 3 | Core Entity Management | 60 | Delivered, extended with the Task Template Library |
| 4 | Bid Invitation System | 50 | Delivered |
| 5 | Bid Collection — Vendor Portal | 60 | Delivered |
| 6 | Real-Time Dashboard & Response Tracking | 60 | Delivered (refresh-on-focus model in place of WebSockets) |
| 7 | Automated Reminder System | 40 | Delivered (APScheduler in place of n8n) |
| 8 | Bid Comparison & Scoring | 40 | Delivered |
| 9 | Award Decision & Contract Generation | 40 | Delivered |
| 10 | Vendor Commitment & Milestone Tracking | 50 | Delivered |
| 11 | Testing & Quality Assurance | 80 | Delivered (automated unit and integration suites; UAT with client) |
| 12 | Deployment & Training | 60 | Delivered to AWS development environment; production cut-over checklist in Section 14 |
| — | Post-plan client enhancements | — | Delivered (Section 11) |

### 1.4 Repository

Private monorepo `bluonx-capstone-automation`:

| Folder | Contents |
|--------|----------|
| `backend/` | FastAPI application — routers, services, models, core infrastructure, scheduled jobs, email and contract templates, tests, Dockerfile |
| `frontend/` | React application — staff dashboard and vendor portal, feature modules, UI component library, tests |
| `database/` | Complete schema SQL, RLS policies, storage policies, schema documentation, development seed data |
| `docs/` | This handoff, the Technical Overview, deployment checklist, feature specifications, architecture decision records |

---

## 2. Core Business Rules

### 2.1 Foundational Principle

**One Task = One Trade = One Award = One Contract.** Each task belongs to exactly one trade/scope. Vendor filtering, bid comparison, award, contract, and milestones all operate at the task level.

**Multi-trade scenarios:** the PM creates separate tasks per trade (for example "Erosion Control — Wood Chips" under Mass Grading and "Erosion Control — Maintenance" under Erosion Control). Each goes through its own independent lifecycle.

**Task names are unique within a project.** An exact duplicate name in the same project is rejected; a soft-deleted task's name becomes reusable.

### 2.2 Task Bid Types

The schema supports three bid types. Two are active in the product:

- **competitive** — the full pipeline: automatic vendor filtering, invitations, bid collection, comparison and scoring, award, contract, milestones.
- **internal** — a budget line item only, with no vendor involvement. Internal tasks cannot have bid packages, awards, contracts, or milestones. Used for land, closing costs, interest, fees, taxes, permits, contingency and similar soft costs.
- **direct_assign** — *dormant.* Originally designed as "PM picks a vendor directly" using a synthetic bid submission. During the build the client confirmed that all vendor work would go through the competitive path, so the direct-assignment award pipeline was not built. The value remains in the database constraint (and the `is_direct_assign` column remains on bid submissions) so that it can be revived later without a migration, but the API rejects it on task create and update, and every bid-pipeline entry point accepts only `competitive` tasks.

**Bid type is locked once a task leaves draft.** After bidding starts, changing a task between competitive and internal is rejected.

### 2.3 Project Phases

- **Due Diligence** — investigation tasks (title, legal, engineering, geotechnical, environmental). Bid out first.
- **Development** — construction tasks (grading, utilities, paving, landscaping, amenities). Proceeds only if due diligence passes.

Both phases use the same bid workflow and unified vendor pool. Phase is for **task grouping and display**, not workflow enforcement. The `trades` table carries a `phase` value (`due_diligence`, `development`, or `both`) that controls which trades appear in the task form for the selected phase; the same rule is re-enforced by the API.

### 2.4 Task Lifecycle

Tasks move through a controlled status sequence. Illegal jumps are rejected by the API.

| From | Allowed next status |
|------|---------------------|
| draft | bidding, cancelled |
| bidding | evaluating, cancelled |
| evaluating | awarded, cancelled |
| awarded | in_progress, cancelled |
| in_progress | completed, cancelled |
| completed | (terminal) |
| cancelled | draft (re-open) |

Creating the first bid package moves a draft task to bidding automatically; cancelling the last live bid round returns it to draft; creating an award moves it to awarded.

**Deletion is a soft delete and is blocked while work is live.** A task with an active bid package, award, or contract cannot be deleted — the PM cancels it instead so its history is preserved. Projects follow the same principle: a project with tasks in bidding, evaluating, awarded, or in-progress status cannot be deleted, but it can be **archived**. An archived project is read-only (no task changes) until it is unarchived.

### 2.5 Re-Award / Re-Bid Scenarios

- **Rebidding:** `bid_packages` has a `round_number` (auto-incremented by trigger). A new round is a new bid package for the same task. Full history is preserved.
- **Re-award:** partial unique indexes on `awards` and `contracts` allow exactly one active record per task while preserving declined and terminated history. If a vendor declines the DocuSign envelope, the award moves to `declined_by_vendor`, the contract to `terminated`, and the PM can award the next vendor.
- **Per-vendor revision:** a PM can ask one vendor to revise their bid without re-bidding the whole package (see Section 2.11).

### 2.6 Bid Templates (Template Library Model)

Templates define how vendors submit pricing — a lump-sum total versus a structured line-item breakdown. The `bid_templates` table stores a library of reusable templates. Each template is **optionally affiliated with a trade** through a nullable `trade_id`:

- **Trade-affiliated** templates appear as suggestions when the PM bids on tasks of that trade.
- **General-purpose** templates (no trade) are available for any task.

**Template selection happens at bid package creation**, not at task creation. `bid_packages.bid_template_id` records which template the PM chose for that bidding round; no template means "lump sum only." All vendors in a bid package use the same template, which is what makes their submissions directly comparable in the scoring engine.

**PM-driven flow (no auto-selection):**
1. The system lists templates matching the task's trade plus general-purpose templates.
2. If matches are found, the PM picks one or chooses lump sum only.
3. If none match, the PM is informed and can browse all templates or proceed with lump sum.
4. The selection is stored on the bid package.

**Downstream impact:** when a vendor opens the bid form, the template's items pre-populate it. Vendor responses are captured in `bid_line_items`, which snapshot the template's description, item type and unit of measure at submission time, so a later template edit can never rewrite a submitted bid.

**Template protection (as built):**
- A template referenced by any bid package **cannot be deleted**.
- A template referenced by a live (non-cancelled) bid package **cannot be edited**, so already-issued bids stay comparable.
- **Duplicate Template** is the deliberate escape hatch: the PM copies the template and edits the copy.

The **Bid Template management UI** (Task 3.6) lets PMs and admins create, edit, duplicate and delete templates, optionally associate them with a trade, manage line items (description, item type, unit of measure, sort order), and see a live preview rendered exactly as the vendor will see it.

**Design rationale:** client spreadsheet data showed templates do not map cleanly one-to-one to trades — some are trade-level, some task-specific, some cross-trade. Decoupling templates from a strict trade requirement, while keeping optional affiliation, gives flexibility without losing organisational convenience.

### 2.7 Document Sharing with Bid Invitations

Documents are uploaded at **project level** (`project_documents`). When setting up a bid package, the PM selects which project documents to include through the `bid_package_documents` junction table. Files stay in Supabase Storage — nothing is duplicated.

**Scope of Work (added during build):** every bid package requires a **Scope of Work document**, uploaded during package creation. It is stored as a project document of kind `scope_of_work` (kept out of the general reference pool) and linked to the package. Vendors must type their company name to **attest** that they reviewed the scope of work before they can submit; the attestation name and a server timestamp are stored on the submission and are carried onto the contract as the "Date of signed scope of work."

### 2.8 Vendor Onboarding Status

Managed **manually by the PM or admin**, not auto-synced from documents. The PM may need to verify details beyond document presence (confirm insurance with the carrier, review the W-9 for corrections). The auto-sync trigger exists in the schema but is intentionally disabled, with the rationale recorded in the schema.

### 2.9 Document Expiration Monitoring

Vendor documents with expiration dates (primarily insurance certificates) are monitored by a **daily scheduled job inside the backend**. As built:

- `vendors.insurance_expiration_date` is kept as an exact mirror of the latest valid insurance certificate, recomputed whenever a certificate is uploaded or deleted.
- Administrators receive **in-app notifications** at exactly T-30 and T-7 days before expiry, and daily once a certificate has expired until an admin acknowledges it by marking the certificate expired.
- The vendor filter disqualifies vendors with expired or missing insurance from new invitations; pre-award validation **blocks** an award to a vendor whose insurance has expired and **warns** when it will lapse before the project's estimated end date.
- The sidebar shows a badge with the count of vendors whose insurance is expiring.

### 2.10 Task Template Library and Default Tasks (Client Enhancement)

At the client's request, the system includes a **Task Template Library**: a standard set of **58 activity-coded task templates** that reflects BluOnX's cost-activity chart (activity codes B0010 through B0760). Each template defines the task name, activity code, phase, trade and bid type, so a PM no longer has to key in the same standard tasks for every new project.

- **14 Due Diligence templates** (B0010–B0150): land, closing costs, capitalised interest, financing fees, real estate taxes, legal, engineering and surveying, zoning, three geotechnical activities, and three environmental activities.
- **44 Development templates** (B0200–B0760): demolition, clearing and grading, rock work, erosion control, sanitary and storm sewers, water main, electric and street lights, utilities, paving and streets, sidewalks, signage, sod and landscaping, irrigation, monuments, lakes and fountains, amenities, retaining walls, fencing, permits and fees, contingency, developer fee, escrow release, HOA overages, and post-construction clean-up.
- **Bid type is pre-assigned:** 43 templates are `competitive` (vendor-bid trade packages and professional services) and 15 are `internal` (land, fees, taxes, interest, permits, contingency, escrow and similar budget lines).

**How PMs use it:** on a project's task list, the **Add Default Tasks** button (next to **+ Add Task**) applies the whole library to the project in one action. Each template becomes a draft task named "*Activity Code* – *Activity Name*" (for example "B0220 – Mass Grading"), placed after any existing tasks in activity-code order, with the description, phase, trade and bid type already filled in. A confirmation message reports how many tasks were added and how many were skipped.

**Rules that keep it safe:**
- **Safe to click more than once.** A template whose task name already exists in the project is skipped, so repeating the action only fills gaps and never creates duplicates.
- **Trade matching is by name** against the active trades in the system, with an alias for the two spellings of the geotechnical trade ("Geotechnical Engineering" and "Geo Tech"). The trades the library expects must exist and be active (see Section 5).
- **Archived projects** cannot receive default tasks until they are unarchived.
- **Budgets are left blank** — the PM enters budget estimates per project.

**Editing:** every task created from a template is an ordinary task. The PM can rename it, change its description, phase, trade, bid type or budget, reorder it by drag-and-drop, delete tasks the project does not need, and add custom tasks alongside them through **+ Add Task**. Changes to a project's tasks never alter the library itself. The library's standard content (which activities, and their default phase, trade and bid type) is maintained centrally by the engineering team so every project starts from the same company standard; the procedure for changing it is described in the Technical Overview. The full library is listed in Appendix A.

### 2.11 Per-Vendor Bid Revision (Client Enhancement)

After a round closes, the PM can ask **one vendor** to revise their bid without disturbing the rest of the package:

- The PM writes a personalised note and sets a per-vendor revision deadline (which may extend past the original package deadline).
- The vendor receives a magic-link email and can **submit a revised bid** (pre-filled from their original, which they edit) or **decline** with an optional reason.
- The revised bid becomes the current submission; the original is preserved as immutable, superseded history. The PM sees a "Revised" badge with an inline version history and price delta.
- Limits: at most **2 revision requests per vendor per package**, only **one pending** at a time, and **blocked once an award exists**.
- Unanswered requests **expire automatically** at the deadline (hourly scheduled job) and their links are revoked.
- Other vendors are never notified.

The complete specification is in `docs/features/per-vendor-bid-revision.md`.

### 2.12 Working-Day Calendar (Client Enhancement)

Vendor responsiveness is measured in **working days**. The system skips weekends and an **organisation-wide holiday calendar** maintained by administrators under Settings → Calendar.

- US federal holidays (observed dates, no state subdivision — Missouri state closures are not observed by a private construction firm) are seeded automatically and topped up every January 2 so the calendar always runs at least twelve months ahead.
- Admins can add, rename, or remove holidays individually or as a date range. Guardrails prevent editing past dates, more than 25 holidays a year, or runs longer than 14 consecutive days; weekend dates are rejected as unnecessary.
- The calendar drives the milestone "no response in 3 working days" escalation.

---

## 3. Key Schema Design Decisions

> **Note:** full table-by-table detail is in `database/bluonx_schema_documentation.md` and the SQL files. This section covers the *reasoning* behind non-obvious decisions.

### 3.1 Schema at a Glance

The production schema contains **34 tables**, 3 reporting views, and a set of stored procedures for multi-row atomic writes. The plan anticipated 28 tables; the additions came from the revision feature, milestone hardening (event ledger and check-in tokens), vendor performance reviews, the holiday calendar, and the contract signer roster.

| Group | Tables |
|-------|--------|
| Access control | users |
| Trade & vendor | trades, vendors, vendor_contacts, vendor_trades, vendor_documents |
| Project & task | projects, project_documents, tasks |
| Bid lifecycle | bid_templates, bid_template_items, bid_packages, bid_package_documents, bid_invitations, bid_submissions, bid_line_items, bid_attachments, bid_scores, bid_revision_requests, magic_link_tokens |
| Award & contract | awards, contracts, docusign_envelopes, contract_signers |
| Milestone & performance | milestones, milestone_alerts, milestone_responses, milestone_events, milestone_checkin_tokens, vendor_performance_reviews |
| Communication & audit | email_log, notifications, vendor_flags |
| System configuration | holidays |

Views: `v_vendor_performance` (average PM rating per vendor and its 0–100 score), `v_milestone_overview` (milestone list and dashboard read model), `v_vendor_email_log` (vendor communication history).

### 3.2 Denormalized Fields with Consistency Triggers

Several tables carry a denormalized foreign key for query performance. Each is enforced by a BEFORE INSERT/UPDATE trigger that raises an error on any mismatch, so the application never trusts a client-supplied denormalized value:

| Table | Denormalized field | Validated against |
|-------|-------------------|-------------------|
| `bid_submissions` | `vendor_id` | `bid_invitations.vendor_id` |
| `awards` | `vendor_id` | `bid_submissions.vendor_id` |
| `awards` | `task_id` | Chain: submission → invitation → package → task |
| `contracts` | `vendor_id`, `task_id` | `awards.vendor_id`, `awards.task_id` |
| `milestones` | `task_id` | `contracts.task_id` |
| `vendor_performance_reviews` | `vendor_id` | `contracts.vendor_id` |

### 3.3 Cascade Strategy

- **RESTRICT** (the default) — audit-safe; prevents accidental data loss on core entities.
- **CASCADE** — only on tightly-coupled children (line items, attachments, template items, magic-link and check-in tokens, junction tables, notifications, the milestone event ledger).
- **SET NULL** — on optional or advisory references (scored by, resolved by, reviewer, archived by, holiday creator).

### 3.4 Soft Deletes and Archiving

`deleted_at` on `users`, `vendors`, `projects` and `tasks`. Core entities are never hard-deleted; RLS read policies hide soft-deleted rows. Projects additionally have an **archive** state (`archived_at`, `archived_by`), separate from deletion, that freezes a project without hiding it.

### 3.5 Status Fields as CHECK Constraints

All status fields use CHECK constraints rather than PostgreSQL enums, so new values can be added without type migrations.

### 3.6 Vendor Capacity Management

Two triggers maintain `vendors.current_active_jobs`:
- Award accepted (the vendor signs the contract): +1. Award revoked after acceptance: −1, with double-decrement protection.
- Contract completed or terminated: −1.

Application code never edits the capacity counter directly.

### 3.7 RLS and Data-Access Architecture

- **Reads** by staff (admin and PM) go directly from the browser to Supabase and are governed by Row Level Security.
- **Writes** go through FastAPI using the `service_role` key, which bypasses RLS. FastAPI is the primary gatekeeper for every mutation.
- **Scheduled jobs** run inside the FastAPI process and use the same server-side client. (Version 3.1 described n8n writing directly to the database; n8n was removed and no external system writes to the database.)
- **Vendors never access Supabase.** FastAPI mediates all vendor access.
- **Anonymous:** zero access on all tables and the private schema.
- **Database-level write guards** where the database itself should enforce policy: admin-only writes on `users`, `trades` and `holidays`; owner-scoped `notifications`; admin-only read of `magic_link_tokens`.
- Helper functions (`private.is_active_user()`, `private.is_admin()`) are SECURITY DEFINER functions in a `private` schema not exposed through the API.

### 3.8 Atomic Multi-Row Writes via Stored Procedures

Most writes are single-statement operations protected by triggers and partial unique indexes. Where one user action must write several rows all-or-nothing, the work is done in a single stored procedure transaction:

| Procedure | What it makes atomic |
|-----------|----------------------|
| `fn_create_bid_package_with_invitations` | Bid package, document links, one invitation and one magic-link token per vendor, and the task's move to bidding |
| `fn_create_milestone` | Milestone row and its opening ledger event |
| `transition_milestone` | Every milestone status change: row lock, transition legality, date updates, and one immutable ledger event |
| `fn_record_milestone_response` | Vendor answer, the resulting transition, and spending the check-in token |
| `fn_mark_contract_complete` | Contract completion, refused while any milestone is still open |
| Business-day functions | Working-day arithmetic against the holiday calendar |

### 3.9 Storage Architecture

Three private buckets with the "coat check" pattern (metadata row in the database, file bytes in storage):

| Bucket | Path pattern | Database table |
|--------|-------------|----------------|
| `vendor-documents` | `{vendor_id}/{document_type}/{filename}` | `vendor_documents` |
| `project-documents` | `{project_id}/{filename}` | `project_documents` (reference documents and scopes of work) |
| `bid-attachments` | `{bid_submission_id}/{filename}` | `bid_attachments` |

Uploads are validated server-side (allowed extensions per bucket, size limits, and a file-signature check). Downloads use one-hour signed URLs. Bid attachments are capped at 10 MB each.

### 3.10 Dormant Seams

When a capability was dropped from scope, its schema elements were deliberately left in place so it can return without a migration: `direct_assign` (bid type and `is_direct_assign`), `bid_scores.scored_by` (manual score adjustment), `email_log.opened_at` / `clicked_at` (open and click tracking), the disabled onboarding-sync trigger, Supabase Realtime plumbing in the frontend, and `contract_signers.user_id`.

---

## 4. Vendor Information

### 4.1 Structure

- A **vendor is a company**, not an individual.
- Each vendor has **multiple contacts**, one marked primary.
- Bid invitations target a contact, not the company directly; milestone check-ins go to the vendor's primary contact.
- A vendor can serve **multiple trades** (`vendor_trades`).
- Latitude and longitude are stored on vendors and projects, geocoded by the backend on create, update and import.
- Vendors carry insurance expiration, insurance coverage amount, bonding capacity, maximum active jobs, current active jobs (trigger-maintained), onboarding status, and an active / inactive / suspended status.

### 4.2 Required Onboarding Documents (uploaded by admin)

1. W-9
2. Insurance Certificate (has an expiration date and is monitored automatically)
3. Executed Master Trade Agreement

### 4.3 Vendor Data Management

- **CSV import:** a three-step import (upload, map and validate, confirm) parses the file in the browser, sends the rows to the API, creates each vendor through the same validation path as manual entry, and reports per-row errors with partial success.
- **Vendor detail page** tabs cover profile, contacts, trades, documents, communication history (every email the system has sent the vendor, with delivery status), and flags.
- **Data migration between environments:** trades, vendors, contacts, vendor trades, vendor documents, bid templates and template items can be copied from one Supabase environment to another in dependency order, replacing user references with a valid user in the target environment. The procedure is in the Technical Overview.

### 4.4 Vendor Flags and Performance

The original plan called for PMs to manually flag problematic vendors. During Phase 10 the client chose a simpler, more objective mechanism: a **1–5 performance rating recorded by the PM when a contract is completed**. Ratings are averaged per vendor and feed the 20% past-performance dimension of bid scoring. The `vendor_flags` table and the read-only Flags tab remain, and flagged vendors still show a warning during vendor selection, but flag creation is no longer part of the workflow.

---

## 5. Trade / Scope Categories

Trades are managed by administrators under **Settings → Trades** (create, rename, set phase, activate/deactivate, delete when unused). Each trade carries a phase of `due_diligence`, `development`, or `both`.

**Due Diligence:** Engineering, Phase 1/Phase 2, Title, Traffic Study, Ecological Study, Geo Tech (also known as Geotechnical Engineering), Legal, Manual Entry (Self Perform)

**Development:** Engineering, Mass Grading, Underground Utilities, Electric Conduit/Crossings, Paving, Blasting, Demo, Erosion Control, Retaining Walls, Site Final Grading, Common Ground Electric, Common Ground Flatwork, Common Ground Amenities, Street Signs, Landscaping, Irrigation, Fencing, Sod, Monuments, Fountains and Aeration, Basins, Mailboxes, Manual Entry

**Notes:**
- Engineering and Manual Entry appear in both phases (`phase = 'both'`).
- "Common Ground Amenities" can include 40+ sub-tasks; PMs create only what each project needs.
- **Trades required by the Task Template Library:** Title, Legal, Engineering, Geo Tech (or Geotechnical Engineering), Ecological Study, Site Final Grading, Mass Grading, Blasting, Erosion Control, Underground Utilities, Electric Conduit/Crossings, Common Ground Electric, Paving, Common Ground Flatwork, Street Signs, Sod, Landscaping, Irrigation, Monuments, Fountains and Aeration, Common Ground Amenities, Retaining Walls, Fencing, and Basins. These must exist and be active, with a phase compatible with the template's phase, in every environment where Add Default Tasks is used.

---

## 6. Users, Authentication & Roles

- **Authentication:** Supabase Auth, email and password. No OAuth or Google Sign-In for the MVP.
- **Invite-only accounts:** there is no public sign-up page. Admins invite users from **Settings → Users** (name, email, role). Supabase sends the invitation; the link lands on the **Accept Invite** page where the user sets a password. Admins can resend an invitation to a user who has not yet accepted, change roles, deactivate, delete (soft) and restore users.
- **Safety guards:** an admin cannot change their own role, deactivate or delete themselves, and no action can remove the last active admin.
- **Auth to profile:** a trigger on Supabase Auth user creation creates the matching `public.users` row with the same id, taking `full_name` and `role` from the invitation metadata.
- **Password recovery:** Forgot Password sends a Supabase reset email; the reset link lands on the Reset Password page.
- **Sessions:** persisted in the browser under the `bluonx-auth` key with automatic token refresh. Deactivated users are signed out automatically.
- **Roles:**
  - `admin` — full access including the Settings area (Trades, Users, Calendar, Contract Signers).
  - `project_manager` — projects, tasks, vendors, bid templates, the full bid process, awards, contracts, milestones and reviews.
- All projects are visible to all active users for the MVP (no per-project access restriction).
- No executive approval workflow for the MVP.
- **Vendors** never have accounts. They are authenticated per invitation by magic link (see Section 7.4 and Section 9.3).
- **Key engineering lessons (retained from 3.1):** the Supabase auth-state callback must stay synchronous (fire-and-forget), and profile loading has a timeout so a slow request cannot hang the app.

---

## 7. Bid Process Details

### 7.1 Bid Package Creation

From a competitive task, **Start Bidding** opens a three-step wizard:

1. **Configure** — bid deadline, desired start date (optional), bid template (or lump sum only), Scope of Work upload (required), instructions to vendors, and project documents to include.
2. **Select vendors** — the qualified vendor list, pre-selected, with distance, flags and capacity; a collapsible list of disqualified vendors with the reason for each. The PM can add a disqualified vendor with an explicit override confirmation, or remove any vendor.
3. **Review and send** — a summary, then send.

Creation is atomic: the package, documents, invitations and tokens are written in one transaction. Emails are then sent per vendor; any invitation that fails to send is marked **Failed to Send** and can be re-sent from the package page.

### 7.2 Bid Format

Hybrid: lump sum for simple scopes, structured line items for complex trades. Both item types (`lump_sum` and `unit_price`) can coexist in one template. The vendor portal enforces the arithmetic server-side: each line total must equal its own quantity × unit price, and the grand total must equal the sum of the lines.

### 7.3 Vendor Filtering

Vendors are filtered from the system's own database (not an external search) by:

| Criterion | Rule |
|-----------|------|
| Trade | Vendor must be linked to the task's trade |
| Status | Vendor must be active |
| Onboarding | Considered in qualification and compliance scoring |
| Insurance | Expired or missing insurance disqualifies; lapsing before project end is advisory |
| Bonding | Bonding capacity compared against the task budget |
| Capacity | Current active jobs compared against maximum |
| Distance | Within **75 miles** of the project (straight-line distance; configurable per request) |
| Flags | Shown as warnings; never auto-exclude |

The PM always reviews the list and confirms before any invitation is sent.

### 7.4 Vendor Portal and Magic Links

- Each invitation email contains a unique link. Only a SHA-256 hash of the token is stored; the raw token exists only in the email.
- The link remains valid until the bid package deadline. Re-sending a link revokes the old one and issues a new one.
- Opening a valid link issues a **vendor session** (a short-lived signed token, 4 hours by default). If it expires, the vendor clicks the original link again and resumes from their saved draft.
- The portal is a four-step form: company information, pricing (template line items or a single total, plus a proposed start date when the package has a desired start date), notes and attachments, then review — including the Scope of Work attestation.
- Drafts auto-save every two minutes and when the window loses focus, and can be saved manually.
- On submission the vendor sees a confirmation page and receives a confirmation email. (No PDF receipt — see Section 12.)
- Clear dedicated pages handle expired, invalid, closed and already-submitted links.

### 7.5 Reminders and Escalation

- Vendors who have not submitted receive reminder emails at **T-7 (friendly), T-3 (urgent) and T-0 (final call)** relative to the package deadline. Vendors who submitted, declined or expired are skipped; each reminder is sent at most once per day per invitation.
- Reminders do not carry a new link; they refer the vendor to the original invitation email so each invitation keeps exactly one valid link.
- After the deadline passes, the package creator receives an in-app **post-deadline escalation** listing non-responders, and those invitations are marked no-response.
- Overdue packages close automatically when viewed after the deadline.

### 7.6 Scoring Weights (Client-Confirmed, Fixed for MVP)

| Dimension | Weight | As-built method |
|-----------|--------|-----------------|
| Price | 50% | Lowest bid in the round ÷ this bid × 100 (lowest bid scores 100) |
| Compliance | 5% | Average of onboarding (complete 100, partial 50, pending 0) and insurance (valid 30+ days beyond the bid deadline 100, valid at the deadline 50, otherwise 0) |
| Past Performance | 20% | The vendor's average PM rating (1–5) mapped to 0–100; vendors with no completed-contract ratings receive a neutral 75 |
| Capacity | 10% | Available jobs ÷ maximum jobs × 100; neutral 75 when maximum is unknown |
| Timeline Alignment | 15% | Proposed start versus desired start: on time 100, up to 7 days late 75, up to 14 days 50, up to 30 days 25, later 0. When the package has no desired start date every bid scores 100, so the dimension cancels out of the ranking |

Scoring is run on demand by the PM (normally at or after the deadline, since every new bid changes every price score) and can be recomputed at any time. Each score row stores a snapshot of the inputs and weights used.

### 7.7 Comparison and Recommendation

The **Compare Bids** workspace shows a recommendation panel, a sortable, colour-coded comparison table with expandable line items, and a bid-amount chart. The recommendation ranks bids by total weighted score (ties go to the lower price), gives a plain-language justification for the top pick, and flags four risks per vendor: over budget, late start, insurance window, and incomplete onboarding. The page is print-friendly for browser print-to-PDF. **The system recommends; it never awards automatically.**

### 7.8 Bid Deadline

The same deadline applies to all vendors on a given package (`bid_packages.deadline`). Per-vendor revision requests carry their own deadline.

### 7.9 Award Process

100% manual. The PM reviews the comparison, makes the final call, and clicks **Award**. Pre-award validation runs automatically and the PM sees the result before committing (Section 9.1). Warnings can be overridden only with a written justification, stored with the award together with a full snapshot of the validation results.

---

## 8. Email and Notification Architecture

### 8.1 Service Stack

- **AWS SES** sends every transactional email: bid invitations, reminders, submission and revision confirmations, revision requests, award notifications, decline letters, milestone check-ins, and PM milestone alerts.
- **AWS SNS** delivers SES delivery, bounce and complaint events to the backend webhook, which updates the matching `email_log` row. Correlation is by the SES message id stored at send time.
- **APScheduler** (inside the backend) triggers every time-based send. n8n is not used anywhere in the delivered system.
- **Supabase Auth's mailer** sends the staff invitation and password-reset emails. This is a separate track from SES and must be configured with production SMTP before go-live.
- A **mock email provider** is the default for local development so no real email is sent unintentionally. Production refuses to start unless SES is configured.

### 8.2 Channel Split by Recipient

- **External vendors receive email.**
- **Internal staff receive in-app notifications** (bell icon with unread badge, dropdown, and a full Notifications page). Milestone delays and non-responses also email the owning PM because they need action.

Notification types include insurance expiring, insurance expired, post-deadline non-responders, scheduler alerts, milestone delayed, milestone unresponsive, milestone completed, and milestone check-in delivery failure.

### 8.3 Email Templates

Every email ships as a branded HTML version and a plain-text version.

| Category | Templates |
|----------|-----------|
| Bidding | Bid invitation; friendly, urgent and final reminders; submission confirmation |
| Revisions | Revision request; revised bid received |
| Award | Award notification (with DocuSign signing request); decline letter to unsuccessful vendors |
| Milestones | Start check; progress check; completion check; PM delay alert; PM no-response alert |
| Internal digests (available, not used in the default flow) | Insurance expiration digest; post-deadline escalation digest; scheduler self-check alert |

### 8.4 Email Tracking Scope (MVP)

The `email_log` table records every send with `status` (queued, sent, delivered, bounced, failed, complained), `sent_at`, the provider message id, and any error. Failed sends retry up to three times with backoff.

**Deferred:** `opened_at` and `clicked_at` exist but are not populated. The system knows a vendor acted from the action itself (a submission, a revision response, a milestone answer), so pixel and link tracking were not needed for the MVP.

---

## 9. Awards, Contracts & Milestones (As Built)

### 9.1 Pre-Award Validation

Six checks run against the candidate bid, fresh on the server every time:

| Check | Block (cannot award) | Warn (override with justification) | Skipped |
|-------|---------------------|-------------------------------------|---------|
| Submission eligibility | Superseded, draft, non-awardable status, or no positive amount | — | — |
| Insurance validity | Expired | Missing on file, or lapses before project end | — |
| Bonding capacity | — | Not on file, or below the award amount | — |
| Vendor capacity | — | At or over maximum active jobs | Maximum not set |
| Budget variance | — | More than ±5% from the task budget estimate | No budget estimate |
| Start-date feasibility | — | No proposed start, or later than the desired start | No desired start date |

A preview of the result is shown before the PM commits. A blocked award is rejected. An award with warnings requires a justification and is recorded with `has_override = true`.

### 9.2 Award Details Captured

At award time the PM also chooses the **BluOnX signer** (from the admin-managed Contract Signers roster), optional **award instructions** for the vendor, the **contract validity period** (default 365 days) and an optional **work duration** in days. The award is created in `pending_acceptance` and the task moves to awarded.

### 9.3 Contracts and DocuSign

- Immediately after the award is created, the system creates the **contract record** (status `sent_for_signature`), generates the **contract PDF** (firm terms, scope, amount, dates, the signed scope-of-work date, and the scope-of-work exhibit), and sends a **two-signer DocuSign envelope**: the BluOnX signer signs first, then the vendor.
- The vendor receives the **award notification email** alongside the DocuSign signing request.
- If the send fails, the award still stands and the task page shows a **Contract Not Sent** alert with a re-send action. Re-sending is idempotent: if DocuSign already holds an envelope for the contract, the system reconciles to it instead of sending a second contract.
- **DocuSign Connect** reports status back to the system:
  - **Completed** → contract `executed` (signature date and validity end recorded), award `accepted`, vendor capacity +1, and **decline letters sent to every other invited vendor**. Declines are sent only once the winner has signed, so the backup pool is not lost if the winner declines.
  - **Declined or voided** → contract `terminated`, award `declined_by_vendor`; the PM can award another vendor.
  - Webhooks are signature-verified and safe to receive more than once.
- The signer name and email are snapshotted onto the contract so later roster changes never rewrite an executed contract.

### 9.4 Milestone Tracking

**Overview:** simple, email-driven milestone tracking with no vendor account. The PM defines milestones; the system asks the vendor the right question at the right time and alerts the PM only when a human needs to act.

**Creating milestones:** milestones can be added to a task once it has an active contract (internal tasks never have milestones). Each has a name, start date, end date and notes. Typically 2–5 per awarded task; short engagements can use a single completion milestone. Statuses: `scheduled`, `in_progress`, `delayed`, `unresponsive`, `completed`, `cancelled`. A mistaken milestone is cancelled rather than deleted, so the audit history stays intact.

**Check-in schedule (per milestone, sent each morning by the daily job):**
- **Start date:** "Did you start?"
- **Progress check:** 5 days before the end date, only when that still leaves at least 3 days after the start (in practice, milestones of 8 days or longer).
- **End date:** "Did you complete?"
- A one-day milestone receives both the start and the completion check. Check dates already in the past are never back-filled.

**How the vendor answers (as built):** the email contains a single secure link to a one-question page in the vendor portal with **Yes** and **No** buttons. The answer is recorded only when the vendor presses a button — not when the link is opened — so email security scanners that pre-open links can never answer on the vendor's behalf. Links expire after 7 days; the first answer wins, and a second click shows "already answered."

**Outcomes:**
- **Yes** advances the milestone (scheduled → in progress → completed). A completion "Yes" notifies the PM.
- **No** sets the milestone to `delayed`, emails and notifies the owning PM, and **pauses** the check-in cycle.
- **No response in 3 working days** (weekends and holidays excluded) sets the milestone to `unresponsive`, emails and notifies the PM, and pauses the cycle. A **bounced** check-in email is not treated as silence; the PM is instead told to correct the vendor's email address.

**PM actions:** from the milestone page (linked directly from every PM alert) the PM can mark started, mark completed (with actual dates), **reschedule** the end date, or cancel. A reschedule keeps the originally committed end date as the baseline (so on-time performance is measured honestly), starts a new check-in cycle, and makes all earlier links stale automatically.

**Visibility:** every transition is written to an append-only event ledger that drives the milestone **activity timeline**. A global Milestones page lists milestones across projects, and the dashboard's **Needs Attention** card lists every delayed or unresponsive milestone, worst-stalled first.

### 9.5 Contract Completion and Vendor Review

When the work is done, the PM marks the contract **complete** (refused while any milestone is still open). The **review panel** then asks for a 1–5 rating and optional notes. One review is allowed per contract and can be edited for corrections. Ratings feed the vendor's past-performance score in future bids.

---

## 10. Phase-by-Phase Completion Record

Each phase is summarised against the original project plan (Version 2.0, February 10, 2026): what the plan asked for, what was delivered, and where the build differed.

### Phase 1 — Foundation & Database Setup (60 h)

**Plan:** Supabase environments, the core schema, indexes, RLS, triggers, storage buckets, authentication framework, separate environments, and AWS infrastructure.

**Delivered:**
- Complete PostgreSQL schema (now 34 tables), with UUID keys, timezone-aware timestamps, CHECK-constrained statuses, and RESTRICT-by-default foreign keys.
- Foreign-key, filter, sort and partial unique indexes. The load-bearing partial unique indexes enforce one active award per task, one active contract per task, one current submission per invitation, and one pending revision request per invitation.
- RLS enabled on every table with security-definer helpers in a private schema; zero anonymous access.
- Triggers for timestamps, bid round numbering, invitation status sync, denormalized-key consistency, vendor capacity, revision supersession, milestone date guards, and holiday guardrails.
- Three private storage buckets with twelve policies.
- Supabase Auth integration, including the trigger that creates each user's profile.
- Development and production Supabase projects, with a documented procedure for copying reference data (trades, vendors, bid templates) between them.

**Differences:** the onboarding-sync trigger was built but deliberately disabled; AWS infrastructure was stood up during Phase 12 rather than in Phase 1.

### Phase 2 — Frontend Foundation, Backend API & Authentication (100 h)

**Plan:** React + Vite + Tailwind project, routing, Supabase client, React Query, UI component library, FastAPI on AWS, authentication including Google Sign-In, dashboard layout, responsive design.

**Delivered:**
- React application with three isolated route areas: public authentication pages, the protected staff dashboard (with an admin-only Settings area), and the vendor portal (its own layout and authentication, never touching Supabase).
- A hand-built library of about 25 UI components (forms, modals, tables with mobile card layouts, tabs, toasts, badges, skeletons, stat cards, file upload) with no third-party UI kit.
- React Query data layer with centralised query keys and invalidate-on-success mutations.
- Layered FastAPI backend (routers, services, models, core infrastructure, jobs), containerised with a multi-stage, non-root Docker image.
- Staff authentication: login, forgot password, reset password, accept invite, protected routes, role-based navigation, automatic token refresh; backend verification of both current (ES256) and legacy (HS256) Supabase tokens.
- Responsive layouts for mobile, tablet and desktop, with a collapsible sidebar and mobile menu.
- Production safety checks at start-up (CORS origins, frontend URL, email provider) and structured JSON request logging with a correlation id on every request.

**Differences:** Google Sign-In and self-registration were removed from scope (accounts are invite-only); Supabase Realtime is plumbed but not used.

### Phase 3 — Core Entity Management (60 h)

**Plan:** vendor, project and task CRUD; CSV vendor import; document upload; Google Maps; bid template builder.

**Delivered:**
- Vendor management with contacts, trades, documents (with expiry), CSV import with per-row validation, search, filters and sort.
- Project management with budget, address autocomplete and geocoding, documents, status, archive and unarchive.
- Task management within projects: create, edit, soft delete with safety blocks, drag-and-drop reordering, phase-filtered trade selection, unique names, controlled status transitions, and bid-type locking after draft.
- Document upload with drag-and-drop, server-side type and signature validation, and signed-URL downloads.
- Google Maps geocoding, address autocomplete, straight-line distance filtering, and on-demand driving distance.
- Bid Template Builder with live vendor-view preview, duplicate, and edit/delete protection.
- **Added at client request:** the Task Template Library and **Add Default Tasks** button (Section 2.10).

**Differences:** the bulk 75-mile filter uses straight-line distance rather than driving distance (Section 12).

### Phase 4 — Bid Invitation System (50 h)

**Plan:** intelligent vendor filtering, invitation email templates, email service integration, batch sending, invitation tracking, vendor selection UI.

**Delivered:**
- Qualified / disqualified vendor lists with per-vendor reasons and PM override.
- Three-step bid package wizard with deadline, desired start date, template, Scope of Work, instructions and document selection.
- Atomic package creation; per-vendor magic links; SES sending with retry and audit logging; truthful "Failed to Send" status with one-click re-send.
- SES/SNS delivery, bounce and complaint tracking, verified end to end with the SES mailbox simulator.
- Bid package detail page with summary cards, submission status chart, invitations table (send/re-send link, mark declined, view bid, request or cancel revision) and email log.

**Differences:** batch sending is sequential inside the API rather than an n8n/Redis queue, which is appropriate at the system's volume.

### Phase 5 — Bid Collection: Custom Secure Forms (60 h)

**Plan:** multi-step bid form, magic-link authentication, form API, validation, file upload, drafts, confirmation, portal routing, vendor help.

**Delivered:**
- Account-free vendor portal: magic-link validation with precise outcomes (unknown, revoked, expired, closed, already submitted), then a short-lived vendor session that can never be confused with a staff session.
- Four-step form with progress indicator, help text, auto-save drafts, attachment upload, Scope of Work attestation and review.
- Server-side validation of every amount and line total, ownership checks on every request, and rate limiting on link validation.
- Confirmation page and confirmation email.
- **Added at client request:** per-vendor bid revision flow in the portal (Section 2.11).

**Differences:** no PDF receipt is generated (the email and on-screen summary serve as the receipt); virus scanning was not added — uploads are restricted by type, size and file signature instead.

### Phase 6 — Real-Time Dashboard & Response Tracking (60 h)

**Plan:** live submission tracking via WebSockets, bid tracking dashboard, completeness indicators, charts.

**Delivered:**
- Dashboard with Active Projects, Open Tasks, Pending Bids and Active Vendors cards, quick-access navigation, and (from Phase 10) the Needs Attention milestones card.
- Cross-project **Bids** list with status, project and sorting, and submission counts.
- Bid package tracking (invited / submitted / pending / failed counts) and a submission status pie chart; single-bid detail view with line items and attachments.
- Data refreshes on window focus, on navigation, and immediately after every action.

**Differences:** WebSocket push was replaced by refresh-on-focus and mutation-driven refresh. The plumbing for Supabase Realtime exists and can be enabled later.

### Phase 7 — Automated Reminder System (40 h)

**Plan:** n8n reminder workflows, tiered reminder templates, admin escalation, reminder history.

**Delivered:**
- In-process scheduler with eight jobs (Section 13.3), each recording its last run and result, visible on an admin scheduler-health endpoint, with a daily self-check that alerts admins about stale jobs.
- T-7 / T-3 / T-0 vendor reminders, insurance expiration monitoring, and post-deadline escalation.
- In-app notification centre (bell, unread count, dropdown, full page).
- Complete communication history per bid package and per vendor.

**Differences:** n8n was replaced by APScheduler; staff alerts are in-app rather than email digests.

### Phase 8 — Bid Comparison & Scoring (40 h)

**Plan:** normalisation engine, weighted scoring, comparison UI, recommendation engine, export.

**Delivered:**
- Five-dimension weighted scoring with client-confirmed weights (Section 7.6), stored with an input snapshot.
- Desired-start / proposed-start dates added to packages and submissions so the timeline dimension is measurable.
- Compare Bids workspace with recommendation, justification, risk flags, sortable colour-coded table, expandable line items, chart, and print-friendly layout.

**Differences:** no separate normalisation engine was needed because every vendor in a package bids on the same frozen template; manual score adjustment was replaced by award-time override; export is browser print-to-PDF rather than Excel.

### Phase 9 — Award Decision & Contract Generation (40 h)

**Plan:** pre-award validation, override workflow, DocuSign integration, award letter, contract record, decline notifications.

**Delivered:** everything in Sections 9.1–9.3 — six-check validation with preview, mandatory justification for overrides with a stored snapshot, contract signer roster, generated contract PDF, two-signer DocuSign envelopes, Connect webhook processing, award notification, decline letters on signature, contract-send failure recovery, and capacity updates by trigger.

**Differences:** decline letters are sent when the winner signs rather than at award time (to protect the backup pool); contract payment terms are currently placeholder text awaiting the client's subcontract language (Section 14).

### Phase 10 — Vendor Commitment & Performance Tracking (50 h)

**Plan:** milestone management, milestone schema, email response handlers, n8n alert workflows, email templates, PM dashboard widgets, vendor flagging.

**Delivered:** everything in Section 9.4 and 9.5 — milestone management, a transactional state machine with an immutable event ledger, secure portal-based Yes/No check-ins, daily check-in and no-response jobs, working-day calendar with holiday administration, PM alert emails and notifications, milestone timeline, global milestone list, dashboard attention card, contract completion, and PM performance reviews feeding bid scoring.

**Differences:** Yes/No answers are given on a portal page behind the emailed link rather than by clicking an answer link in the email (scanner-safe); "no response for 2 days" became **3 working days**; manual vendor flagging was replaced by post-contract ratings; the "starting soon" T-5 reminder is supported by the data model but not sent by the daily job.

### Phase 11 — Comprehensive Testing & QA (80 h)

**Plan:** unit, integration, end-to-end and user acceptance testing, bug fixing and performance optimisation.

**Delivered:**
- Backend: about 170 pytest modules covering routers, services, scoring, validation, tokens, jobs (against an in-memory database double), webhooks, and email rendering. A small set of tests that exercise real triggers, business-day functions and stored-procedure permissions run against a live Supabase project on demand.
- Frontend: about 100 Vitest / React Testing Library test files covering pages, forms, the vendor portal, notifications, milestones and contracts.
- A dedicated test container (`api-test`) so the backend suite runs identically on every machine.
- Client walkthroughs and UAT on the development environment, followed by a hardening pass (correct 404/409 responses instead of 500s, upload allow-list alignment, ECS-safe scheduling, accessible table markup, lint clean-up).

**Differences:** end-to-end browser automation (Playwright) was not added; end-to-end flows were exercised through UAT. Continuous integration on GitHub Actions is recommended (Section 14).

### Phase 12 — Deployment & Training (60 h)

**Plan:** production deployment, production Supabase, production email, n8n production, monitoring, documentation, video tutorials, live training.

**Delivered:**
- Backend container published to Amazon ECR and running on ECS Fargate behind an Application Load Balancer at the development API domain; frontend on AWS Amplify, connected to GitHub, at the development app domain.
- SES sending with SNS delivery tracking; DocuSign sandbox integration; separate production Supabase project.
- Structured JSON logging to CloudWatch, `/health` for load-balancer checks, scheduler and DocuSign health endpoints.
- Documentation set: this handoff, the Technical Overview, the deployment checklist, the schema documentation, feature specifications and the scheduler ADR.
- Walkthroughs with the client team.

**Differences:** hosting moved from Vercel to AWS Amplify; n8n is not deployed; Sentry and an external uptime monitor are recommended but not yet configured. The remaining production cut-over items are listed in Section 14.

---

## 11. Features Added Beyond the Original Plan

These capabilities were requested by the client or proved necessary during the build and were delivered in addition to the approved scope.

| # | Feature | What it gives the client |
|---|---------|--------------------------|
| 1 | **Task Template Library & Add Default Tasks** | 58 standard activity-coded task templates (B0010–B0760) with phase, trade and bid type; one click seeds a project; safe to repeat; every resulting task fully editable (Section 2.10, Appendix A) |
| 2 | **Per-vendor bid revision** | Negotiate with one vendor after the round closes, with full version history and automatic expiry (Section 2.11) |
| 3 | **Scope of Work requirement and attestation** | Mandatory SoW per bid package; vendor attestation carried onto the contract (Section 2.7) |
| 4 | **Contract Signers roster** | Admin-managed list of authorised BluOnX signers; the PM picks one per award; it can never be emptied (Section 9.2) |
| 5 | **Working-day holiday calendar** | Admin-managed holidays, auto-seeded federal holidays, drives fair responsiveness rules (Section 2.12) |
| 6 | **User Management** | Invite, resend invite, change role, deactivate, delete and restore users, with last-admin protection (Section 6) |
| 7 | **Trades administration** | Admins manage the trade list and phases from Settings |
| 8 | **Vendor performance reviews** | 1–5 PM rating per completed contract, feeding the 20% past-performance score (Section 9.5) |
| 9 | **Milestone activity timeline and attention card** | Complete audit trail of every milestone change, plus a cross-project "needs attention" view |
| 10 | **Contract send recovery** | Visible alert and safe, idempotent re-send when a DocuSign send fails |
| 11 | **Project archiving** | Freeze completed or paused projects without deleting them |
| 12 | **Vendor communication history** | Every email sent to a vendor, with delivery status, on the vendor page |
| 13 | **Bid template duplication and freeze** | Issued bids stay comparable; templates can be copied and adapted |
| 14 | **Desired start / proposed start dates** | Vendors commit to a start date; feeds timeline scoring and pre-award checks |
| 15 | **Delivery-failure awareness** | A bounced milestone email alerts the PM to fix the address rather than flagging the vendor |

---

## 12. Deviations from the Original Plan

| # | Plan said | As built | Reason |
|---|-----------|----------|--------|
| 1 | 28 tables | 34 tables | Revision feature, milestone ledger and tokens, reviews, holidays, contract signers |
| 2 | `direct_assign` is a supported bid type | Dormant; API accepts only competitive and internal | Client confirmed all vendor work is competitive; schema value kept for future revival |
| 3 | n8n Pro for scheduling and email orchestration | APScheduler inside the backend; n8n removed | Version-controlled, testable, no extra paid service or second deployment |
| 4 | Vercel Pro frontend hosting | AWS Amplify | Single cloud provider for frontend, backend and email |
| 5 | Google Sign-In; self-registration | Email/password, invite-only | Internal tool with a small, controlled user base |
| 6 | Supabase Realtime / WebSockets | Refresh on focus and after actions; Realtime plumbing dormant | Simpler and sufficient at current scale |
| 7 | Driving-distance radius filter | Straight-line distance for the bulk filter; driving distance on demand | Cost and speed; adequate for a 75-mile qualification radius |
| 8 | Onboarding status auto-synced from documents | Manual PM control | PM verifies beyond document presence |
| 9 | Template protected on delete only | Also frozen on edit while referenced; duplicate as escape hatch | Keeps issued bids comparable |
| 10 | Vendor PDF receipt | Confirmation email and on-screen summary | No business need identified for a PDF |
| 11 | Virus scanning of uploads | Type, size and file-signature validation | Avoided an extra scanning service for the MVP |
| 12 | Per-step React Hook Form validation in the vendor portal | Server-driven validation with field errors mapped to steps | One authoritative rule set |
| 13 | Staff email digests | In-app notifications for staff | Clear channel split; reduces inbox noise |
| 14 | Bid normalisation engine | Not needed | One template per package guarantees comparability |
| 15 | Manual score adjustment | Not built; override at award time instead | PM discretion recorded once, with justification |
| 16 | Excel export of comparisons | Print-to-PDF | No export library required |
| 17 | Answer links directly in milestone emails | One portal link; Yes/No on the page | Prevents email scanners from answering automatically |
| 18 | No response for 2 days | 3 working days, holiday-aware | Fairer to vendors; matches business practice |
| 19 | Manual vendor flagging | Post-contract 1–5 ratings | Objective, measurable input to scoring |
| 20 | Decline letters at award | Sent when the winner signs | Protects the backup vendor pool |
| 21 | Playwright end-to-end tests | Unit/integration suites plus UAT | Effort focused on hardening the core workflows |
| — | Not in plan | Task Template Library and Add Default Tasks | Client request — standardises project set-up |

---

## 13. Environments, Deployment and Operations Summary

Full engineering detail is in `docs/BluOnX_Technical_Overview.md`; the go-live runbook is `docs/DEPLOYMENT_CHECKLIST.md`.

### 13.1 Environments

| Environment | Frontend | Backend | Database |
|-------------|----------|---------|----------|
| Local development | Vite dev server (port 5173) | Docker Compose (port 8000) | Shared development Supabase project |
| AWS development | AWS Amplify (dev app domain) | ECS Fargate behind ALB (dev API domain) | Development Supabase project |
| Production | AWS Amplify (production app domain) | ECS Fargate behind ALB (production API domain) | Production Supabase project |

### 13.2 Release Flow (Summary)

1. Changes are committed and pushed to GitHub (`dev`, then `main`).
2. **Frontend:** Amplify builds and deploys automatically from the connected branch.
3. **Backend:** a fresh container image is built without cache, pushed to ECR, and the ECS service is redeployed with "force new deployment." The new version is confirmed from the API documentation page and the health endpoint.
4. **Database changes** are applied through the Supabase SQL editor in the target environment before the code that depends on them.

### 13.3 Scheduled Jobs

| Job | When (US Central) | Purpose |
|-----|-------------------|---------|
| Revision expiry | Hourly | Expire unanswered revision requests and revoke their links |
| Bid reminders | Daily, morning | T-7 / T-3 / T-0 vendor reminders |
| Insurance expiration | Daily, morning | Admin notifications at T-30, T-7 and while expired |
| Scheduler self-check | Daily, morning | Alert admins if any job has stopped running |
| Post-deadline escalation | Daily, morning | Notify package creator of non-responders and mark them |
| Milestone daily check-in | Daily, morning | Send start, progress and completion checks |
| Milestone no-response | Daily, morning | Escalate check-ins unanswered for 3 working days |
| Holiday seed | Annually, January 2 | Top up federal holidays for the following year |

**The backend must run as exactly one instance.** Every instance runs its own scheduler, so two instances would send every email twice.

### 13.4 Administrator Routine

- **Users:** invite and manage staff under Settings → Users.
- **Trades:** maintain the trade list under Settings → Trades (keep the Task Template Library trades active).
- **Calendar:** review next year's holidays each January.
- **Contract Signers:** keep at least one active signer.
- **Insurance:** act on expiring-insurance notifications and update certificates.
- **Health:** check scheduler health and email delivery status periodically.

---

## 14. Open Items and Pre-Production Checklist

| # | Item | Owner | Notes |
|---|------|-------|-------|
| 1 | **Replace placeholder contract payment terms** with the client's subcontract language | Client + engineering | Every generated contract currently renders placeholder payment terms; must be replaced before contracts are sent to real vendors |
| 2 | Move DocuSign from sandbox to production account (integration key, account, consent, Connect HMAC key and webhook URL) | Engineering + client admin | Requires DocuSign production go-live approval |
| 3 | Configure production SMTP for Supabase Auth emails and brand the invite template | Engineering | Default Supabase mailer is rate-limited |
| 4 | Confirm SES production access, domain verification (SPF/DKIM/DMARC), configuration set and SNS subscription in production | Engineering | Without the configuration set, delivery tracking stays at "sent" |
| 5 | Set production environment values and secrets (Section 15 of the Technical Overview) | Engineering | Backend refuses to start on unsafe CORS, frontend URL or email settings |
| 6 | Seed the production holiday calendar and confirm trades required by the Task Template Library exist | Engineering / admin | |
| 7 | Bootstrap at least one active admin in production | Engineering | |
| 8 | Add GitHub Actions CI (backend tests, frontend type-check, lint, tests) | Engineering | Recommended |
| 9 | Configure an external uptime monitor on the scheduler-health endpoint, and optionally Sentry | Engineering | A total scheduler outage has no other automated alert |
| 10 | Regenerate frontend database types from the live schema | Engineering | Improves type safety of direct reads |
| 11 | Optional: an in-app editor for the Task Template Library | Future enhancement | Today the library is maintained centrally by engineering |

---

## 15. Out of MVP Scope

- Mobile native apps (iOS / Android)
- Advanced analytics and reporting dashboards
- Automated payment processing and invoicing
- Contingency budget tracking with a variance workflow (requested; flagged out of scope)
- Multi-company and granular per-project permissions
- Change order management
- Subcontractor and tier-2 vendor coordination
- SMS notifications
- Photo uploads for milestone completion
- A full vendor portal for milestone tracking (kept email-based)
- Google Sign-In / OAuth authentication
- Vendor self-service onboarding
- Email open and click tracking
- Budget forecasting and variance analysis
- Weather delay tracking
- Equipment scheduling and management
- Direct (non-competitive) vendor assignment — dormant, revivable
- Excel export of bid comparisons

---

## 16. Glossary

| Term | Meaning |
|------|---------|
| Activity code | BluOnX cost-chart code (B0010–B0760) used to name template tasks |
| Bid package | One bidding round for a task: deadline, template, documents, invited vendors |
| Bid template | A reusable pricing structure (lump sum or line items) |
| Task template | A standard task definition in the Task Template Library |
| Magic link | A one-per-invitation secure link that lets a vendor in without an account |
| Supersession | Replacing a submitted bid with a revised one while keeping the original as history |
| Pre-award validation | Automatic checks run before an award can be made |
| Override | Awarding despite warnings, with a recorded justification |
| Envelope | A DocuSign signing package containing the contract |
| Check-in | A scheduled milestone question sent to the vendor |
| Cycle | A milestone's check-in generation; a reschedule starts a new cycle |
| Working day | A weekday that is not on the holiday calendar |
| Soft delete | Hiding a record by timestamp instead of removing it |

---

## Appendix A — Standard Task Template Library (58 Templates)

Applied to a project with **Add Default Tasks**. Each becomes a draft task named "*Code* – *Task*" with the description, phase, trade and bid type shown. Budget is left blank for the PM.

### A.1 Due Diligence (14)

| Code | Task | Trade | Bid type |
|------|------|-------|----------|
| B0010 | Land | Title | internal |
| B0020 | Closing Costs & Commission | Title | internal |
| B0030 | Capitalized Interest | Legal | internal |
| B0040 | Financing Fees | Legal | internal |
| B0050 | Real Estate Taxes | Legal | internal |
| B0060 | Legal | Legal | competitive |
| B0100 | Engineering and Surveying | Engineering | competitive |
| B0110 | Zoning | Engineering | internal |
| B0120 | Geotech - soils | Geo Tech | competitive |
| B0125 | Geotech - Global Stability | Geo Tech | competitive |
| B0130 | Geo Tech - Compacting Testing | Geo Tech | competitive |
| B0140 | Environmental - Army Corps wetlands | Ecological Study | competitive |
| B0145 | Environmental - Fisheries or Cultural | Ecological Study | competitive |
| B0150 | Natural Resources & Mitigation | Ecological Study | competitive |

### A.2 Development (44)

| Code | Task | Trade | Bid type |
|------|------|-------|----------|
| B0200 | Demolition | Site Final Grading | competitive |
| B0210 | Clearing | Mass Grading | competitive |
| B0220 | Mass Grading | Mass Grading | competitive |
| B0230 | Grading - Clean Up | Site Final Grading | competitive |
| B0240 | Grading Rock | Blasting | competitive |
| B0250 | Utility Rock Excavation | Blasting | competitive |
| B0260 | Erosion Control - silt fence and storm protections | Erosion Control | competitive |
| B0265 | Street Cleaning | Erosion Control | competitive |
| B0270 | Creek Imp./Channel Revetment | Erosion Control | competitive |
| B0300 | Sanitary Sewers | Underground Utilities | competitive |
| B0310 | Off-site Sanitary Sewers | Underground Utilities | competitive |
| B0320 | Sanitary Lift Station | Underground Utilities | competitive |
| B0330 | Sanitary Connection Prepaid Fees | Underground Utilities | internal |
| B0340 | Storm Sewers | Underground Utilities | competitive |
| B0350 | Off-site Storm Sewers | Underground Utilities | competitive |
| B0400 | Water Main | Underground Utilities | competitive |
| B0410 | Off-site Water Main | Underground Utilities | competitive |
| B0420 | Water Main Tax | Underground Utilities | internal |
| B0430 | Electric Install | Electric Conduit/Crossings | competitive |
| B0440 | Street Lights | Common Ground Electric | competitive |
| B0450 | Offsite Utilities | Underground Utilities | competitive |
| B0460 | Utility Relocation | Underground Utilities | competitive |
| B0500 | Concrete Streets | Paving | competitive |
| B0510 | Asphalt Streets | Paving | competitive |
| B0520 | Street Winter Service | Paving | internal |
| B0530 | Common Sidewalks | Common Ground Flatwork | competitive |
| B0540 | Asphalt Parking & Trails | Paving | competitive |
| B0550 | TGA Fees | Engineering | internal |
| B0560 | Offsite Roadwork | Paving | competitive |
| B0600 | Street Signs | Street Signs | competitive |
| B0610 | Seed & Sod | Sod | competitive |
| B0620 | Common Landscaping | Landscaping | competitive |
| B0630 | Irrigation | Irrigation | competitive |
| B0640 | Entry Monuments | Monuments | competitive |
| B0650 | Lakes/Fountains & Bubblers | Fountains and Aeration | competitive |
| B0660 | Amenities | Common Ground Amenities | competitive |
| B0670 | Retaining Walls | Retaining Walls | competitive |
| B0680 | Fencing | Fencing | competitive |
| B0700 | Permits, Inspection & Recording Fees | Engineering | internal |
| B0720 | Contingency (not a payable category) | Engineering | internal |
| B0730 | Developer Fee (Management Fee) | Engineering | internal |
| B0740 | Escrow Release | Engineering | internal |
| B0750 | HOA Overages and initiation | Engineering | internal |
| B0760 | Post-Construction BMP and site clean up | Basins | competitive |

> Two template names are stored with minor spelling as entered from the source cost chart ("sotrm" in B0260 and "Permits , Inspection" in B0700). The tables above show the intended wording; PMs can correct the task name per project, and the library text can be corrected centrally.

---

*End of Project Context Handoff — Version 4.0*
