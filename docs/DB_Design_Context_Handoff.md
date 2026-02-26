# BluOnX Bid Management System — Project Context Handoff
**Date:** February 25, 2026  
**Version:** 3.0  
**Purpose:** Complete project context for continuing development across conversation threads.

---

## 1. System Overview

Building a **Bid Management & Vendor Coordination System** for **BluOnX Development** (land/horizontal) and **Capstone LLC** (vertical construction). The system manages the complete vendor lifecycle: bid invitation → bid collection → comparison/scoring → contract award → milestone tracking.

**Tech Stack:** React + Vite + TypeScript + TailwindCSS v4 (frontend), FastAPI (backend), PostgreSQL via Supabase (database), Supabase Storage (files), Supabase Auth (email/password only — no OAuth).

**Full 12-phase project plan (700 hours, 11 weeks) is attached to the Claude project.**


## 2. Core Business Rules

### 2.1 Foundational Principle
**One Task = One Trade = One Award = One Contract.** Each task belongs to exactly one trade/scope. Vendor filtering, bid comparison, award, contract, and milestones all operate at the task level.

**Multi-trade scenarios:** PM creates separate tasks per trade (e.g., "Erosion Control - Wood Chips" under Mass Grading, "Erosion Control - Maintenance" under Erosion Control). Each goes through its own independent lifecycle.

### 2.2 Three Task Bid Types
- **competitive** — full pipeline: auto-filter vendors → invitations → collection → comparison → award
- **direct_assign** — PM picks a vendor directly. Backend creates a synthetic bid_submission (with `is_direct_assign = TRUE`) so the full downstream chain (award → contract → milestones) works identically. No schema exceptions.
- **internal** — budget line item only, no vendor involvement. Cannot have bid_packages, awards, contracts, or milestones (enforced at application layer, documented in schema comments).

### 2.3 Project Phases
- **Due Diligence** — investigation tasks (geotech, surveys, environmental). Bid out first.
- **Development** — construction tasks (grading, utilities, paving). Proceeds only if DD passes.

Both phases use the same bid workflow and unified vendor pool. Phase is for **task grouping/display only** — not workflow enforcement. The `trades` table has a `phase` field (`due_diligence`, `development`, `both`) that controls which trades appear in the dropdown based on the task's phase.

### 2.4 Re-Award / Re-Bid Scenarios
- **Rebidding:** `bid_packages` has a `round_number` (auto-incremented by trigger). New round = new bid_package for the same task. Full history preserved.
- **Re-award:** Partial unique indexes on `awards` and `contracts` tables allow one active record per task while preserving declined/cancelled history. A vendor can decline → the old award moves to `declined_by_vendor` → a new award is created.

### 2.5 Bid Templates
Steve confirmed some trades use lump sum and others need structured line-item templates. `bid_templates` + `bid_template_items` tables define per-trade bid formats. When a vendor opens the bid form, the system checks if the task's trade has a template — if yes, pre-populates line items; if no, shows a simple lump sum field.

### 2.6 Document Sharing with Bid Invitations
Documents are uploaded at **project level** (`project_documents`). When setting up a bid package, the PM selects which project documents to include via `bid_package_documents` junction table. Actual files stay in Supabase Storage — no duplication.

### 2.7 Vendor Onboarding Status
Managed **manually by PM**, not auto-synced from documents. The PM may need to verify details beyond document presence (confirm insurance with carrier, review W-9 for corrections). The auto-sync trigger exists in the schema but is intentionally disabled (commented out with rationale).

---

## 3. Key Schema Design Decisions

> **Note:** Full schema details are in the attached SQL files. This section covers the *reasoning* behind non-obvious decisions.

### 3.1 Denormalized Fields with Consistency Triggers
Several tables have denormalized FKs for query performance (avoiding expensive JOINs on high-traffic queries). Each is enforced by a BEFORE INSERT/UPDATE trigger:

| Table | Denormalized Field | Validated Against |
|-------|-------------------|-------------------|
| `bid_submissions` | `vendor_id` | `bid_invitations.vendor_id` |
| `awards` | `vendor_id` | `bid_submissions.vendor_id` |
| `awards` | `task_id` | Chain: submission → invitation → package → task |
| `contracts` | `vendor_id`, `task_id` | `awards.vendor_id`, `awards.task_id` |
| `milestones` | `task_id` | `contracts.task_id` |

### 3.2 Cascade Strategy
- **RESTRICT** (39 FKs) — audit-safe, prevents accidental data loss on core entities
- **CASCADE** (8 FKs) — only on tightly-coupled children (line items, attachments, template items, magic link tokens, junction tables, notifications)
- **SET NULL** (5 FKs) — on optional/advisory references (scored_by, resolved_by, milestone_id on flags, email_log_id on alerts)

### 3.3 Soft Deletes
`deleted_at` TIMESTAMPTZ on: `users`, `vendors`, `projects`, `tasks`. Core entities are never hard-deleted. RLS policies filter out soft-deleted records automatically.

### 3.4 Status Fields as CHECK Constraints
All status fields use CHECK constraints (not PostgreSQL enums). Easier to extend without ALTER TYPE migrations.

### 3.5 Vendor Capacity Management
Two triggers maintain `vendors.current_active_jobs`:
- Award accepted → +1; Award revoked after acceptance → -1 (with double-decrement prevention checking if contract already handled it)
- Contract completed/terminated → -1

### 3.6 RLS Architecture
- **Authenticated users (admin/PM):** RLS policies govern all reads via Supabase client
- **All writes:** Go through FastAPI using `service_role` key (bypasses RLS). FastAPI is the primary gatekeeper.
- **Vendors:** Never access Supabase directly — FastAPI mediates all access using `service_role`
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
2. Insurance Certificate (has expiration date)
3. Executed Master Trade Agreement

### 4.3 Data Still Missing from Client
Phone numbers, addresses, insurance details per vendor, W-9 status. The ScopeContracter spreadsheet provides ~25+ vendors with company name, contact, and email organized by scope.

---

## 5. Trade/Scope Categories (~27 from client spreadsheet)

**Due Diligence:** Engineering, Phase 1/Phase 2, Title, Traffic Study, Ecological Study, Geo Tech, Legal, Manual Entry (Self Perform)

**Development:** Engineering, Mass Grading, Underground Utilities, Electric Conduit/Crossings, Paving, Blasting, Demo, Erosion Control, Retaining Walls, Site Final Grading, Common Ground Electric, Common Ground Flatwork, Common Ground Amenities, Street Signs, Landscaping, Irrigation, Fencing, Sod, Monuments, Foundations and Aeration, Mailboxes, Manual Entry

**Notes:** Engineering and Manual Entry appear in both phases (`phase = 'both'`). "Common Ground Amenities" can include 40+ sub-tasks — PM creates only what's needed per project as freeform tasks.

---

## 6. Users, Auth & Roles

- **Authentication:** Supabase Auth — email/password only. No OAuth/Google Sign-In (confirmed as mistake in project plan).
- **Auth → Profile:** Trigger on `auth.users` INSERT auto-creates `public.users` row with matching UUID. Signup passes `full_name` and `role` via `raw_user_meta_data`; trigger reads them with fallbacks (email prefix for name, `project_manager` for role).
- **Frontend auth framework (Task 1.7):** Supabase client singleton → AuthContext/Provider (session + profile state) → auth service layer (signUp, signIn, signOut, resetPassword, getAccessToken) → ProtectedRoute shell. Session persists in localStorage under `bluonx-auth` key. Auto token refresh handled by Supabase client.
- **Roles:** `admin` (full access, manages vendors/trades/users) and `project_manager` (manages projects, tasks, bid process, awards).
- All projects visible to all users for MVP (no project-level access restriction).
- No executive approval workflow for MVP.
- **Remaining auth work:** Login/signup UI pages (Task 2.7), dashboard layout with user menu (Task 2.8), FastAPI JWT validation middleware (Task 2.6).

---

## 7. Bid Process Details

### 7.1 Bid Format
Hybrid: lump sum for simple scopes, structured line items for complex trades. Both supported in same submission via `bid_line_items` table (supports `lump_sum` and `unit_price` item types simultaneously).

### 7.2 Scoring Weights (Fixed for MVP)
40% price, 20% compliance, 20% past performance, 10% capacity, 10% timeline alignment.

`bid_scores.scored_by` is nullable: NULL = system-generated score, non-NULL = manually adjusted by a user.

### 7.3 Bid Deadline
Same deadline for all vendors on a given task. Stored on `bid_packages.deadline`.

---

## 8. Contracts & Milestones

**Contracts:** One per accepted award. DocuSign integration for e-signatures. Partial unique index allows re-contracting if previous contract terminated.

**Milestones:** 2–5 per awarded task. Email-based check-ins (no vendor portal). Track planned vs actual dates. Statuses: scheduled, started, on_track, delayed, completed.

**Milestone alerts** reference `email_log` for delivery details — no data duplication. Milestone-specific context (alert_type, response_token) lives on `milestone_alerts`; delivery tracking lives on `email_log`.

---

## 9. Out of MVP Scope

Mobile native apps, advanced analytics/reporting, automated payment processing, contingency budget tracking with variance workflow (Steve requested; Fatima flagged out of scope), multi-user granular permissions, change order management, SMS notifications, photo uploads for milestones, vendor self-service onboarding portal.
