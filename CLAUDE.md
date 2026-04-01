# BluOnX Bid Management & Vendor Coordination System

## Project Overview

Bid Management & Vendor Coordination System for BluOnX Development (land/horizontal) and Capstone LLC (vertical construction). Manages the complete vendor lifecycle: bid invitation → bid collection → comparison/scoring → contract award → milestone tracking.

## Tech Stack

- **Frontend:** React 18 + Vite + TypeScript + TailwindCSS v4 (in `frontend/`)
- **Backend:** FastAPI + Python (in `backend/` — not started yet)
- **Database:** PostgreSQL via Supabase (28 tables, schema in `database/`)
- **Storage:** Supabase Storage — 3 private buckets (vendor-documents, project-documents, bid-attachments)
- **Auth:** Supabase Auth — email/password only. No OAuth/Google Sign-In.
- **Monorepo:** Root package.json for workspace config, each directory is independent.

## Repository Structure

```
bluonx-capstone-automation/
├── frontend/          # React + Vite + TailwindCSS v4 app
├── backend/           # FastAPI (not started yet)
├── database/          # SQL schema, migrations, RLS policies
├── docs/              # Project documentation, handoff docs
├── .github/           # GitHub config
├── .env               # Root env vars (Supabase keys)
└── .env.example       # Template for env vars
```

## Core Business Rules

### Foundational Principle
**One Task = One Trade = One Award = One Contract.** Each task belongs to exactly one trade/scope category. The full chain: task → bid_package → bid_invitations → bid_submissions → award → contract → milestones.

### Three Task Bid Types
- **competitive** — full pipeline: auto-filter vendors → invitations → collection → comparison → award
- **direct_assign** — PM picks vendor directly. Backend creates a synthetic bid_submission (`is_direct_assign = TRUE`) so downstream chain (award → contract → milestones) works identically. No schema exceptions.
- **internal** — budget line item only, no vendor involvement. Cannot have bid_packages, awards, contracts, or milestones (enforced at application layer).

### Project Phases
- **Due Diligence** — investigation tasks (geotech, surveys, environmental)
- **Development** — construction tasks (grading, utilities, paving)
- Both phases use the same bid workflow and unified vendor pool. Phase is for task grouping/display only.

### Re-Award / Re-Bid
- Rebidding: `bid_packages.round_number` auto-increments. New round = new bid_package for same task.
- Re-award: Partial unique indexes allow one active award/contract per task while preserving history.

## Architecture Decisions

### Hybrid Data Access Pattern
- **Reads:** React → Supabase client directly (protected by RLS policies)
- **Writes:** React → FastAPI → Supabase using service_role key (bypasses RLS)
- **Vendor portal:** FastAPI only — vendors never access Supabase directly

### RLS Summary
- All 28 tables have RLS enabled
- `authenticated` role: SELECT on all tables, limited writes (users, trades, vendor_docs, vendor_flags, notifications)
- `anon` role: ZERO access (revoked on all tables)
- Helper functions: `private.is_active_user()`, `private.is_admin()` in private schema

### Storage Pattern ("Coat Check")
Database tables store file paths. Actual files live in Supabase Storage buckets.
- `vendor-documents`: `{vendor_id}/{document_type}/{filename}`
- `project-documents`: `{project_id}/{filename}`
- `bid-attachments`: `{bid_submission_id}/{filename}`

### Denormalized Fields
Several tables have denormalized FKs for query performance, each enforced by BEFORE INSERT/UPDATE triggers:
- `bid_submissions.vendor_id` → validated against `bid_invitations.vendor_id`
- `awards.vendor_id` + `awards.task_id` → validated against submission chain
- `contracts.vendor_id` + `contracts.task_id` → validated against `awards`
- `milestones.task_id` → validated against `contracts.task_id`

## Database Reference

Full schema: `database/bluonx_complete_schema_v2_2.sql` (28 tables, 49 indexes, 25 triggers, 11 functions)
RLS policies: `database/rls_policies.sql`
Storage policies: `database/storage_rls_policies.sql`

## Development Conventions

### Git
- Use Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
- Branch from main for features

### Code Style
- TypeScript strict mode
- Prefer named exports
- Use path aliases (`@/` maps to `src/`)

### User Roles
- `admin` — full access, manages vendors/trades/users
- `project_manager` — manages projects, tasks, bid process, awards
- All projects visible to all users for MVP (no project-level access restriction)

For detailed task breakdowns, acceptance criteria, and what each subtask involves, see `docs/CURRENT_PHASE_TASKS.md`.
For the complete 12-phase project plan, see `docs/PROJECT_PLAN.pdf`.
For detailed business rules and schema reasoning, see `docs/BluOnX_Context_Handoff.md`.
