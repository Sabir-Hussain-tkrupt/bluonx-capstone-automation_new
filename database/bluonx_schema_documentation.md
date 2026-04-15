# BluOnX Bid Management & Vendor Coordination System — Database Schema Documentation

**Schema Version:** 2.2  
**Last Updated:** February 23, 2026  
**Author:** Awais Anwer (Tkrupt)  
**Engine:** PostgreSQL via Supabase  
**Tables:** 28 | **Triggers:** 25 (24 active + 1 disabled) | **Functions:** 11 (10 active + 1 disabled)

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
| `role` | VARCHAR(20) | `admin` or `project_manager`. Controls RLS access. |
| `is_active` | BOOLEAN | Active/inactive toggle. Checked by all RLS policies via `private.is_active_user()`. |
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

### Group 4: Bid Lifecycle (10 tables)

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
| `expires_at` | TIMESTAMPTZ | Token expiry (7 days). |
| `is_used` | BOOLEAN | First-response-wins pattern. After first use, subsequent clicks show a friendly "already responded" page. |
| `ip_address` | INET | Security logging. |

**Security model:** Tokens are time-limited (7 days) with first-response-wins logic, not single-use. This handles email scanner pre-fetches and accidental double-clicks gracefully. After successful magic link validation, FastAPI issues a short-lived stateless JWT (2–4 hours) for the vendor's bid form session.

#### `bid_submissions`

The vendor's actual bid response. One submission per invitation (enforced by `UNIQUE(bid_invitation_id)`). Supports draft auto-save — the same row transitions from `is_draft = TRUE` to `FALSE` on final submission.

| Column | Type | Notes |
|---|---|---|
| `bid_invitation_id` | UUID, FK → bid_invitations, UNIQUE | One submission per invitation. |
| `vendor_id` | UUID, FK → vendors | **Denormalized** for query performance. Enforced equal to `bid_invitations.vendor_id` by trigger. |
| `total_amount` | DECIMAL(15,2) | Sum of all line items. |
| `status` | VARCHAR(20) | `draft` → `submitted` → `under_review` → `accepted` or `rejected`. |
| `is_draft` | BOOLEAN | `TRUE` while vendor is editing. `FALSE` on final submission. |
| `is_direct_assign` | BOOLEAN | `TRUE` for synthetic submissions created via the direct_assign flow. Distinguishes from competitive bids in comparison and reporting views. |

**Backend contract for `vendor_id`:** The vendor never inserts into this table directly. The API layer resolves `vendor_id` from the `bid_invitation` record when creating a submission. Client-supplied `vendor_id` is never trusted.

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

A `BEFORE UPDATE` trigger on every table with an `updated_at` column calls `fn_set_updated_at()`, which sets `updated_at = NOW()`. Applied to 15 tables.

### 4.2 Bid Package Round Number

`fn_set_bid_package_round_number()` — `BEFORE INSERT` on `bid_packages`. Automatically sets `round_number` to `MAX(round_number) + 1` for the task, ensuring sequential round tracking across rebids.

### 4.3 Bid Invitation Status Sync

`fn_sync_bid_invitation_on_submission()` — `AFTER INSERT OR UPDATE` on `bid_submissions`. When a submission transitions to `status = 'submitted'`, the parent `bid_invitation` is automatically updated to `status = 'submitted'` with `responded_at = NOW()`. Keeps dashboard counts accurate without relying on application code.

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

`fn_handle_new_auth_user()` — `AFTER INSERT` on `auth.users` (Supabase managed schema). Uses `SECURITY DEFINER` because it runs in the auth schema context but inserts into the public schema. Reads `full_name` and `role` from `raw_user_meta_data` passed during signup.

### 4.7 Vendor Onboarding Status Sync (Disabled)

The `fn_sync_vendor_onboarding_status` trigger is **intentionally disabled** (commented out in the schema). The decision was made to keep onboarding status as a manual PM-controlled field because real-world onboarding involves verification steps beyond document presence (e.g., calling the insurance carrier, reviewing W-9 for corrections). The trigger is preserved in the schema for potential future activation.

---

## 5. Indexing Strategy

50 custom indexes plus automatic indexes on all PK and UNIQUE columns. Key patterns:

- **Every FK column** has a dedicated index for JOIN performance.
- **Composite indexes** on common query patterns (e.g., `tasks(project_id, status)`, `bid_invitations(bid_package_id, status)`).
- **Partial indexes** on soft-deleted tables (`WHERE deleted_at IS NULL`) to exclude soft-deleted records from index scans. idx_projects_archived on projects(archived_at) WHERE deleted_at IS NULL — efficient filtering for archived vs. non-archived project views.
- **Conditional indexes** for high-frequency filtered queries: unread notifications (`WHERE is_read = FALSE`), unresolved vendor flags (`WHERE is_resolved = FALSE`), active magic link tokens (`WHERE is_used = FALSE`).
- **Two partial unique indexes** enforce the "one active record per task" rule on `awards` and `contracts` while preserving historical records.

---

## 6. Security Architecture

### Row Level Security (RLS)

RLS is enabled on all 28 tables. The access model:

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
| **Manual onboarding status** | PM controls the `onboarding_status` field directly. Auto-sync from documents was considered but rejected because real-world verification involves steps beyond document presence. |
| **email_log + milestone_alerts (no duplication)** | `email_log` is the single source of truth for delivery status. `milestone_alerts` holds milestone-specific context (alert type, response token) and references `email_log` via FK. No data is duplicated between the two. |
| **Archive as separate column, not a status value** | "Archived" is a visibility concept (hide from default view), not a lifecycle stage. Using a separate archived_at column preserves the original project status, enabling clean unarchive without needing a previous_status field. Projects in any non-active status can be archived; active projects with in-flight tasks cannot. |

---

## 8. Schema Statistics

| Metric | Count |
|---|---|
| Tables | 28 |
| Custom indexes | 50 (47 regular + 2 partial unique) |
| Active triggers | 24 |
| Active functions | 10 |
| Disabled triggers | 1 (onboarding sync) |
| Disabled functions | 1 (onboarding sync) |
| CHECK constraints | 46 |
| Foreign keys (RESTRICT) | 39 |
| Foreign keys (CASCADE) | 8 |
| Foreign keys (SET NULL) | 6 |

---

## 9. Companion SQL Files

| File | Purpose |
|---|---|
| `bluonx_complete_schema_v2_2.sql` | Complete schema: tables, indexes, triggers, functions. |
| `rls_policies.sql` | All RLS policies, helper functions in `private` schema, anon role revocations. Depends on the schema file. |
| `storage_rls_policies.sql` | Storage bucket RLS policies. Buckets must be created via Supabase Dashboard before running. |
