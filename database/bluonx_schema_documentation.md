# BluOnX Bid Management & Vendor Coordination System — Database Schema Documentation

**Schema Version:** 4.1 (Bid Management v3.9 + Financial Automation Phases 1–2)  
**Last Updated:** November 18, 2026  
**Author:** Awais Anwer (Tkrupt)  
**Engine:** PostgreSQL via Supabase  
**Tables:** 53 (34 bid management + 19 financial) — see [Section 10](#10-financial-automation-v40--groups-914) for the financial module

> **v4.0 note.** Sections 1–9 describe the Bid Management & Vendor Coordination System. Some counts there date from v2.31 and predate later bid-system tables (milestone events, holidays, contract signers, reviews). Section 10 documents everything the Financial Automation module adds; it is authoritative for Groups 9–14.

---

## 1. Purpose & Scope

This document describes the complete database schema for the BluOnX Bid Management & Vendor Coordination System. The system manages the full vendor lifecycle for land development projects: vendor onboarding, bid invitations, competitive and direct-assign bid collection, weighted scoring, contract awards via DocuSign, and email-based milestone tracking.

The schema is designed for production use on Supabase (PostgreSQL) and follows these conventions:

- **All primary keys** are UUID, generated via `gen_random_uuid()` (pgcrypto extension).
- **Timestamps** use `TIMESTAMPTZ` (timezone-aware) throughout.
- **Soft deletes** via a nullable `deleted_at` column on core entities (users, vendors, projects, tasks). Records are never hard-deleted.
- **Status fields** use `CHECK` constraints, not PostgreSQL enums, for easier extension.
- **Foreign key delete rules** follow a deliberate strategy: `RESTRICT` on most FKs (audit-safe), `CASCADE` only on tightly-coupled children (line items, attachments, template items), and `SET NULL` on optional/advisory references (scored_by, resolved_by).
- **Denormalized fields** (e.g., `vendor_id` on bid_submissions, awards, contracts) exist for query performance and are enforced by database triggers to prevent mismatch.

---

## 2. Entity Lifecycle

The core data chain from top to bottom:

```
Project → Task → Bid Package → Bid Invitation → Bid Submission → Award → Contract → Milestones
```

A single task maps to exactly one trade, one award (active at a time), and one contract (active at a time). This one-to-one-to-one chain is enforced by partial unique indexes that allow historical records (declined awards, terminated contracts) while preventing duplicates on active records.

Three task types flow differently through this chain:

| Bid Type | Flow |
|---|---|
| `competitive` | Full pipeline — bid package, invitations to multiple vendors, scoring, award. |
| `direct_assign` | PM picks a vendor. Backend creates a synthetic bid_submission (`is_direct_assign = TRUE`) so the downstream chain (award → contract → milestones) works identically. |
| `internal` | Budget line item only. No bid package, award, contract, or milestones. Enforced at the application layer. |

**Revisions:** A submitted bid can later be revised at PM request (see `bid_revision_requests`). A revision is a *new* `bid_submissions` row that supersedes the original via `supersedes_submission_id`, so the chain above is preserved and the prior version is retained as immutable history. The original bid is never mutated in place.

---

## 3. Table Groups

### Group 1: Access Control (1 table)

#### `users`

Internal user profiles extending Supabase `auth.users`. Password hashing, email verification, session management, and last sign-in are fully managed by Supabase Auth — this table stores only app-specific profile data.

The `id` column is **not** auto-generated. It is set to match `auth.users.id` on insert via the `fn_handle_new_auth_user` trigger, which fires when a new user signs up through Supabase Auth.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID, PK | Matches `auth.users.id`. Set on insert, not auto-generated. |
| `email` | VARCHAR(255), UNIQUE | Mirrors auth.users.email. |
| `full_name` | VARCHAR(255) | Display name. |
| `role` | VARCHAR(20) | `admin` or `project_manager`. Base application access tier. Unchanged in v4.0; financial roles live in `user_roles`. |
| `is_active` | BOOLEAN | Active/inactive toggle. Checked by all RLS policies via `private.is_active_user()`. |
| `is_employee` | BOOLEAN, default TRUE | *v4.0.* FALSE = external / temporary field manager (may confirm work, never authorise payment). |
| `reports_to` | UUID, FK → users, SET NULL | *v4.0.* Manager one level above; receives second approvals. |
| `backup_approver_id` | UUID, FK → users, SET NULL | *v4.0.* Standing backup approver. |
| `approval_limit` | DECIMAL(15,2), nullable | *v4.0.* Single-approval limit; NULL = `financial_settings.default_field_approval_limit`. |
| `deleted_at` | TIMESTAMPTZ | Soft delete. NULL = active record. |

**Roles:** Admins can manage users, trades, and all system configuration. Project managers handle day-to-day operations (projects, tasks, bids, awards, milestones). Both roles have read access to all tables. Write restrictions are enforced by a combination of RLS policies (admin-only on users and trades) and FastAPI business logic (all other writes via service_role key).

---

### Group 2: Trade & Vendor Management (5 tables)

#### `trades`

Controlled lookup table of ~27 trade/scope categories (e.g., "Excavation & Grading," "Engineering," "Paving"). Each trade is tagged with a `phase` that determines which tasks can use it.

| Column | Type | Notes |
|---|---|---|
| `name` | VARCHAR(100), UNIQUE | Trade name. |
| `phase` | VARCHAR(20) | `due_diligence`, `development`, or `both`. Filters the trade dropdown when a PM creates a task. |
| `is_active` | BOOLEAN | Soft-toggle. Inactive trades hidden from dropdowns but preserved for historical data. |

**Why phase exists on both trades and tasks:** When a PM creates a task and selects `phase = due_diligence`, the trade dropdown shows only trades relevant to that phase. This prevents a PM from accidentally assigning a paving trade to a due-diligence task.

#### `vendors`

Company-level vendor records. This is one of the most field-heavy tables because it drives the intelligent vendor filtering algorithm (Phase 4) and pre-award validation (Phase 9).

| Column | Type | Notes |
|---|---|---|
| `company_name` | VARCHAR(255) | Vendor company name. |
| `address`, `city`, `state`, `zip_code` | TEXT/VARCHAR | Physical address. |
| `latitude`, `longitude` | DECIMAL(10,7) | Geocoded from address via Google Maps API. Used for distance filtering (75-mile radius). Populated once on create/update, not on every query. |
| `insurance_expiration_date` | DATE | Checked during bid invitation filtering and pre-award validation. |
| `insurance_coverage_amount` | DECIMAL(15,2) | Minimum coverage threshold for project eligibility. |
| `bonding_capacity` | DECIMAL(15,2) | Nullable — most trades don't require bonding. |
| `max_active_jobs` | INTEGER | Capacity ceiling. Nullable if no limit. |
| `current_active_jobs` | INTEGER | **Maintained by database triggers** on award acceptance (+1) and contract completion/termination (−1). Never set directly by the application. |
| `onboarding_status` | VARCHAR(20) | `pending` → `partial` → `complete`. Managed manually by PM, not auto-synced from documents. |
| `status` | VARCHAR(20) | `active`, `inactive`, or `suspended`. |
| `deleted_at` | TIMESTAMPTZ | Soft delete. |

**Vendor filtering criteria** (used during bid invitation flow): trade match via `vendor_trades`, distance from project ≤ 75 miles, valid insurance (not expired), adequate bonding, available capacity (`current_active_jobs < max_active_jobs`), and `onboarding_status = 'complete'`.

#### `vendor_contacts`

Multiple contacts per vendor company. Bid invitations are sent to individual contacts, not to the vendor entity directly.

| Column | Type | Notes |
|---|---|---|
| `vendor_id` | UUID, FK → vendors | Parent vendor. |
| `full_name` | VARCHAR(255) | Contact name. |
| `email` | VARCHAR(255) | Email used for bid invitations and milestone check-ins. |
| `is_primary` | BOOLEAN | Primary contact flag. |

#### `vendor_trades`

Many-to-many junction between vendors and trades. Powers the auto-filtering that matches vendors to tasks by trade specialty.

| Column | Type | Notes |
|---|---|---|
| `vendor_id` | UUID, FK → vendors | |
| `trade_id` | UUID, FK → trades | |
| UNIQUE | (vendor_id, trade_id) | Prevents duplicate assignments. |

**Index note:** Indexed on both `(vendor_id, trade_id)` via the unique constraint and separately on `trade_id` for reverse lookups ("which vendors do this trade?").

#### `vendor_documents`

Tracks the three required onboarding documents: W-9, Insurance Certificate, and Master Trade Agreement. Files are stored in Supabase Storage (`vendor-documents` bucket); this table holds metadata and the storage path reference.

| Column | Type | Notes |
|---|---|---|
| `vendor_id` | UUID, FK → vendors | |
| `document_type` | VARCHAR(30) | `w9`, `insurance_certificate`, or `master_trade_agreement`. |
| `file_path` | TEXT | Path in Supabase Storage: `{vendor_id}/{document_type}/{filename}`. |
| `expiration_date` | DATE | Applicable to insurance certificates. NULL for non-expiring docs. Monitored by n8n daily workflow (T-30 and T-7 day reminders). |
| `status` | VARCHAR(20) | `valid`, `expired`, or `pending_review`. |
| `uploaded_by` | UUID, FK → users | Admin/PM who uploaded the document. |

---

### Group 3: Project & Task Management (3 tables)

#### `projects`

Construction/land development projects. Each project contains multiple tasks, each associated with a single trade.

| Column | Type | Notes |
|---|---|---|
| `name` | VARCHAR(255) | Project name (e.g., "Sunset Hills Phase 2"). |
| `address`, `city`, `state`, `zip_code` | TEXT/VARCHAR | Project site location. |
| `latitude`, `longitude` | DECIMAL(10,7) | Geocoded from address. Used to calculate distance to vendor locations for the 75-mile filter. |
| `budget` | DECIMAL(15,2) | Total project budget. Task budget sum validation is enforced at the FastAPI layer, not at DB level. |
| `status` | VARCHAR(20) | `planning`, `active`, `on_hold`, `completed`, `cancelled`. |
|`archived_at`| TIMESTAMPTZ | When project was archived. NULL = not archived. Separate from deleted_at (soft delete). |
| `archived_by` | UUID, FK → users | User who archived the project. NULL when not archived. ON DELETE SET NULL. |
| `created_by` | UUID, FK → users | PM who created the project. |
| `deleted_at` | TIMESTAMPTZ | Soft delete. |

#### `project_documents`

Civil plans, landscape drawings, construction specs, and site photos uploaded at the project level. These are shared to vendors selectively via `bid_package_documents` — not all documents go to all bid packages.

| Column | Type | Notes |
|---|---|---|
| `project_id` | UUID, FK → projects | |
| `file_path` | TEXT | Path in Supabase Storage (`project-documents` bucket): `{project_id}/{filename}`. |
| `uploaded_by` | UUID, FK → users | |

#### `tasks`

The fundamental work unit. **One task = one trade = one award = one contract.** Separate tasks are created per trade to preserve clean vendor filtering and bid comparison.

| Column | Type | Notes |
|---|---|---|
| `project_id` | UUID, FK → projects | Parent project. |
| `trade_id` | UUID, FK → trades | The trade/scope for this task. Determines which vendors are eligible. |
| `phase` | VARCHAR(20) | `due_diligence` or `development`. Filters the trade dropdown for this task. |
| `bid_type` | VARCHAR(20) | `competitive` (full bid pipeline), `direct_assign` (PM picks vendor, synthetic submission created), or `internal` (budget line item only — no bids, awards, contracts, or milestones). |
| `budget_estimate` | DECIMAL(15,2) | Individual task budget. Used in pre-award budget variance check (±5%). |
| `sort_order` | INTEGER | Numeric ordering for chronological display and budgeting views. |
| `status` | VARCHAR(20) | `draft` → `bidding` → `evaluating` → `awarded` → `in_progress` → `completed`. Also `cancelled`. Tracks position in the full lifecycle. |
| `deleted_at` | TIMESTAMPTZ | Soft delete. |

---

### Group 4: Bid Lifecycle (11 tables)

#### `bid_templates`

A library of reusable bid formats that define how vendors submit pricing. Templates are **optionally** affiliated with a trade — trade-affiliated templates appear as suggestions when a PM creates a bid for that trade, while general-purpose templates (no trade) are available for any task. The PM always explicitly selects a template (or chooses "lump sum only") when creating a bid package; no template is ever auto-applied.

| Column | Type | Notes |
|---|---|---|
| `trade_id` | UUID, FK → trades, **nullable** | Optional trade affiliation. NULL = general-purpose template available to any task. When non-NULL, the template appears in the suggested list when bidding on tasks of that trade. |
| `name` | VARCHAR(255) | Template display name (e.g., "Sanitary Sewer", "Erosion Control"). |
| `is_lump_sum` | BOOLEAN | `TRUE` = vendor submits one total amount. `FALSE` = vendor fills predefined line items from `bid_template_items`. |

**Design rationale:** Templates were originally strictly linked to trades (`trade_id NOT NULL`). Client data revealed a mixed reality: some templates map cleanly to trades, others are task-specific or cross-trade. Making `trade_id` nullable preserves the trade-suggestion convenience for the majority of templates while allowing general-purpose templates to exist without forcing a fake trade relationship. The PM always makes the final template selection.

#### `bid_template_items`

Predefined line-item rows for structured bid templates. When a vendor opens the bid form for a trade that has a template with `is_lump_sum = FALSE`, the form is pre-populated with these rows and the vendor fills in quantities and prices.

| Column | Type | Notes |
|---|---|---|
| `bid_template_id` | UUID, FK → bid_templates | Parent template. CASCADE on delete. |
| `description` | VARCHAR(255) | Line item description (e.g., "8-inch PVC Water Pipe"). |
| `item_type` | VARCHAR(20) | `lump_sum` or `unit_price`. |
| `unit_of_measure` | VARCHAR(50) | e.g., "linear_feet", "each". Nullable for lump sum items. |
| `sort_order` | INTEGER | Display order on the bid form. |

#### `bid_packages`

Represents a single bidding round for a task. When a PM clicks "Start Bidding," a bid_package is created. If the round fails (no vendors respond, no suitable bids), the PM can rebid — creating a new bid_package with an incremented `round_number`. This preserves the full audit history of each bidding attempt.

| Column | Type | Notes |
|---|---|---|
| `task_id` | UUID, FK → tasks | |
| `bid_template_id` | UUID, FK → bid_templates, **nullable** | Template the PM selected for this bidding round. NULL = lump sum only (no structured line items). Records the point-in-time template choice — all vendors in this package use the same format. ON DELETE RESTRICT (never delete a template used in a bid package). |
| `round_number` | INTEGER | Auto-set by trigger: `MAX(round_number) + 1` for the task. |
| `deadline` | TIMESTAMPTZ | Bid submission deadline. Same for all vendors in the package. |
| `instructions` | TEXT, **nullable** | Optional PM-supplied bid-submission guidance shown to vendors in the portal and invitation email. Distinct from tasks.description (scope of work). May change between rebid rounds. Examples: "include mobilization as separate line item", "bid held firm for 30 days". |
| `desired_start_date` | DATE, **nullable** | PM-communicated target start date for this bidding round. NULL = flexible/none. Pre-fills the vendor's `proposed_start_date` in the form. When NULL, the timeline dimension is neutralized in scoring. |
| `status` | VARCHAR(20) | `open`, `closed`, `evaluating`, `cancelled`. |

**Application-layer rule:** Must not be created for tasks with `bid_type = 'internal'`.

**Template selection flow:** When creating a bid package, the system queries templates where `trade_id` matches the task's trade OR `trade_id IS NULL`, sorted with trade-matched templates first. If matches exist, the PM selects one from the list or chooses "No template — lump sum only." If no matches exist, the PM is informed and can either browse all templates or proceed with lump sum. The selected `bid_template_id` (or NULL) is stored on the bid package and determines the vendor bid form structure.

#### `bid_package_documents`

Junction table linking project documents to a specific bid package. When the PM sets up a bid package, they select which project documents to share with vendors (e.g., scope of work, relevant civil plans — not necessarily the entire document set).

| Column | Type | Notes |
|---|---|---|
| `bid_package_id` | UUID, FK → bid_packages | CASCADE on delete. |
| `project_document_id` | UUID, FK → project_documents | RESTRICT on delete. |
| UNIQUE | (bid_package_id, project_document_id) | Prevents duplicate attachments. |

#### `bid_invitations`

One invitation per vendor per bid package. Tracks the complete delivery and response lifecycle for each invited vendor.

| Column | Type | Notes |
|---|---|---|
| `bid_package_id` | UUID, FK → bid_packages | |
| `vendor_id` | UUID, FK → vendors | |
| `vendor_contact_id` | UUID, FK → vendor_contacts | Which contact received the invitation email. |
| `status` | VARCHAR(20) | `sent` → `opened` → `submitted` or `declined` or `expired` or `no_response`. The `submitted` status is auto-set by trigger when a bid_submission transitions to `submitted`. |
| `sent_at`, `opened_at`, `responded_at` | TIMESTAMPTZ | Delivery tracking timestamps. |
| UNIQUE | (bid_package_id, vendor_id) | One invitation per vendor per round. |

#### `magic_link_tokens`

Secure tokens for vendor bid portal authentication. Vendors access the bid form via a magic link emailed to them. The raw token is embedded in the email URL; only the SHA-256 hash is stored in the database.

| Column | Type | Notes |
|---|---|---|
| `bid_invitation_id` | UUID, FK → bid_invitations | CASCADE on delete. |
| `vendor_id` | UUID, FK → vendors | |
| `token_hash` | VARCHAR(255), UNIQUE | SHA-256 hash of the raw token. Raw token is never stored. |
| `expires_at` | TIMESTAMPTZ | Token expiry, set to the bid package deadline (not a fixed window). |
| `used_at` | TIMESTAMPTZ, nullable | Timestamp of first use. Audit detail. |
| `is_used` | BOOLEAN | Audit-only flag recording whether the token has been used. Not an access gate — validity is governed by expiry and revocation, not by `is_used`. |
| `revoked_at` | TIMESTAMPTZ, nullable | Hard-revocation timestamp (e.g., via "Resend Bid Link"). NULL = live. The validator rejects revoked tokens with HTTP 410. |
| `revoked_by` | UUID, FK → users, nullable | User who revoked the token. SET NULL if that user is later deleted. |
| `bid_revision_request_id` | UUID, FK → bid_revision_requests, nullable | **Discriminator.** NULL = initial bid-invitation token. Non-NULL = revision token; the validator branches on this to bypass the package-status check and to confirm the revision request is still pending. RESTRICT on delete. |
| `ip_address` | INET | Security logging. |

**Security model:** Token expiry is tied to the bid package deadline rather than an arbitrary window. After successful magic link validation, FastAPI issues a short-lived stateless JWT (2–4 hours) for the vendor's bid form session; if the JWT expires, the vendor clicks the magic link again and resumes from their saved draft. Revision tokens (`bid_revision_request_id` set) follow the same mechanics but branch the validator past the package-status check and instead validate against the revision request's `pending` state and per-request deadline.

#### `bid_submissions`

The vendor's actual bid response. Supports draft auto-save — a row transitions from `is_draft = TRUE` to `FALSE` on final submission. Originally constrained to one row per invitation via a column-level `UNIQUE(bid_invitation_id)`; as of the per-vendor bid revision feature this is enforced by a **partial unique index** (`WHERE is_superseded = FALSE AND is_draft = FALSE`), so exactly one *current* submission exists per invitation while superseded revisions and concurrent drafts coexist.

| Column | Type | Notes |
|---|---|---|
| `bid_invitation_id` | UUID, FK → bid_invitations | Parent invitation. One *current* (non-superseded, non-draft) submission per invitation, enforced by partial unique index. |
| `vendor_id` | UUID, FK → vendors | **Denormalized** for query performance. Enforced equal to `bid_invitations.vendor_id` by trigger. |
| `total_amount` | DECIMAL(15,2) | Sum of all line items. |
| `status` | VARCHAR(20) | `draft` → `submitted` → `under_review` → `accepted` or `rejected`. |
| `is_draft` | BOOLEAN | `TRUE` while vendor is editing. `FALSE` on final submission. |
| `is_direct_assign` | BOOLEAN | `TRUE` for synthetic submissions created via the direct_assign flow. Distinguishes from competitive bids in comparison and reporting views. |
| `submitted_at` | TIMESTAMPTZ | Set on final submission. |
| `vendor_notes` | TEXT | Free-text notes from the vendor accompanying the bid. |
| `proposed_start_date` | DATE | Vendor's committed start date. Pre-filled with `bid_packages.desired_start_date`; required on submit when a desired date exists. `proposed ≤ desired` = on time (feeds timeline scoring). |
| `supersedes_submission_id` | UUID, FK → bid_submissions, nullable | Chain pointer to the predecessor this row supersedes. NULL = original. RESTRICT on delete (audit chain). CHECK `chk_bid_submissions_supersedes_not_self` prevents self-reference. |
| `is_superseded` | BOOLEAN | `TRUE` when a newer revision exists. Trigger-maintained on revision finalize. |
| `revision_number` | INTEGER | Human-visible version. `1` = original; each revision = predecessor + 1 (trigger-enforced). CHECK ≥ 1. |

**Backend contract for `vendor_id`:** The vendor never inserts into this table directly. The API layer resolves `vendor_id` from the `bid_invitation` record when creating a submission. Client-supplied `vendor_id` is never trusted.

**Supersession & revisions:** A revision is a new row whose `supersedes_submission_id` points at the row being revised. The original is preserved unchanged as audit history; when the revision finalizes, triggers flip the predecessor's `is_superseded` to `TRUE` and increment `revision_number`. See §4.8 and `bid_revision_requests`.

#### `bid_line_items`

Pricing breakdown within a submission. Supports both lump sum and unit pricing in the same bid.

| Column | Type | Notes |
|---|---|---|
| `bid_submission_id` | UUID, FK → bid_submissions | CASCADE on delete. |
| `item_type` | VARCHAR(20) | `lump_sum` or `unit_price`. |
| `quantity` | DECIMAL(12,2) | Only for unit_price items. |
| `unit_of_measure` | VARCHAR(50) | e.g., "linear_feet", "each". Only for unit_price items. |
| `unit_price` | DECIMAL(15,2) | Only for unit_price items. |
| `lump_sum_amount` | DECIMAL(15,2) | Only for lump_sum items. |
| `line_total` | DECIMAL(15,2) | `qty × unit_price` for unit items, or `lump_sum_amount` for lump sum items. |

#### `bid_attachments`

Documents vendors upload alongside their bids (updated W-9, signed Scope of Work, supporting materials). Stored in Supabase Storage (`bid-attachments` bucket).

| Column | Type | Notes |
|---|---|---|
| `bid_submission_id` | UUID, FK → bid_submissions | CASCADE on delete. |
| `file_path` | TEXT | Path in storage: `{bid_submission_id}/{filename}`. |

#### `bid_scores`

Weighted scoring results per submission. One score record per submission (enforced by `UNIQUE(bid_submission_id)`).

| Column | Type | Notes |
|---|---|---|
| `bid_submission_id` | UUID, FK → bid_submissions, UNIQUE | CASCADE on delete. |
| `price_score` | DECIMAL(5,2) | 0–100 scale. Weight: 50%. |
| `compliance_score` | DECIMAL(5,2) | Weight: 5%. Insurance validity, required docs, onboarding status. |
| `performance_score` | DECIMAL(5,2) | Weight: 20%. Milestone on-time rate + vendor flag history. New vendors get a neutral baseline. |
| `capacity_score` | DECIMAL(5,2) | Weight: 10%. Available jobs vs. maximum. |
| `timeline_score` | DECIMAL(5,2) | Weight: 15%. Can start on required date, schedule fit. |
| `total_weighted_score` | DECIMAL(5,2) | Composite score on 0–100 scale. |
| `scoring_metadata` | JSONB | Snapshot of scoring breakdown and weights used at time of scoring. Immutable audit record. |
| `scored_by` | UUID, FK → users, nullable | `NULL` = system-generated score. Non-NULL = manually adjusted by a PM. |

#### `bid_revision_requests`

PM-initiated request asking a single vendor to revise their already-submitted bid after the round has closed, **without disturbing the rest of the package**. Lifecycle: `pending` → `submitted` | `declined` | `expired` | `cancelled`. One **pending** request per invitation at a time (partial unique index); terminal-state rows coexist as audit history.

| Column | Type | Notes |
|---|---|---|
| `bid_invitation_id` | UUID, FK → bid_invitations | RESTRICT on delete. The invitation whose submission is being revised. |
| `original_submission_id` | UUID, FK → bid_submissions | RESTRICT. Denormalized pointer to the submission being revised. The successor relationship itself lives on `bid_submissions.supersedes_submission_id`. |
| `pm_note` | TEXT, NOT NULL | Personalized note to the vendor. CHECK `length(pm_note) > 0`. |
| `revision_deadline` | TIMESTAMPTZ | Per-request deadline, independent of `bid_packages.deadline` (may outlive it). |
| `status` | VARCHAR(20) | `pending`, `submitted`, `declined`, `expired`, `cancelled`. |
| `decline_reason` | TEXT, nullable | Optional short note from the vendor on decline. |
| `requested_by` | UUID, FK → users | RESTRICT. PM who initiated the request. |
| `requested_at`, `responded_at` | TIMESTAMPTZ | Request and response timestamps. |

**How it ties together:** A revision token (a `magic_link_tokens` row with `bid_revision_request_id` set) is emailed to the vendor. The validator branches on that discriminator to bypass the package-status check and confirm the request is still pending. On submit, the vendor's new submission row points at the original via `supersedes_submission_id`; on finalize, triggers flip the predecessor's `is_superseded` flag and close this request to `submitted` (see §4.8).

**Application-layer rules:** PM-initiated only; capped at 2 revisions per vendor per package; blocked once an award is in place for the task.

---

### Group 5: Award & Contract (3 tables)

#### `awards`

The award decision record. One active award per task at any time, enforced by a **partial unique index** on `task_id WHERE status NOT IN ('declined_by_vendor', 'cancelled')`. This allows re-awarding to a different vendor if the first declines, while preserving the complete decision history.

| Column | Type | Notes |
|---|---|---|
| `task_id` | UUID, FK → tasks | Partial unique — one active award per task. |
| `bid_submission_id` | UUID, FK → bid_submissions | The winning bid. |
| `vendor_id` | UUID, FK → vendors | **Denormalized.** Enforced equal to `bid_submissions.vendor_id` by trigger. |
| `awarded_by` | UUID, FK → users | PM who made the decision. |
| `award_amount` | DECIMAL(15,2) | |
| `instructions` | TEXT, nullable | PM-supplied award / mobilization instructions, carried into the award letter email. |
| `has_override` | BOOLEAN | `TRUE` if PM overrode pre-award validation warnings. |
| `override_justification` | TEXT | Required when `has_override = TRUE`. Audit trail for compliance. |
| `validation_results` | JSONB | Snapshot of all pre-award validation checks at time of award (insurance, bonding, capacity, budget variance, start date feasibility). |
| `status` | VARCHAR(30) | `pending_acceptance` → `accepted` or `declined_by_vendor` or `cancelled`. |

**Task_id validation:** A trigger walks the full chain (bid_submission → bid_invitation → bid_package → task) to ensure `awards.task_id` matches the actual task in the bid chain. Prevents awarding a submission to the wrong task.

**Application-layer rule:** Must not be created for tasks with `bid_type = 'internal'`.

#### `contracts`

One contract per accepted award. Follows the same partial unique index pattern on `task_id WHERE status NOT IN ('terminated')`, allowing re-contracting if a contract is terminated.

| Column | Type | Notes |
|---|---|---|
| `award_id` | UUID, FK → awards, UNIQUE | One contract per award. |
| `vendor_id` | UUID, FK → vendors | **Denormalized.** Enforced equal to `awards.vendor_id` by trigger. |
| `task_id` | UUID, FK → tasks | **Denormalized.** Enforced equal to `awards.task_id` by trigger. |
| `contract_number` | VARCHAR(50), UNIQUE | Auto-generated by the application. |
| `contract_amount` | DECIMAL(15,2) | |
| `status` | VARCHAR(20) | `draft` → `sent_for_signature` → `executed` → `active` → `completed` or `terminated`. |
| `signed_at` | TIMESTAMPTZ | Set when DocuSign reports signature completion. |

**Application-layer rule:** Must not be created for tasks with `bid_type = 'internal'`.

#### `docusign_envelopes`

DocuSign e-signature envelope tracking, intentionally decoupled from the contracts table so the DocuSign integration can evolve independently.

| Column | Type | Notes |
|---|---|---|
| `contract_id` | UUID, FK → contracts | |
| `envelope_id` | VARCHAR(255), UNIQUE | DocuSign's envelope identifier. |
| `status` | VARCHAR(20) | `sent`, `delivered`, `signed`, `completed`, `declined`, `voided`. |
| `webhook_payload` | JSONB | Full DocuSign webhook payload stored for debugging and audit. |

---

### Group 6: Milestone Tracking (3 tables)

Milestone tracking uses a simple email-based approach: automated HTML emails with styled Yes/No buttons, no complex vendor portal. n8n handles outbound scheduling and email sending; FastAPI handles inbound vendor click responses.

#### `milestones`

Work milestones for awarded tasks. Typically 2–5 per task. Milestones are optional and PM-controlled.

| Column | Type | Notes |
|---|---|---|
| `task_id` | UUID, FK → tasks | **Denormalized.** Enforced equal to `contracts.task_id` by trigger. |
| `contract_id` | UUID, FK → contracts | Parent contract. |
| `name` | VARCHAR(255) | e.g., "Site Clearing Complete." |
| `start_date`, `end_date` | DATE | Planned dates. |
| `actual_start_date`, `actual_end_date` | DATE | Set when vendor confirms start/completion. Compared with planned dates for performance tracking. |
| `status` | VARCHAR(20) | `scheduled` → `started` → `on_track` → `completed`. Also `delayed` (set when vendor responds "No" to a check-in). |

**Automated check-in schedule** (handled by n8n):
- T−5 days before start: reminder to vendor + PM (only if milestone duration > 7 days)
- On start date: start confirmation request with Yes/No buttons
- T−5 days before end: progress check with Yes/No buttons (only if duration > 7 days)
- On end date: completion confirmation with Yes/No buttons

**Delay cycle:** When a vendor responds "No," status becomes `delayed` and the automated cycle pauses. PM must update the end date (resets to `on_track`, restarts cycle) or manually mark complete.

**Application-layer rule:** Must not be created for tasks with `bid_type = 'internal'`.

#### `milestone_responses`

Immutable audit log of every vendor email-link response. Records are append-only — never updated or deleted.

| Column | Type | Notes |
|---|---|---|
| `milestone_id` | UUID, FK → milestones | |
| `response_type` | VARCHAR(30) | `start_confirmation`, `progress_check`, or `completion_confirmation`. |
| `response_value` | VARCHAR(10) | `yes` or `no`. |
| `response_token_hash` | VARCHAR(255) | SHA-256 hash linking this response to the email that was sent. |
| `vendor_contact_id` | UUID, FK → vendor_contacts | Who clicked the link. |
| `responded_at` | TIMESTAMPTZ | Immutable timestamp of the response. |

#### `milestone_alerts`

Milestone-specific email tracking. References `email_log` for delivery details (no data duplication between the two tables). Milestone context lives here; delivery status lives in `email_log`.

| Column | Type | Notes |
|---|---|---|
| `milestone_id` | UUID, FK → milestones | |
| `email_log_id` | UUID, FK → email_log, nullable | Links to the master email audit record for delivery details. |
| `alert_type` | VARCHAR(30) | `starting_soon`, `start_check`, `progress_check`, `completion_check`, `delay_alert`, `no_response_alert`, `completion_notification`. |
| `recipient_type` | VARCHAR(20) | `vendor` or `pm`. |
| `response_token_hash` | VARCHAR(255) | Links to `milestone_responses` when the email contains clickable Yes/No buttons. |

---

### Group 7: Communication & Audit (3 tables)

#### `email_log`

Master audit log for **all** system emails — bid invitations, reminders, award notifications, decline letters, milestone alerts, and general communications. Single source of truth for email delivery status.

| Column | Type | Notes |
|---|---|---|
| `recipient_email` | VARCHAR(255) | |
| `recipient_type` | VARCHAR(20) | `vendor_contact` or `user`. |
| `email_type` | VARCHAR(30) | `bid_invitation`, `bid_reminder`, `award_notification`, `decline_notification`, `milestone_alert`, `general`. |
| `reference_type`, `reference_id` | VARCHAR(50), UUID | **Polymorphic reference.** `reference_type` = table name (e.g., "bid_invitations," "milestones"), `reference_id` = row UUID in that table. |
| `status` | VARCHAR(20) | `queued` → `sent` → `delivered` or `bounced` or `failed`. Updated via AWS SNS bounce notifications. |
| `opened_at`, `clicked_at` | TIMESTAMPTZ | Deferred to post-MVP. Columns exist but will not be populated initially. |
| `retry_count` | INTEGER | Incremented on failed send attempts. |

#### `vendor_flags`

PM-initiated flags for problematic vendors. Flags are surfaced as warnings during vendor selection for new bids.

| Column | Type | Notes |
|---|---|---|
| `vendor_id` | UUID, FK → vendors | |
| `flagged_by` | UUID, FK → users | PM who created the flag. |
| `reason` | VARCHAR(20) | `missed_deadline`, `poor_quality`, `unresponsive`, `other`. |
| `milestone_id` | UUID, FK → milestones, nullable | Optional link to the specific milestone that triggered the flag. |
| `is_resolved` | BOOLEAN | Resolution toggle. Only the flag creator or an admin can resolve. |
| `resolved_by` | UUID, FK → users, nullable | |

#### `notifications`

In-app notifications for the PM dashboard. User-scoped — each user can only see their own notifications (enforced by RLS).

| Column | Type | Notes |
|---|---|---|
| `user_id` | UUID, FK → users | Owner. CASCADE on delete. |
| `notification_type` | VARCHAR(30) | Categorization for filtering. |
| `reference_type`, `reference_id` | VARCHAR(50), UUID | Polymorphic link to the relevant entity (same pattern as email_log). |
| `is_read` | BOOLEAN | Users can mark their own notifications as read via direct Supabase update. |

---

## 4. Triggers & Business Logic

### 4.1 Automatic Timestamps

A `BEFORE UPDATE` trigger on every table with an `updated_at` column calls `fn_set_updated_at()`, which sets `updated_at = NOW()`. Applied to 16 tables.

### 4.2 Bid Package Round Number

`fn_set_bid_package_round_number()` — `BEFORE INSERT` on `bid_packages`. Automatically sets `round_number` to `MAX(round_number) + 1` for the task, ensuring sequential round tracking across rebids.

### 4.3 Bid Invitation Status Sync

`fn_sync_bid_invitation_on_submission()` — `AFTER INSERT OR UPDATE` on `bid_submissions`. When a submission transitions to `status = 'submitted'`, the parent `bid_invitation` is automatically updated to `status = 'submitted'` with `responded_at = NOW()`. Keeps dashboard counts accurate without relying on application code. The function uses `COALESCE(responded_at, NOW())` and an `OLD IS NULL` guard so that a later revision submission does not overwrite the original response timestamp.

### 4.4 Denormalized Field Consistency (4 triggers)

These triggers enforce that denormalized foreign keys match their source of truth. They exist because several tables carry a `vendor_id` or `task_id` directly for query performance, but the authoritative value lives further up the chain.

| Trigger | Validates |
|---|---|
| `trg_bid_submissions_enforce_vendor` | `bid_submissions.vendor_id` = `bid_invitations.vendor_id` |
| `trg_awards_enforce_consistency` | `awards.vendor_id` = `bid_submissions.vendor_id` AND `awards.task_id` = chain walk through bid_submission → bid_invitation → bid_package → task |
| `trg_contracts_enforce_consistency` | `contracts.vendor_id` = `awards.vendor_id` AND `contracts.task_id` = `awards.task_id` |
| `trg_milestones_enforce_task` | `milestones.task_id` = `contracts.task_id` |

All four use `BEFORE INSERT OR UPDATE OF <column>` — they only fire when the relevant column is touched, not on every update.

### 4.5 Vendor Capacity Management (2 triggers)

Two triggers maintain `vendors.current_active_jobs`:

**On award status change (`trg_awards_manage_vendor_capacity`):**
- Award accepted → increment (+1).
- Accepted award revoked (cancelled/declined after acceptance) → decrement (−1), but only if no contract for this award was already completed/terminated (prevents double-decrement).

**On contract status change (`trg_contracts_manage_vendor_capacity`):**
- Contract completed or terminated → decrement (−1).

Both use `GREATEST(..., 0)` as a safety net to prevent negative values.

### 4.6 Supabase Auth → Profile Creation

`fn_handle_new_auth_user()` — `AFTER INSERT` on `auth.users` (Supabase managed schema). Uses `SECURITY DEFINER` because it runs in the auth schema context but inserts into the public schema. Reads `full_name` and `role` from `raw_user_meta_data` passed during signup. *v4.0:* also reads optional `roles` (JSON array → `user_roles`, unknown values ignored) and `is_employee`; a failure in that part only logs a warning and never blocks a signup.

### 4.7 Vendor Onboarding Status Sync (Disabled)

The `fn_sync_vendor_onboarding_status` trigger is **intentionally disabled** (commented out in the schema). The decision was made to keep onboarding status as a manual PM-controlled field because real-world onboarding involves verification steps beyond document presence (e.g., calling the insurance carrier, reviewing W-9 for corrections). The trigger is preserved in the schema for potential future activation.

### 4.8 Per-Vendor Bid Revision Triggers (3 triggers)

These three triggers, all on `bid_submissions`, implement the supersession mechanics behind the per-vendor bid revision feature.

| Trigger (function) | Timing | Behavior |
|---|---|---|
| `trg_bid_submissions_enforce_supersession` (`fn_enforce_supersession_chain`) | `BEFORE INSERT OR UPDATE OF supersedes_submission_id, revision_number` | Validates the chain: predecessor exists, same `bid_invitation_id`, predecessor is finalized (not a draft), and `revision_number = predecessor.revision_number + 1`. |
| `trg_bid_submissions_flip_superseded` (`fn_flip_superseded_on_revision_finalize`) | `BEFORE UPDATE OF is_draft` | When a revision draft finalizes (`is_draft` TRUE → FALSE), flips the predecessor's `is_superseded` to `TRUE`. Running BEFORE means the predecessor leaves the partial unique index *before* the outer row is checked, so the index sees only one current row — no conflict. The `OF is_draft` column filter prevents the trigger from re-firing on the predecessor's own update (recursion termination). |
| `trg_bid_submissions_close_revision_request` (`fn_close_revision_request_on_finalize`) | `AFTER UPDATE` | On the same finalize, sets the matching `pending` `bid_revision_requests` row to `submitted` with `responded_at = NOW()`, in the same transaction. |

Together with the partial unique index `idx_bid_submissions_current_per_invitation`, these keep exactly one current submission per invitation while preserving every prior version as immutable history.

---

## 5. Indexing Strategy

57 custom indexes plus automatic indexes on all PK and UNIQUE columns. Key patterns:

- **Every FK column** has a dedicated index for JOIN performance.
- **Composite indexes** on common query patterns (e.g., `tasks(project_id, status)`, `bid_invitations(bid_package_id, status)`).
- **Partial indexes** on soft-deleted tables (`WHERE deleted_at IS NULL`) to exclude soft-deleted records from index scans. `idx_projects_archived` on `projects(archived_at) WHERE deleted_at IS NULL` — efficient filtering for archived vs. non-archived project views.
- **Conditional indexes** for high-frequency filtered queries: unread notifications (`WHERE is_read = FALSE`), unresolved vendor flags (`WHERE is_resolved = FALSE`), active magic link tokens (`WHERE is_used = FALSE AND revoked_at IS NULL`).
- **Four partial unique indexes** enforce single-active-record rules while preserving historical rows: one active award per task, one active contract per task, one *current* (non-superseded, non-draft) bid submission per invitation, and one *pending* revision request per invitation.
- **Revision feature indexes:** `bid_revision_requests` is indexed on `bid_invitation_id`, `status`, and `original_submission_id`; `magic_link_tokens` has a partial index on `bid_revision_request_id` (WHERE NOT NULL) for revision-token lookups.

---

## 6. Security Architecture

### Row Level Security (RLS)

RLS is enabled on all 29 tables. The access model:

| Access Pattern | Auth Method | RLS Behavior |
|---|---|---|
| Admin/PM dashboard reads | Supabase Auth JWT | `authenticated` role, filtered by `private.is_active_user()` |
| All write operations | FastAPI service_role key | Bypasses RLS entirely |
| Vendor bid portal | FastAPI service_role key | Bypasses RLS entirely |
| n8n automations | FastAPI service_role key | Bypasses RLS entirely |
| Anonymous / public | — | Zero access (no policies, privileges revoked) |

Two helper functions in a `private` schema (not exposed via PostgREST) use `SECURITY DEFINER` to check user status and admin role without circular RLS dependency.

**Admin-only write policies** exist on `users` (only admin can modify other users' accounts) and `trades` (controlled lookup, admin-managed). All other writes go through FastAPI.

**User-scoped table:** `notifications` — each user can only see and update their own notifications.

`bid_revision_requests` follows the standard bid-lifecycle pattern: authenticated read access via `private.is_active_user()`, all writes through FastAPI service_role, zero anon access.

### Storage Buckets

Three private Supabase Storage buckets with RLS policies:

| Bucket | Contents | Path Convention |
|---|---|---|
| `vendor-documents` | W-9, insurance certs, master trade agreements | `{vendor_id}/{document_type}/{filename}` |
| `project-documents` | Civil plans, drawings, specs, photos | `{project_id}/{filename}` |
| `bid-attachments` | Documents vendors upload with bids | `{bid_submission_id}/{filename}` |

Authenticated users have full CRUD. Anonymous has zero access. Vendor uploads are handled by FastAPI using the service_role key (bypasses RLS).

---

## 7. Key Design Decisions

| Decision | Rationale |
|---|---|
| **CHECK constraints over PostgreSQL enums** | Enums require `ALTER TYPE` to add values, which is painful in production migrations. CHECK constraints are modified with a simple `ALTER TABLE`. |
| **Soft deletes on core entities** | Compliance and audit requirements for a system handling legal contracts and financial decisions. Data is never lost. |
| **Denormalized FKs with trigger enforcement** | `vendor_id` appears on bid_submissions, awards, and contracts for query performance. Triggers enforce consistency rather than relying on application code, providing database-level data integrity. |
| **Partial unique indexes for re-award/re-contract** | Allows a task to be re-awarded if a vendor declines, while preserving the full history of all awards. Only one active/pending record per task at any time. |
| **Separate bid_packages table** | Supports rebidding (multiple rounds per task) with clean audit trail per round. |
| **Synthetic submissions for direct_assign** | Instead of making `bid_submission_id` nullable on awards (which would break the entire consistency trigger chain), direct_assign tasks create a minimal submission record. The entire downstream pipeline (award → contract → milestones) works identically for both competitive and direct-assign tasks. |
| **Per-vendor bid revision via supersession chain** | A PM can ask one vendor to revise after the round closes without reopening the package. Rather than mutating the original bid (which would destroy audit history), a revised submission is inserted pointing at the original via `supersedes_submission_id`. The original column-level `UNIQUE(bid_invitation_id)` was replaced by a partial unique index so that one *current* row exists per invitation while every prior version is retained. A per-request deadline (`bid_revision_requests.revision_deadline`) lets a single vendor's revision window outlive the package deadline. |
| **Manual onboarding status** | PM controls the `onboarding_status` field directly. Auto-sync from documents was considered but rejected because real-world verification involves steps beyond document presence. |
| **email_log + milestone_alerts (no duplication)** | `email_log` is the single source of truth for delivery status. `milestone_alerts` holds milestone-specific context (alert type, response token) and references `email_log` via FK. No data is duplicated between the two. |
| **Archive as separate column, not a status value** | "Archived" is a visibility concept (hide from default view), not a lifecycle stage. Using a separate archived_at column preserves the original project status, enabling clean unarchive without needing a previous_status field. Projects in any non-active status can be archived; active projects with in-flight tasks cannot. |

---

## 8. Schema Statistics

| Metric | Count |
|---|---|
| Tables | 29 |
| Custom indexes | 57 (53 regular + 4 partial unique) |
| Active triggers | 28 |
| Active functions | 13 |
| Disabled triggers | 1 (onboarding sync) |
| Disabled functions | 1 (onboarding sync) |
| CHECK constraints | 50 |
| Foreign keys (RESTRICT) | 44 |
| Foreign keys (CASCADE) | 7 |
| Foreign keys (SET NULL) | 6 |

---

## 9. Companion SQL Files

| File | Purpose |
|---|---|
| `bluonx_complete_schema.sql` | Complete schema (v4.0): tables, indexes, triggers, functions. Section 9 = financial module. Use for **fresh installs** only. |
| `rls_policies.sql` | All RLS policies, helper functions in `private` schema, anon role revocations. Depends on the schema file. Ends with the financial (v4.0) policies. |
| `storage_rls_policies.sql` | Storage bucket RLS policies. Buckets must be created via Supabase Dashboard before running. |
| `migrations/20261111_financial_phase1/` | **How existing databases (dev, production) get v4.0.** `000` pre-flight (read-only) · `001` idempotent change script · `002` self-checking verification (rolls back its own test data) · `099` rollback (dev only). See its `README.md` and `docs/financial/PHASE1_RUNBOOK.md`. |
| `seed_data/dev_seed_financial_phase1.sql` | Dev-only financial demo data (discovery examples). Refuses to run unless `financial_settings.environment = "development"`. |

---

## 10. Financial Automation (v4.0) — Groups 9–14

Added by migration `20261111_financial_phase1` (Phase 1 · Module 1 of the Financial Automation & Cash Flow Management project). The module carries every project dollar from budget and accepted bid through to approved payment, keeps the total budget **flat** by funding every overrun from contingency, and records every contingency movement in an immutable ledger.

### 10.1 Design rules

- **Additive to the bid system.** No existing table, column or row was dropped, renamed or rewritten. New columns on `users`, `projects`, `contracts` are nullable or have a constant default. `users.role` and `projects.budget` are untouched.
- **Writes through FastAPI only.** RLS on the 19 tables is read-only for `authenticated`; all writes use the service_role key, and every multi-row money movement is one stored procedure (supabase-py has no client transactions).
- **The authoritative-writer flag.** Guarded columns change only while the transaction-local setting `bluonx.financial_write = 'on'`, which only the financial procedures set (same pattern as `bluonx.milestone_transition`).
- **Contingency balance = the contingency line.** Each project has exactly one live `budget_lines` row of type `contingency`; its `budget_amount` is the live balance (it may go negative). Every change to it has a `contingency_ledger` row.
- **Error codes.** `PT403` (role / immutability), `PT404` (not found), `PT409` (state conflict, locked, closed, flat-budget), `PT422` (bad input) — mapped to HTTP by PostgREST like the rest of the system.

### 10.2 Entity relationships

```
projects ─┬─< budget_lines >── tasks (1:1, bid / internal activities)
          │      │  ├── awards / contracts (applied bid, lock)
          │      │  ├─< variance_lines (each with its own variance budget line)
          │      │  ├─< land_closings (phased takedowns)
          │      │  └─< payment_approvals ─── finance_handoffs ── email_log
          │      └── contingency line ─< contingency_buckets (initial + top-ups)
          │                          └─< contingency_ledger (append-only)
          ├─< escrows (premium line + repair line)
          ├─< property_taxes
          ├─< internal_invoices
          ├─< financial_alerts
          └─< cash_flow_entries >── accounting_periods (month close)
users ─┬─< user_roles  (many roles per user)
       └─< approval_delegations
budget_templates ─< budget_template_lines ─> budget_lines.template_line_id
financial_settings (key / value)          company_cash_items ─< cash_flow_entries
```

### 10.3 Changes to existing tables

| Table | New columns | Purpose |
|---|---|---|
| `users` | `is_employee`, `reports_to`, `backup_approver_id`, `approval_limit` | Approval routing, external field managers, limits |
| `projects` | `manager_id`, `field_manager_id`, `contingency_percent`, `budget_status` (`none`/`draft`/`baselined`, default `none`), `approved_budget_total`, `budget_baselined_at/by`, `contingency_at_groundbreaking`, `long_tail_reserve_amount`, `business_entity` (`bluonx`/`capstone`) | Assignments, budget lifecycle, guardrail inputs, owner views |
| `contracts` | `payment_terms_days`, `retainage_percent` | Numeric terms for cash flow; retainage (legacy `payment_terms` text untouched) |
| `email_log` | `email_type` CHECK widened (superset) | Financial email types (below) |
| `notifications` | none (no CHECK by design) | Financial types documented in the column comment |
| `auth.users` trigger | `fn_handle_new_auth_user()` extended | Reads optional `roles[]` and `is_employee` invite metadata; identical behaviour otherwise |

**New `email_type` values:** `payment_approval_request`, `payment_approved`, `payment_rejected`, `finance_handoff`, `finance_daily_summary`, `contingency_alert`, `contingency_escalation`, `contingency_top_up`, `long_tail_reserve_alert`, `bidding_checkpoint`, `property_tax_reminder`, `bond_renewal_reminder`, `owner_weekly_summary`.

**Financial `notification_type` vocabulary:** `contingency_health_alert`, `contingency_urgent_alert`, `long_tail_reserve_alert`, `bidding_checkpoint_alert`, `top_up_requested`, `top_up_decided`, `payment_approval_requested`, `payment_approved`, `payment_rejected`, `variance_pending_approval`, `property_tax_due`, `bond_renewal_due`, `month_closed`.

### 10.4 Group 9 — Budget Structure (4 tables)

#### `budget_templates`
Standard budget layouts. `is_default` (at most one active default — partial unique index), `is_active`, soft delete. Template edits never change existing budgets.

#### `budget_template_lines`
Ordered template rows: `line_type`, `line_subtype`, `name`, `section_name`, `trade_id`, `task_template_id` (FK only where `task_templates` exists), `sort_order`, default amount / payment terms / cash bucket. CASCADE from template.

#### `budget_lines` — the core table
| Column | Type | Notes |
|---|---|---|
| `project_id` | UUID FK | Immutable after insert. |
| `task_id` | UUID FK, nullable | Unique among non-deleted lines. Only for `bid_activity` (competitive / direct_assign task) and `internal_tm` (internal task) — trigger-enforced. |
| `parent_line_id` | UUID FK self | Variance → activity; groups e.g. engineering T&M under a heading. |
| `line_type` | CHECK | `land`, `bid_activity`, `internal_tm`, `permit`, `impact_fee`, `soft_cost`, `contingency`, `variance`, `long_tail`. Immutable. |
| `line_subtype` | CHECK, nullable | `land_purchase`, `earnest_money`, `due_diligence`, `engineering`, `escrow_bond_premium`, `escrow_repairs`, `property_tax`, `other`. |
| `original_estimate` | DECIMAL(15,2) | Frozen at baseline (A21). |
| `budget_amount` | DECIMAL(15,2) | ≥ 0 except contingency. After baseline: procedures only. |
| `committed_amount` | DECIMAL(15,2) | Award amount once applied. |
| `pre_award_budget_amount` | DECIMAL(15,2) | Restored by a bid reversal. |
| `award_id`, `contract_id` | FK | Applied award; contract that locked the line. |
| `is_locked`, `locked_at/by`, `lock_reason` | | Locked on contract execution. |
| `anticipated_start_date`, `anticipated_end_date` | DATE | end ≥ start. Cash-flow inputs. |
| `payment_terms_days` | INT, default 30 | 0–365. |
| `cash_bucket` | CHECK | `land`, `vertical_construction`, `overhead`. |
| `approval_state` | CHECK | `not_requested`, `pending`, `field_approved`, `manager_approved`, `sent_to_finance`, `rejected`. |
| `is_payment_exempt` | BOOLEAN | Must be TRUE for land and contingency. |
| `deleted_at` | | Soft delete (lines not needed are removed). |

Partial unique indexes: one live line per task; one live contingency line per project.

#### `land_closings`
Phased takedowns under a land-purchase line: `closing_sequence` (unique per line), `acres`, `amount`, `planned_closing_date`, `actual_closing_date`, `status` (`planned`/`closed`/`cancelled`).

### 10.5 Group 10 — Contingency (3 tables)

#### `contingency_buckets`
Every funding source: `bucket_kind` `initial` (one per project, created at baseline) or `top_up`; `requested_amount`, `approved_amount`, `status` (`pending`/`approved`/`rejected`/`cancelled`), `reason`, requester, decider. Only pending top-ups may be inserted directly; decisions only via `fn_approve_contingency_top_up`; decided buckets are frozen.

#### `contingency_ledger` (append-only)
`entry_no` (identity — order by it), `movement_type` (`initial_funding`, `bid_overrun`, `bid_savings`, `bid_reversal`, `variance_created`, `variance_adjusted`, `variance_cancelled`, `top_up`, `invoice_overage`), signed `amount` (+ into contingency), `balance_before`, `balance_after` (CHECK after = before + amount), source line, variance, award, bucket, `actor_user_id`, `reason`. UPDATE / DELETE / TRUNCATE raise `PT403`. Gaps in `entry_no` are normal (rolled-back transactions consume numbers).

#### `variance_lines`
Metadata for a field variance; the money lives on its own `budget_lines` row (`line_type = variance`, 1:1). `parent_budget_line_id`, `trade_id`, `vendor_id`, `description`, `estimated_amount` (first estimate, history), `status` (`draft`, `pending_approval`, `approved`, `rejected`, `cancelled`). CHECK: `approved_by <> created_by`. Created / adjusted / cancelled only by procedures; approved and cancelled variances are frozen.

### 10.6 Group 11 — Payments & Finance Hand-off (3 tables)

#### `internal_invoices`
Incoming invoices for internal T&M lines: payee (vendor or free text), number, date, amount, file in the `finance-documents` bucket, `status` (`received`, `categorised`, `in_approval`, `approved`, `rejected`, `cancelled`). Must be categorised to a line beyond `received`. **Finance-restricted read.**

#### `payment_approvals`
One request per payment: `payment_kind` (`full`, `progress`, `retainage_release`), `progress_percent`, `retainage_amount`, `status` (`pending` → `field_approved` → `awaiting_manager` / `awaiting_executive` → `approved` → `sent_to_finance`; or `rejected` / `cancelled`), field / manager / executive approvers and timestamps, `routed_to_user_id`, `expected_payment_date`. CHECK two-person rule: manager and executive approver ≠ field approver.

#### `finance_handoffs`
One per finally-approved payment: unique `po_number`, `amount`, JSON `payload` (trade, amount, project, activity, date, approvers), generated PDF path, `email_log_id` (delivery proof), `status` (`pending`/`sent`/`delivered`/`failed`). **Finance-restricted read.**

### 10.7 Group 12 — Long-tail Items (2 tables)

#### `escrows`
`beneficiary` (`city`/`county`/`hoa`/`other`), `covered_areas TEXT[]` (several areas per escrow), `security_form` (`cash`/`bond`), holder, `secured_amount` (value of the works), premium, bond number / expiry, `status` (`planned` → `posted` → `works_built` → `inspection` → `corrections` → `signed_off` → `released`, or `cancelled`), `premium_line_id` and `repair_line_id` (the two escrow costs), document path.

#### `property_taxes`
Per project / `tax_year` / `jurisdiction` / `installment_number` (unique): `due_date`, `estimate_basis` (`prior_year_actual`/`assessed_value`/`manual`), `estimated_amount`, `actual_amount`, `sold_portion_percent`, `status`.

### 10.8 Group 13 — Cash Flow (3 tables)

#### `accounting_periods`
Company-wide months (`period_month` = first of month, unique), `status` `open`/`closed`. Closed only via `fn_close_accounting_month` (finance / executive); never reopened or deleted.

#### `company_cash_items`
Overhead, deposits, closings, vertical construction entered manually or by CSV (`direction` in/out, `cash_bucket`, `business_entity`, `period_month`, `amount`). **Finance-restricted read.**

#### `cash_flow_entries`
Monthly schedule rows with exactly-one-or-more source FKs (budget line, land closing, escrow, payment approval, company item), `direction`, `cash_bucket` (`land`, `vertical_construction`, `overhead`, `deposits`, `closings`), `amount`, `entry_kind` (`forecast`/`expected`/`actual`). Rows in a closed month cannot be inserted, changed or deleted. **Finance-restricted read.**

### 10.9 Group 14 — Settings, Alerts & Roles (4 tables)

#### `financial_settings`
Key / JSON value. Seeded defaults (never overwritten on re-run): `default_contingency_percent` 15, `contingency_min_percent` 15, `contingency_max_percent` 20, `bidding_target_contingency_percent` 10, `bidding_escalation_percent` 5, `default_payment_terms_days` 30, `default_field_approval_limit` 5000, `executive_approval_threshold` null, `contingency_near_zero_percent` 5, `alert_recipients`, `land_team_emails`, `finance_emails`, `sales_emails`, `po_number_format`, `environment` ("unset" — set to "development" on dev), `schema_version`.

#### `financial_alerts`
`alert_type` (`contingency_health`, `contingency_near_zero`, `contingency_negative`, `long_tail_reserve`, `bidding_checkpoint`), `severity`, `status`, snapshot (`contingency_left_pct`, `work_left_pct`, `contingency_remaining`, `reserve_required`), recorded `decision` (`proceed`/`hold`) with mandatory reason. One open alert per project and type.

#### `user_roles`
`role` ∈ `admin`, `project_manager`, `field_manager`, `executive`, `finance`; partial unique (user, role) among un-revoked rows; revoke = `revoked_at`. Base role mirrors `users.role` automatically.

#### `approval_delegations`
Temporary hand-over of a manager's approvals (`starts_at` < `ends_at`, delegator ≠ delegate, revocable).

### 10.10 Stored procedures (service_role only)

| Procedure | Effect | Errors |
|---|---|---|
| `fn_baseline_project_budget(project, actor)` | draft → baselined; freezes `original_estimate`; `approved_budget_total` = sum of lines; initial bucket + `initial_funding` ledger row | PT404, PT409 |
| `fn_apply_bid_to_line(line, award, amount, actor)` | Line budget = committed = award; difference out of / into contingency (`bid_overrun` / `bid_savings`). Idempotent. Draft budgets: line only. | PT404, PT409 (locked, other award, on hold), PT422 |
| `fn_reverse_bid_on_line(line, award, actor, reason)` | Restores pre-award amount, clears award / commitment / lock, `bid_reversal` ledger row | PT404, PT409 |
| `fn_lock_budget_line(line, contract, actor)` | Locks on contract execution; defaults dates from the contract. Idempotent. | PT404, PT409, PT422 |
| `fn_create_variance(parent, description, amount, actor, trade?, vendor?, start?, end?)` | Variance line + metadata (`pending_approval`); contingency −amount (`variance_created`) | PT404, PT409 (not baselined / on hold), PT422 |
| `fn_adjust_variance(variance, new_amount, actor, reason)` | Δ back to / out of contingency (`variance_adjusted`); 0 = cancel (`variance_cancelled`) | PT404, PT409 (approved / cancelled), PT422 |
| `fn_request_contingency_top_up(project, amount, reason, actor)` | Pending top-up bucket | PT404, PT409, PT422 |
| `fn_approve_contingency_top_up(bucket, approver, approve, amount?, note?)` | **Executive only.** Approve: contingency +amount, approved total +amount, `top_up` ledger row. Reject: decision only. | PT403, PT404, PT409, PT422 |
| `fn_close_accounting_month(month, actor, notes?)` | **Finance / executive only.** Closes the month for good. | PT403, PT409, PT422 |

Internal helpers (schema `private`, not exposed): `fin_move_contingency`, `fin_lock_project`, `fin_write_authorized`, `user_has_role`, `has_any_role`.

Lock order in every procedure: **project → bucket → lines** (prevents deadlocks).

### 10.11 Triggers

| Trigger | Table | Rule |
|---|---|---|
| `trg_<table>_updated_at` (18) | all financial tables except the ledger | `fn_set_updated_at()` |
| `trg_contingency_ledger_immutable`, `trg_contingency_ledger_no_truncate` | `contingency_ledger` | append-only (PT403) |
| `trg_budget_lines_guard` | `budget_lines` | identity columns immutable; task / project / type consistency; locked lines frozen; after baseline, amounts change only via procedures and new lines start at $0 |
| `trg_budget_lines_flat_total` (constraint trigger, **DEFERRABLE INITIALLY DEFERRED**) | `budget_lines` | at COMMIT: sum of live lines = `approved_budget_total` once baselined (PT409). Code must not `SET CONSTRAINTS … IMMEDIATE` around procedures. |
| `trg_projects_guard_budget_total` | `projects` (only on the new budget columns) | approved total / baseline only via procedures; `none ↔ draft` free |
| `trg_contingency_buckets_guard` | `contingency_buckets` | only pending top-ups inserted directly; decisions via procedure; decided rows frozen |
| `trg_variance_lines_guard` | `variance_lines` | create / cancel via procedures; approved & cancelled frozen; history columns immutable |
| `trg_accounting_periods_guard` | `accounting_periods` | close via procedure; never reopen / delete a closed month |
| `trg_cash_flow_entries_closed_period` | `cash_flow_entries` | no insert / update / delete in a closed month |
| `trg_users_sync_base_role` | `users` | mirrors `users.role` into `user_roles` on insert / role change |

### 10.12 Security

- RLS enabled on all 19 tables; `anon` has no privileges; `authenticated` has SELECT only.
- **Any active user** reads: budget templates / lines, land closings, contingency buckets / ledger, variances, payment approvals, escrows, property taxes, accounting periods, settings, alerts, user roles, delegations.
- **Finance / executive / admin** read: `internal_invoices`, `finance_handoffs`, `company_cash_items`, `cash_flow_entries` (via `private.has_any_role`).
- Procedures re-check roles in the database (executive top-up, finance month close) as defence in depth; FastAPI remains the primary gate.
- Storage: the private `finance-documents` bucket is created in a later phase (invoice upload); only the path columns exist now.

### 10.13 Statistics added by v4.0

| Metric | Added |
|---|---|
| Tables | 19 |
| Indexes (incl. unique / partial) | 63 |
| Triggers | 28 |
| Functions (public + private) | 23 |
| RLS policies | 19 |
| CHECK constraints | 114 |
| Foreign keys | 83 |

---

## 11. Financial Automation (v4.1) — Phase 2: project budget structure

Added by migration `20261118_financial_phase2`. No new tables: Phase 2 adds the procedures, trigger, views and seed data that turn the Phase 1 tables into a working budget.

### 11.1 Budget lifecycle

| `projects.budget_status` | Meaning | How it changes |
|---|---|---|
| `none` | No financial budget (all existing projects) | — |
| `draft` | Lines freely editable by admins; import allowed | `fn_create_project_budget` |
| `baselined` | Estimates frozen; total flat; amounts move only through procedures | `fn_baseline_project_budget` (Phase 1) |

### 11.2 Procedures (service_role only)

| Procedure | Effect | Errors |
|---|---|---|
| `fn_create_project_budget(project, actor, template?, contingency_pct?)` | none → draft. One line per non-activity template row; **one line per live task** at its matching template slot (name, then trade; else after the last slot of that type). Contingency = pct × base (base excludes land and contingency). | PT409 budget exists / no template, PT422 |
| `fn_reorder_budget_lines(project, ids[], actor)` | sort_order = 10, 20, 30 … for every live line (must list each exactly once) | PT422 |
| `fn_remove_budget_line(line, actor)` | Soft-deletes a non-task line. Never the contingency line; task lines go with their task; land lines with open closings and open escrow cost lines are kept; after baseline only an empty $0 line | PT409, PT422 |
| `fn_apply_budget_import(project, rows jsonb, actor)` | Draft only. Rows with `line_id` update amount / dates / terms / bucket / heading; rows without add a non-activity line after the last line of its heading | PT409 not draft, PT422 |
| `fn_categorise_internal_invoice(invoice, line, actor)` | Invoice → internal T&M line; allowance = line budget − other categorised invoices; on a baselined budget the overage becomes a variance line (contingency −overage, ledger `invoice_overage`); creates `pending` payment approval request(s); invoice → `in_approval` | PT404, PT409 (on hold / already in approval / no budget), PT422 (wrong line type) |

Helpers (private): `fin_line_type_for_bid_type`, `fin_line_invoiced` (SECURITY DEFINER sum), `fin_line_is_empty`, `fin_next_activity_position`.

### 11.3 Task ↔ budget line sync — `trg_tasks_sync_budget_line`

`AFTER INSERT OR UPDATE OF name, budget_estimate, bid_type, deleted_at ON tasks`. No-op when the project has no budget.

| Task change | Budget line |
|---|---|
| created / restored | new line (draft: task estimate; baselined: $0), after the last line of the same type |
| renamed | line name follows |
| estimate changed | line amount follows while draft and the line was not edited |
| bid_type changed | line replaced with the right type (bid_activity ↔ internal_tm); after baseline only if the line is empty, else PT409 |
| soft-deleted | line soft-deleted; after baseline only if empty, else PT409 (the tasks API returns it as a 409) |

### 11.4 Views (security_invoker)

- **`v_budget_lines`**: one row per live line with task / trade / award / vendor / contract / variance context and NUMERIC totals:
  - `variance_total`, `invoiced`;
  - `committed`: award for bid lines, categorised invoices for T&M lines, the amount for an approved variance;
  - `spent`: payments approved or sent to finance;
  - `pending_approval`, `remaining` (budget − spent), `bid_vs_estimate`, `has_dates`, `closings_total`, `closings_count`.
- **`v_project_budget_summary`**: per project:
  - totals: `total_budget`, `committed`, `spent`, `remaining`, `pending_approval`;
  - contingency: `contingency_now`, `contingency_at_baseline`;
  - `land_total`, `contingency_base`, `lines_missing_dates`, `tasks_without_line`;
  - `flat_ok`: lines total = approved total.

### 11.5 Integration with the bid system (application code)

| Existing event | Hook (post-commit, best-effort, idempotent, never raises) |
|---|---|
| `award_service.create_award` after `fn_create_award` | `fn_apply_bid_to_line` |
| DocuSign `completed` | `fn_lock_budget_line` (applies the award first if it never reached the line) |
| DocuSign `declined` / `voided` | `fn_reverse_bid_on_line` |
| Admin "Sync awards" (`POST /projects/{id}/budget/sync-awards`) | Repairs any missed hook and back-fills awards that existed before the budget |

### 11.6 Storage

`finance-documents`: private, 25 MB, and no storage policies for `authenticated`. Invoice files are reachable only through FastAPI and 1-hour signed URLs.

### 11.7 Default standard template

Land (land purchase, earnest money, due diligence) → Soft costs (engineering, permits, impact fees, other soft costs) → Site work / Utilities / Roads activity slots (clearing, grading, sanitary sewer, water + storm, paving) → Internal (attorney) → Contingency → Long-tail (escrow bond premium, escrow repairs, property tax). Created only when no default template exists, and edited in **Settings → Budget Template**.
