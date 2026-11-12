# Phase 1 · Module 1 — Financial Data Foundation, Roles & Schema Extension

**Implementation plan (for approval before any SQL is written)**

| | |
|---|---|
| Project | Financial Automation & Cash Flow Management System (BluOnX / Capstone) |
| Source documents | Project Plan v1.3 (Nov 3, 2026) · Financial workflow map (A1–A24) · existing master schema v3.9 |
| Scope of this plan | Phase 1, Module 1, Tasks 1.1 – 1.7 (52 h) |
| Hard constraints | Database work only, **no backend/frontend code changes**. Runs against a **live production database**: additive only, nothing existing is dropped, renamed, rewritten or deleted. |
| Status | **Approved Nov 11, 2026 (defaults D1–D7) — implemented.** See `database/migrations/20261111_financial_phase1/` and `PHASE1_RUNBOOK.md`. Changes during implementation: a 9th procedure, `fn_request_contingency_top_up` (convenience writer); `contingency_ledger.entry_no` for deterministic ordering. |

---

## 0. TL;DR

- One **idempotent, transactional migration script** adds 19 new financial tables, a handful of **nullable / defaulted columns** on `users`, `projects` and `contracts`, the financial **stored procedures**, the **guard triggers** (immutable ledger, flat budget, locked lines, closed months) and **RLS read policies**.
- Nothing in the existing Bid Management System changes behaviour. `users.role` keeps its current `admin | project_manager` values, so the current FastAPI models and React types (which hard-code those two values) keep working. The new roles (`field_manager`, `executive`, `finance`) live in a new `user_roles` table, which also lets one person hold several roles.
- Delivered as new files under `database/migrations/` plus updates to the master files `bluonx_complete_schema.sql`, `rls_policies.sql` and `bluonx_schema_documentation.md`, and a dev-only seed file.
- You apply it in the Supabase SQL editor: **dev first → verify → re-run to prove idempotency → back up prod → apply to prod → verify**. Section 9 gives the runbook.
- Section 10 lists **7 decisions** for you to confirm. Each has a recommended default, and I will use those defaults unless you say otherwise.

---

## 1. What I analysed

### 1.1 Existing system (Phase 1, Bid Management & Vendor Coordination)

| Area | What exists today | Relevance to finance |
|---|---|---|
| Stack | FastAPI (Python 3.11) + supabase-py using the **service_role** key for all writes; React 19 + Vite + TS; Supabase Postgres 15; APScheduler in-process (single ECS task); AWS SES + SNS | All reused. supabase-py has **no multi-statement transactions**, so every multi-row money movement must be a PL/pgSQL function called via `db.rpc()`. That is the existing house pattern (`fn_create_award`, `transition_milestone`, …). |
| Schema | 34 tables in 8 groups, master file `database/bluonx_complete_schema.sql` v3.9 | Conventions copied exactly (see §3.1). |
| Access | `users.role ∈ {admin, project_manager}`; `private.is_active_user()`, `private.is_admin()` helpers; RLS = read-only safety net, writes via service_role | New helper `private.has_any_role(text[])` added; new tables follow the same "read via RLS, write via FastAPI" pattern. |
| Auth / invite | `user_service.invite_user()` → `auth.admin.invite_user_by_email(data={full_name, role})` → trigger `fn_handle_new_auth_user` inserts `public.users` | Trigger extended to also read optional `roles[]` and `is_employee` from metadata (backward compatible). |
| Error mapping | SQLSTATE `PT404 / PT409 / PT422` (plus `PT403` in the milestone ledger) become real HTTP codes via PostgREST | All new procedures and guards raise the same codes. |
| Audit pattern | `milestone_events` append-only, protected by `trg_milestone_events_immutable` (`PT403`) | `contingency_ledger` copies this pattern. |
| "Authoritative writer" pattern | `transition_milestone()` sets `set_config('bluonx.milestone_transition','on',true)`; guard trigger blocks any other writer | Reused for the flat-budget, contingency and locked-line guards (`bluonx.financial_write`). |
| Projects | `projects.budget` (admin-only edit in `routers/projects.py`), `status` already includes `on_hold` | **Left untouched.** The new financial total lives in new columns, so the existing admin budget edit keeps working. |
| Tasks | `bid_type ∈ {competitive, direct_assign, internal}`, `budget_estimate`, soft-deleted only (no hard deletes anywhere in code) | Each task becomes one budget line (`task_id` unique). |
| Awards / contracts | `fn_create_award` (atomic), DocuSign Connect webhook → `completed` executes contract and accepts award; `declined/voided` terminates contract and sets award `declined_by_vendor`; `fn_mark_contract_complete` | Integration hooks for Phase 2 (apply / reverse / lock). Phase 1 only provides the procedures they will call. |
| Milestones | `transition_milestone('pm_reschedule')` moves `end_date`, keeps `baseline_end_date` | Phase 8 re-spread hook; Phase 1 only adds nothing-breaking columns. |
| email_log | `email_type` CHECK: `bid_invitation, bid_reminder, award_notification, decline_notification, milestone_alert, general` (VARCHAR 30) | Extended with financial types (§5.4). |
| notifications | `notification_type` VARCHAR(30), **no CHECK** (code writes `milestone_*`, `insurance_*`, `scheduler_alert`, escalation types) | Vocabulary documented only; **no CHECK added**, since an incomplete list would break existing jobs. |
| Storage | Buckets `vendor-documents`, `project-documents`, `bid-attachments` | `finance-documents` bucket is Phase 2 / 12 work; only the path columns are created now. |

### 1.2 Things I noticed in the repo that you should know about

1. **Uncommitted change in `database/bluonx_complete_schema.sql`.** A `task_templates` block was appended at the end. It (a) defines a second updated-at function `public.update_updated_at_column()` that duplicates `fn_set_updated_at()`, (b) uses `CREATE POLICY` without `DROP POLICY IF EXISTS`, so it is not re-runnable, and (c) adds the policy **`"Allow authenticated manage task_templates" FOR ALL … USING (true) WITH CHECK (true)`**, which lets *any* logged-in user insert, update or delete templates directly through the anon key and bypass FastAPI. That breaks the project's security rule. I will **not touch it** in this phase. I would suggest fixing it separately; it is not a blocker.
2. The master schema file is a "fresh install" script (plain `CREATE TABLE`), not re-runnable. That is why the financial work ships as a **separate migration** and is also appended to the master file for documentation (§7).
3. `users.role` is a hard-coded `Literal["admin","project_manager"]` in `backend/app/models/users.py` and in five frontend type files. If a row ever held a third value, `GET /users` would fail response validation (500). This is the main reason for decision D1.

---

## 2. Task 1.1: Integration map (existing tables → financial records)

| Existing table | New financial link | How it is used |
|---|---|---|
| `projects` | `budget_lines.project_id`, `contingency_*`, `escrows`, `property_taxes`, `cash_flow_entries`, `financial_alerts`… | Every financial record hangs off a project. New columns: assigned manager / field manager, contingency %, approved budget total, baseline info, long-tail reserve, business entity. |
| `tasks` | `budget_lines.task_id` (nullable, **unique among non-deleted lines**) | competitive / direct_assign → `bid_activity` line; internal → `internal_tm` line. Land, permit, impact fee, soft cost, contingency, variance and long-tail lines have no task. |
| `trades` | `budget_template_lines.trade_id`, `variance_lines.trade_id` | Grouping and reports. |
| `awards` | `budget_lines.award_id`, `contingency_ledger.award_id` | Award amount → committed amount (A2/A3). Decline/cancel → reversal. |
| `contracts` | `budget_lines.contract_id`, + `contracts.payment_terms_days`, `contracts.retainage_percent` (new, nullable) | Executed contract → line locked; contract dates default line dates; numeric payment terms for cash flow. |
| `vendors` | `variance_lines.vendor_id`, `payment_approvals.vendor_id`, `internal_invoices.vendor_id`, `finance_handoffs.vendor_id` | Payee / trade on approvals, POs, finance export, contractor scorecard (A23). |
| `milestones` | read only (physical % complete; reschedule → proposed new line end date) | Phase 5 / 8. No schema link needed now. |
| `users` | approvers, actors, `user_roles`, `approval_delegations`, `reports_to`, `backup_approver_id` | Role model and two-person rule. |
| `notifications` | new financial `notification_type` values | Financial alerts in the existing bell. |
| `email_log` | new `email_type` values; `finance_handoffs.email_log_id` | Delivery proof for the finance hand-off audit. |

**Integration points confirmed (these are called by later-phase code, not in this phase):**

| Event in existing code | Where | Financial procedure it will call (Phase 2+) |
|---|---|---|
| Award created | `award_service` → `fn_create_award` | `fn_apply_bid_to_line` |
| DocuSign `completed` | `docusign_webhooks.handle_envelope_event` → `contract_service.mark_contract_executed` | `fn_lock_budget_line` (lock + default dates) |
| DocuSign `declined` / `voided`, award cancelled | same handler → `mark_contract_terminated` | `fn_reverse_bid_on_line` |
| Milestone reschedule | `milestone_service` → `transition_milestone('pm_reschedule')` | Phase 8: propose new line end date (PM confirms) |
| Contract complete | `contract_service` → `fn_mark_contract_complete` | Phase 6/7: final approval eligibility |

**Reuse confirmed:** Supabase Auth + invite flow, `EmailService.send_email()` (→ `email_log`), `notification_service`, APScheduler job contract (`tracked_job`, `KNOWN_JOB_IDS`, UTC cron), `core/storage.py` (validated uploads + 1 h signed URLs). No new infrastructure is needed for Phase 1.

---

## 3. Design principles for this migration

### 3.1 Conventions (copied from the existing schema)
UUID PKs (`gen_random_uuid()`), money `DECIMAL(15,2)`, `TIMESTAMPTZ`, statuses as `VARCHAR + CHECK` (not enums), `ON DELETE RESTRICT` by default (`CASCADE` only for tightly owned child rows, `SET NULL` for advisory refs), `deleted_at` soft delete on core entities, `created_at/updated_at` with the existing `fn_set_updated_at()` trigger, `COMMENT ON` every table and key column, write RPCs `REVOKE … FROM PUBLIC, anon, authenticated; GRANT EXECUTE … TO service_role`, RLS read policies `TO authenticated` using `(SELECT private.…())`.

### 3.2 Production-safety rules
1. **Additive only.** `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, new indexes, new functions. No `DROP TABLE`, no `DROP COLUMN`, no data rewrite, no `UPDATE` of existing business rows.
2. **New columns on existing tables are nullable, or `NOT NULL DEFAULT <constant>`.** On PG 11+ a constant default is metadata-only: no table rewrite and only a momentary lock. They are also invisible to existing `select("id, email, …")` queries.
3. **Only three existing objects are modified in place:**
   - the `email_log.email_type` CHECK, which is **widened** to a superset of today's values and validated against existing rows;
   - `fn_handle_new_auth_user()`, `CREATE OR REPLACE`, which behaves exactly as before when the new metadata keys are absent;
   - a new sync trigger on `users.role`, which only mirrors the role into `user_roles`.
4. **Idempotent:** every statement is guarded, so running the script twice gives the same result with no errors. Constraints use `DO $$ … IF NOT EXISTS (pg_constraint) …`, triggers and policies use `DROP … IF EXISTS` then `CREATE`, and seeds use `ON CONFLICT DO NOTHING` so production edits to settings are never overwritten.
5. **Atomic:** the whole script is wrapped in `BEGIN; … COMMIT;`. If any statement fails, nothing is applied.
6. **Pre-flight and post-verify scripts** check the live database before and after (§7).

### 3.3 How the money rules are enforced in the database (not only in Python)

| Rule | Mechanism |
|---|---|
| Every contingency movement has a ledger row | Contingency balance = `budget_amount` of the project's single `contingency` budget line. A BEFORE UPDATE trigger rejects any change to it unless the transaction-local flag `bluonx.financial_write = on` is set, and only the financial procedures set that flag. Each of those procedures writes the `contingency_ledger` row in the same transaction. |
| Ledger is immutable | `trg_contingency_ledger_immutable`: BEFORE UPDATE OR DELETE → `RAISE … ERRCODE 'PT403'` (same as `milestone_events`). |
| Total budget stays flat | Once a project budget is **baselined**, a `DEFERRABLE INITIALLY DEFERRED` constraint trigger on `budget_lines` checks at COMMIT that `SUM(budget_amount of live lines) = projects.approved_budget_total`. A bid overrun (+2,000 on the line, −2,000 on contingency) passes; any one-sided edit fails with `PT409`. |
| Total changes only by executive top-up | A BEFORE UPDATE trigger on `projects.approved_budget_total` allows a change only inside `fn_approve_contingency_top_up` (which checks that the approver holds the `executive` role) or the one-time `fn_baseline_project_budget`. |
| Locked lines can't be edited | Trigger rejects changes to `budget_amount` / `committed_amount` on `is_locked = true` lines unless the flag is set (only the reversal procedure needs that). |
| Original estimate frozen (A21) | `original_estimate` can be written while the budget is a draft and is frozen at baseline (trigger). |
| Closed months immutable | Trigger on `cash_flow_entries` rejects insert, update or delete in a month whose `accounting_periods.status = 'closed'`. |
| Two-person rule | `CHECK` constraints on `payment_approvals` (field approver ≠ manager approver) and `variance_lines` (creator ≠ approver). |

---

## 4. Task 1.2: The 19 new tables

All tables get `id UUID PK`, `created_at`, `updated_at` (+ `trg_<table>_updated_at`) unless marked *append-only*. All FKs are `ON DELETE RESTRICT` unless noted. Below, **bold** = NOT NULL.

### Group 9 · Budget structure

**`budget_templates`**: the standard budget layout (Phase 2.1).
`name` · `description` · **`is_default`** (partial unique: only one default among active templates) · **`is_active`** · `created_by → users (SET NULL)` · `deleted_at`.

**`budget_template_lines`**: ordered lines of a template.
**`budget_template_id`** (CASCADE) · **`line_type`** · `line_subtype` · **`name`** · `section_name` (heading, e.g. "Land", "Soft costs") · `trade_id → trades` · `task_template_id → task_templates (SET NULL, only if that table exists)` · **`sort_order`** · `default_amount` · `default_payment_terms_days` · `default_cash_bucket` · **`is_active`**.

**`budget_lines`**: the core table. One row per budget line of a project.

| Column | Type / rule | Notes |
|---|---|---|
| **project_id** | → projects | |
| task_id | → tasks, **partial UNIQUE where deleted_at IS NULL** | NULL for land / permit / impact fee / soft cost / contingency / variance / long-tail |
| template_line_id | → budget_template_lines (SET NULL) | which template line it came from |
| parent_line_id | → budget_lines | variance → its activity line; engineering T&M portion → engineering heading |
| **line_type** | CHECK `land, bid_activity, internal_tm, permit, impact_fee, soft_cost, contingency, variance, long_tail` | |
| line_subtype | CHECK `land_purchase, earnest_money, due_diligence, engineering, escrow_bond_premium, escrow_repairs, property_tax, other` (nullable) | |
| **name**, description, section_name, **sort_order** | | top-to-bottom budget view |
| original_estimate | DECIMAL(15,2) ≥ 0 | A21 baseline, frozen at baseline |
| **budget_amount** | DECIMAL(15,2), DEFAULT 0, CHECK ≥ 0 **except contingency** (can go negative; that is what the urgent alert detects) | current budget for the line |
| **committed_amount** | DECIMAL(15,2), DEFAULT 0, ≥ 0 | award amount once a bid is applied |
| award_id / contract_id | → awards / contracts (nullable) | |
| **is_locked**, locked_at, locked_by, lock_reason | | locked on contract execution |
| anticipated_start_date, anticipated_end_date | DATE, CHECK end ≥ start | cash-flow input |
| **payment_terms_days** | INTEGER DEFAULT 30, CHECK 0–365 | |
| **cash_bucket** | CHECK `land, vertical_construction, overhead` DEFAULT `land` | cash *out* buckets |
| **approval_state** | CHECK `not_requested, pending, field_approved, manager_approved, sent_to_finance, rejected` DEFAULT `not_requested` | rolled-up state; detail in `payment_approvals` |
| **is_payment_exempt** | BOOLEAN; TRUE for land and contingency lines | land handled by title co. / bank |
| created_by, updated_by, deleted_at | | |

Extra constraints and indexes:
- partial UNIQUE (project_id) WHERE line_type = 'contingency' AND deleted_at IS NULL, so there is one contingency line per project;
- a consistency trigger checks that `task.project_id = line.project_id`, and that `bid_activity ↔ task.bid_type IN (competitive, direct_assign)` and `internal_tm ↔ internal` (same pattern as `fn_enforce_award_consistency`);
- indexes on (project_id, sort_order), task_id, award_id, parent_line_id, line_type.

**`land_closings`**: phased takedowns under a land-purchase line.
**`budget_line_id`** · **`project_id`** · **`closing_sequence`** (UNIQUE per line) · `acres DECIMAL(12,4)` · **`amount`** · **`planned_closing_date`** · `actual_closing_date` · **`status`** CHECK `planned, closed, cancelled` · `notes`.

### Group 10 · Contingency

**`contingency_buckets`**: every funding source of a project's contingency, including each top-up request and its decision. This keeps top-ups auditable separately (Steve's preference) while the balance lives on one contingency line (Plan v1.3 Task 3.5).
**`project_id`** · **`contingency_line_id`** → budget_lines · **`bucket_kind`** CHECK `initial, top_up` · **`requested_amount`** > 0 · `approved_amount` · **`status`** CHECK `pending, approved, rejected, cancelled` · **`reason`** · **`requested_by`** · `requested_at` · `decided_by`, `decided_at`, `decision_note` · CHECK (status = approved ⇒ decided_by/approved_amount NOT NULL).

**`contingency_ledger`** *(append-only, no updated_at)*: every movement.
**`project_id`** · **`contingency_line_id`** · `contingency_bucket_id` · **`movement_type`** CHECK `initial_funding, bid_overrun, bid_savings, bid_reversal, variance_created, variance_adjusted, variance_cancelled, top_up, invoice_overage` · **`amount`** (signed: + into contingency, − out of it, ≠ 0) · **`balance_before`**, **`balance_after`** (CHECK after = before + amount) · `source_budget_line_id` · `variance_line_id` · `award_id` · **`actor_user_id`** · `reason` · **`created_at`**.
Index (project_id, created_at DESC). Immutable trigger (`PT403`).

**`variance_lines`**: field variance metadata. The money sits on a `budget_lines` row of type `variance` (1:1), so totals, the flat-budget check and cash flow all see it without special cases.
**`project_id`** · **`budget_line_id`** → budget_lines (UNIQUE, the variance's own line) · **`parent_budget_line_id`** (the activity) · `trade_id` · `vendor_id` · **`description`** · **`estimated_amount`** (first estimate, kept for history) · **`status`** CHECK `draft, pending_approval, approved, rejected, cancelled` · **`created_by`** · `approved_by`, `approved_at` · CHECK (approved_by IS NULL OR approved_by <> created_by) · `deleted_at`.

### Group 11 · Payments & finance hand-off

**`payment_approvals`**: one approval request per payment (full, progress or retainage release).
**`project_id`** · **`budget_line_id`** · `internal_invoice_id` · `vendor_id` · **`amount`** > 0 · **`payment_kind`** CHECK `full, progress, retainage_release` · `progress_percent` (0–100) · `retainage_amount` · **`status`** CHECK `pending, field_approved, awaiting_manager, awaiting_executive, approved, sent_to_finance, rejected, cancelled` · **`requested_by`** · `field_approved_by/at` · `routed_to_user_id` (manager or backup) · `manager_approved_by/at` · `executive_approved_by/at` · `rejected_by/at`, `rejection_reason` · `expected_payment_date` · CHECKs: manager_approved_by ≠ field_approved_by; executive_approved_by ≠ field_approved_by.

**`internal_invoices`**: incoming invoices for internal T&M lines (e.g. attorney).
**`project_id`** · `budget_line_id` (NULL until categorised) · `vendor_id` · `payee_name` · `invoice_number` · `invoice_date` · **`amount`** ≥ 0 · **`file_path`** (finance-documents bucket), `file_name`, `file_size` · **`status`** CHECK `received, categorised, in_approval, approved, rejected, cancelled` · **`uploaded_by`** · `deleted_at`.

**`finance_handoffs`**: what was sent to finance (internal invoice / PO record, A12).
**`payment_approval_id`** (UNIQUE) · **`project_id`** · **`po_number`** (UNIQUE) · `vendor_id` · **`amount`** · **`payload`** JSONB (trade, amount, project, activity, date, approvers) · `document_path` (generated PDF) · `email_log_id` → email_log (SET NULL) · **`status`** CHECK `pending, sent, delivered, failed` · `sent_at` · `exported_at`.

### Group 12 · Long-tail items

**`escrows`**: **`project_id`** · **`name`** · **`beneficiary`** CHECK `city, county, hoa, other` · `covered_areas TEXT[]` (several areas per escrow) · **`security_form`** CHECK `cash, bond` · `holder_type` CHECK `insurance_company, bank, other` · `holder_name` · **`secured_amount`** (= value of the works) · `premium_amount`, `bond_number`, `bond_expiry_date` · **`status`** CHECK `planned, posted, works_built, inspection, corrections, signed_off, released, cancelled` · `posted_date`, `released_date` · `premium_line_id`, `repair_line_id` → budget_lines (the two costs, A15) · `document_path` · `notes` · `deleted_at`.

**`property_taxes`**: **`project_id`** · `budget_line_id` · **`tax_year`** · **`jurisdiction`** · `parcel_reference` · **`installment_number`** DEFAULT 1 · `due_date` · **`estimate_basis`** CHECK `prior_year_actual, assessed_value, manual` · **`estimated_amount`** · `actual_amount` · `sold_portion_percent` · **`status`** CHECK `estimated, billed, in_approval, sent_to_finance, cancelled` · UNIQUE (project_id, tax_year, jurisdiction, installment_number).

### Group 13 · Cash flow

**`accounting_periods`**: **`period_month`** DATE UNIQUE (CHECK day = 1) · **`status`** CHECK `open, closed` · `closed_by`, `closed_at` · `notes`. These are company-wide months.

**`cash_flow_entries`**: monthly cash schedule rows (generated by Phase 8 code).
`project_id` (NULL for company items) · `budget_line_id` · `land_closing_id` · `escrow_id` · `payment_approval_id` · `company_cash_item_id` · **`period_month`** (day = 1) · **`direction`** CHECK `out, in` · **`cash_bucket`** CHECK `land, vertical_construction, overhead, deposits, closings` · **`amount`** ≥ 0 · **`entry_kind`** CHECK `forecast, expected, actual` · `source_note`. CHECK that at least one source FK is set. Index (period_month, cash_bucket), (project_id, period_month).

**`company_cash_items`**: overhead, deposits and closings entered manually or imported.
**`item_type`** CHECK `overhead, deposit, closing, vertical_construction, other` · **`direction`** · **`cash_bucket`** · `business_entity` · `project_id` (optional) · **`description`** · **`period_month`** · **`amount`** · **`source`** CHECK `manual, csv_import` · `created_by` · `deleted_at`.

### Group 14 · Settings, alerts, roles

**`financial_settings`**: key/value with typed JSON so new settings never need a migration.
**`setting_key`** VARCHAR PK · **`value`** JSONB · `description` · `updated_by` · `updated_at`. Seeded (ON CONFLICT DO NOTHING, so production edits are never overwritten): `default_contingency_percent = 15`, `contingency_min_percent = 15`, `contingency_max_percent = 20`, `bidding_target_contingency_percent = 10`, `default_payment_terms_days = 30`, `default_field_approval_limit = 5000`, `executive_approval_threshold = null`, `contingency_near_zero_percent = 5`, `alert_recipients = {}`, `land_team_emails = []`, `finance_emails = []`, `sales_emails = []`, `po_number_format = "PO-{YYYY}-{SEQ:05}"`. Values marked "open question" in the plan stay editable.

**`financial_alerts`**: guardrail alerts and their decisions (A8/A9/A10/A4).
**`project_id`** · **`alert_type`** CHECK `contingency_health, contingency_near_zero, contingency_negative, long_tail_reserve, bidding_checkpoint` · **`severity`** CHECK `warning, urgent, critical` · **`status`** CHECK `open, acknowledged, proceed_approved, on_hold, resolved, superseded` · snapshot: `contingency_left_pct`, `work_left_pct`, `contingency_remaining`, `reserve_required` · `message` · `decision` CHECK `proceed, hold` · `decision_reason` · `decided_by`, `decided_at` · `resolved_at`. Partial UNIQUE (project_id, alert_type) WHERE status = 'open', so the daily sweep never duplicates an alert.

**`user_roles`**: many roles per user.
**`user_id`** → users · **`role`** CHECK `admin, project_manager, field_manager, executive, finance` · `granted_by` · **`granted_at`** · `revoked_at`, `revoked_by`. Partial UNIQUE (user_id, role) WHERE revoked_at IS NULL. Revoking sets `revoked_at` (audit), never deletes.

**`approval_delegations`**: temporary delegation while a manager is away.
**`delegator_user_id`** · **`delegate_user_id`** · **`starts_at`** · **`ends_at`** (CHECK > starts_at) · `reason` · **`created_by`** · `revoked_at` · CHECK delegator ≠ delegate.

---

## 5. Task 1.3: Extensions to existing tables

### 5.1 `users` (additive)
| Column | Type | Default | Purpose |
|---|---|---|---|
| `is_employee` | BOOLEAN NOT NULL | `TRUE` | FALSE = external / temporary field manager (can confirm work, never authorise payment) |
| `reports_to` | UUID → users (SET NULL), CHECK ≠ id | NULL | manager one level above (fixed per person) |
| `backup_approver_id` | UUID → users (SET NULL), CHECK ≠ id | NULL | standing backup; temporary windows go in `approval_delegations` |
| `approval_limit` | DECIMAL(15,2) ≥ 0 | NULL | NULL ⇒ `financial_settings.default_field_approval_limit` |

`users.role` CHECK is **not changed** (see D1). Backfill: one `user_roles` row per existing user mirroring `users.role` (`INSERT … SELECT … ON CONFLICT DO NOTHING`). This writes only to the new table.
Sync trigger `trg_users_sync_base_role`: when the existing admin screen flips `users.role` admin ↔ project_manager, the old base role is revoked in `user_roles` and the new one granted. Existing behaviour is unchanged.

### 5.2 `projects` (additive, all nullable unless stated)
`manager_id`, `field_manager_id` → users (SET NULL) · `contingency_percent DECIMAL(5,2)` (NULL ⇒ settings default) · **`budget_status`** VARCHAR CHECK `none, draft, baselined` NOT NULL DEFAULT `none` · `approved_budget_total DECIMAL(15,2)` · `budget_baselined_at`, `budget_baselined_by` · `contingency_at_groundbreaking DECIMAL(15,2)` · `long_tail_reserve_amount DECIMAL(15,2)` · `business_entity` CHECK `bluonx, capstone` (for separate owner views). `projects.budget` stays exactly as it is.

### 5.3 `contracts` (additive, nullable)
`payment_terms_days INTEGER` (0–365) and `retainage_percent DECIMAL(5,2)` (0–100). The existing `payment_terms TEXT` is untouched.

### 5.4 Type vocabularies
- **`email_log.email_type`**: the CHECK is replaced by a superset. Existing values plus `payment_approval_request, payment_approved, payment_rejected, finance_handoff, finance_daily_summary, contingency_alert, contingency_escalation, contingency_top_up, long_tail_reserve_alert, bidding_checkpoint, property_tax_reminder, bond_renewal_reminder, owner_weekly_summary` (all ≤ 30 chars). Method: look up the current constraint name in `pg_constraint` (do not guess it), add the new constraint `NOT VALID`, `VALIDATE`, then drop the old one, all inside the transaction. The pre-flight script first lists `SELECT DISTINCT email_type FROM email_log`, so any production value missing from the master file is caught before we touch it.
- **`notifications.notification_type`**: no CHECK exists today, and adding one could reject types written by existing jobs (insurance tiers, escalations, scheduler alerts). The financial vocabulary is documented in the column COMMENT and in the schema doc instead: `contingency_health_alert, contingency_urgent_alert, long_tail_reserve_alert, bidding_checkpoint_alert, top_up_requested, top_up_decided, payment_approval_requested, payment_approved, payment_rejected, variance_pending_approval, property_tax_due, bond_renewal_due, month_closed`.

---

## 6. Task 1.4 & 1.5: Procedures, triggers, RLS

### 6.1 Stored procedures (all `SECURITY INVOKER`, service_role only, `PT` error codes)

| Procedure | What it does atomically | Key errors |
|---|---|---|
| `fn_baseline_project_budget(p_project_id, p_actor)` | Locks project row; requires `budget_status = draft`, one contingency line and dates rules; freezes `original_estimate` on every line; sets `approved_budget_total = SUM(lines)`, `budget_status = baselined`; creates the `initial` contingency bucket (approved) and the `initial_funding` ledger row | PT404 project, PT409 already baselined / no contingency line |
| `fn_apply_bid_to_line(p_budget_line_id, p_award_id, p_amount, p_actor)` | Locks line and contingency line; Δ = amount − budget_amount; line `budget_amount = committed_amount = amount`, `award_id` set; contingency −Δ; ledger `bid_overrun` / `bid_savings` (no row if Δ = 0). Award must belong to the line's task. | PT404, PT409 locked / already applied to another award, PT422 amount < 0 |
| `fn_reverse_bid_on_line(p_budget_line_id, p_award_id, p_actor, p_reason)` | Undoes the last applied bid for that award: restores pre-bid amount from the ledger, contingency +/−, ledger `bid_reversal`, clears award_id / committed; unlocks if locked | PT404, PT409 nothing to reverse |
| `fn_lock_budget_line(p_budget_line_id, p_contract_id, p_actor)` | Locks line; defaults anticipated dates from contract start / end when NULL | PT404, PT409 |
| `fn_create_variance(p_parent_line_id, p_description, p_amount, p_trade_id, p_vendor_id, p_actor)` | Creates `variance` budget line under parent + `variance_lines` row (`pending_approval`); contingency −amount; ledger `variance_created` | PT404, PT409 project not baselined / on hold, PT422 amount ≤ 0 |
| `fn_adjust_variance(p_variance_id, p_new_amount, p_actor, p_reason)` | Only while not approved; Δ applied to line, −Δ to contingency; ledger `variance_adjusted`. `p_new_amount = 0` with cancel ⇒ status `cancelled`, ledger `variance_cancelled` | PT409 approved / cancelled, PT422 |
| `fn_approve_contingency_top_up(p_bucket_id, p_approver, p_approve BOOL, p_amount, p_note)` | Checks approver has active `executive` role; approve: contingency line +amount, `approved_budget_total` +amount (the only path besides baseline), ledger `top_up`; reject: status only | **PT403** not executive, PT404, PT409 not pending |
| `fn_close_accounting_month(p_month, p_actor)` | Checks actor has `finance` or `executive` role; upserts `accounting_periods` closed; from then the guard trigger freezes that month | PT403, PT409 already closed, PT422 not first-of-month / future month |

Every procedure: `SELECT … FOR UPDATE` row locks, `set_config('bluonx.financial_write','on', true)` around the guarded writes and `'off'` after (house pattern), returns the changed row(s) or JSONB, and has a `COMMENT ON FUNCTION`.

### 6.2 Triggers

| Trigger | Table | Purpose |
|---|---|---|
| `trg_<table>_updated_at` (×18) | all new tables except ledger | existing `fn_set_updated_at()` |
| `trg_contingency_ledger_immutable` | contingency_ledger | blocks UPDATE / DELETE (PT403) |
| `trg_budget_lines_guard` | budget_lines BEFORE INSERT/UPDATE | contingency line, locked line and frozen `original_estimate` only via procedures; task / project / type consistency |
| `trg_budget_lines_flat_total` (constraint, deferred) | budget_lines | sum = approved total at commit, once baselined (PT409) |
| `trg_projects_guard_budget_total` | projects BEFORE UPDATE OF approved_budget_total, budget_status | only baseline / top-up procedures |
| `trg_cash_flow_entries_closed_period` | cash_flow_entries | no change in closed months (PT409) |
| `trg_accounting_periods_no_reopen` | accounting_periods | closed → open forbidden (PT409) |
| `trg_variance_lines_guard` | variance_lines | approved / cancelled variances are frozen (PT409) |
| `trg_users_sync_base_role` | users AFTER UPDATE OF role | mirror into user_roles |

### 6.3 RLS (`database/rls_policies.sql` gets a new Group 9–14 section)
- `ENABLE ROW LEVEL SECURITY` on all 19 tables; `REVOKE ALL … FROM anon`; `REVOKE INSERT, UPDATE, DELETE … FROM authenticated` (writes only via FastAPI service_role).
- New helper `private.has_any_role(p_roles text[])`: `SECURITY DEFINER`, `search_path = ''`, true if the caller is active and has an un-revoked `user_roles` row in the list (admins always pass).
- **SELECT for any active user:** budget_templates, budget_template_lines, budget_lines, land_closings, contingency_buckets, contingency_ledger, variance_lines, payment_approvals, escrows, property_taxes, financial_alerts, financial_settings, user_roles, approval_delegations, accounting_periods. Field managers can see contingency figures (Plan Task 10.1).
- **Finance-restricted SELECT** (`has_any_role('{finance,executive,admin}')`): `finance_handoffs`, `internal_invoices`, `company_cash_items` (salaries / overhead), `cash_flow_entries`.
- Phase 9+ views will be `security_invoker = true` so they inherit these rules.

---

## 7. Task 1.6 & 1.7: Invite flow, seed data, docs

### 7.1 Invite / profile trigger (database part, done now)
`fn_handle_new_auth_user()` is replaced (`CREATE OR REPLACE`, same signature, still `SECURITY DEFINER SET search_path = ''`):
- inserts `public.users` exactly as today (`role` = metadata `role`, default `project_manager`);
- additionally reads optional metadata `roles` (JSON array) and `is_employee` (bool) and inserts one `user_roles` row per **valid** role plus the base role; unknown values are ignored, so a bad value can never block a signup;
- with today's metadata (`{full_name, role}`) the result is identical to now plus one `user_roles` row.

### 7.2 Code part of Task 1.6 (**deferred, because you said no code changes in this phase**)
These need code and are **not** in this delivery. I will list them in the docs as the first item for the next coding phase:
- backend: `UserInviteRequest.roles: list[...]`, `is_employee`; pass them in invite metadata; `require_roles(*roles)` dependency in `core/auth.py` (reads `user_roles`); include `roles` in `get_current_active_user`;
- frontend: multi-select roles + external toggle in `InviteUserModal`; `ProtectedRoute requiredRoles` guard for finance screens; regenerate `database.types.ts`.

Until that code lands, admins can grant financial roles with a one-line SQL statement (the runbook includes it).

### 7.3 Seed data (dev only, never prod)
`database/seed_data/dev_seed_financial_phase1.sql`, guarded by a check that refuses to run if a marker setting says "production". It creates (through the procedures, so the ledger is real):
- "Discovery Demo: $100k Budget": tasks for clearing / grading / sanitary sewer / water + storm, land lines (purchase, earnest money, due diligence + 2 phased closings), permits, impact fee, contingency $10,000 (base excludes land), baselined;
- bid applied: sewer $9,000 → $10,000 (−$1,000 contingency), clearing $20,000 → $22,000, grading $60,000 → $58,000 (+$2,000);
- **sanitary sewer variance** $5,000 → adjusted to $3,000 (+$2,000 back), so the ledger reproduces the worked example;
- escrow "Roads to city": bond $10,000, premium line + repair line; HOA landscaping escrow (cash);
- property tax 2027 line; test users holding field_manager / executive / finance roles (one external field manager, one user with two roles); a pending top-up request.

### 7.4 Documentation
- `database/bluonx_complete_schema.sql`: append **Section 9: Financial Automation (v4.0)** with the same DDL, header bumped to v4.0 / 53 tables. Your uncommitted `task_templates` block is left as it is.
- `database/rls_policies.sql`: new financial section.
- `database/bluonx_schema_documentation.md`: new groups 9–14, procedures, guards, role model, ER relationships, updated statistics.
- `docs/financial/PHASE1_RUNBOOK.md`: the step-by-step setup guide (§9 expanded).

---

## 8. Files that will be created or changed

```
database/
  migrations/
    20261111_financial_phase1/
      000_preflight_checks.sql        read-only; run first, review output
      001_financial_foundation.sql    THE migration (BEGIN…COMMIT, idempotent)
      002_verify_financial_foundation.sql  assertions inside a transaction that ROLLS BACK
      099_rollback_financial_foundation.sql DEV ONLY – drops only the new objects
      README.md                       order of execution
  seed_data/
    dev_seed_financial_phase1.sql     DEV ONLY
  bluonx_complete_schema.sql          + Section 9 (financial), v4.0
  rls_policies.sql                    + financial policies
  bluonx_schema_documentation.md      + groups 9–14
docs/financial/
  PHASE1_MODULE1_PLAN.md              this file
  PHASE1_RUNBOOK.md                   setup and operating guide
```
No file under `backend/` or `frontend/` is touched.

---

## 9. How you will apply it (runbook summary)

> The detailed version with screenshots-level steps goes into `PHASE1_RUNBOOK.md`.

**A. Development project**
1. Supabase dashboard → *dev* project → **SQL Editor** → New query.
2. Paste and run `000_preflight_checks.sql`. Check that: PG ≥ 15, `private` schema and `fn_set_updated_at` exist, none of the 19 table names exist yet (or only from a previous run of this script), the list of `email_type` values in use, and the current email_log CHECK name. Send me the output if anything looks unexpected.
3. Paste and run `001_financial_foundation.sql`. Expected result: *Success. No rows returned.* If anything fails, the whole script rolls back and the database is unchanged.
4. Run `002_verify_financial_foundation.sql`. It prints `PASS` / `FAIL` for each acceptance criterion: 19 tables with RLS, ledger UPDATE/DELETE blocked, one-sided budget edit rejected, top-up by a non-executive rejected, top-up by an executive accepted, procedures write ledger rows, closed month frozen, re-run safety. It rolls back, so it leaves no test data behind.
5. **Run `001` a second time** → must again succeed (idempotency criterion).
6. Run `dev_seed_financial_phase1.sql`, then browse the tables in Table Editor to see the $100k example.
7. Run the existing backend test suite against dev (`pytest`, including the live-DB marker) to confirm no Phase 1 regression. Click through the existing app: users list, invite, projects, awards, milestones.

**B. Production project** (after dev is green and you sign off)
1. Take a backup. Confirm PITR is enabled, or run `pg_dump` of the `public` schema, or at minimum Database → Backups → note the latest restore point.
2. Choose a quiet window. The script takes a few seconds; locks on `users`, `projects`, `contracts` and `email_log` are momentary (no table rewrites).
3. Run `000` → review → run `001` → run `002` (rolls back, safe in prod).
4. Do **not** run the seed file in production.
5. Grant real roles with SQL until the admin UI exists (Task 1.6 code), for example:
   `INSERT INTO user_roles (user_id, role, granted_by) VALUES ('<user uuid>', 'executive', '<your uuid>');`
6. Smoke-test the live app (login, invite, project, award pages).

**C. Rollback**
- Production: the change is additive, so leaving the new objects unused is safe. A real rollback is *restore from backup* or the targeted `099` script (it drops only new objects and restores the original `fn_handle_new_auth_user` and email_log CHECK). Use it only after confirming no financial data needs keeping.

---

## 10. Decisions for you to confirm (defaults in **bold** are what I will build)

| # | Decision | Options | Recommended default |
|---|---|---|---|
| D1 | Where the new roles live | (a) widen `users.role` CHECK; (b) keep `users.role` = legacy app tier, financial roles only in `user_roles` | **(b)**: (a) would make `GET /users` return 500 for a finance-only user, because the backend and frontend hard-code two roles, and fixing that needs code. With (b), a finance-only person still gets base role `project_manager` until Phase 10 adds screen restrictions. |
| D2 | Flat-budget start point | (a) from baseline (admin baselines the budget); (b) from the first insert | **(a)**: lets admins build and adjust a draft freely (Phase 2 checklist behaviour), then the guard applies. |
| D3 | Top-ups | (a) one contingency line, each top-up a separate bucket + ledger row; (b) separate contingency line per top-up | **(a)**, matches Plan v1.3 Task 3.5 and keeps audit separation. |
| D4 | Variance storage | (a) variance = its own `budget_lines` row + `variance_lines` metadata; (b) `variance_lines` only | **(a)**: totals, flat check and cash flow need no special cases. |
| D5 | Extra procedures beyond the 4 named | add `fn_baseline_project_budget`, `fn_reverse_bid_on_line`, `fn_lock_budget_line` now | **Yes**. Reversal and lock are contingency/lock movements that must be atomic, and Phase 2 needs them. |
| D6 | Forward-looking columns now (`business_entity`, `long_tail_reserve_amount`, `contingency_at_groundbreaking`, `contracts.payment_terms_days`, `retainage_percent`) | now vs. in their phase | **Now**: one migration on prod instead of several; all nullable and unused until code reads them. |
| D7 | Task 1.6 backend/frontend code | defer vs. do now | **Defer** (you asked for no code changes); DB side done now, SQL grant workaround documented. |

---

## 11. Acceptance criteria → how each is proven

| Criterion | Proof |
|---|---|
| Script applies cleanly to dev and is re-runnable | Steps A3 + A5; `002` checks object counts |
| New tables linked to tasks / projects / awards / contracts without breaking Phase 1 | FKs in `001`; existing pytest suite + manual smoke test (A7) |
| New roles, employee flag, reporting line, backup approver, approval limit; multiple roles per user | `user_roles`, `users` columns; seed creates a two-role user; `002` asserts |
| Every contingency movement via a procedure with its ledger entry | Guard trigger rejects direct writes; `002` attempts a direct update (expects PT409) and runs each procedure (expects ledger row with correct balance_after) |
| Ledger rows cannot be edited or deleted | `002` attempts UPDATE / DELETE (expects PT403), including as service_role |
| Total budget unchanged without executive top-up | `002`: one-sided line edit → PT409; top-up by non-executive → PT403; by executive → total +amount |
| Master schema file and documentation updated | Files in §8 |

---

## 12. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Production `email_log` holds a type not in the master file → widened CHECK fails validation | Pre-flight lists actual values; script builds the new list as *existing distinct values ∪ planned list*, so it can't fail on data |
| Constraint names differ between environments | Looked up dynamically from `pg_catalog`, never hard-coded |
| Auth trigger change breaks invites | Trigger keeps exact old behaviour; new logic wrapped so invalid metadata is ignored; verified with a test invite on dev |
| Deferred flat-budget trigger surprises later code | Documented in procedures and runbook; error message names the project, expected and actual totals |
| Someone runs the seed in prod | Seed refuses unless `financial_settings.environment = 'development'` is set manually first |
| Lock contention on prod | Additive DDL only, run in quiet window, `SET lock_timeout = '5s'` at top so it fails fast instead of queueing behind traffic |

---

## 13. Effort (matches Plan v1.3)

| Task | Hours | Deliverable |
|---|---|---|
| 1.1 Review & integration map | 4 | §1–2 of this plan, done |
| 1.2 Financial schema change script | 16 | `001` tables, constraints, indexes, comments |
| 1.3 Extend existing tables | 8 | `001` users / projects / contracts / vocabularies / user_roles backfill |
| 1.4 Stored procedures | 10 | 8 procedures in `001` |
| 1.5 Triggers & RLS | 6 | guards + RLS in `001`, `rls_policies.sql` |
| 1.6 Invite flow & role checks | 5 | DB trigger now; code items documented (D7) |
| 1.7 Seed & docs | 3 | seed file, master schema, schema doc, runbook |
| **Total** | **52** | |

---

**Next step:** reply *"approved"* (optionally with changes to D1–D7). I will then write the SQL files and documentation listed in §8 and walk you through the runbook step by step.
