-- ============================================================================
-- BluOnX Financial Automation — Phase 1 · Module 1
-- 001  FINANCIAL FOUNDATION (schema change script)
-- ============================================================================
-- Version:  4.0.0
-- Date:     November 11, 2026
-- Applies:  on top of bluonx_complete_schema.sql v3.9 + rls_policies.sql v3.3
-- Engine:   PostgreSQL 15+ (Supabase)
-- ============================================================================
--
-- WHAT THIS SCRIPT DOES
--   • 19 new tables (Groups 9–14): budget structure, contingency, payments &
--     finance hand-off, long-tail items, cash flow, settings / alerts / roles
--   • Additive columns on users, projects, contracts (nullable, or NOT NULL
--     with a constant default → metadata-only, no table rewrite)
--   • email_log.email_type CHECK widened to a SUPERSET of what exists today
--   • fn_handle_new_auth_user() extended (identical behaviour when the new
--     metadata keys are absent)
--   • Financial stored procedures (service_role only)
--   • Guard triggers: immutable ledger, flat budget, locked lines, frozen
--     baseline estimates, closed accounting months, executive-only top-ups
--   • RLS read policies (writes stay behind FastAPI / service_role)
--   • Default financial settings (ON CONFLICT DO NOTHING — never overwrites)
--
-- PRODUCTION SAFETY
--   • ADDITIVE ONLY: nothing existing is dropped, renamed or rewritten.
--     The only in-place replacements are the email_log CHECK (widened, built
--     from the values actually present) and fn_handle_new_auth_user().
--   • IDEMPOTENT: safe to run again; a re-run changes nothing.
--   • ATOMIC: wrapped in BEGIN … COMMIT. Any error → nothing is applied.
--   • lock_timeout set so a busy table makes the script FAIL FAST instead of
--     queueing behind live traffic. Just re-run it in a quieter moment.
--
-- HOW TO RUN
--   Supabase Dashboard → SQL Editor → paste this whole file → Run.
--   Run 000_preflight_checks.sql before, 002_verify_financial_foundation.sql
--   after. See docs/financial/PHASE1_RUNBOOK.md.
--
-- CONVENTIONS (same as the master schema)
--   UUID PKs · DECIMAL(15,2) money · TIMESTAMPTZ · VARCHAR + CHECK statuses ·
--   ON DELETE RESTRICT by default · soft delete via deleted_at · comments on
--   every table and key column · write RPCs granted to service_role only ·
--   SQLSTATE PT403 / PT404 / PT409 / PT422 → HTTP 403 / 404 / 409 / 422.
--
-- THE AUTHORITATIVE-WRITER FLAG
--   Guarded money columns may only change while the transaction-local setting
--   bluonx.financial_write = 'on'. Only the procedures in SECTION F set it
--   (same pattern as bluonx.milestone_transition / transition_milestone()).
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE SCHEMA IF NOT EXISTS private;


-- ============================================================================
-- SECTION A: HELPER FUNCTIONS (private schema — not exposed by the Data API)
-- ============================================================================

-- A.1  Is the current transaction an authorised financial writer?
CREATE OR REPLACE FUNCTION private.fin_write_authorized()
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  SELECT COALESCE(current_setting('bluonx.financial_write', TRUE), '') = 'on';
$$;

COMMENT ON FUNCTION private.fin_write_authorized() IS
  'TRUE while a financial stored procedure has set bluonx.financial_write = on for this transaction. Guard triggers use it to tell the authoritative writer apart from every other writer.';


-- ============================================================================
-- SECTION B: EXTEND EXISTING TABLES (additive only)
-- ============================================================================

-- ── B.1 users ───────────────────────────────────────────────────────────────
-- users.role is deliberately NOT changed (stays admin | project_manager): the
-- current backend and frontend hard-code those two values. Financial roles
-- live in user_roles (Section C), which also allows several roles per person.

ALTER TABLE public.users ADD COLUMN IF NOT EXISTS is_employee        BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS reports_to         UUID;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS backup_approver_id UUID;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS approval_limit     DECIMAL(15,2);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_reports_to') THEN
    ALTER TABLE public.users ADD CONSTRAINT fk_users_reports_to
      FOREIGN KEY (reports_to) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_backup_approver') THEN
    ALTER TABLE public.users ADD CONSTRAINT fk_users_backup_approver
      FOREIGN KEY (backup_approver_id) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_reports_to_not_self') THEN
    ALTER TABLE public.users ADD CONSTRAINT chk_users_reports_to_not_self
      CHECK (reports_to IS NULL OR reports_to <> id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_backup_not_self') THEN
    ALTER TABLE public.users ADD CONSTRAINT chk_users_backup_not_self
      CHECK (backup_approver_id IS NULL OR backup_approver_id <> id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_approval_limit_nonneg') THEN
    ALTER TABLE public.users ADD CONSTRAINT chk_users_approval_limit_nonneg
      CHECK (approval_limit IS NULL OR approval_limit >= 0);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_users_reports_to         ON public.users (reports_to)         WHERE reports_to IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_backup_approver_id ON public.users (backup_approver_id) WHERE backup_approver_id IS NOT NULL;

COMMENT ON COLUMN public.users.is_employee        IS 'TRUE = internal employee. FALSE = external / temporary field manager with their own login: may confirm work is done, may NEVER authorise payment.';
COMMENT ON COLUMN public.users.reports_to         IS 'Manager one level above this person (fixed per person). Receives over-limit / external approvals for second approval.';
COMMENT ON COLUMN public.users.backup_approver_id IS 'Standing backup approver used when reports_to is unavailable. Temporary windows go in approval_delegations.';
COMMENT ON COLUMN public.users.approval_limit     IS 'Max amount this user may approve alone. NULL = financial_settings.default_field_approval_limit.';
COMMENT ON COLUMN public.users.role               IS 'Base application access tier for the Bid Management System (admin | project_manager). Unchanged by the financial module; financial roles are held in user_roles (a user may hold several).';


-- ── B.2 projects ────────────────────────────────────────────────────────────
-- projects.budget (admin-editable today) is left exactly as it is. The
-- financial total lives in approved_budget_total and is guarded.

ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS manager_id                    UUID;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS field_manager_id              UUID;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS contingency_percent           DECIMAL(5,2);
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS budget_status                 VARCHAR(20) NOT NULL DEFAULT 'none';
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS approved_budget_total         DECIMAL(15,2);
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS budget_baselined_at           TIMESTAMPTZ;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS budget_baselined_by           UUID;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS contingency_at_groundbreaking DECIMAL(15,2);
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS long_tail_reserve_amount      DECIMAL(15,2);
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS business_entity               VARCHAR(20);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_projects_manager') THEN
    ALTER TABLE public.projects ADD CONSTRAINT fk_projects_manager
      FOREIGN KEY (manager_id) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_projects_field_manager') THEN
    ALTER TABLE public.projects ADD CONSTRAINT fk_projects_field_manager
      FOREIGN KEY (field_manager_id) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_projects_budget_baselined_by') THEN
    ALTER TABLE public.projects ADD CONSTRAINT fk_projects_budget_baselined_by
      FOREIGN KEY (budget_baselined_by) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_projects_budget_status') THEN
    ALTER TABLE public.projects ADD CONSTRAINT chk_projects_budget_status
      CHECK (budget_status IN ('none', 'draft', 'baselined'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_projects_contingency_percent') THEN
    ALTER TABLE public.projects ADD CONSTRAINT chk_projects_contingency_percent
      CHECK (contingency_percent IS NULL OR contingency_percent BETWEEN 0 AND 100);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_projects_approved_total_nonneg') THEN
    ALTER TABLE public.projects ADD CONSTRAINT chk_projects_approved_total_nonneg
      CHECK (approved_budget_total IS NULL OR approved_budget_total >= 0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_projects_baselined_has_total') THEN
    ALTER TABLE public.projects ADD CONSTRAINT chk_projects_baselined_has_total
      CHECK (budget_status <> 'baselined' OR approved_budget_total IS NOT NULL);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_projects_long_tail_reserve_nonneg') THEN
    ALTER TABLE public.projects ADD CONSTRAINT chk_projects_long_tail_reserve_nonneg
      CHECK (long_tail_reserve_amount IS NULL OR long_tail_reserve_amount >= 0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_projects_business_entity') THEN
    ALTER TABLE public.projects ADD CONSTRAINT chk_projects_business_entity
      CHECK (business_entity IS NULL OR business_entity IN ('bluonx', 'capstone'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_projects_manager_id       ON public.projects (manager_id)       WHERE manager_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_projects_field_manager_id ON public.projects (field_manager_id) WHERE field_manager_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_projects_budget_status    ON public.projects (budget_status)    WHERE deleted_at IS NULL;

COMMENT ON COLUMN public.projects.manager_id                    IS 'Assigned manager (one level above the field manager). Receives guardrail alerts and second approvals.';
COMMENT ON COLUMN public.projects.field_manager_id              IS 'Assigned field manager. Confirms work and first-approves payments.';
COMMENT ON COLUMN public.projects.contingency_percent           IS 'Program contingency % for this project. NULL = financial_settings.default_contingency_percent (15). Longer deals may carry more.';
COMMENT ON COLUMN public.projects.budget_status                 IS 'none = no financial budget yet; draft = budget being built (lines freely editable); baselined = estimates frozen, flat-budget rule active. Only fn_baseline_project_budget() moves draft → baselined.';
COMMENT ON COLUMN public.projects.approved_budget_total         IS 'Approved financial budget total. Set at baseline; changes ONLY through an executive-approved contingency top-up (fn_approve_contingency_top_up). Independent of the legacy projects.budget field.';
COMMENT ON COLUMN public.projects.budget_baselined_at           IS 'When the budget was baselined (original estimates frozen).';
COMMENT ON COLUMN public.projects.budget_baselined_by           IS 'Admin who baselined the budget.';
COMMENT ON COLUMN public.projects.contingency_at_groundbreaking IS 'Contingency amount at groundbreaking — denominator of the guardrail "contingency left %". Set by the Phase 5 checkpoint.';
COMMENT ON COLUMN public.projects.long_tail_reserve_amount      IS 'Fixed dollar reserve kept in contingency for open escrows and property taxes (per project). Used by the long-tail reserve check.';
COMMENT ON COLUMN public.projects.business_entity               IS 'bluonx (land / horizontal) or capstone (vertical). Drives the separate owner-dashboard views. NULL = not yet classified.';


-- ── B.3 contracts ───────────────────────────────────────────────────────────
ALTER TABLE public.contracts ADD COLUMN IF NOT EXISTS payment_terms_days INTEGER;
ALTER TABLE public.contracts ADD COLUMN IF NOT EXISTS retainage_percent  DECIMAL(5,2);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_contracts_payment_terms_days') THEN
    ALTER TABLE public.contracts ADD CONSTRAINT chk_contracts_payment_terms_days
      CHECK (payment_terms_days IS NULL OR payment_terms_days BETWEEN 0 AND 365);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_contracts_retainage_percent') THEN
    ALTER TABLE public.contracts ADD CONSTRAINT chk_contracts_retainage_percent
      CHECK (retainage_percent IS NULL OR retainage_percent BETWEEN 0 AND 100);
  END IF;
END $$;

COMMENT ON COLUMN public.contracts.payment_terms_days IS 'Numeric payment terms in days used by cash flow. NULL = line / settings default (30). The legacy free-text payment_terms column is unchanged.';
COMMENT ON COLUMN public.contracts.retainage_percent  IS 'Retainage held back on progress payments, % of each payment. NULL = no retainage.';


-- ============================================================================
-- SECTION C: NEW TABLES
-- ============================================================================

-- ========================================
-- GROUP 9: BUDGET STRUCTURE (4 tables)
-- ========================================

-- 9.1 budget_templates ─ the standard budget layout
CREATE TABLE IF NOT EXISTS public.budget_templates (
  id           UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  name         VARCHAR(255)  NOT NULL,
  description  TEXT,
  is_default   BOOLEAN       NOT NULL DEFAULT FALSE,
  is_active    BOOLEAN       NOT NULL DEFAULT TRUE,
  created_by   UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at   TIMESTAMPTZ,

  CONSTRAINT chk_budget_templates_name_not_blank CHECK (btrim(name) <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_budget_templates_one_default
  ON public.budget_templates (is_default)
  WHERE is_default = TRUE AND is_active = TRUE AND deleted_at IS NULL;

COMMENT ON TABLE  public.budget_templates            IS 'Standard budget layouts maintained by admins. Applied when a project budget is created; later template edits never change existing budgets.';
COMMENT ON COLUMN public.budget_templates.is_default IS 'The template applied to new budgets. At most one active, non-deleted default (partial unique index).';
COMMENT ON COLUMN public.budget_templates.deleted_at IS 'Soft delete. NULL = active record.';


-- 9.2 budget_template_lines ─ ordered rows of a template
CREATE TABLE IF NOT EXISTS public.budget_template_lines (
  id                          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  budget_template_id          UUID          NOT NULL REFERENCES public.budget_templates(id) ON DELETE CASCADE,
  line_type                   VARCHAR(20)   NOT NULL
                                            CHECK (line_type IN ('land', 'bid_activity', 'internal_tm', 'permit',
                                                                 'impact_fee', 'soft_cost', 'contingency', 'long_tail')),
  line_subtype                VARCHAR(30)
                                            CHECK (line_subtype IS NULL OR line_subtype IN (
                                                     'land_purchase', 'earnest_money', 'due_diligence', 'engineering',
                                                     'escrow_bond_premium', 'escrow_repairs', 'property_tax', 'other')),
  name                        VARCHAR(255)  NOT NULL CHECK (btrim(name) <> ''),
  section_name                VARCHAR(100),
  trade_id                    UUID          REFERENCES public.trades(id) ON DELETE RESTRICT,
  task_template_id            UUID,
  sort_order                  INTEGER       NOT NULL DEFAULT 0,
  default_amount              DECIMAL(15,2) CHECK (default_amount IS NULL OR default_amount >= 0),
  default_payment_terms_days  INTEGER       CHECK (default_payment_terms_days IS NULL OR default_payment_terms_days BETWEEN 0 AND 365),
  default_cash_bucket         VARCHAR(30)   CHECK (default_cash_bucket IS NULL OR default_cash_bucket IN ('land', 'vertical_construction', 'overhead')),
  is_active                   BOOLEAN       NOT NULL DEFAULT TRUE,
  created_at                  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at                  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- task_templates is a newer table; link to it only where it exists.
DO $$
BEGIN
  IF to_regclass('public.task_templates') IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_budget_template_lines_task_template') THEN
    ALTER TABLE public.budget_template_lines ADD CONSTRAINT fk_budget_template_lines_task_template
      FOREIGN KEY (task_template_id) REFERENCES public.task_templates(id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_budget_template_lines_template ON public.budget_template_lines (budget_template_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_budget_template_lines_trade    ON public.budget_template_lines (trade_id) WHERE trade_id IS NOT NULL;

COMMENT ON TABLE  public.budget_template_lines                  IS 'Ordered lines of a budget template, from land acquisition down to escrows and property taxes. Copied into budget_lines when a budget is created.';
COMMENT ON COLUMN public.budget_template_lines.section_name     IS 'Heading the line sits under in the budget view (e.g. Land, Soft costs, Site work, Long-tail).';
COMMENT ON COLUMN public.budget_template_lines.task_template_id IS 'Optional link to task_templates (FK added only when that table exists).';
COMMENT ON COLUMN public.budget_template_lines.sort_order       IS 'Top-to-bottom order in the standard layout.';


-- 9.3 budget_lines ─ THE core financial table
CREATE TABLE IF NOT EXISTS public.budget_lines (
  id                       UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id               UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  task_id                  UUID          REFERENCES public.tasks(id) ON DELETE RESTRICT,
  template_line_id         UUID          REFERENCES public.budget_template_lines(id) ON DELETE SET NULL,
  parent_line_id           UUID          REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  line_type                VARCHAR(20)   NOT NULL
                                         CHECK (line_type IN ('land', 'bid_activity', 'internal_tm', 'permit', 'impact_fee',
                                                              'soft_cost', 'contingency', 'variance', 'long_tail')),
  line_subtype             VARCHAR(30)
                                         CHECK (line_subtype IS NULL OR line_subtype IN (
                                                  'land_purchase', 'earnest_money', 'due_diligence', 'engineering',
                                                  'escrow_bond_premium', 'escrow_repairs', 'property_tax', 'other')),
  name                     VARCHAR(255)  NOT NULL CHECK (btrim(name) <> ''),
  description              TEXT,
  section_name             VARCHAR(100),
  sort_order               INTEGER       NOT NULL DEFAULT 0,
  original_estimate        DECIMAL(15,2) CHECK (original_estimate IS NULL OR original_estimate >= 0),
  budget_amount            DECIMAL(15,2) NOT NULL DEFAULT 0,
  committed_amount         DECIMAL(15,2) NOT NULL DEFAULT 0 CHECK (committed_amount >= 0),
  pre_award_budget_amount  DECIMAL(15,2) CHECK (pre_award_budget_amount IS NULL OR pre_award_budget_amount >= 0),
  award_id                 UUID          REFERENCES public.awards(id) ON DELETE RESTRICT,
  contract_id              UUID          REFERENCES public.contracts(id) ON DELETE RESTRICT,
  is_locked                BOOLEAN       NOT NULL DEFAULT FALSE,
  locked_at                TIMESTAMPTZ,
  locked_by                UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  lock_reason              TEXT,
  anticipated_start_date   DATE,
  anticipated_end_date     DATE,
  payment_terms_days       INTEGER       NOT NULL DEFAULT 30 CHECK (payment_terms_days BETWEEN 0 AND 365),
  cash_bucket              VARCHAR(30)   NOT NULL DEFAULT 'land'
                                         CHECK (cash_bucket IN ('land', 'vertical_construction', 'overhead')),
  approval_state           VARCHAR(20)   NOT NULL DEFAULT 'not_requested'
                                         CHECK (approval_state IN ('not_requested', 'pending', 'field_approved',
                                                                   'manager_approved', 'sent_to_finance', 'rejected')),
  is_payment_exempt        BOOLEAN       NOT NULL DEFAULT FALSE,
  created_by               UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  updated_by               UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at               TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at               TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at               TIMESTAMPTZ,

  -- Contingency is the only line that may go negative (that is what the
  -- urgent "negative contingency" alert detects).
  CONSTRAINT chk_budget_lines_amount_nonneg
    CHECK (line_type = 'contingency' OR budget_amount >= 0),
  CONSTRAINT chk_budget_lines_dates
    CHECK (anticipated_start_date IS NULL OR anticipated_end_date IS NULL
           OR anticipated_end_date >= anticipated_start_date),
  -- Only bid / internal activity lines are tied to a task.
  CONSTRAINT chk_budget_lines_task_type
    CHECK (task_id IS NULL OR line_type IN ('bid_activity', 'internal_tm')),
  -- A variance always hangs under its activity line.
  CONSTRAINT chk_budget_lines_variance_parent
    CHECK (line_type <> 'variance' OR parent_line_id IS NOT NULL),
  CONSTRAINT chk_budget_lines_parent_not_self
    CHECK (parent_line_id IS NULL OR parent_line_id <> id),
  -- Land and contingency never go through the payment workflow.
  CONSTRAINT chk_budget_lines_exempt_types
    CHECK (line_type NOT IN ('land', 'contingency') OR is_payment_exempt = TRUE),
  CONSTRAINT chk_budget_lines_lock_fields
    CHECK (is_locked = FALSE OR locked_at IS NOT NULL)
);

-- One live budget line per task (task_id nullable; soft-deleted lines free the task).
CREATE UNIQUE INDEX IF NOT EXISTS uq_budget_lines_task
  ON public.budget_lines (task_id)
  WHERE task_id IS NOT NULL AND deleted_at IS NULL;

-- Exactly one live contingency line per project.
CREATE UNIQUE INDEX IF NOT EXISTS uq_budget_lines_one_contingency_per_project
  ON public.budget_lines (project_id)
  WHERE line_type = 'contingency' AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_budget_lines_project_sort ON public.budget_lines (project_id, sort_order) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_budget_lines_project_type ON public.budget_lines (project_id, line_type) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_budget_lines_parent       ON public.budget_lines (parent_line_id) WHERE parent_line_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_budget_lines_award        ON public.budget_lines (award_id)       WHERE award_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_budget_lines_contract     ON public.budget_lines (contract_id)    WHERE contract_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_budget_lines_template_line ON public.budget_lines (template_line_id) WHERE template_line_id IS NOT NULL;

COMMENT ON TABLE  public.budget_lines                         IS 'Every line of a project budget. Bid / internal activity lines link 1:1 to an existing task; land, permit, impact fee, soft cost, contingency, variance and long-tail lines have no task. The contingency line''s budget_amount IS the live contingency balance. Once the project is baselined the SUM of live lines must equal projects.approved_budget_total (flat-budget rule).';
COMMENT ON COLUMN public.budget_lines.task_id                 IS 'Existing task this line represents (bid_activity ↔ competitive / direct_assign, internal_tm ↔ internal). Nullable; unique among non-deleted lines.';
COMMENT ON COLUMN public.budget_lines.parent_line_id          IS 'Variance → its activity line; also groups e.g. an engineering T&M portion under the engineering heading.';
COMMENT ON COLUMN public.budget_lines.line_type               IS 'land | bid_activity | internal_tm | permit | impact_fee | soft_cost | contingency | variance | long_tail.';
COMMENT ON COLUMN public.budget_lines.line_subtype             IS 'Finer classification: land_purchase, earnest_money, due_diligence, engineering, escrow_bond_premium, escrow_repairs, property_tax, other.';
COMMENT ON COLUMN public.budget_lines.original_estimate       IS 'Baseline estimate frozen when the budget is baselined (A21). Never changes afterwards. Feeds the budget accuracy report.';
COMMENT ON COLUMN public.budget_lines.budget_amount           IS 'Current budget for the line. After baseline it changes ONLY through financial procedures, always offset by contingency so the total stays flat.';
COMMENT ON COLUMN public.budget_lines.committed_amount        IS 'Amount committed by an accepted award (= award amount once fn_apply_bid_to_line runs).';
COMMENT ON COLUMN public.budget_lines.pre_award_budget_amount IS 'Budget amount just before the current award was applied. Used by fn_reverse_bid_on_line to restore the line if the award is declined / voided.';
COMMENT ON COLUMN public.budget_lines.award_id                IS 'Award currently applied to this line (set by fn_apply_bid_to_line, cleared by fn_reverse_bid_on_line).';
COMMENT ON COLUMN public.budget_lines.contract_id             IS 'Executed contract that locked this line (fn_lock_budget_line).';
COMMENT ON COLUMN public.budget_lines.is_locked               IS 'TRUE once the contract is executed. Locked amounts cannot be edited; later changes only via variance lines.';
COMMENT ON COLUMN public.budget_lines.anticipated_start_date  IS 'Planned start — cash-flow input.';
COMMENT ON COLUMN public.budget_lines.anticipated_end_date    IS 'Planned end — cash-flow input (cash recognised end + payment terms).';
COMMENT ON COLUMN public.budget_lines.payment_terms_days      IS 'Days between work completion / approval and cash out. Default 30.';
COMMENT ON COLUMN public.budget_lines.cash_bucket             IS 'Cash-out bucket: land (incl. development crews, escrows, taxes), vertical_construction, overhead.';
COMMENT ON COLUMN public.budget_lines.approval_state          IS 'Roll-up of the payment approval state for the line. Detail lives in payment_approvals.';
COMMENT ON COLUMN public.budget_lines.is_payment_exempt       IS 'TRUE for land (title company / bank) and contingency (never paid against).';
COMMENT ON COLUMN public.budget_lines.deleted_at              IS 'Soft delete (lines not needed are removed; the budget doubles as a checklist).';


-- 9.4 land_closings ─ phased takedowns under a land-purchase line
CREATE TABLE IF NOT EXISTS public.land_closings (
  id                    UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  budget_line_id        UUID          NOT NULL REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  closing_sequence      INTEGER       NOT NULL CHECK (closing_sequence >= 1),
  acres                 DECIMAL(12,4) CHECK (acres IS NULL OR acres >= 0),
  amount                DECIMAL(15,2) NOT NULL CHECK (amount >= 0),
  planned_closing_date  DATE          NOT NULL,
  actual_closing_date   DATE,
  status                VARCHAR(20)   NOT NULL DEFAULT 'planned'
                                      CHECK (status IN ('planned', 'closed', 'cancelled')),
  notes                 TEXT,
  created_by            UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_land_closings_sequence UNIQUE (budget_line_id, closing_sequence)
);

CREATE INDEX IF NOT EXISTS idx_land_closings_project ON public.land_closings (project_id);

COMMENT ON TABLE  public.land_closings                     IS 'Phased land takedowns (e.g. 40 of 100 acres now, 60 acres later). Each closing feeds cash flow on its own date.';
COMMENT ON COLUMN public.land_closings.budget_line_id      IS 'The land_purchase budget line this closing belongs to.';
COMMENT ON COLUMN public.land_closings.closing_sequence    IS '1 = first takedown, 2 = second … unique per land line.';
COMMENT ON COLUMN public.land_closings.planned_closing_date IS 'Planned closing date (cash-flow month).';


-- ========================================
-- GROUP 10: CONTINGENCY (3 tables)
-- ========================================

-- 10.1 contingency_buckets ─ every funding source, incl. top-up requests
CREATE TABLE IF NOT EXISTS public.contingency_buckets (
  id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id           UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  contingency_line_id  UUID          NOT NULL REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  bucket_kind          VARCHAR(20)   NOT NULL CHECK (bucket_kind IN ('initial', 'top_up')),
  requested_amount     DECIMAL(15,2) NOT NULL CHECK (requested_amount >= 0),
  approved_amount      DECIMAL(15,2) CHECK (approved_amount IS NULL OR approved_amount >= 0),
  status               VARCHAR(20)   NOT NULL DEFAULT 'pending'
                                     CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
  reason               TEXT          NOT NULL CHECK (btrim(reason) <> ''),
  requested_by         UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  requested_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  decided_by           UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  decided_at           TIMESTAMPTZ,
  decision_note        TEXT,
  created_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_contingency_buckets_topup_positive
    CHECK (bucket_kind = 'initial' OR requested_amount > 0),
  CONSTRAINT chk_contingency_buckets_approved_fields
    CHECK (status <> 'approved' OR (approved_amount IS NOT NULL AND decided_by IS NOT NULL AND decided_at IS NOT NULL)),
  CONSTRAINT chk_contingency_buckets_rejected_fields
    CHECK (status <> 'rejected' OR (decided_by IS NOT NULL AND decided_at IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_contingency_buckets_one_initial
  ON public.contingency_buckets (project_id) WHERE bucket_kind = 'initial';
CREATE INDEX IF NOT EXISTS idx_contingency_buckets_project ON public.contingency_buckets (project_id, status);

COMMENT ON TABLE  public.contingency_buckets                 IS 'Funding sources of a project''s contingency: the initial bucket (at baseline) and every top-up request with its executive decision. The balance itself lives on the single contingency budget line; each approved bucket also has a contingency_ledger row.';
COMMENT ON COLUMN public.contingency_buckets.bucket_kind     IS 'initial = funded at baseline; top_up = executive-approved increase (recorded separately for audit).';
COMMENT ON COLUMN public.contingency_buckets.status          IS 'pending → approved | rejected | cancelled. Approve / reject only via fn_approve_contingency_top_up (executive role).';
COMMENT ON COLUMN public.contingency_buckets.approved_amount IS 'Amount actually approved (may differ from requested).';


-- 10.2 contingency_ledger ─ APPEND-ONLY record of every contingency movement
CREATE TABLE IF NOT EXISTS public.contingency_ledger (
  id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  entry_no               BIGINT        GENERATED ALWAYS AS IDENTITY UNIQUE,
  project_id            UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  contingency_line_id    UUID          NOT NULL REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  contingency_bucket_id  UUID          REFERENCES public.contingency_buckets(id) ON DELETE RESTRICT,
  movement_type          VARCHAR(30)   NOT NULL
                                       CHECK (movement_type IN ('initial_funding', 'bid_overrun', 'bid_savings', 'bid_reversal',
                                                                'variance_created', 'variance_adjusted', 'variance_cancelled',
                                                                'top_up', 'invoice_overage')),
  amount                 DECIMAL(15,2) NOT NULL,
  balance_before         DECIMAL(15,2) NOT NULL,
  balance_after          DECIMAL(15,2) NOT NULL,
  source_budget_line_id  UUID          REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  variance_line_id       UUID,
  award_id               UUID          REFERENCES public.awards(id) ON DELETE RESTRICT,
  actor_user_id          UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  reason                 TEXT,
  created_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_contingency_ledger_balance  CHECK (balance_after = balance_before + amount),
  CONSTRAINT chk_contingency_ledger_nonzero  CHECK (amount <> 0 OR movement_type = 'initial_funding')
);

CREATE INDEX IF NOT EXISTS idx_contingency_ledger_project     ON public.contingency_ledger (project_id, entry_no DESC);
CREATE INDEX IF NOT EXISTS idx_contingency_ledger_source_line ON public.contingency_ledger (source_budget_line_id) WHERE source_budget_line_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contingency_ledger_variance    ON public.contingency_ledger (variance_line_id)      WHERE variance_line_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contingency_ledger_award       ON public.contingency_ledger (award_id)              WHERE award_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contingency_ledger_bucket      ON public.contingency_ledger (contingency_bucket_id) WHERE contingency_bucket_id IS NOT NULL;

COMMENT ON TABLE  public.contingency_ledger                IS 'Append-only audit ledger. One immutable row per contingency movement, always written by a financial stored procedure in the same transaction as the movement. UPDATE / DELETE / TRUNCATE blocked by trg_contingency_ledger_immutable (PT403).';
COMMENT ON COLUMN public.contingency_ledger.entry_no       IS 'Monotonic sequence number. Order the ledger by entry_no (several movements in one transaction share created_at).';
COMMENT ON COLUMN public.contingency_ledger.amount         IS 'Signed: + money INTO contingency (bid savings, adjustment down, top-up), − money OUT of contingency (bid overrun, new variance).';
COMMENT ON COLUMN public.contingency_ledger.balance_before IS 'Contingency line balance before this movement.';
COMMENT ON COLUMN public.contingency_ledger.balance_after  IS 'Contingency line balance after this movement (= before + amount, CHECK-enforced). Running balance for the ledger view.';
COMMENT ON COLUMN public.contingency_ledger.source_budget_line_id IS 'Budget line that caused the movement (bid line, variance line).';
COMMENT ON COLUMN public.contingency_ledger.actor_user_id  IS 'User on whose behalf the procedure ran (who).';


-- 10.3 variance_lines ─ field variance metadata (money is on its own budget line)
CREATE TABLE IF NOT EXISTS public.variance_lines (
  id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id             UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  budget_line_id         UUID          NOT NULL UNIQUE REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  parent_budget_line_id  UUID          NOT NULL REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  trade_id               UUID          REFERENCES public.trades(id) ON DELETE RESTRICT,
  vendor_id              UUID          REFERENCES public.vendors(id) ON DELETE RESTRICT,
  description            TEXT          NOT NULL CHECK (btrim(description) <> ''),
  estimated_amount       DECIMAL(15,2) NOT NULL CHECK (estimated_amount > 0),
  status                 VARCHAR(20)   NOT NULL DEFAULT 'pending_approval'
                                       CHECK (status IN ('draft', 'pending_approval', 'approved', 'rejected', 'cancelled')),
  created_by             UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  approved_by            UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  approved_at            TIMESTAMPTZ,
  rejected_by            UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  rejected_at            TIMESTAMPTZ,
  rejection_reason       TEXT,
  created_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at             TIMESTAMPTZ,

  -- The person who created a variance can never approve it.
  CONSTRAINT chk_variance_lines_not_self_approved CHECK (approved_by IS NULL OR approved_by <> created_by),
  CONSTRAINT chk_variance_lines_approved_fields   CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)),
  CONSTRAINT chk_variance_lines_parent_not_self   CHECK (parent_budget_line_id <> budget_line_id)
);

CREATE INDEX IF NOT EXISTS idx_variance_lines_project ON public.variance_lines (project_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_variance_lines_parent  ON public.variance_lines (parent_budget_line_id);
CREATE INDEX IF NOT EXISTS idx_variance_lines_trade   ON public.variance_lines (trade_id)  WHERE trade_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_variance_lines_vendor  ON public.variance_lines (vendor_id) WHERE vendor_id IS NOT NULL;

-- Ledger → variance FK (variance_lines created after contingency_ledger)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_contingency_ledger_variance') THEN
    ALTER TABLE public.contingency_ledger ADD CONSTRAINT fk_contingency_ledger_variance
      FOREIGN KEY (variance_line_id) REFERENCES public.variance_lines(id) ON DELETE RESTRICT;
  END IF;
END $$;

COMMENT ON TABLE  public.variance_lines                       IS 'Unforeseen field conditions (e.g. rock in the sanitary sewer). The amount lives on the variance''s own budget_lines row (line_type = variance), so totals, the flat-budget rule and cash flow treat it like any line. Created / adjusted only via fn_create_variance / fn_adjust_variance, which move contingency and write the ledger.';
COMMENT ON COLUMN public.variance_lines.budget_line_id        IS 'The variance''s own budget line (1:1). Its budget_amount is the current variance amount.';
COMMENT ON COLUMN public.variance_lines.parent_budget_line_id IS 'Activity line the variance sits under (e.g. sanitary sewer).';
COMMENT ON COLUMN public.variance_lines.estimated_amount      IS 'First estimate at creation (history). The current amount is on the variance budget line.';
COMMENT ON COLUMN public.variance_lines.status                IS 'draft | pending_approval | approved | rejected | cancelled. Approved and cancelled variances are frozen; a further change needs a new variance.';


-- ========================================
-- GROUP 11: PAYMENTS & FINANCE HAND-OFF (3 tables)
-- ========================================

-- 11.1 internal_invoices ─ incoming invoices for internal T&M lines
CREATE TABLE IF NOT EXISTS public.internal_invoices (
  id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id       UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  budget_line_id   UUID          REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  vendor_id        UUID          REFERENCES public.vendors(id) ON DELETE RESTRICT,
  payee_name       VARCHAR(255),
  invoice_number   VARCHAR(100),
  invoice_date     DATE,
  amount           DECIMAL(15,2) NOT NULL CHECK (amount >= 0),
  file_path        TEXT          NOT NULL,
  file_name        VARCHAR(255)  NOT NULL,
  file_size        BIGINT        CHECK (file_size IS NULL OR file_size >= 0),
  status           VARCHAR(20)   NOT NULL DEFAULT 'received'
                                 CHECK (status IN ('received', 'categorised', 'in_approval', 'approved', 'rejected', 'cancelled')),
  notes            TEXT,
  uploaded_by      UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at       TIMESTAMPTZ,

  CONSTRAINT chk_internal_invoices_payee CHECK (vendor_id IS NOT NULL OR payee_name IS NOT NULL),
  CONSTRAINT chk_internal_invoices_categorised CHECK (status IN ('received', 'cancelled') OR budget_line_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_internal_invoices_project ON public.internal_invoices (project_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_internal_invoices_line    ON public.internal_invoices (budget_line_id) WHERE budget_line_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_internal_invoices_vendor  ON public.internal_invoices (vendor_id)      WHERE vendor_id IS NOT NULL;

COMMENT ON TABLE  public.internal_invoices                IS 'Invoices received for internal T&M lines (e.g. attorney). Categorised against a budget line, then sent through payment approval. An invoice over its line allowance creates a variance (Phase 2).';
COMMENT ON COLUMN public.internal_invoices.file_path      IS 'Path in Supabase Storage (finance-documents private bucket).';
COMMENT ON COLUMN public.internal_invoices.budget_line_id IS 'Line the invoice is categorised to. NULL while status = received.';


-- 11.2 payment_approvals ─ one approval request per payment
CREATE TABLE IF NOT EXISTS public.payment_approvals (
  id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id             UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  budget_line_id         UUID          NOT NULL REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  internal_invoice_id    UUID          REFERENCES public.internal_invoices(id) ON DELETE RESTRICT,
  vendor_id              UUID          REFERENCES public.vendors(id) ON DELETE RESTRICT,
  amount                 DECIMAL(15,2) NOT NULL CHECK (amount > 0),
  payment_kind           VARCHAR(20)   NOT NULL DEFAULT 'full'
                                       CHECK (payment_kind IN ('full', 'progress', 'retainage_release')),
  progress_percent       DECIMAL(5,2)  CHECK (progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100),
  retainage_amount       DECIMAL(15,2) CHECK (retainage_amount IS NULL OR retainage_amount >= 0),
  status                 VARCHAR(20)   NOT NULL DEFAULT 'pending'
                                       CHECK (status IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive',
                                                         'approved', 'sent_to_finance', 'rejected', 'cancelled')),
  requested_by           UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  field_approved_by      UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  field_approved_at      TIMESTAMPTZ,
  routed_to_user_id      UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  manager_approved_by    UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  manager_approved_at    TIMESTAMPTZ,
  executive_approved_by  UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  executive_approved_at  TIMESTAMPTZ,
  rejected_by            UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  rejected_at            TIMESTAMPTZ,
  rejection_reason       TEXT,
  comments               TEXT,
  expected_payment_date  DATE,
  created_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  -- Two-person rule: the second approval is always a different person.
  CONSTRAINT chk_payment_approvals_two_person_manager
    CHECK (manager_approved_by IS NULL OR field_approved_by IS NULL OR manager_approved_by <> field_approved_by),
  CONSTRAINT chk_payment_approvals_two_person_executive
    CHECK (executive_approved_by IS NULL OR field_approved_by IS NULL OR executive_approved_by <> field_approved_by),
  CONSTRAINT chk_payment_approvals_progress
    CHECK (payment_kind <> 'progress' OR progress_percent IS NOT NULL),
  CONSTRAINT chk_payment_approvals_rejected_fields
    CHECK (status <> 'rejected' OR (rejected_by IS NOT NULL AND rejected_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_payment_approvals_project  ON public.payment_approvals (project_id, status);
CREATE INDEX IF NOT EXISTS idx_payment_approvals_line     ON public.payment_approvals (budget_line_id);
CREATE INDEX IF NOT EXISTS idx_payment_approvals_routed   ON public.payment_approvals (routed_to_user_id, status) WHERE routed_to_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payment_approvals_invoice  ON public.payment_approvals (internal_invoice_id) WHERE internal_invoice_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payment_approvals_vendor   ON public.payment_approvals (vendor_id) WHERE vendor_id IS NOT NULL;

COMMENT ON TABLE  public.payment_approvals                       IS 'Approve-for-payment requests on bid, variance and internal invoice lines (full, progress or retainage release). Flow: pending → field_approved → awaiting_manager / awaiting_executive → approved → sent_to_finance. Two-person rule CHECK-enforced.';
COMMENT ON COLUMN public.payment_approvals.routed_to_user_id     IS 'Who the second approval is waiting on: reports_to manager, or the backup / delegate when the manager is unavailable.';
COMMENT ON COLUMN public.payment_approvals.expected_payment_date IS 'Final approval date + payment terms. Written to cash flow.';
COMMENT ON COLUMN public.payment_approvals.retainage_amount      IS 'Amount held back from this payment under the contract''s retainage terms.';


-- 11.3 finance_handoffs ─ what was sent to finance (internal invoice / PO record)
CREATE TABLE IF NOT EXISTS public.finance_handoffs (
  id                    UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  payment_approval_id   UUID          NOT NULL UNIQUE REFERENCES public.payment_approvals(id) ON DELETE RESTRICT,
  project_id            UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  po_number             VARCHAR(50)   NOT NULL UNIQUE,
  vendor_id             UUID          REFERENCES public.vendors(id) ON DELETE RESTRICT,
  amount                DECIMAL(15,2) NOT NULL CHECK (amount > 0),
  payload               JSONB         NOT NULL DEFAULT '{}'::jsonb,
  document_path         TEXT,
  email_log_id          UUID          REFERENCES public.email_log(id) ON DELETE SET NULL,
  status                VARCHAR(20)   NOT NULL DEFAULT 'pending'
                                      CHECK (status IN ('pending', 'sent', 'delivered', 'failed')),
  sent_at               TIMESTAMPTZ,
  exported_at           TIMESTAMPTZ,
  created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finance_handoffs_project ON public.finance_handoffs (project_id, status);
CREATE INDEX IF NOT EXISTS idx_finance_handoffs_email   ON public.finance_handoffs (email_log_id) WHERE email_log_id IS NOT NULL;

COMMENT ON TABLE  public.finance_handoffs               IS 'Finance hand-off log: one row per finally-approved payment with its internal invoice / PO record. Finance pays outside the system; delivery is proven by email_log.';
COMMENT ON COLUMN public.finance_handoffs.payload       IS 'Snapshot sent to finance: trade, amount, project, activity, date, approvers, contract number.';
COMMENT ON COLUMN public.finance_handoffs.document_path IS 'Generated PO / internal invoice PDF in the finance-documents bucket.';
COMMENT ON COLUMN public.finance_handoffs.email_log_id  IS 'The finance email in email_log (delivery status = audit proof).';


-- ========================================
-- GROUP 12: LONG-TAIL ITEMS (2 tables)
-- ========================================

-- 12.1 escrows
CREATE TABLE IF NOT EXISTS public.escrows (
  id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  name              VARCHAR(255)  NOT NULL CHECK (btrim(name) <> ''),
  beneficiary       VARCHAR(20)   NOT NULL CHECK (beneficiary IN ('city', 'county', 'hoa', 'other')),
  covered_areas     TEXT[]        NOT NULL DEFAULT '{}',
  security_form     VARCHAR(10)   NOT NULL CHECK (security_form IN ('cash', 'bond')),
  holder_type       VARCHAR(30)   CHECK (holder_type IS NULL OR holder_type IN ('insurance_company', 'bank', 'other')),
  holder_name       VARCHAR(255),
  secured_amount    DECIMAL(15,2) NOT NULL CHECK (secured_amount >= 0),
  premium_amount    DECIMAL(15,2) CHECK (premium_amount IS NULL OR premium_amount >= 0),
  bond_number       VARCHAR(100),
  bond_expiry_date  DATE,
  status            VARCHAR(20)   NOT NULL DEFAULT 'planned'
                                  CHECK (status IN ('planned', 'posted', 'works_built', 'inspection', 'corrections',
                                                    'signed_off', 'released', 'cancelled')),
  posted_date       DATE,
  released_date     DATE,
  premium_line_id   UUID          REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  repair_line_id    UUID          REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  document_path     TEXT,
  notes             TEXT,
  created_by        UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at        TIMESTAMPTZ,

  CONSTRAINT chk_escrows_release_after_post CHECK (released_date IS NULL OR posted_date IS NULL OR released_date >= posted_date),
  CONSTRAINT chk_escrows_released_has_date  CHECK (status <> 'released' OR released_date IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_escrows_project ON public.escrows (project_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_escrows_bond_expiry ON public.escrows (bond_expiry_date) WHERE bond_expiry_date IS NOT NULL AND deleted_at IS NULL;

COMMENT ON TABLE  public.escrows                  IS 'Escrows posted for public / HOA works (roads to the city; landscaping, trails, common areas to the HOA). Each carries two cost lines: the bond / insurance premium and repairs to city standard. Lifecycle posted → works_built → inspection → corrections → signed_off → released.';
COMMENT ON COLUMN public.escrows.covered_areas    IS 'One escrow may cover several areas, e.g. {roads} or {landscaping, trails, benches}.';
COMMENT ON COLUMN public.escrows.security_form    IS 'cash = cash posted (cash out, back in on release); bond = insurance policy equal to the value of the works.';
COMMENT ON COLUMN public.escrows.secured_amount   IS 'Value of the works the escrow secures (e.g. $10k bond for $10k of roads).';
COMMENT ON COLUMN public.escrows.premium_line_id  IS 'Cost 1: budget line for the bond / insurance premium.';
COMMENT ON COLUMN public.escrows.repair_line_id   IS 'Cost 2: budget line for repairs to city standard found at the inspection walk.';
COMMENT ON COLUMN public.escrows.bond_expiry_date IS 'Bond expiry — drives renewal reminders while the escrow is open.';


-- 12.2 property_taxes
CREATE TABLE IF NOT EXISTS public.property_taxes (
  id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id             UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  budget_line_id         UUID          REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  tax_year               INTEGER       NOT NULL CHECK (tax_year BETWEEN 2000 AND 2200),
  jurisdiction           VARCHAR(150)  NOT NULL CHECK (btrim(jurisdiction) <> ''),
  parcel_reference       VARCHAR(100),
  installment_number     INTEGER       NOT NULL DEFAULT 1 CHECK (installment_number >= 1),
  due_date               DATE,
  estimate_basis         VARCHAR(20)   NOT NULL DEFAULT 'manual'
                                       CHECK (estimate_basis IN ('prior_year_actual', 'assessed_value', 'manual')),
  estimated_amount       DECIMAL(15,2) NOT NULL CHECK (estimated_amount >= 0),
  actual_amount          DECIMAL(15,2) CHECK (actual_amount IS NULL OR actual_amount >= 0),
  sold_portion_percent   DECIMAL(5,2)  CHECK (sold_portion_percent IS NULL OR sold_portion_percent BETWEEN 0 AND 100),
  status                 VARCHAR(20)   NOT NULL DEFAULT 'estimated'
                                       CHECK (status IN ('estimated', 'billed', 'in_approval', 'sent_to_finance', 'cancelled')),
  notes                  TEXT,
  created_by             UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_property_taxes_installment UNIQUE (project_id, tax_year, jurisdiction, installment_number)
);

CREATE INDEX IF NOT EXISTS idx_property_taxes_due ON public.property_taxes (due_date) WHERE status IN ('estimated', 'billed');

COMMENT ON TABLE  public.property_taxes                      IS 'Yearly property tax for each year the land is owned, per jurisdiction and instalment. Estimated internally; estimate vs actual tracked to catch increases; reduced as lots sell.';
COMMENT ON COLUMN public.property_taxes.estimate_basis       IS 'prior_year_actual | assessed_value | manual (entered by finance).';
COMMENT ON COLUMN public.property_taxes.sold_portion_percent IS 'Share of the land already sold — the tax line is reduced for it.';


-- ========================================
-- GROUP 13: CASH FLOW (3 tables)
-- ========================================

-- 13.1 accounting_periods ─ company-wide months
CREATE TABLE IF NOT EXISTS public.accounting_periods (
  id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  period_month  DATE          NOT NULL UNIQUE CHECK (EXTRACT(DAY FROM period_month) = 1),
  status        VARCHAR(10)   NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
  closed_by     UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  closed_at     TIMESTAMPTZ,
  notes         TEXT,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_accounting_periods_closed_fields CHECK (status <> 'closed' OR (closed_by IS NOT NULL AND closed_at IS NOT NULL))
);

COMMENT ON TABLE  public.accounting_periods              IS 'Company-wide accounting months. A closed month is never changed retroactively: cash_flow_entries in it are frozen. Closed only via fn_close_accounting_month (finance / executive); never reopened.';
COMMENT ON COLUMN public.accounting_periods.period_month IS 'First day of the month (e.g. 2027-01-01).';


-- 13.2 company_cash_items ─ overhead, deposits, closings (manual / CSV)
CREATE TABLE IF NOT EXISTS public.company_cash_items (
  id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  item_type        VARCHAR(30)   NOT NULL CHECK (item_type IN ('overhead', 'deposit', 'closing', 'vertical_construction', 'other')),
  direction        VARCHAR(3)    NOT NULL CHECK (direction IN ('out', 'in')),
  cash_bucket      VARCHAR(30)   NOT NULL CHECK (cash_bucket IN ('land', 'vertical_construction', 'overhead', 'deposits', 'closings')),
  business_entity  VARCHAR(20)   CHECK (business_entity IS NULL OR business_entity IN ('bluonx', 'capstone')),
  project_id       UUID          REFERENCES public.projects(id) ON DELETE RESTRICT,
  description      VARCHAR(255)  NOT NULL CHECK (btrim(description) <> ''),
  period_month     DATE          NOT NULL CHECK (EXTRACT(DAY FROM period_month) = 1),
  amount           DECIMAL(15,2) NOT NULL CHECK (amount >= 0),
  source           VARCHAR(20)   NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'csv_import')),
  created_by       UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_company_cash_items_month   ON public.company_cash_items (period_month, cash_bucket) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_company_cash_items_project ON public.company_cash_items (project_id) WHERE project_id IS NOT NULL;

COMMENT ON TABLE  public.company_cash_items           IS 'Company-level cash items not tied to a budget line: overhead (salaries, insurance), customer deposits, closings, vertical construction. Entered manually or by CSV import. Finance-restricted.';
COMMENT ON COLUMN public.company_cash_items.direction IS 'out = cash leaving the account; in = cash arriving (deposits, closings).';


-- 13.3 cash_flow_entries ─ monthly cash schedule
CREATE TABLE IF NOT EXISTS public.cash_flow_entries (
  id                    UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            UUID          REFERENCES public.projects(id) ON DELETE RESTRICT,
  budget_line_id        UUID          REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  land_closing_id       UUID          REFERENCES public.land_closings(id) ON DELETE RESTRICT,
  escrow_id             UUID          REFERENCES public.escrows(id) ON DELETE RESTRICT,
  payment_approval_id   UUID          REFERENCES public.payment_approvals(id) ON DELETE RESTRICT,
  company_cash_item_id  UUID          REFERENCES public.company_cash_items(id) ON DELETE RESTRICT,
  period_month          DATE          NOT NULL CHECK (EXTRACT(DAY FROM period_month) = 1),
  direction             VARCHAR(3)    NOT NULL CHECK (direction IN ('out', 'in')),
  cash_bucket           VARCHAR(30)   NOT NULL CHECK (cash_bucket IN ('land', 'vertical_construction', 'overhead', 'deposits', 'closings')),
  amount                DECIMAL(15,2) NOT NULL CHECK (amount >= 0),
  entry_kind            VARCHAR(10)   NOT NULL DEFAULT 'forecast' CHECK (entry_kind IN ('forecast', 'expected', 'actual')),
  source_note           TEXT,
  created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_cash_flow_entries_has_source CHECK (
    budget_line_id IS NOT NULL OR land_closing_id IS NOT NULL OR escrow_id IS NOT NULL
    OR payment_approval_id IS NOT NULL OR company_cash_item_id IS NOT NULL
  )
);

CREATE INDEX IF NOT EXISTS idx_cash_flow_entries_month   ON public.cash_flow_entries (period_month, cash_bucket);
CREATE INDEX IF NOT EXISTS idx_cash_flow_entries_project ON public.cash_flow_entries (project_id, period_month) WHERE project_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cash_flow_entries_line    ON public.cash_flow_entries (budget_line_id)       WHERE budget_line_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cash_flow_entries_closing ON public.cash_flow_entries (land_closing_id)      WHERE land_closing_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cash_flow_entries_escrow  ON public.cash_flow_entries (escrow_id)            WHERE escrow_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cash_flow_entries_payment ON public.cash_flow_entries (payment_approval_id)  WHERE payment_approval_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cash_flow_entries_company ON public.cash_flow_entries (company_cash_item_id) WHERE company_cash_item_id IS NOT NULL;

COMMENT ON TABLE  public.cash_flow_entries              IS 'Monthly cash schedule (macro, not day-level). Generated from line dates + payment terms, land closings, escrow postings / releases, approved payments and company items. Rows in a closed accounting month are frozen (trg_cash_flow_entries_closed_period).';
COMMENT ON COLUMN public.cash_flow_entries.period_month IS 'First day of the month the cash moves in.';
COMMENT ON COLUMN public.cash_flow_entries.entry_kind   IS 'forecast = from line dates; expected = from an approved payment''s expected date; actual = confirmed (optional).';


-- ========================================
-- GROUP 14: SETTINGS, ALERTS & ROLES (4 tables)
-- ========================================

-- 14.1 financial_settings ─ key / value (typed JSON)
CREATE TABLE IF NOT EXISTS public.financial_settings (
  setting_key  VARCHAR(100)  PRIMARY KEY CHECK (setting_key ~ '^[a-z][a-z0-9_]*$'),
  value        JSONB         NOT NULL,
  description  TEXT,
  updated_by   UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  public.financial_settings       IS 'Organisation-wide financial settings (contingency %, targets, limits, thresholds, notification recipients). Key / value so a new setting never needs a migration.';
COMMENT ON COLUMN public.financial_settings.value IS 'JSON value: number, string, array or object depending on the key (see description).';


-- 14.2 financial_alerts ─ guardrail alerts and their decisions
CREATE TABLE IF NOT EXISTS public.financial_alerts (
  id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id             UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  alert_type             VARCHAR(30)   NOT NULL
                                       CHECK (alert_type IN ('contingency_health', 'contingency_near_zero', 'contingency_negative',
                                                             'long_tail_reserve', 'bidding_checkpoint')),
  severity               VARCHAR(10)   NOT NULL CHECK (severity IN ('warning', 'urgent', 'critical')),
  status                 VARCHAR(20)   NOT NULL DEFAULT 'open'
                                       CHECK (status IN ('open', 'acknowledged', 'proceed_approved', 'on_hold', 'resolved', 'superseded')),
  contingency_left_pct   DECIMAL(7,2),
  work_left_pct          DECIMAL(7,2),
  contingency_remaining  DECIMAL(15,2),
  reserve_required       DECIMAL(15,2),
  message                TEXT,
  decision               VARCHAR(10)   CHECK (decision IS NULL OR decision IN ('proceed', 'hold')),
  decision_reason        TEXT,
  decided_by             UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  decided_at             TIMESTAMPTZ,
  resolved_at            TIMESTAMPTZ,
  created_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_financial_alerts_decision_fields
    CHECK (decision IS NULL OR (decided_by IS NOT NULL AND decided_at IS NOT NULL AND btrim(COALESCE(decision_reason, '')) <> ''))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_financial_alerts_one_open
  ON public.financial_alerts (project_id, alert_type) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_financial_alerts_project ON public.financial_alerts (project_id, created_at DESC);

COMMENT ON TABLE  public.financial_alerts                 IS 'Contingency guardrail alerts (health, near zero, negative, long-tail reserve, bidding checkpoint) with the snapshot that triggered them and the manager''s recorded OK-to-proceed / hold decision. One open alert per project and type.';
COMMENT ON COLUMN public.financial_alerts.decision        IS 'proceed = work continues (reason logged); hold = project placed on the existing on_hold status.';
COMMENT ON COLUMN public.financial_alerts.decision_reason IS 'Required whenever a decision is recorded.';


-- 14.3 user_roles ─ many roles per user
CREATE TABLE IF NOT EXISTS public.user_roles (
  id           UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  role         VARCHAR(20)   NOT NULL
                             CHECK (role IN ('admin', 'project_manager', 'field_manager', 'executive', 'finance')),
  granted_by   UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  granted_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  revoked_at   TIMESTAMPTZ,
  revoked_by   UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_roles_active
  ON public.user_roles (user_id, role) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON public.user_roles (role) WHERE revoked_at IS NULL;

COMMENT ON TABLE  public.user_roles            IS 'Roles held by each user. One person may hold several (e.g. executive + manager). Base role mirrors users.role (sync trigger); financial roles field_manager / executive / finance are granted here. Revoke = set revoked_at (never deleted, for audit).';
COMMENT ON COLUMN public.user_roles.role       IS 'admin | project_manager | field_manager | executive | finance.';
COMMENT ON COLUMN public.user_roles.revoked_at IS 'NULL = role active. Partial unique index allows re-granting after a revoke.';


-- 14.4 approval_delegations ─ temporary delegation while a manager is away
CREATE TABLE IF NOT EXISTS public.approval_delegations (
  id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  delegator_user_id  UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  delegate_user_id   UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  starts_at          TIMESTAMPTZ   NOT NULL,
  ends_at            TIMESTAMPTZ   NOT NULL,
  reason             TEXT,
  created_by         UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  revoked_at         TIMESTAMPTZ,
  created_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_approval_delegations_window  CHECK (ends_at > starts_at),
  CONSTRAINT chk_approval_delegations_not_self CHECK (delegator_user_id <> delegate_user_id)
);

CREATE INDEX IF NOT EXISTS idx_approval_delegations_delegator ON public.approval_delegations (delegator_user_id, starts_at, ends_at) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_approval_delegations_delegate  ON public.approval_delegations (delegate_user_id) WHERE revoked_at IS NULL;

COMMENT ON TABLE  public.approval_delegations          IS 'Temporary hand-over of a manager''s approvals to another user for a time window (holiday, sick leave). Overrides users.backup_approver_id while active.';
COMMENT ON COLUMN public.approval_delegations.ends_at  IS 'Exclusive end of the delegation window.';


-- ============================================================================
-- SECTION D: TYPE VOCABULARIES (email_log, notifications)
-- ============================================================================

-- D.1 email_log.email_type — widen the CHECK to a SUPERSET.
--     The new list = planned values ∪ every value already present in the
--     table, so validation can never fail on production data. The old
--     constraint is found by definition (name differs between environments).
DO $$
DECLARE
  v_planned  TEXT[] := ARRAY[
    -- existing (Phase 1 bid system)
    'bid_invitation', 'bid_reminder', 'award_notification', 'decline_notification',
    'milestone_alert', 'general',
    -- financial
    'payment_approval_request', 'payment_approved', 'payment_rejected',
    'finance_handoff', 'finance_daily_summary',
    'contingency_alert', 'contingency_escalation', 'contingency_top_up',
    'long_tail_reserve_alert', 'bidding_checkpoint',
    'property_tax_reminder', 'bond_renewal_reminder', 'owner_weekly_summary'
  ];
  v_existing TEXT[];
  v_all      TEXT[];
  v_list     TEXT;
  r          RECORD;
BEGIN
  SELECT array_agg(DISTINCT email_type) INTO v_existing FROM public.email_log;
  SELECT array_agg(x ORDER BY x) INTO v_all
    FROM (SELECT DISTINCT unnest(v_planned || COALESCE(v_existing, '{}'::text[])) AS x) s;

  FOR r IN
    SELECT conname
      FROM pg_constraint
     WHERE conrelid = 'public.email_log'::regclass
       AND contype  = 'c'
       AND pg_get_constraintdef(oid) ILIKE '%email_type%'
  LOOP
    EXECUTE format('ALTER TABLE public.email_log DROP CONSTRAINT %I', r.conname);
  END LOOP;

  SELECT string_agg(quote_literal(x), ', ' ORDER BY x) INTO v_list FROM unnest(v_all) AS x;
  EXECUTE format(
    'ALTER TABLE public.email_log ADD CONSTRAINT chk_email_log_email_type CHECK (email_type IN (%s)) NOT VALID',
    v_list);
  EXECUTE 'ALTER TABLE public.email_log VALIDATE CONSTRAINT chk_email_log_email_type';
END $$;

COMMENT ON COLUMN public.email_log.email_type IS
  'Bid system: bid_invitation, bid_reminder, award_notification, decline_notification, milestone_alert, general. Financial (v4.0): payment_approval_request, payment_approved, payment_rejected, finance_handoff, finance_daily_summary, contingency_alert, contingency_escalation, contingency_top_up, long_tail_reserve_alert, bidding_checkpoint, property_tax_reminder, bond_renewal_reminder, owner_weekly_summary.';

-- D.2 notifications.notification_type — no CHECK exists and none is added
--     (an incomplete list would reject types written by existing jobs).
COMMENT ON COLUMN public.notifications.notification_type IS
  'Free-text type (VARCHAR 30, no CHECK by design). Bid system: milestone_completed, milestone_delayed, milestone_unresponsive, milestone_delivery_failed, insurance_*, scheduler_alert, post-deadline escalation. Financial (v4.0): contingency_health_alert, contingency_urgent_alert, long_tail_reserve_alert, bidding_checkpoint_alert, top_up_requested, top_up_decided, payment_approval_requested, payment_approved, payment_rejected, variance_pending_approval, property_tax_due, bond_renewal_due, month_closed.';


-- ============================================================================
-- SECTION D2: ROLE HELPERS (need user_roles, so defined after the tables)
-- ============================================================================

-- A.2  Does a given user hold a given role? (procedure-side check)
--      Considers the user active, non-deleted, and the role un-revoked.
CREATE OR REPLACE FUNCTION private.user_has_role(p_user_id UUID, p_role TEXT)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT 1
      FROM public.user_roles ur
      JOIN public.users u ON u.id = ur.user_id
     WHERE ur.user_id   = p_user_id
       AND ur.role      = p_role
       AND ur.revoked_at IS NULL
       AND u.is_active  = TRUE
       AND u.deleted_at IS NULL
  );
$$;

COMMENT ON FUNCTION private.user_has_role(UUID, TEXT) IS
  'TRUE when the user is active and holds the role in user_roles (not revoked). Used inside financial procedures for defence-in-depth role checks (e.g. executive-only top-ups).';


-- A.3  Does the CALLER (auth.uid()) hold any of the roles? (RLS-side check)
--      Admins always pass.
CREATE OR REPLACE FUNCTION private.has_any_role(p_roles TEXT[])
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT 1
      FROM public.users u
     WHERE u.id = (SELECT auth.uid())
       AND u.is_active = TRUE
       AND u.deleted_at IS NULL
       AND (
             u.role = 'admin'
          OR EXISTS (
               SELECT 1 FROM public.user_roles ur
                WHERE ur.user_id = u.id
                  AND ur.revoked_at IS NULL
                  AND (ur.role = 'admin' OR ur.role = ANY (p_roles))
             )
       )
  );
$$;

COMMENT ON FUNCTION private.has_any_role(TEXT[]) IS
  'RLS helper: TRUE when the signed-in user is active and holds any of the given roles (admins always pass). SECURITY DEFINER so it can read users/user_roles without recursive RLS.';


-- ============================================================================
-- SECTION E: TRIGGERS (guards, consistency, timestamps)
-- ============================================================================

-- ── E.1 updated_at on every new table (except the append-only ledger) ───────
DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'budget_templates', 'budget_template_lines', 'budget_lines', 'land_closings',
    'contingency_buckets', 'variance_lines', 'internal_invoices', 'payment_approvals',
    'finance_handoffs', 'escrows', 'property_taxes', 'accounting_periods',
    'company_cash_items', 'cash_flow_entries', 'financial_settings', 'financial_alerts',
    'user_roles', 'approval_delegations'
  ] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I', 'trg_' || t || '_updated_at', t);
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at()',
      'trg_' || t || '_updated_at', t);
  END LOOP;
END $$;


-- ── E.2 contingency_ledger immutability (same pattern as milestone_events) ──
CREATE OR REPLACE FUNCTION public.fn_block_contingency_ledger_mutation()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_LEVEL = 'STATEMENT' THEN
    RAISE EXCEPTION 'contingency_ledger is append-only (attempted %)', TG_OP
      USING ERRCODE = 'PT403';
  END IF;
  RAISE EXCEPTION 'contingency_ledger is append-only (attempted % on ledger row %)',
    TG_OP, OLD.id
    USING ERRCODE = 'PT403';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_contingency_ledger_immutable ON public.contingency_ledger;
CREATE TRIGGER trg_contingency_ledger_immutable
  BEFORE UPDATE OR DELETE ON public.contingency_ledger
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_contingency_ledger_mutation();

DROP TRIGGER IF EXISTS trg_contingency_ledger_no_truncate ON public.contingency_ledger;
CREATE TRIGGER trg_contingency_ledger_no_truncate
  BEFORE TRUNCATE ON public.contingency_ledger
  FOR EACH STATEMENT EXECUTE FUNCTION public.fn_block_contingency_ledger_mutation();


-- ── E.3 budget_lines guard ──────────────────────────────────────────────────
-- Consistency (always):
--   • project_id and line_type never change after insert
--   • task belongs to the same project, and line_type matches task.bid_type
--   • parent line belongs to the same project
-- Money (once the project is BASELINED, unless a financial procedure runs):
--   • budget_amount, committed_amount, award_id, original_estimate frozen
--   • a new line may only be inserted with budget_amount = 0
-- Locks (always, unless a financial procedure runs):
--   • a locked line's amounts / award cannot change and it cannot be unlocked
CREATE OR REPLACE FUNCTION public.fn_guard_budget_lines()
RETURNS TRIGGER AS $$
DECLARE
  v_auth        BOOLEAN := private.fin_write_authorized();
  v_baselined   BOOLEAN;
  v_task        RECORD;
  v_parent_proj UUID;
BEGIN
  -- Immutable identity columns
  IF TG_OP = 'UPDATE' THEN
    IF NEW.project_id IS DISTINCT FROM OLD.project_id THEN
      RAISE EXCEPTION 'A budget line cannot move to another project (line %)', OLD.id USING ERRCODE = 'PT422';
    END IF;
    IF NEW.line_type IS DISTINCT FROM OLD.line_type THEN
      RAISE EXCEPTION 'line_type cannot change after a line is created (line %: % → %). Remove the line and add a new one.',
        OLD.id, OLD.line_type, NEW.line_type USING ERRCODE = 'PT422';
    END IF;
  END IF;

  -- Task consistency
  IF NEW.task_id IS NOT NULL
     AND (TG_OP = 'INSERT' OR NEW.task_id IS DISTINCT FROM OLD.task_id) THEN
    SELECT project_id, bid_type, deleted_at INTO v_task FROM public.tasks WHERE id = NEW.task_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Task % not found', NEW.task_id USING ERRCODE = 'PT404';
    END IF;
    IF v_task.project_id <> NEW.project_id THEN
      RAISE EXCEPTION 'Task % belongs to project %, not %', NEW.task_id, v_task.project_id, NEW.project_id
        USING ERRCODE = 'PT422';
    END IF;
    IF (NEW.line_type = 'bid_activity' AND v_task.bid_type NOT IN ('competitive', 'direct_assign'))
       OR (NEW.line_type = 'internal_tm' AND v_task.bid_type <> 'internal') THEN
      RAISE EXCEPTION 'Line type % does not match task bid_type % (bid_activity ↔ competitive/direct_assign, internal_tm ↔ internal)',
        NEW.line_type, v_task.bid_type USING ERRCODE = 'PT422';
    END IF;
  END IF;

  -- Parent consistency
  IF NEW.parent_line_id IS NOT NULL
     AND (TG_OP = 'INSERT' OR NEW.parent_line_id IS DISTINCT FROM OLD.parent_line_id) THEN
    SELECT project_id INTO v_parent_proj FROM public.budget_lines WHERE id = NEW.parent_line_id;
    IF v_parent_proj IS DISTINCT FROM NEW.project_id THEN
      RAISE EXCEPTION 'Parent line % is not in project %', NEW.parent_line_id, NEW.project_id USING ERRCODE = 'PT422';
    END IF;
  END IF;

  -- Authoritative writer: everything below is the procedures' business.
  IF v_auth THEN
    RETURN NEW;
  END IF;

  -- Lock rules (always)
  IF TG_OP = 'UPDATE' AND OLD.is_locked THEN
    IF NEW.is_locked = FALSE
       OR NEW.budget_amount    IS DISTINCT FROM OLD.budget_amount
       OR NEW.committed_amount IS DISTINCT FROM OLD.committed_amount
       OR NEW.award_id         IS DISTINCT FROM OLD.award_id
       OR NEW.contract_id      IS DISTINCT FROM OLD.contract_id THEN
      RAISE EXCEPTION 'Budget line % is locked (contract executed). Locked amounts cannot be edited; use a variance line.',
        OLD.id USING ERRCODE = 'PT409';
    END IF;
  END IF;

  SELECT budget_status = 'baselined' INTO v_baselined FROM public.projects WHERE id = NEW.project_id;

  IF COALESCE(v_baselined, FALSE) THEN
    IF TG_OP = 'INSERT' THEN
      IF NEW.budget_amount <> 0 OR NEW.committed_amount <> 0 OR NEW.award_id IS NOT NULL THEN
        RAISE EXCEPTION 'Project budget is baselined: a new line must start at $0 and be funded through a financial procedure (total budget must stay flat).'
          USING ERRCODE = 'PT409';
      END IF;
    ELSE
      IF NEW.budget_amount     IS DISTINCT FROM OLD.budget_amount
         OR NEW.committed_amount  IS DISTINCT FROM OLD.committed_amount
         OR NEW.award_id          IS DISTINCT FROM OLD.award_id
         OR NEW.original_estimate IS DISTINCT FROM OLD.original_estimate THEN
        RAISE EXCEPTION 'Project budget is baselined: amounts on line % change only through financial procedures (bid, variance, top-up) so contingency and the ledger stay in step.',
          OLD.id USING ERRCODE = 'PT409';
      END IF;
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_budget_lines_guard ON public.budget_lines;
CREATE TRIGGER trg_budget_lines_guard
  BEFORE INSERT OR UPDATE ON public.budget_lines
  FOR EACH ROW EXECUTE FUNCTION public.fn_guard_budget_lines();


-- ── E.4 Flat-budget rule (deferred: checked once, at COMMIT) ────────────────
-- A bid overrun is two writes (+2,000 on the line, −2,000 on contingency);
-- checking at commit lets every procedure move money in balanced pairs while
-- any one-sided change — from anywhere — fails the whole transaction.
CREATE OR REPLACE FUNCTION public.fn_check_flat_budget_total()
RETURNS TRIGGER AS $$
DECLARE
  v_project_id UUID := COALESCE(NEW.project_id, OLD.project_id);
  v_status     TEXT;
  v_approved   NUMERIC;
  v_actual     NUMERIC;
BEGIN
  SELECT budget_status, approved_budget_total INTO v_status, v_approved
    FROM public.projects WHERE id = v_project_id;

  IF v_status IS DISTINCT FROM 'baselined' THEN
    RETURN NULL;
  END IF;

  SELECT COALESCE(SUM(budget_amount), 0) INTO v_actual
    FROM public.budget_lines
   WHERE project_id = v_project_id AND deleted_at IS NULL;

  IF v_actual <> v_approved THEN
    RAISE EXCEPTION 'Flat-budget rule violated for project %: lines total % but the approved budget is %. The total can only change through an executive-approved contingency top-up.',
      v_project_id, v_actual, v_approved
      USING ERRCODE = 'PT409';
  END IF;

  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_budget_lines_flat_total ON public.budget_lines;
CREATE CONSTRAINT TRIGGER trg_budget_lines_flat_total
  AFTER INSERT OR UPDATE OR DELETE ON public.budget_lines
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION public.fn_check_flat_budget_total();


-- ── E.5 projects: approved total / baseline only via procedures ─────────────
-- none ↔ draft is free (Phase 2 budget builder). Anything touching
-- 'baselined', the approved total or the baseline stamp needs the flag.
-- Fires only when these new columns are in the UPDATE, so the existing
-- project PATCH endpoint is unaffected.
CREATE OR REPLACE FUNCTION public.fn_guard_project_budget_total()
RETURNS TRIGGER AS $$
BEGIN
  IF private.fin_write_authorized() THEN
    RETURN NEW;
  END IF;

  IF NEW.approved_budget_total IS DISTINCT FROM OLD.approved_budget_total
     OR NEW.budget_baselined_at IS DISTINCT FROM OLD.budget_baselined_at
     OR NEW.budget_baselined_by IS DISTINCT FROM OLD.budget_baselined_by
     OR (NEW.budget_status IS DISTINCT FROM OLD.budget_status
         AND 'baselined' IN (NEW.budget_status, OLD.budget_status)) THEN
    RAISE EXCEPTION 'The approved budget of project % can only be set by baselining and changed by an executive-approved contingency top-up.',
      OLD.id USING ERRCODE = 'PT409';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_projects_guard_budget_total ON public.projects;
CREATE TRIGGER trg_projects_guard_budget_total
  BEFORE UPDATE OF approved_budget_total, budget_status, budget_baselined_at, budget_baselined_by
  ON public.projects
  FOR EACH ROW EXECUTE FUNCTION public.fn_guard_project_budget_total();


-- ── E.6 contingency_buckets: decisions only via the top-up procedure ────────
CREATE OR REPLACE FUNCTION public.fn_guard_contingency_buckets()
RETURNS TRIGGER AS $$
BEGIN
  IF private.fin_write_authorized() THEN
    RETURN NEW;
  END IF;

  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'pending' OR NEW.bucket_kind <> 'top_up' THEN
      RAISE EXCEPTION 'Only pending top-up requests may be inserted directly; initial buckets and decisions are written by financial procedures.'
        USING ERRCODE = 'PT409';
    END IF;
    RETURN NEW;
  END IF;

  IF OLD.status <> 'pending' THEN
    RAISE EXCEPTION 'Contingency bucket % is already % and cannot change.', OLD.id, OLD.status USING ERRCODE = 'PT409';
  END IF;
  IF NEW.status = 'approved' OR NEW.status = 'rejected'
     OR NEW.approved_amount IS DISTINCT FROM OLD.approved_amount
     OR NEW.decided_by      IS DISTINCT FROM OLD.decided_by THEN
    RAISE EXCEPTION 'Top-up decisions are recorded only by fn_approve_contingency_top_up (executive role).'
      USING ERRCODE = 'PT409';
  END IF;
  IF NEW.project_id IS DISTINCT FROM OLD.project_id
     OR NEW.contingency_line_id IS DISTINCT FROM OLD.contingency_line_id
     OR NEW.bucket_kind IS DISTINCT FROM OLD.bucket_kind THEN
    RAISE EXCEPTION 'Bucket identity columns cannot change.' USING ERRCODE = 'PT422';
  END IF;
  RETURN NEW;  -- pending → cancelled, or editing reason / requested amount while pending
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_contingency_buckets_guard ON public.contingency_buckets;
CREATE TRIGGER trg_contingency_buckets_guard
  BEFORE INSERT OR UPDATE ON public.contingency_buckets
  FOR EACH ROW EXECUTE FUNCTION public.fn_guard_contingency_buckets();


-- ── E.7 variance_lines guard ────────────────────────────────────────────────
-- Variances are created / adjusted / cancelled only by procedures (money moves
-- with them). Approved and cancelled variances are frozen. Approval itself is
-- a status change the Phase 4 service performs directly.
CREATE OR REPLACE FUNCTION public.fn_guard_variance_lines()
RETURNS TRIGGER AS $$
BEGIN
  IF private.fin_write_authorized() THEN
    RETURN NEW;
  END IF;

  IF TG_OP = 'INSERT' THEN
    RAISE EXCEPTION 'Variances are created only through fn_create_variance (it moves contingency and writes the ledger).'
      USING ERRCODE = 'PT409';
  END IF;

  IF OLD.status IN ('approved', 'cancelled') THEN
    RAISE EXCEPTION 'Variance % is % and frozen. Create a new variance instead.', OLD.id, OLD.status
      USING ERRCODE = 'PT409';
  END IF;

  IF NEW.status = 'cancelled' THEN
    RAISE EXCEPTION 'Cancel a variance through fn_adjust_variance(…, 0, …) so its amount returns to contingency.'
      USING ERRCODE = 'PT409';
  END IF;

  IF NEW.project_id IS DISTINCT FROM OLD.project_id
     OR NEW.budget_line_id IS DISTINCT FROM OLD.budget_line_id
     OR NEW.parent_budget_line_id IS DISTINCT FROM OLD.parent_budget_line_id
     OR NEW.estimated_amount IS DISTINCT FROM OLD.estimated_amount
     OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
    RAISE EXCEPTION 'Variance identity / history columns cannot change (variance %).', OLD.id USING ERRCODE = 'PT422';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_variance_lines_guard ON public.variance_lines;
CREATE TRIGGER trg_variance_lines_guard
  BEFORE INSERT OR UPDATE ON public.variance_lines
  FOR EACH ROW EXECUTE FUNCTION public.fn_guard_variance_lines();


-- ── E.8 accounting periods: close only via procedure, never reopen ─────────
CREATE OR REPLACE FUNCTION public.fn_guard_accounting_periods()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status = 'closed' THEN
      RAISE EXCEPTION 'Closed month % cannot be deleted.', OLD.period_month USING ERRCODE = 'PT409';
    END IF;
    RETURN OLD;
  END IF;

  IF TG_OP = 'UPDATE' AND OLD.status = 'closed' THEN
    IF NEW.status <> 'closed' OR NEW.period_month <> OLD.period_month
       OR NEW.closed_by IS DISTINCT FROM OLD.closed_by OR NEW.closed_at IS DISTINCT FROM OLD.closed_at THEN
      RAISE EXCEPTION 'Month % is closed and can never be reopened or changed.', OLD.period_month USING ERRCODE = 'PT409';
    END IF;
    RETURN NEW;
  END IF;

  IF NEW.status = 'closed' AND NOT private.fin_write_authorized() THEN
    RAISE EXCEPTION 'Months are closed only through fn_close_accounting_month (finance / executive).'
      USING ERRCODE = 'PT409';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_accounting_periods_guard ON public.accounting_periods;
CREATE TRIGGER trg_accounting_periods_guard
  BEFORE INSERT OR UPDATE OR DELETE ON public.accounting_periods
  FOR EACH ROW EXECUTE FUNCTION public.fn_guard_accounting_periods();


-- ── E.9 cash_flow_entries: closed months are frozen ─────────────────────────
CREATE OR REPLACE FUNCTION public.fn_guard_cash_flow_closed_period()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') AND EXISTS (
       SELECT 1 FROM public.accounting_periods
        WHERE period_month = OLD.period_month AND status = 'closed') THEN
    RAISE EXCEPTION 'Cash-flow month % is closed; its entries cannot be changed.', OLD.period_month
      USING ERRCODE = 'PT409';
  END IF;

  IF TG_OP IN ('INSERT', 'UPDATE') AND EXISTS (
       SELECT 1 FROM public.accounting_periods
        WHERE period_month = NEW.period_month AND status = 'closed') THEN
    RAISE EXCEPTION 'Cash-flow month % is closed; new entries cannot be added to it.', NEW.period_month
      USING ERRCODE = 'PT409';
  END IF;

  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cash_flow_entries_closed_period ON public.cash_flow_entries;
CREATE TRIGGER trg_cash_flow_entries_closed_period
  BEFORE INSERT OR UPDATE OR DELETE ON public.cash_flow_entries
  FOR EACH ROW EXECUTE FUNCTION public.fn_guard_cash_flow_closed_period();


-- ── E.10 users.role → user_roles mirror ─────────────────────────────────────
-- Keeps the base role in user_roles in step with the existing admin screen
-- (which flips users.role admin ↔ project_manager). Never touches users.
CREATE OR REPLACE FUNCTION public.fn_sync_user_base_role()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.role IS NOT DISTINCT FROM OLD.role THEN
    RETURN NEW;
  END IF;

  IF TG_OP = 'UPDATE' THEN
    UPDATE public.user_roles
       SET revoked_at = NOW()
     WHERE user_id = NEW.id
       AND role = OLD.role
       AND revoked_at IS NULL;
  END IF;

  INSERT INTO public.user_roles (user_id, role, granted_by)
  VALUES (NEW.id, NEW.role, NEW.invited_by)
  ON CONFLICT (user_id, role) WHERE revoked_at IS NULL DO NOTHING;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_users_sync_base_role ON public.users;
CREATE TRIGGER trg_users_sync_base_role
  AFTER INSERT OR UPDATE OF role ON public.users
  FOR EACH ROW EXECUTE FUNCTION public.fn_sync_user_base_role();


-- ── E.11 Backfill: every existing user's base role into user_roles ──────────
--     Writes only to the new table. Re-run safe.
INSERT INTO public.user_roles (user_id, role, granted_by)
SELECT u.id, u.role, u.invited_by
  FROM public.users u
 WHERE u.role IN ('admin', 'project_manager')
ON CONFLICT (user_id, role) WHERE revoked_at IS NULL DO NOTHING;


-- ── E.12 Supabase Auth → profile trigger (extended, backward compatible) ────
-- Behaviour with today's invite metadata {full_name, role} is identical to
-- v3.9 (plus the base-role row, written by trg_users_sync_base_role).
-- New optional metadata keys:
--   roles        JSON array of extra roles, e.g. ["executive","finance"]
--   is_employee  boolean (false = external / temporary field manager)
-- Invalid extra roles are ignored, and a failure in the financial part is
-- logged as a WARNING — it can never block a signup / invite.
CREATE OR REPLACE FUNCTION public.fn_handle_new_auth_user()
RETURNS TRIGGER AS $$
DECLARE
  v_meta JSONB := COALESCE(NEW.raw_user_meta_data, '{}'::jsonb);
BEGIN
  INSERT INTO public.users (id, email, full_name, role)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(v_meta ->> 'full_name', split_part(NEW.email, '@', 1)),
    COALESCE(v_meta ->> 'role', 'project_manager')
  );

  BEGIN
    IF jsonb_typeof(v_meta -> 'is_employee') = 'boolean' THEN
      UPDATE public.users
         SET is_employee = (v_meta ->> 'is_employee')::boolean
       WHERE id = NEW.id;
    END IF;

    IF jsonb_typeof(v_meta -> 'roles') = 'array' THEN
      INSERT INTO public.user_roles (user_id, role)
      SELECT NEW.id, r.role_name
        FROM jsonb_array_elements_text(v_meta -> 'roles') AS r(role_name)
       WHERE r.role_name IN ('admin', 'project_manager', 'field_manager', 'executive', 'finance')
      ON CONFLICT (user_id, role) WHERE revoked_at IS NULL DO NOTHING;
    END IF;
  EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'fn_handle_new_auth_user: financial role metadata ignored for user % (%)', NEW.id, SQLERRM;
  END;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';


-- ============================================================================
-- SECTION F: FINANCIAL STORED PROCEDURES (callable via PostgREST /rpc)
-- ============================================================================
-- Each runs in ONE implicit transaction (supabase-py has no client
-- transactions). Python validates first; these are the atomic writes, with
-- defence-in-depth checks. Errors: PT403 / PT404 / PT409 / PT422.
-- PRIVILEGES: REVOKE from PUBLIC, anon, authenticated; GRANT to service_role.
-- ----------------------------------------------------------------------------

-- F.0  Internal: move contingency + write the ledger row (private, not exposed)
CREATE OR REPLACE FUNCTION private.fin_move_contingency(
  p_project_id      UUID,
  p_amount          NUMERIC,          -- signed: + into contingency, − out
  p_movement_type   TEXT,
  p_actor_user_id   UUID,
  p_reason          TEXT DEFAULT NULL,
  p_source_line_id  UUID DEFAULT NULL,
  p_variance_id     UUID DEFAULT NULL,
  p_award_id        UUID DEFAULT NULL,
  p_bucket_id       UUID DEFAULT NULL
)
RETURNS public.contingency_ledger
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_line   public.budget_lines;
  v_entry  public.contingency_ledger;
BEGIN
  IF p_actor_user_id IS NULL THEN
    RAISE EXCEPTION 'An actor is required for every contingency movement' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_line
    FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Project % has no contingency line', p_project_id USING ERRCODE = 'PT409';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  UPDATE public.budget_lines
     SET budget_amount = budget_amount + p_amount,
         updated_by    = p_actor_user_id
   WHERE id = v_line.id;

  INSERT INTO public.contingency_ledger (
    project_id, contingency_line_id, contingency_bucket_id, movement_type,
    amount, balance_before, balance_after,
    source_budget_line_id, variance_line_id, award_id, actor_user_id, reason
  ) VALUES (
    p_project_id, v_line.id, p_bucket_id, p_movement_type,
    p_amount, v_line.budget_amount, v_line.budget_amount + p_amount,
    p_source_line_id, p_variance_id, p_award_id, p_actor_user_id, p_reason
  )
  RETURNING * INTO v_entry;

  RETURN v_entry;
END;
$$;

COMMENT ON FUNCTION private.fin_move_contingency(UUID, NUMERIC, TEXT, UUID, TEXT, UUID, UUID, UUID, UUID) IS
  'Internal: row-locks the project contingency line, applies a signed movement and writes the matching contingency_ledger row. Called only by the public financial procedures (private schema = not exposed via the Data API).';


-- F.0b Internal: load + check a project for a money movement
CREATE OR REPLACE FUNCTION private.fin_lock_project(
  p_project_id       UUID,
  p_require_baseline BOOLEAN,
  p_block_on_hold    BOOLEAN
)
RETURNS public.projects
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
BEGIN
  SELECT * INTO v_project FROM public.projects WHERE id = p_project_id FOR UPDATE;
  IF NOT FOUND OR v_project.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Project % not found', p_project_id USING ERRCODE = 'PT404';
  END IF;
  IF p_require_baseline AND v_project.budget_status <> 'baselined' THEN
    RAISE EXCEPTION 'Project % budget is not baselined yet (status %)', p_project_id, v_project.budget_status
      USING ERRCODE = 'PT409';
  END IF;
  IF p_block_on_hold AND v_project.status = 'on_hold' THEN
    RAISE EXCEPTION 'Project % is on hold; financial changes are blocked until the hold is lifted', p_project_id
      USING ERRCODE = 'PT409';
  END IF;
  RETURN v_project;
END;
$$;


-- F.1  fn_baseline_project_budget — freeze estimates, set approved total
CREATE OR REPLACE FUNCTION public.fn_baseline_project_budget(
  p_project_id UUID,
  p_actor      UUID
)
RETURNS SETOF public.projects
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project  public.projects;
  v_cont     public.budget_lines;
  v_total    NUMERIC;
  v_bucket   public.contingency_buckets;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);

  IF v_project.budget_status = 'baselined' THEN
    RAISE EXCEPTION 'Project % budget is already baselined', p_project_id USING ERRCODE = 'PT409';
  END IF;
  IF v_project.budget_status <> 'draft' THEN
    RAISE EXCEPTION 'Project % has no draft budget to baseline', p_project_id USING ERRCODE = 'PT409';
  END IF;

  SELECT * INTO v_cont
    FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Project % needs a contingency line before it can be baselined', p_project_id
      USING ERRCODE = 'PT409';
  END IF;
  IF v_cont.budget_amount < 0 THEN
    RAISE EXCEPTION 'Contingency cannot start negative (%)', v_cont.budget_amount USING ERRCODE = 'PT422';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  -- A21: freeze the original estimate of every live line (caller may preset it).
  UPDATE public.budget_lines
     SET original_estimate = COALESCE(original_estimate, budget_amount),
         updated_by        = p_actor
   WHERE project_id = p_project_id
     AND deleted_at IS NULL
     AND line_type <> 'contingency';

  UPDATE public.budget_lines
     SET original_estimate = budget_amount
   WHERE id = v_cont.id;

  SELECT COALESCE(SUM(budget_amount), 0) INTO v_total
    FROM public.budget_lines
   WHERE project_id = p_project_id AND deleted_at IS NULL;

  INSERT INTO public.contingency_buckets (
    project_id, contingency_line_id, bucket_kind, requested_amount, approved_amount,
    status, reason, requested_by, decided_by, decided_at
  ) VALUES (
    p_project_id, v_cont.id, 'initial', v_cont.budget_amount, v_cont.budget_amount,
    'approved', 'Initial contingency at budget baseline', p_actor, p_actor, NOW()
  )
  RETURNING * INTO v_bucket;

  INSERT INTO public.contingency_ledger (
    project_id, contingency_line_id, contingency_bucket_id, movement_type,
    amount, balance_before, balance_after, actor_user_id, reason
  ) VALUES (
    p_project_id, v_cont.id, v_bucket.id, 'initial_funding',
    v_cont.budget_amount, 0, v_cont.budget_amount, p_actor, 'Initial contingency at budget baseline'
  );

  UPDATE public.projects
     SET budget_status         = 'baselined',
         approved_budget_total = v_total,
         budget_baselined_at   = NOW(),
         budget_baselined_by   = p_actor
   WHERE id = p_project_id
   RETURNING * INTO v_project;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_project;
END;
$$;

COMMENT ON FUNCTION public.fn_baseline_project_budget(UUID, UUID) IS
  'Draft → baselined: freezes every line''s original_estimate (A21), sets projects.approved_budget_total = SUM(live lines), records the initial contingency bucket and the initial_funding ledger row. From then on the flat-budget rule applies.';


-- F.2  fn_apply_bid_to_line — award amount → line, difference ↔ contingency
CREATE OR REPLACE FUNCTION public.fn_apply_bid_to_line(
  p_budget_line_id UUID,
  p_award_id       UUID,
  p_amount         NUMERIC,
  p_actor          UUID
)
RETURNS SETOF public.budget_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_line     public.budget_lines;
  v_award    public.awards;
  v_project  public.projects;
  v_delta    NUMERIC;
  v_result   public.budget_lines;
BEGIN
  IF p_amount IS NULL OR p_amount < 0 THEN
    RAISE EXCEPTION 'Bid amount must be zero or more (got %)', p_amount USING ERRCODE = 'PT422';
  END IF;
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_budget_line_id;
  IF NOT FOUND OR v_line.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Budget line % not found', p_budget_line_id USING ERRCODE = 'PT404';
  END IF;

  -- Lock order everywhere: project → lines (avoids deadlocks).
  v_project := private.fin_lock_project(v_line.project_id, FALSE, TRUE);
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_budget_line_id FOR UPDATE;

  IF v_line.line_type <> 'bid_activity' THEN
    RAISE EXCEPTION 'Bids apply only to bid_activity lines (line % is %)', v_line.id, v_line.line_type
      USING ERRCODE = 'PT422';
  END IF;
  IF v_line.is_locked THEN
    RAISE EXCEPTION 'Budget line % is locked (contract executed)', v_line.id USING ERRCODE = 'PT409';
  END IF;

  SELECT * INTO v_award FROM public.awards WHERE id = p_award_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Award % not found', p_award_id USING ERRCODE = 'PT404';
  END IF;
  IF v_award.task_id IS DISTINCT FROM v_line.task_id THEN
    RAISE EXCEPTION 'Award % is for task %, not this line''s task %', p_award_id, v_award.task_id, v_line.task_id
      USING ERRCODE = 'PT422';
  END IF;
  IF v_award.status IN ('declined_by_vendor', 'cancelled') THEN
    RAISE EXCEPTION 'Award % is % and cannot be applied', p_award_id, v_award.status USING ERRCODE = 'PT409';
  END IF;
  IF v_line.award_id IS NOT NULL AND v_line.award_id <> p_award_id THEN
    RAISE EXCEPTION 'Line % already carries award %; reverse it first', v_line.id, v_line.award_id
      USING ERRCODE = 'PT409';
  END IF;

  -- Idempotent retry: same award, same amount → nothing to do.
  IF v_line.award_id = p_award_id AND v_line.budget_amount = p_amount AND v_line.committed_amount = p_amount THEN
    RETURN NEXT v_line;
    RETURN;
  END IF;

  v_delta := p_amount - v_line.budget_amount;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  UPDATE public.budget_lines
     SET pre_award_budget_amount = CASE WHEN award_id IS NULL THEN budget_amount ELSE pre_award_budget_amount END,
         budget_amount           = p_amount,
         committed_amount        = p_amount,
         award_id                = p_award_id,
         updated_by              = p_actor
   WHERE id = v_line.id
   RETURNING * INTO v_result;

  -- Draft budgets have no ledger yet: the line simply takes the bid.
  IF v_project.budget_status = 'baselined' AND v_delta <> 0 THEN
    PERFORM private.fin_move_contingency(
      v_line.project_id, -v_delta,
      CASE WHEN v_delta > 0 THEN 'bid_overrun' ELSE 'bid_savings' END,
      p_actor,
      format('Bid applied to "%s": %s → %s', v_line.name, v_line.budget_amount, p_amount),
      v_line.id, NULL, p_award_id, NULL);
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_result;
END;
$$;

COMMENT ON FUNCTION public.fn_apply_bid_to_line(UUID, UUID, NUMERIC, UUID) IS
  'A2/A3: sets the bid line''s budget and committed amount to the award amount; the difference moves out of (overrun) or into (savings) contingency with a ledger row. Idempotent for the same award + amount. Blocked on locked lines and on-hold projects.';


-- F.3  fn_reverse_bid_on_line — award declined / voided / cancelled
CREATE OR REPLACE FUNCTION public.fn_reverse_bid_on_line(
  p_budget_line_id UUID,
  p_award_id       UUID,
  p_actor          UUID,
  p_reason         TEXT DEFAULT NULL
)
RETURNS SETOF public.budget_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_line     public.budget_lines;
  v_project  public.projects;
  v_restore  NUMERIC;
  v_delta    NUMERIC;
  v_result   public.budget_lines;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_budget_line_id;
  IF NOT FOUND OR v_line.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Budget line % not found', p_budget_line_id USING ERRCODE = 'PT404';
  END IF;

  -- Reversals are allowed even when the project is on hold (a decline happens regardless).
  v_project := private.fin_lock_project(v_line.project_id, FALSE, FALSE);
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_budget_line_id FOR UPDATE;

  IF v_line.award_id IS DISTINCT FROM p_award_id THEN
    RAISE EXCEPTION 'Award % is not applied to line % — nothing to reverse', p_award_id, p_budget_line_id
      USING ERRCODE = 'PT409';
  END IF;

  v_restore := COALESCE(v_line.pre_award_budget_amount, v_line.budget_amount);
  v_delta   := v_restore - v_line.budget_amount;   -- change on the line

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  UPDATE public.budget_lines
     SET budget_amount           = v_restore,
         committed_amount        = 0,
         award_id                = NULL,
         contract_id             = NULL,
         pre_award_budget_amount = NULL,
         is_locked               = FALSE,
         locked_at               = NULL,
         locked_by               = NULL,
         lock_reason             = NULL,
         updated_by              = p_actor
   WHERE id = v_line.id
   RETURNING * INTO v_result;

  IF v_project.budget_status = 'baselined' AND v_delta <> 0 THEN
    PERFORM private.fin_move_contingency(
      v_line.project_id, -v_delta, 'bid_reversal', p_actor,
      COALESCE(p_reason, format('Award reversed on "%s": %s → %s', v_line.name, v_line.budget_amount, v_restore)),
      v_line.id, NULL, p_award_id, NULL);
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_result;
END;
$$;

COMMENT ON FUNCTION public.fn_reverse_bid_on_line(UUID, UUID, UUID, TEXT) IS
  'Undoes fn_apply_bid_to_line when the vendor declines or the award / envelope is cancelled or voided: restores the pre-award amount, clears committed / award / lock, and moves the difference back with a bid_reversal ledger row.';


-- F.4  fn_lock_budget_line — contract executed
CREATE OR REPLACE FUNCTION public.fn_lock_budget_line(
  p_budget_line_id UUID,
  p_contract_id    UUID,
  p_actor          UUID
)
RETURNS SETOF public.budget_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_line      public.budget_lines;
  v_contract  public.contracts;
  v_start     DATE;
  v_end       DATE;
  v_result    public.budget_lines;
BEGIN
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_budget_line_id FOR UPDATE;
  IF NOT FOUND OR v_line.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Budget line % not found', p_budget_line_id USING ERRCODE = 'PT404';
  END IF;

  SELECT * INTO v_contract FROM public.contracts WHERE id = p_contract_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Contract % not found', p_contract_id USING ERRCODE = 'PT404';
  END IF;
  IF v_contract.task_id IS DISTINCT FROM v_line.task_id THEN
    RAISE EXCEPTION 'Contract % is for task %, not this line''s task %', p_contract_id, v_contract.task_id, v_line.task_id
      USING ERRCODE = 'PT422';
  END IF;
  IF v_line.award_id IS NOT NULL AND v_line.award_id <> v_contract.award_id THEN
    RAISE EXCEPTION 'Line % carries award %, but contract % belongs to award %',
      v_line.id, v_line.award_id, p_contract_id, v_contract.award_id USING ERRCODE = 'PT409';
  END IF;

  IF v_line.is_locked AND v_line.contract_id = p_contract_id THEN
    RETURN NEXT v_line;   -- idempotent (webhook retries)
    RETURN;
  END IF;

  v_start := COALESCE(v_line.anticipated_start_date, v_contract.start_date);
  v_end   := COALESCE(v_line.anticipated_end_date,   v_contract.end_date);
  IF v_start IS NOT NULL AND v_end IS NOT NULL AND v_end < v_start THEN
    v_start := v_line.anticipated_start_date;
    v_end   := v_line.anticipated_end_date;
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  UPDATE public.budget_lines
     SET is_locked              = TRUE,
         locked_at              = NOW(),
         locked_by              = p_actor,
         lock_reason            = 'Contract executed',
         contract_id            = p_contract_id,
         anticipated_start_date = v_start,
         anticipated_end_date   = v_end,
         updated_by             = p_actor
   WHERE id = v_line.id
   RETURNING * INTO v_result;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_result;
END;
$$;

COMMENT ON FUNCTION public.fn_lock_budget_line(UUID, UUID, UUID) IS
  'Locks a bid line when its contract is executed (DocuSign completed) and defaults the line dates from the contract start / end when they are empty. Idempotent.';


-- F.5  fn_create_variance — variance line + contingency deduction (A5)
CREATE OR REPLACE FUNCTION public.fn_create_variance(
  p_parent_line_id UUID,
  p_description    TEXT,
  p_amount         NUMERIC,
  p_actor          UUID,
  p_trade_id       UUID DEFAULT NULL,
  p_vendor_id      UUID DEFAULT NULL,
  p_start_date     DATE DEFAULT NULL,
  p_end_date       DATE DEFAULT NULL
)
RETURNS SETOF public.variance_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_parent    public.budget_lines;
  v_line      public.budget_lines;
  v_variance  public.variance_lines;
BEGIN
  IF p_amount IS NULL OR p_amount <= 0 THEN
    RAISE EXCEPTION 'Variance amount must be greater than zero (got %)', p_amount USING ERRCODE = 'PT422';
  END IF;
  IF btrim(COALESCE(p_description, '')) = '' THEN
    RAISE EXCEPTION 'A variance needs a description' USING ERRCODE = 'PT422';
  END IF;
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_parent FROM public.budget_lines WHERE id = p_parent_line_id;
  IF NOT FOUND OR v_parent.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Budget line % not found', p_parent_line_id USING ERRCODE = 'PT404';
  END IF;
  IF v_parent.line_type IN ('contingency', 'variance', 'land') THEN
    RAISE EXCEPTION 'A variance cannot be created under a % line', v_parent.line_type USING ERRCODE = 'PT422';
  END IF;

  PERFORM private.fin_lock_project(v_parent.project_id, TRUE, TRUE);

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  INSERT INTO public.budget_lines (
    project_id, parent_line_id, line_type, name, description, section_name, sort_order,
    budget_amount, anticipated_start_date, anticipated_end_date,
    payment_terms_days, cash_bucket, created_by, updated_by
  ) VALUES (
    v_parent.project_id, v_parent.id, 'variance',
    left('Variance: ' || btrim(p_description), 255), p_description,
    v_parent.section_name, v_parent.sort_order,
    p_amount,
    COALESCE(p_start_date, v_parent.anticipated_start_date),
    COALESCE(p_end_date,   v_parent.anticipated_end_date),
    v_parent.payment_terms_days, v_parent.cash_bucket, p_actor, p_actor
  )
  RETURNING * INTO v_line;

  INSERT INTO public.variance_lines (
    project_id, budget_line_id, parent_budget_line_id, trade_id, vendor_id,
    description, estimated_amount, status, created_by
  ) VALUES (
    v_parent.project_id, v_line.id, v_parent.id, p_trade_id, p_vendor_id,
    btrim(p_description), p_amount, 'pending_approval', p_actor
  )
  RETURNING * INTO v_variance;

  PERFORM private.fin_move_contingency(
    v_parent.project_id, -p_amount, 'variance_created', p_actor,
    format('Variance under "%s": %s', v_parent.name, btrim(p_description)),
    v_line.id, v_variance.id, NULL, NULL);

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_variance;
END;
$$;

COMMENT ON FUNCTION public.fn_create_variance(UUID, TEXT, NUMERIC, UUID, UUID, UUID, DATE, DATE) IS
  'A5: creates a variance (own budget line of type variance + variance_lines row, status pending_approval) under an activity line and deducts the same amount from contingency with a ledger row. Total budget stays flat.';


-- F.6  fn_adjust_variance — edit before approval, or cancel (A6)
CREATE OR REPLACE FUNCTION public.fn_adjust_variance(
  p_variance_id UUID,
  p_new_amount  NUMERIC,
  p_actor       UUID,
  p_reason      TEXT DEFAULT NULL
)
RETURNS SETOF public.variance_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_variance  public.variance_lines;
  v_line      public.budget_lines;
  v_delta     NUMERIC;
BEGIN
  IF p_new_amount IS NULL OR p_new_amount < 0 THEN
    RAISE EXCEPTION 'New variance amount must be zero (cancel) or more (got %)', p_new_amount USING ERRCODE = 'PT422';
  END IF;
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id;
  IF NOT FOUND OR v_variance.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Variance % not found', p_variance_id USING ERRCODE = 'PT404';
  END IF;

  -- Adjustments may be needed on a held project to free contingency, so no hold block.
  PERFORM private.fin_lock_project(v_variance.project_id, TRUE, FALSE);
  SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id FOR UPDATE;
  SELECT * INTO v_line     FROM public.budget_lines   WHERE id = v_variance.budget_line_id FOR UPDATE;

  IF v_variance.status NOT IN ('draft', 'pending_approval', 'rejected') THEN
    RAISE EXCEPTION 'Variance % is % and can no longer be changed; create a new variance', p_variance_id, v_variance.status
      USING ERRCODE = 'PT409';
  END IF;

  v_delta := p_new_amount - v_line.budget_amount;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  IF p_new_amount = 0 THEN
    -- Cancel: return the full amount, retire the line.
    UPDATE public.budget_lines
       SET budget_amount = 0, deleted_at = NOW(), updated_by = p_actor
     WHERE id = v_line.id;

    UPDATE public.variance_lines
       SET status = 'cancelled'
     WHERE id = p_variance_id
     RETURNING * INTO v_variance;

    IF v_delta <> 0 THEN
      PERFORM private.fin_move_contingency(
        v_variance.project_id, -v_delta, 'variance_cancelled', p_actor,
        COALESCE(p_reason, 'Variance cancelled'), v_line.id, p_variance_id, NULL, NULL);
    END IF;
  ELSIF v_delta <> 0 THEN
    UPDATE public.budget_lines
       SET budget_amount = p_new_amount, updated_by = p_actor
     WHERE id = v_line.id;

    PERFORM private.fin_move_contingency(
      v_variance.project_id, -v_delta, 'variance_adjusted', p_actor,
      COALESCE(p_reason, format('Variance adjusted %s → %s', v_line.budget_amount, p_new_amount)),
      v_line.id, p_variance_id, NULL, NULL);

    SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id;
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_variance;
END;
$$;

COMMENT ON FUNCTION public.fn_adjust_variance(UUID, NUMERIC, UUID, TEXT) IS
  'A6: changes a not-yet-approved variance amount; the difference flows back to (or out of) contingency with a ledger row (e.g. $5,000 estimate → $3,000 actual returns $2,000). p_new_amount = 0 cancels the variance and returns everything.';


-- F.7  fn_request_contingency_top_up — convenience writer for a request
CREATE OR REPLACE FUNCTION public.fn_request_contingency_top_up(
  p_project_id UUID,
  p_amount     NUMERIC,
  p_reason     TEXT,
  p_actor      UUID
)
RETURNS SETOF public.contingency_buckets
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_cont    public.budget_lines;
  v_bucket  public.contingency_buckets;
BEGIN
  IF p_amount IS NULL OR p_amount <= 0 THEN
    RAISE EXCEPTION 'Top-up amount must be greater than zero' USING ERRCODE = 'PT422';
  END IF;
  IF btrim(COALESCE(p_reason, '')) = '' THEN
    RAISE EXCEPTION 'A top-up request needs a reason' USING ERRCODE = 'PT422';
  END IF;
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  PERFORM private.fin_lock_project(p_project_id, TRUE, FALSE);

  SELECT * INTO v_cont FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL;

  INSERT INTO public.contingency_buckets (
    project_id, contingency_line_id, bucket_kind, requested_amount, status, reason, requested_by
  ) VALUES (
    p_project_id, v_cont.id, 'top_up', p_amount, 'pending', btrim(p_reason), p_actor
  )
  RETURNING * INTO v_bucket;

  RETURN NEXT v_bucket;
END;
$$;

COMMENT ON FUNCTION public.fn_request_contingency_top_up(UUID, NUMERIC, TEXT, UUID) IS
  'Records a pending contingency top-up request (amount + reason). Approval is executive-only via fn_approve_contingency_top_up.';


-- F.8  fn_approve_contingency_top_up — executive decision (A13)
CREATE OR REPLACE FUNCTION public.fn_approve_contingency_top_up(
  p_bucket_id        UUID,
  p_approver         UUID,
  p_approve          BOOLEAN,
  p_approved_amount  NUMERIC DEFAULT NULL,
  p_note             TEXT DEFAULT NULL
)
RETURNS SETOF public.contingency_buckets
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_bucket  public.contingency_buckets;
  v_amount  NUMERIC;
BEGIN
  IF p_approver IS NULL OR p_approve IS NULL THEN
    RAISE EXCEPTION 'p_approver and p_approve are required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_bucket FROM public.contingency_buckets WHERE id = p_bucket_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Contingency bucket % not found', p_bucket_id USING ERRCODE = 'PT404';
  END IF;

  IF NOT private.user_has_role(p_approver, 'executive') THEN
    RAISE EXCEPTION 'Only an executive can approve or reject a contingency top-up' USING ERRCODE = 'PT403';
  END IF;

  -- Lock order: project → bucket → lines.
  PERFORM private.fin_lock_project(v_bucket.project_id, TRUE, FALSE);
  SELECT * INTO v_bucket FROM public.contingency_buckets WHERE id = p_bucket_id FOR UPDATE;

  IF v_bucket.bucket_kind <> 'top_up' THEN
    RAISE EXCEPTION 'Bucket % is not a top-up request', p_bucket_id USING ERRCODE = 'PT422';
  END IF;
  IF v_bucket.status <> 'pending' THEN
    RAISE EXCEPTION 'Top-up request % is already %', p_bucket_id, v_bucket.status USING ERRCODE = 'PT409';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  IF NOT p_approve THEN
    UPDATE public.contingency_buckets
       SET status = 'rejected', decided_by = p_approver, decided_at = NOW(), decision_note = p_note
     WHERE id = p_bucket_id
     RETURNING * INTO v_bucket;
  ELSE
    v_amount := COALESCE(p_approved_amount, v_bucket.requested_amount);
    IF v_amount <= 0 THEN
      RAISE EXCEPTION 'Approved amount must be greater than zero' USING ERRCODE = 'PT422';
    END IF;

    -- The ONLY path (besides baseline) that changes the approved total.
    UPDATE public.projects
       SET approved_budget_total = approved_budget_total + v_amount
     WHERE id = v_bucket.project_id;

    PERFORM private.fin_move_contingency(
      v_bucket.project_id, v_amount, 'top_up', p_approver,
      COALESCE(p_note, v_bucket.reason), NULL, NULL, NULL, p_bucket_id);

    UPDATE public.contingency_buckets
       SET status = 'approved', approved_amount = v_amount,
           decided_by = p_approver, decided_at = NOW(), decision_note = p_note
     WHERE id = p_bucket_id
     RETURNING * INTO v_bucket;
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_bucket;
END;
$$;

COMMENT ON FUNCTION public.fn_approve_contingency_top_up(UUID, UUID, BOOLEAN, NUMERIC, TEXT) IS
  'A13: executive-only (PT403 otherwise). Approve: contingency line + amount, projects.approved_budget_total + amount (the only way the total grows after baseline), top_up ledger row tied to the bucket. Reject: decision recorded, no money moves.';


-- F.9  fn_close_accounting_month — finance / executive close
CREATE OR REPLACE FUNCTION public.fn_close_accounting_month(
  p_month DATE,
  p_actor UUID,
  p_notes TEXT DEFAULT NULL
)
RETURNS SETOF public.accounting_periods
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_period  public.accounting_periods;
  v_current DATE := date_trunc('month', (NOW() AT TIME ZONE 'America/Chicago'))::date;
BEGIN
  IF p_month IS NULL OR EXTRACT(DAY FROM p_month) <> 1 THEN
    RAISE EXCEPTION 'p_month must be the first day of a month (got %)', p_month USING ERRCODE = 'PT422';
  END IF;
  IF p_month > v_current THEN
    RAISE EXCEPTION 'Cannot close a future month (%)', p_month USING ERRCODE = 'PT422';
  END IF;
  IF p_actor IS NULL
     OR NOT (private.user_has_role(p_actor, 'finance') OR private.user_has_role(p_actor, 'executive')) THEN
    RAISE EXCEPTION 'Only finance or an executive can close a month' USING ERRCODE = 'PT403';
  END IF;

  SELECT * INTO v_period FROM public.accounting_periods WHERE period_month = p_month FOR UPDATE;
  IF FOUND AND v_period.status = 'closed' THEN
    RAISE EXCEPTION 'Month % is already closed', p_month USING ERRCODE = 'PT409';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  INSERT INTO public.accounting_periods (period_month, status, closed_by, closed_at, notes)
  VALUES (p_month, 'closed', p_actor, NOW(), p_notes)
  ON CONFLICT (period_month) DO UPDATE
     SET status = 'closed', closed_by = EXCLUDED.closed_by, closed_at = EXCLUDED.closed_at,
         notes = COALESCE(EXCLUDED.notes, public.accounting_periods.notes)
  RETURNING * INTO v_period;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_period;
END;
$$;

COMMENT ON FUNCTION public.fn_close_accounting_month(DATE, UUID, TEXT) IS
  'Closes a company-wide accounting month (finance or executive role, PT403 otherwise). From then on cash_flow_entries in that month are frozen and the month can never be reopened.';


-- F.10 Privileges: write RPCs for service_role only; internals not exposed.
DO $$
DECLARE
  f TEXT;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'public.fn_baseline_project_budget(uuid, uuid)',
    'public.fn_apply_bid_to_line(uuid, uuid, numeric, uuid)',
    'public.fn_reverse_bid_on_line(uuid, uuid, uuid, text)',
    'public.fn_lock_budget_line(uuid, uuid, uuid)',
    'public.fn_create_variance(uuid, text, numeric, uuid, uuid, uuid, date, date)',
    'public.fn_adjust_variance(uuid, numeric, uuid, text)',
    'public.fn_request_contingency_top_up(uuid, numeric, text, uuid)',
    'public.fn_approve_contingency_top_up(uuid, uuid, boolean, numeric, text)',
    'public.fn_close_accounting_month(date, uuid, text)',
    'private.fin_move_contingency(uuid, numeric, text, uuid, text, uuid, uuid, uuid, uuid)',
    'private.fin_lock_project(uuid, boolean, boolean)'
  ] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role', f);
  END LOOP;
END $$;

-- Trigger functions are not callable as RPCs, but keep them closed anyway.
REVOKE ALL ON FUNCTION public.fn_block_contingency_ledger_mutation() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_guard_budget_lines()               FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_check_flat_budget_total()          FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_guard_project_budget_total()       FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_guard_contingency_buckets()        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_guard_variance_lines()             FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_guard_accounting_periods()         FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_guard_cash_flow_closed_period()    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_sync_user_base_role()              FROM PUBLIC, anon, authenticated;

-- Private helpers: service_role (procedures) and authenticated (RLS) need them.
GRANT USAGE ON SCHEMA private TO service_role, authenticated;
REVOKE ALL ON FUNCTION private.fin_write_authorized()           FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.user_has_role(UUID, TEXT)        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.has_any_role(TEXT[])             FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.fin_write_authorized()        TO service_role, authenticated;
GRANT EXECUTE ON FUNCTION private.user_has_role(UUID, TEXT)     TO service_role;
GRANT EXECUTE ON FUNCTION private.has_any_role(TEXT[])          TO authenticated, service_role;


-- ============================================================================
-- SECTION G: ROW LEVEL SECURITY (reads only — writes go through FastAPI)
-- ============================================================================

DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'budget_templates', 'budget_template_lines', 'budget_lines', 'land_closings',
    'contingency_buckets', 'contingency_ledger', 'variance_lines',
    'internal_invoices', 'payment_approvals', 'finance_handoffs',
    'escrows', 'property_taxes',
    'accounting_periods', 'company_cash_items', 'cash_flow_entries',
    'financial_settings', 'financial_alerts', 'user_roles', 'approval_delegations'
  ] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon', t);
    EXECUTE format('REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE public.%I FROM authenticated', t);
    EXECUTE format('GRANT SELECT ON TABLE public.%I TO authenticated', t);
    EXECUTE format('GRANT ALL ON TABLE public.%I TO service_role', t);
  END LOOP;
END $$;

-- Any active internal user may read these (field managers see contingency).
DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'budget_templates', 'budget_template_lines', 'budget_lines', 'land_closings',
    'contingency_buckets', 'contingency_ledger', 'variance_lines',
    'payment_approvals', 'escrows', 'property_taxes', 'accounting_periods',
    'financial_settings', 'financial_alerts', 'user_roles', 'approval_delegations'
  ] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_select_authenticated', t);
    EXECUTE format(
      'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING ((SELECT private.is_active_user()))',
      t || '_select_authenticated', t);
  END LOOP;
END $$;

-- Finance-restricted reads (finance, executive, admin).
DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'internal_invoices', 'finance_handoffs', 'company_cash_items', 'cash_flow_entries'
  ] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_select_finance', t);
    EXECUTE format(
      'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING ((SELECT private.has_any_role(ARRAY[''finance'',''executive''])))',
      t || '_select_finance', t);
  END LOOP;
END $$;


-- ============================================================================
-- SECTION H: DEFAULT FINANCIAL SETTINGS (never overwrites existing values)
-- ============================================================================

INSERT INTO public.financial_settings (setting_key, value, description) VALUES
  ('default_contingency_percent',       '15'::jsonb,   'Program contingency % applied to the contingency base (total budget − land − contingency). Per-project override: projects.contingency_percent.'),
  ('contingency_min_percent',           '15'::jsonb,   'Lower bound of the program contingency range agreed at discovery.'),
  ('contingency_max_percent',           '20'::jsonb,   'Upper bound of the program contingency range agreed at discovery.'),
  ('bidding_target_contingency_percent','10'::jsonb,   'Target contingency left after bidding (checkpoint A4). Far below → executive escalation.'),
  ('bidding_escalation_percent',        '5'::jsonb,    'Contingency % after bidding at or below which the checkpoint escalates to executives. Open question — confirm with client.'),
  ('default_payment_terms_days',        '30'::jsonb,   'Default payment terms (days) for budget lines and contracts.'),
  ('default_field_approval_limit',      '5000'::jsonb, 'Amount a field manager may approve alone when users.approval_limit is NULL.'),
  ('executive_approval_threshold',      'null'::jsonb, 'Payments above this amount also need an executive approval. NULL = not configured yet (open question).'),
  ('contingency_near_zero_percent',     '5'::jsonb,    'Contingency left % at or below which the urgent near-zero alert fires. Open question — confirm with client.'),
  ('alert_recipients',                  '{"warning": [], "urgent": [], "critical": []}'::jsonb, 'User ids (or emails) per alert severity, in addition to the project manager / field manager.'),
  ('land_team_emails',                  '[]'::jsonb,   'Land team addresses copied on payment approvals.'),
  ('finance_emails',                    '[]'::jsonb,   'Finance addresses receiving hand-offs and the daily summary.'),
  ('sales_emails',                      '[]'::jsonb,   'Sales addresses notified of approved contingency top-ups.'),
  ('po_number_format',                  '"PO-{YYYY}-{SEQ:05}"'::jsonb, 'Format for internal invoice / PO numbers. Open question — confirm with client.'),
  ('environment',                       '"unset"'::jsonb, 'Set to "development" on non-production databases. The dev seed script refuses to run unless it is "development".')
ON CONFLICT (setting_key) DO NOTHING;


-- ============================================================================
-- SECTION I: SCHEMA VERSION MARKER
-- ============================================================================
-- Always updated (not DO NOTHING) so it reflects the last migration applied.

INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.0.0 (20261111_financial_phase1)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;

COMMIT;

-- ============================================================================
-- END OF 001_financial_foundation.sql
-- ============================================================================
