-- ============================================================================
-- BluOnX Financial Automation — Phase 2 · Module 2
-- 001  PROJECT BUDGET STRUCTURE (schema change script)
-- ============================================================================
-- Version:  4.1.0
-- Date:     November 18, 2026
-- Requires: 20261111_financial_phase1 (schema v4.0) applied
-- Engine:   PostgreSQL 15+ (Supabase)
-- ============================================================================
--
-- WHAT THIS SCRIPT DOES
--   • Default standard budget template (only if no default exists)
--   • fn_create_project_budget   — template + every task → draft budget
--   • fn_reorder_budget_lines    — atomic re-ordering
--   • fn_remove_budget_line      — checklist removal with money rules
--   • fn_apply_budget_import     — atomic CSV / Excel import into a draft budget
--   • fn_categorise_internal_invoice — invoice → line, overage → variance,
--                                      payment approval requests
--   • Task → budget line sync triggers (no double entry)
--   • Views v_budget_lines / v_project_budget_summary (totals in NUMERIC)
--   • Private storage bucket finance-documents (if storage schema exists)
--
-- SAFETY: additive and idempotent, wrapped in one transaction. No existing
-- function or Phase 1 object changes behaviour. The task triggers are a no-op
-- for projects without a budget (budget_status = 'none').
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $$
BEGIN
  IF to_regclass('public.budget_lines') IS NULL OR to_regclass('public.contingency_ledger') IS NULL THEN
    RAISE EXCEPTION 'Phase 1 (20261111_financial_phase1) must be applied first.';
  END IF;
END $$;


-- ============================================================================
-- SECTION A: DEFAULT STANDARD TEMPLATE
-- ============================================================================
-- Activity rows (bid_activity / internal_tm) are ORDERING SLOTS: activity lines
-- only ever exist as tasks; a slot decides where a matching task sits and under
-- which heading. Admins replace this layout in Settings → Budget Template.

DO $$
DECLARE
  v_tmpl UUID;
BEGIN
  IF EXISTS (SELECT 1 FROM public.budget_templates
              WHERE is_default AND is_active AND deleted_at IS NULL) THEN
    RETURN;
  END IF;

  INSERT INTO public.budget_templates (name, description, is_default)
  VALUES ('Standard development budget',
          'Starting layout from land acquisition down to escrows and property taxes. Edit in Settings → Budget Template.',
          TRUE)
  RETURNING id INTO v_tmpl;

  INSERT INTO public.budget_template_lines
    (budget_template_id, line_type, line_subtype, name, section_name, sort_order, default_cash_bucket)
  VALUES
    (v_tmpl, 'land',         'land_purchase',       'Land purchase',                   'Land',        10, 'land'),
    (v_tmpl, 'land',         'earnest_money',       'Earnest money',                   'Land',        20, 'land'),
    (v_tmpl, 'land',         'due_diligence',       'Due diligence',                   'Land',        30, 'land'),
    (v_tmpl, 'soft_cost',    'engineering',         'Engineering',                     'Soft costs',  40, 'land'),
    (v_tmpl, 'permit',       NULL,                  'Permits',                         'Soft costs',  50, 'land'),
    (v_tmpl, 'impact_fee',   NULL,                  'Impact fees',                     'Soft costs',  60, 'land'),
    (v_tmpl, 'soft_cost',    'other',               'Other soft costs',                'Soft costs',  70, 'land'),
    (v_tmpl, 'bid_activity', NULL,                  'Clearing',                        'Site work',   80, 'land'),
    (v_tmpl, 'bid_activity', NULL,                  'Grading',                         'Site work',   90, 'land'),
    (v_tmpl, 'bid_activity', NULL,                  'Sanitary sewer',                  'Utilities',  100, 'land'),
    (v_tmpl, 'bid_activity', NULL,                  'Water + storm',                   'Utilities',  110, 'land'),
    (v_tmpl, 'bid_activity', NULL,                  'Paving',                          'Roads',      120, 'land'),
    (v_tmpl, 'internal_tm',  NULL,                  'Attorney',                        'Internal',   130, 'land'),
    (v_tmpl, 'contingency',  NULL,                  'Contingency',                     'Contingency',140, 'land'),
    (v_tmpl, 'long_tail',    'escrow_bond_premium', 'Escrow bond / insurance premium', 'Long-tail',  150, 'land'),
    (v_tmpl, 'long_tail',    'escrow_repairs',      'Escrow repairs to city standard', 'Long-tail',  160, 'land'),
    (v_tmpl, 'long_tail',    'property_tax',        'Property tax',                    'Long-tail',  170, 'land');
END $$;


-- ============================================================================
-- SECTION B: INTERNAL HELPERS
-- ============================================================================

-- B.1 Map a task bid_type to its budget line type.
CREATE OR REPLACE FUNCTION private.fin_line_type_for_bid_type(p_bid_type TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
SET search_path = ''
AS $$
  SELECT CASE WHEN p_bid_type = 'internal' THEN 'internal_tm' ELSE 'bid_activity' END;
$$;

-- B.2 Invoiced total on a line. SECURITY DEFINER so the totals views are the
--     same for every viewer even though internal_invoices rows are
--     finance-restricted (only the SUM leaves this function).
CREATE OR REPLACE FUNCTION private.fin_line_invoiced(p_line_id UUID)
RETURNS NUMERIC
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT COALESCE(SUM(amount), 0)
    FROM public.internal_invoices
   WHERE budget_line_id = p_line_id
     AND deleted_at IS NULL
     AND status NOT IN ('received', 'rejected', 'cancelled');
$$;

COMMENT ON FUNCTION private.fin_line_invoiced(UUID) IS
  'Sum of categorised (non-rejected, non-cancelled) internal invoices on a budget line. SECURITY DEFINER: exposes only the total, so budget totals are identical for every role.';

-- B.3 Is a line free of money and commitments? (removal / type change rules)
CREATE OR REPLACE FUNCTION private.fin_line_is_empty(p_line_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT l.budget_amount = 0
     AND l.committed_amount = 0
     AND l.award_id IS NULL
     AND NOT EXISTS (SELECT 1 FROM public.internal_invoices i
                      WHERE i.budget_line_id = l.id AND i.deleted_at IS NULL
                        AND i.status NOT IN ('rejected', 'cancelled'))
     AND NOT EXISTS (SELECT 1 FROM public.payment_approvals pa
                      WHERE pa.budget_line_id = l.id AND pa.status NOT IN ('rejected', 'cancelled'))
     AND NOT EXISTS (SELECT 1 FROM public.budget_lines c
                      WHERE c.parent_line_id = l.id AND c.deleted_at IS NULL)
    FROM public.budget_lines l
   WHERE l.id = p_line_id;
$$;

-- B.4 Next sort position for a new activity line (after the last line of the
--     same type, else before contingency, else at the end).
CREATE OR REPLACE FUNCTION private.fin_next_activity_position(p_project_id UUID, p_line_type TEXT)
RETURNS TABLE (sort_order INTEGER, section_name VARCHAR)
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  WITH same AS (
    SELECT l.sort_order, l.section_name FROM public.budget_lines l
     WHERE l.project_id = p_project_id AND l.deleted_at IS NULL AND l.line_type = p_line_type
     ORDER BY l.sort_order DESC LIMIT 1
  ), cont AS (
    SELECT l.sort_order FROM public.budget_lines l
     WHERE l.project_id = p_project_id AND l.deleted_at IS NULL AND l.line_type = 'contingency'
  ), mx AS (
    SELECT COALESCE(MAX(l.sort_order), 0) AS m FROM public.budget_lines l
     WHERE l.project_id = p_project_id AND l.deleted_at IS NULL
  )
  SELECT COALESCE((SELECT s.sort_order + 1 FROM same s),
                  (SELECT c.sort_order - 1 FROM cont c),
                  (SELECT m + 10 FROM mx)),
         COALESCE((SELECT s.section_name FROM same s),
                  CASE WHEN p_line_type = 'internal_tm' THEN 'Internal' ELSE 'Site work' END)::VARCHAR;
$$;


-- ============================================================================
-- SECTION C: PROCEDURES
-- ============================================================================

-- C.1 fn_create_project_budget ─ template + every task → draft budget
CREATE OR REPLACE FUNCTION public.fn_create_project_budget(
  p_project_id          UUID,
  p_actor               UUID,
  p_template_id         UUID DEFAULT NULL,
  p_contingency_percent NUMERIC DEFAULT NULL
)
RETURNS SETOF public.budget_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project   public.projects;
  v_template  UUID;
  v_pct       NUMERIC;
  v_rank      INTEGER := 0;
  v_tl        RECORD;
  v_task      RECORD;
  v_slot      RECORD;
  v_base      NUMERIC;
  v_cont_id   UUID;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;
  IF p_contingency_percent IS NOT NULL AND (p_contingency_percent < 0 OR p_contingency_percent > 100) THEN
    RAISE EXCEPTION 'Contingency %% must be between 0 and 100 (got %)', p_contingency_percent USING ERRCODE = 'PT422';
  END IF;

  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.budget_status <> 'none' THEN
    RAISE EXCEPTION 'Project % already has a budget (%)', p_project_id, v_project.budget_status USING ERRCODE = 'PT409';
  END IF;

  v_template := COALESCE(p_template_id, (
    SELECT id FROM public.budget_templates
     WHERE is_default AND is_active AND deleted_at IS NULL LIMIT 1));
  IF v_template IS NULL OR NOT EXISTS (
       SELECT 1 FROM public.budget_templates WHERE id = v_template AND is_active AND deleted_at IS NULL) THEN
    RAISE EXCEPTION 'No active budget template found. Set one up in Settings → Budget Template.' USING ERRCODE = 'PT409';
  END IF;

  v_pct := COALESCE(p_contingency_percent, v_project.contingency_percent,
                    (SELECT (value #>> '{}')::numeric FROM public.financial_settings
                      WHERE setting_key = 'default_contingency_percent'),
                    15);

  UPDATE public.projects
     SET budget_status = 'draft', contingency_percent = v_pct
   WHERE id = p_project_id;

  -- Slots ranked 1..n in template order; line sort_order = rank * 1000 (+ task order).
  CREATE TEMP TABLE IF NOT EXISTS _fin_slots (
    rnk INTEGER, line_type TEXT, name TEXT, section_name TEXT, trade_id UUID, template_line_id UUID
  ) ON COMMIT DROP;
  TRUNCATE _fin_slots;

  FOR v_tl IN
    SELECT * FROM public.budget_template_lines
     WHERE budget_template_id = v_template AND is_active
     ORDER BY sort_order, created_at
  LOOP
    v_rank := v_rank + 1;
    IF v_tl.line_type IN ('bid_activity', 'internal_tm') THEN
      INSERT INTO _fin_slots VALUES (v_rank, v_tl.line_type, lower(btrim(v_tl.name)),
                                     v_tl.section_name, v_tl.trade_id, v_tl.id);
    ELSE
      INSERT INTO public.budget_lines (
        project_id, template_line_id, line_type, line_subtype, name, section_name, sort_order,
        budget_amount, payment_terms_days, cash_bucket, is_payment_exempt, created_by, updated_by
      ) VALUES (
        p_project_id, v_tl.id, v_tl.line_type, v_tl.line_subtype, v_tl.name, v_tl.section_name, v_rank * 1000,
        CASE WHEN v_tl.line_type = 'contingency' THEN 0 ELSE COALESCE(v_tl.default_amount, 0) END,
        COALESCE(v_tl.default_payment_terms_days,
                 (SELECT (value #>> '{}')::int FROM public.financial_settings WHERE setting_key = 'default_payment_terms_days'),
                 30),
        COALESCE(v_tl.default_cash_bucket, 'land'),
        v_tl.line_type IN ('land', 'contingency'),
        p_actor, p_actor
      );
    END IF;
  END LOOP;

  -- Every live task becomes a line, at its matching slot (name, then trade).
  FOR v_task IN
    SELECT * FROM public.tasks
     WHERE project_id = p_project_id AND deleted_at IS NULL
     ORDER BY sort_order, created_at
  LOOP
    SELECT * INTO v_slot FROM _fin_slots s
     WHERE s.line_type = private.fin_line_type_for_bid_type(v_task.bid_type)
       AND s.name = lower(btrim(v_task.name))
     ORDER BY s.rnk LIMIT 1;
    IF NOT FOUND THEN
      SELECT * INTO v_slot FROM _fin_slots s
       WHERE s.line_type = private.fin_line_type_for_bid_type(v_task.bid_type)
         AND s.trade_id = v_task.trade_id
       ORDER BY s.rnk LIMIT 1;
    END IF;
    IF NOT FOUND THEN  -- no slot: after the last slot of that type, else at the end
      SELECT * INTO v_slot FROM _fin_slots s
       WHERE s.line_type = private.fin_line_type_for_bid_type(v_task.bid_type)
       ORDER BY s.rnk DESC LIMIT 1;
      IF NOT FOUND THEN
        v_slot := NULL;
      END IF;
    END IF;

    INSERT INTO public.budget_lines (
      project_id, task_id, template_line_id, line_type, name, description, section_name, sort_order,
      budget_amount, payment_terms_days, cash_bucket, created_by, updated_by
    ) VALUES (
      p_project_id, v_task.id, v_slot.template_line_id,
      private.fin_line_type_for_bid_type(v_task.bid_type),
      v_task.name, v_task.description,
      COALESCE(v_slot.section_name, CASE WHEN v_task.bid_type = 'internal' THEN 'Internal' ELSE 'Site work' END),
      COALESCE(v_slot.rnk, v_rank + 1) * 1000 + LEAST(GREATEST(v_task.sort_order, 0), 999),
      COALESCE(v_task.budget_estimate, 0),
      COALESCE((SELECT (value #>> '{}')::int FROM public.financial_settings WHERE setting_key = 'default_payment_terms_days'), 30),
      'land', p_actor, p_actor
    );
  END LOOP;

  -- Contingency: a line always exists; amount = pct × base (base excludes land and contingency).
  SELECT id INTO v_cont_id FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL;
  IF v_cont_id IS NULL THEN
    INSERT INTO public.budget_lines (project_id, line_type, name, section_name, sort_order,
                                     budget_amount, is_payment_exempt, created_by, updated_by)
    VALUES (p_project_id, 'contingency', 'Contingency', 'Contingency', (v_rank + 2) * 1000, 0, TRUE, p_actor, p_actor)
    RETURNING id INTO v_cont_id;
  END IF;

  SELECT COALESCE(SUM(budget_amount), 0) INTO v_base FROM public.budget_lines
   WHERE project_id = p_project_id AND deleted_at IS NULL AND line_type NOT IN ('land', 'contingency');

  UPDATE public.budget_lines
     SET budget_amount = round(v_base * v_pct / 100, 2)
   WHERE id = v_cont_id;

  RETURN QUERY
    SELECT * FROM public.budget_lines
     WHERE project_id = p_project_id AND deleted_at IS NULL
     ORDER BY sort_order;
END;
$$;

COMMENT ON FUNCTION public.fn_create_project_budget(UUID, UUID, UUID, NUMERIC) IS
  'Creates a DRAFT budget: one line per non-activity template row, one line per live task placed at its matching template slot (name, then trade), and the contingency line at pct × base (base excludes land and contingency). none → draft. PT409 if a budget exists.';


-- C.2 fn_reorder_budget_lines
CREATE OR REPLACE FUNCTION public.fn_reorder_budget_lines(
  p_project_id UUID,
  p_line_ids   UUID[],
  p_actor      UUID
)
RETURNS SETOF public.budget_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_live   INTEGER;
  v_given  INTEGER;
BEGIN
  PERFORM private.fin_lock_project(p_project_id, FALSE, FALSE);

  SELECT count(*) INTO v_live FROM public.budget_lines
   WHERE project_id = p_project_id AND deleted_at IS NULL;
  SELECT count(DISTINCT x) INTO v_given FROM unnest(p_line_ids) x
   WHERE x IN (SELECT id FROM public.budget_lines WHERE project_id = p_project_id AND deleted_at IS NULL);

  IF v_given <> v_live OR cardinality(p_line_ids) <> v_live THEN
    RAISE EXCEPTION 'Reorder must list every live line of the project exactly once (% given, % live)',
      cardinality(p_line_ids), v_live USING ERRCODE = 'PT422';
  END IF;

  UPDATE public.budget_lines l
     SET sort_order = o.ord * 10, updated_by = p_actor
    FROM unnest(p_line_ids) WITH ORDINALITY AS o(id, ord)
   WHERE l.id = o.id AND l.sort_order IS DISTINCT FROM o.ord * 10;

  RETURN QUERY SELECT * FROM public.budget_lines
                WHERE project_id = p_project_id AND deleted_at IS NULL ORDER BY sort_order;
END;
$$;

COMMENT ON FUNCTION public.fn_reorder_budget_lines(UUID, UUID[], UUID) IS
  'Rewrites sort_order for every live line of a project in the given order (10, 20, 30 …). Must list each live line exactly once.';


-- C.3 fn_remove_budget_line ─ checklist removal
CREATE OR REPLACE FUNCTION public.fn_remove_budget_line(
  p_line_id UUID,
  p_actor   UUID
)
RETURNS SETOF public.budget_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_line    public.budget_lines;
  v_project public.projects;
  v_result  public.budget_lines;
BEGIN
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_line_id;
  IF NOT FOUND OR v_line.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Budget line % not found', p_line_id USING ERRCODE = 'PT404';
  END IF;

  v_project := private.fin_lock_project(v_line.project_id, FALSE, FALSE);
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_line_id FOR UPDATE;

  IF v_line.line_type = 'contingency' THEN
    RAISE EXCEPTION 'The contingency line cannot be removed' USING ERRCODE = 'PT409';
  END IF;
  IF v_line.line_type = 'variance' THEN
    RAISE EXCEPTION 'Variances are cancelled, not removed' USING ERRCODE = 'PT422';
  END IF;
  IF v_line.task_id IS NOT NULL AND EXISTS (
       SELECT 1 FROM public.tasks WHERE id = v_line.task_id AND deleted_at IS NULL) THEN
    RAISE EXCEPTION 'This line belongs to task "%". Delete the task (Tasks tab) and its budget line goes with it.', v_line.name
      USING ERRCODE = 'PT409';
  END IF;
  IF EXISTS (SELECT 1 FROM public.land_closings WHERE budget_line_id = p_line_id AND status <> 'cancelled') THEN
    RAISE EXCEPTION 'Cancel this line''s land closings first' USING ERRCODE = 'PT409';
  END IF;
  IF EXISTS (SELECT 1 FROM public.escrows
              WHERE (premium_line_id = p_line_id OR repair_line_id = p_line_id)
                AND deleted_at IS NULL AND status <> 'cancelled') THEN
    RAISE EXCEPTION 'This line is an open escrow cost' USING ERRCODE = 'PT409';
  END IF;

  IF v_project.budget_status = 'baselined' THEN
    IF NOT private.fin_line_is_empty(p_line_id) THEN
      RAISE EXCEPTION 'Budget is baselined: only a $0 line with no award, invoices, approvals or variances can be removed (line "%" holds %).',
        v_line.name, v_line.budget_amount USING ERRCODE = 'PT409';
    END IF;
  ELSE
    IF EXISTS (SELECT 1 FROM public.internal_invoices WHERE budget_line_id = p_line_id
                 AND deleted_at IS NULL AND status NOT IN ('rejected', 'cancelled'))
       OR EXISTS (SELECT 1 FROM public.payment_approvals WHERE budget_line_id = p_line_id
                    AND status NOT IN ('rejected', 'cancelled')) THEN
      RAISE EXCEPTION 'Line "%" has invoices or payment approvals', v_line.name USING ERRCODE = 'PT409';
    END IF;
  END IF;

  UPDATE public.budget_lines
     SET deleted_at = NOW(), updated_by = p_actor
   WHERE id = p_line_id
   RETURNING * INTO v_result;

  RETURN NEXT v_result;
END;
$$;

COMMENT ON FUNCTION public.fn_remove_budget_line(UUID, UUID) IS
  'Soft-deletes a non-task line (the budget doubles as a checklist). Never the contingency line; task lines go with their task; after baseline only $0 lines with no award / invoices / approvals / variances.';


-- C.4 fn_apply_budget_import ─ draft budgets only
-- p_rows: JSON array of {line_id?, name, line_type?, line_subtype?, section_name?,
--          budget_amount?, anticipated_start_date?, anticipated_end_date?,
--          payment_terms_days?, cash_bucket?}
CREATE OR REPLACE FUNCTION public.fn_apply_budget_import(
  p_project_id UUID,
  p_rows       JSONB,
  p_actor      UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project  public.projects;
  v_row      JSONB;
  v_line     public.budget_lines;
  v_updated  INTEGER := 0;
  v_added    INTEGER := 0;
  v_sort     INTEGER;
  v_type     TEXT;
BEGIN
  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.budget_status <> 'draft' THEN
    RAISE EXCEPTION 'Import is only possible while the budget is a draft (status %)', v_project.budget_status
      USING ERRCODE = 'PT409';
  END IF;
  IF jsonb_typeof(p_rows) <> 'array' THEN
    RAISE EXCEPTION 'p_rows must be a JSON array' USING ERRCODE = 'PT422';
  END IF;

  SELECT COALESCE(MAX(sort_order), 0) INTO v_sort FROM public.budget_lines
   WHERE project_id = p_project_id AND deleted_at IS NULL AND line_type <> 'contingency';

  FOR v_row IN SELECT * FROM jsonb_array_elements(p_rows) LOOP
    IF v_row ? 'line_id' AND v_row ->> 'line_id' IS NOT NULL THEN
      SELECT * INTO v_line FROM public.budget_lines
       WHERE id = (v_row ->> 'line_id')::uuid AND project_id = p_project_id AND deleted_at IS NULL
       FOR UPDATE;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'Import row refers to unknown line %', v_row ->> 'line_id' USING ERRCODE = 'PT404';
      END IF;

      UPDATE public.budget_lines SET
        budget_amount          = COALESCE((v_row ->> 'budget_amount')::numeric, budget_amount),
        anticipated_start_date = COALESCE((v_row ->> 'anticipated_start_date')::date, anticipated_start_date),
        anticipated_end_date   = COALESCE((v_row ->> 'anticipated_end_date')::date, anticipated_end_date),
        payment_terms_days     = COALESCE((v_row ->> 'payment_terms_days')::int, payment_terms_days),
        cash_bucket            = COALESCE(v_row ->> 'cash_bucket', cash_bucket),
        section_name           = COALESCE(v_row ->> 'section_name', section_name),
        updated_by             = p_actor
       WHERE id = v_line.id;
      v_updated := v_updated + 1;
    ELSE
      v_type := COALESCE(v_row ->> 'line_type', 'soft_cost');
      IF v_type IN ('bid_activity', 'contingency', 'variance') THEN
        RAISE EXCEPTION 'Import cannot add a % line ("%"); bid activities come from tasks', v_type, v_row ->> 'name'
          USING ERRCODE = 'PT422';
      END IF;
      -- Place the new line after the last line of its heading, else just
      -- before contingency, else at the end.
      SELECT COALESCE(
               (SELECT MAX(sort_order) + 1 FROM public.budget_lines
                 WHERE project_id = p_project_id AND deleted_at IS NULL
                   AND section_name = NULLIF(v_row ->> 'section_name', '')),
               (SELECT MIN(sort_order) - 1 FROM public.budget_lines
                 WHERE project_id = p_project_id AND deleted_at IS NULL AND line_type = 'contingency'),
               v_sort + 1)
        INTO v_sort;
      INSERT INTO public.budget_lines (
        project_id, line_type, line_subtype, name, section_name, sort_order, budget_amount,
        anticipated_start_date, anticipated_end_date, payment_terms_days, cash_bucket,
        is_payment_exempt, created_by, updated_by
      ) VALUES (
        p_project_id, v_type, NULLIF(v_row ->> 'line_subtype', ''), btrim(v_row ->> 'name'),
        NULLIF(v_row ->> 'section_name', ''), v_sort,
        COALESCE((v_row ->> 'budget_amount')::numeric, 0),
        (v_row ->> 'anticipated_start_date')::date, (v_row ->> 'anticipated_end_date')::date,
        COALESCE((v_row ->> 'payment_terms_days')::int, 30),
        COALESCE(v_row ->> 'cash_bucket', 'land'),
        v_type = 'land', p_actor, p_actor
      );
      v_added := v_added + 1;
    END IF;
  END LOOP;

  RETURN jsonb_build_object('updated', v_updated, 'added', v_added);
END;
$$;

COMMENT ON FUNCTION public.fn_apply_budget_import(UUID, JSONB, UUID) IS
  'Applies confirmed CSV / Excel import rows to a DRAFT budget in one transaction: rows with line_id update amount / dates / terms / bucket / section; rows without add non-activity lines.';


-- C.5 fn_categorise_internal_invoice ─ invoice → line, overage → variance
CREATE OR REPLACE FUNCTION public.fn_categorise_internal_invoice(
  p_invoice_id UUID,
  p_line_id    UUID,
  p_actor      UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_inv        public.internal_invoices;
  v_line       public.budget_lines;
  v_project    public.projects;
  v_other      NUMERIC;
  v_allowance  NUMERIC;
  v_overage    NUMERIC := 0;
  v_in_amount  NUMERIC;
  v_var_line   public.budget_lines;
  v_variance   public.variance_lines;
  v_approvals  JSONB := '[]'::jsonb;
  v_pa_id      UUID;
  v_label      TEXT;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_inv FROM public.internal_invoices WHERE id = p_invoice_id;
  IF NOT FOUND OR v_inv.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Invoice % not found', p_invoice_id USING ERRCODE = 'PT404';
  END IF;

  v_project := private.fin_lock_project(v_inv.project_id, FALSE, TRUE);
  SELECT * INTO v_inv FROM public.internal_invoices WHERE id = p_invoice_id FOR UPDATE;

  IF v_inv.status NOT IN ('received', 'categorised') THEN
    RAISE EXCEPTION 'Invoice is already % and cannot be re-categorised', v_inv.status USING ERRCODE = 'PT409';
  END IF;
  IF v_inv.amount <= 0 THEN
    RAISE EXCEPTION 'Invoice amount must be greater than zero' USING ERRCODE = 'PT422';
  END IF;
  IF v_project.budget_status = 'none' THEN
    RAISE EXCEPTION 'The project has no budget yet' USING ERRCODE = 'PT409';
  END IF;

  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_line_id FOR UPDATE;
  IF NOT FOUND OR v_line.deleted_at IS NOT NULL OR v_line.project_id <> v_inv.project_id THEN
    RAISE EXCEPTION 'Budget line % not found on this project', p_line_id USING ERRCODE = 'PT404';
  END IF;
  IF v_line.line_type <> 'internal_tm' THEN
    RAISE EXCEPTION 'Invoices are categorised to internal T&M lines only (line "%" is %)', v_line.name, v_line.line_type
      USING ERRCODE = 'PT422';
  END IF;

  SELECT COALESCE(SUM(amount), 0) INTO v_other FROM public.internal_invoices
   WHERE budget_line_id = p_line_id AND id <> p_invoice_id AND deleted_at IS NULL
     AND status NOT IN ('received', 'rejected', 'cancelled');

  v_allowance := GREATEST(v_line.budget_amount - v_other, 0);
  v_overage   := GREATEST(v_inv.amount - v_allowance, 0);
  v_in_amount := v_inv.amount - v_overage;
  v_label     := COALESCE(NULLIF(btrim(v_inv.invoice_number), ''), v_inv.payee_name, 'invoice');

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  -- Overage on a baselined budget → variance funded from contingency.
  IF v_overage > 0 AND v_project.budget_status = 'baselined' THEN
    INSERT INTO public.budget_lines (
      project_id, parent_line_id, line_type, name, description, section_name, sort_order,
      budget_amount, anticipated_start_date, anticipated_end_date,
      payment_terms_days, cash_bucket, approval_state, created_by, updated_by
    ) VALUES (
      v_line.project_id, v_line.id, 'variance',
      left('Variance: invoice overage ' || v_label, 255),
      format('Invoice %s exceeds the remaining allowance of %s on "%s" by %s', v_label, v_allowance, v_line.name, v_overage),
      v_line.section_name, v_line.sort_order, v_overage,
      v_line.anticipated_start_date, v_line.anticipated_end_date,
      v_line.payment_terms_days, v_line.cash_bucket, 'pending', p_actor, p_actor
    ) RETURNING * INTO v_var_line;

    INSERT INTO public.variance_lines (
      project_id, budget_line_id, parent_budget_line_id, vendor_id,
      description, estimated_amount, status, created_by
    ) VALUES (
      v_line.project_id, v_var_line.id, v_line.id, v_inv.vendor_id,
      format('Invoice overage — %s', v_label), v_overage, 'pending_approval', p_actor
    ) RETURNING * INTO v_variance;

    PERFORM private.fin_move_contingency(
      v_line.project_id, -v_overage, 'invoice_overage', p_actor,
      format('Invoice %s over the "%s" allowance by %s', v_label, v_line.name, v_overage),
      v_var_line.id, v_variance.id, NULL, NULL);
  ELSE
    v_in_amount := v_inv.amount;   -- draft: whole invoice on the line; overage reported
  END IF;

  IF v_in_amount > 0 THEN
    INSERT INTO public.payment_approvals (project_id, budget_line_id, internal_invoice_id, vendor_id,
                                          amount, payment_kind, status, requested_by)
    VALUES (v_line.project_id, v_line.id, p_invoice_id, v_inv.vendor_id, v_in_amount, 'full', 'pending', p_actor)
    RETURNING id INTO v_pa_id;
    v_approvals := v_approvals || jsonb_build_object('id', v_pa_id, 'budget_line_id', v_line.id, 'amount', v_in_amount);
  END IF;

  IF v_var_line.id IS NOT NULL THEN
    INSERT INTO public.payment_approvals (project_id, budget_line_id, internal_invoice_id, vendor_id,
                                          amount, payment_kind, status, requested_by)
    VALUES (v_line.project_id, v_var_line.id, p_invoice_id, v_inv.vendor_id, v_overage, 'full', 'pending', p_actor)
    RETURNING id INTO v_pa_id;
    v_approvals := v_approvals || jsonb_build_object('id', v_pa_id, 'budget_line_id', v_var_line.id, 'amount', v_overage);
  END IF;

  UPDATE public.budget_lines SET approval_state = 'pending', updated_by = p_actor
   WHERE id = v_line.id AND approval_state IN ('not_requested', 'rejected');

  UPDATE public.internal_invoices
     SET budget_line_id = p_line_id, status = 'in_approval'
   WHERE id = p_invoice_id
   RETURNING * INTO v_inv;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN jsonb_build_object(
    'invoice_id',        v_inv.id,
    'budget_line_id',    p_line_id,
    'status',            v_inv.status,
    'allowance',         v_allowance,
    'overage',           v_overage,
    'variance_id',       v_variance.id,
    'variance_line_id',  v_var_line.id,
    'budget_status',     v_project.budget_status,
    'payment_approvals', v_approvals
  );
END;
$$;

COMMENT ON FUNCTION public.fn_categorise_internal_invoice(UUID, UUID, UUID) IS
  'Categorises an internal invoice to an internal T&M line and starts payment approval (pending requests). Allowance = line budget − other categorised invoices. On a baselined budget the overage becomes a variance line funded from contingency (ledger invoice_overage) with its own approval request; on a draft budget the overage is only reported.';


-- ============================================================================
-- SECTION D: TASK → BUDGET LINE SYNC (no double entry)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.fn_sync_task_budget_line()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_status   TEXT;
  v_line     public.budget_lines;
  v_pos      RECORD;
  v_type     TEXT;
  v_amount   NUMERIC;
BEGIN
  SELECT budget_status INTO v_status FROM public.projects WHERE id = NEW.project_id;
  IF v_status IS NULL OR v_status = 'none' THEN
    RETURN NEW;   -- no budget on this project: nothing to sync
  END IF;

  SELECT * INTO v_line FROM public.budget_lines
   WHERE task_id = NEW.id AND deleted_at IS NULL;

  v_type := private.fin_line_type_for_bid_type(NEW.bid_type);

  -- ── Task soft-deleted → its line goes too (money rules apply) ────────────
  IF TG_OP = 'UPDATE' AND NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
    IF v_line.id IS NOT NULL THEN
      IF v_status = 'baselined' AND NOT private.fin_line_is_empty(v_line.id) THEN
        RAISE EXCEPTION 'Task "%" cannot be deleted: its budget line holds % (or has an award, invoices or variances). Settle the line first.',
          NEW.name, v_line.budget_amount USING ERRCODE = 'PT409';
      END IF;
      UPDATE public.budget_lines SET deleted_at = NOW() WHERE id = v_line.id;
    END IF;
    RETURN NEW;
  END IF;

  IF NEW.deleted_at IS NOT NULL THEN
    RETURN NEW;
  END IF;

  -- ── New / restored task → new line ──────────────────────────────────────
  IF v_line.id IS NULL THEN
    SELECT * INTO v_pos FROM private.fin_next_activity_position(NEW.project_id, v_type);
    INSERT INTO public.budget_lines (
      project_id, task_id, line_type, name, description, section_name, sort_order,
      budget_amount, payment_terms_days, cash_bucket, created_by, updated_by
    ) VALUES (
      NEW.project_id, NEW.id, v_type, NEW.name, NEW.description, v_pos.section_name, v_pos.sort_order,
      CASE WHEN v_status = 'draft' THEN COALESCE(NEW.budget_estimate, 0) ELSE 0 END,
      COALESCE((SELECT (value #>> '{}')::int FROM public.financial_settings WHERE setting_key = 'default_payment_terms_days'), 30),
      'land', NEW.created_by, NEW.created_by
    );
    RETURN NEW;
  END IF;

  IF TG_OP <> 'UPDATE' THEN
    RETURN NEW;
  END IF;

  -- ── bid_type change → replace the line with the right type ──────────────
  IF NEW.bid_type IS DISTINCT FROM OLD.bid_type AND v_line.line_type <> v_type THEN
    IF v_status = 'baselined' AND NOT private.fin_line_is_empty(v_line.id) THEN
      RAISE EXCEPTION 'Task "%" type cannot change: its budget line holds money or commitments.', NEW.name
        USING ERRCODE = 'PT409';
    END IF;
    v_amount := CASE WHEN v_status = 'draft' THEN v_line.budget_amount ELSE 0 END;
    UPDATE public.budget_lines SET deleted_at = NOW() WHERE id = v_line.id;
    INSERT INTO public.budget_lines (
      project_id, task_id, template_line_id, line_type, name, description, section_name, sort_order,
      budget_amount, anticipated_start_date, anticipated_end_date, payment_terms_days, cash_bucket,
      created_by, updated_by
    ) VALUES (
      NEW.project_id, NEW.id, v_line.template_line_id, v_type, NEW.name, v_line.description,
      v_line.section_name, v_line.sort_order, v_amount,
      v_line.anticipated_start_date, v_line.anticipated_end_date, v_line.payment_terms_days, v_line.cash_bucket,
      v_line.created_by, NEW.created_by
    );
    RETURN NEW;
  END IF;

  -- ── Name follows the task ────────────────────────────────────────────────
  IF NEW.name IS DISTINCT FROM OLD.name THEN
    UPDATE public.budget_lines SET name = NEW.name WHERE id = v_line.id;
  END IF;

  -- ── Estimate follows the task while draft and untouched ─────────────────
  IF NEW.budget_estimate IS DISTINCT FROM OLD.budget_estimate
     AND v_status = 'draft'
     AND v_line.award_id IS NULL
     AND v_line.budget_amount = COALESCE(OLD.budget_estimate, 0) THEN
    UPDATE public.budget_lines SET budget_amount = COALESCE(NEW.budget_estimate, 0) WHERE id = v_line.id;
  END IF;

  RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.fn_sync_task_budget_line() IS
  'Keeps budget lines in step with tasks for projects that have a budget: new / restored task → line (draft: estimate, baselined: $0); rename → line name; estimate change → line amount while draft and untouched; bid_type change → line replaced with the right type; soft delete → line removed (PT409 if it carries money after baseline). No-op for projects without a budget.';

DROP TRIGGER IF EXISTS trg_tasks_sync_budget_line ON public.tasks;
CREATE TRIGGER trg_tasks_sync_budget_line
  AFTER INSERT OR UPDATE OF name, budget_estimate, bid_type, deleted_at ON public.tasks
  FOR EACH ROW EXECUTE FUNCTION public.fn_sync_task_budget_line();


-- ============================================================================
-- SECTION E: READ VIEWS (exact NUMERIC totals; security_invoker)
-- ============================================================================

CREATE OR REPLACE VIEW public.v_budget_lines
WITH (security_invoker = true) AS
SELECT
  bl.id,
  bl.project_id,
  bl.task_id,
  bl.template_line_id,
  bl.parent_line_id,
  bl.line_type,
  bl.line_subtype,
  bl.name,
  bl.description,
  bl.section_name,
  bl.sort_order,
  bl.original_estimate,
  bl.budget_amount,
  bl.committed_amount,
  bl.award_id,
  bl.contract_id,
  bl.is_locked,
  bl.locked_at,
  bl.lock_reason,
  bl.anticipated_start_date,
  bl.anticipated_end_date,
  bl.payment_terms_days,
  bl.cash_bucket,
  bl.approval_state,
  bl.is_payment_exempt,
  bl.created_at,
  bl.updated_at,
  t.name                     AS task_name,
  t.status                   AS task_status,
  t.bid_type                 AS task_bid_type,
  tr.name                    AS trade_name,
  a.status                   AS award_status,
  a.award_amount,
  v.id                       AS vendor_id,
  v.company_name             AS vendor_name,
  c.contract_number,
  c.status                   AS contract_status,
  vl.id                      AS variance_id,
  vl.status                  AS variance_status,
  COALESCE(var.total, 0)     AS variance_total,
  COALESCE(var.cnt, 0)       AS variance_count,
  private.fin_line_invoiced(bl.id) AS invoiced,
  CASE bl.line_type
    WHEN 'internal_tm' THEN private.fin_line_invoiced(bl.id)
    WHEN 'variance'    THEN CASE WHEN vl.status = 'approved' THEN bl.budget_amount ELSE 0 END
    ELSE bl.committed_amount
  END                        AS committed,
  COALESCE(pay.spent, 0)     AS spent,
  COALESCE(pay.pending, 0)   AS pending_approval,
  bl.budget_amount - COALESCE(pay.spent, 0)                                  AS remaining,
  CASE WHEN bl.original_estimate IS NOT NULL
       THEN bl.budget_amount - bl.original_estimate END                     AS bid_vs_estimate,
  (bl.anticipated_start_date IS NOT NULL AND bl.anticipated_end_date IS NOT NULL) AS has_dates,
  COALESCE(cl.total, 0)      AS closings_total,
  COALESCE(cl.cnt, 0)        AS closings_count
FROM public.budget_lines bl
LEFT JOIN public.tasks           t  ON t.id  = bl.task_id
LEFT JOIN public.trades          tr ON tr.id = t.trade_id
LEFT JOIN public.awards          a  ON a.id  = bl.award_id
LEFT JOIN public.vendors         v  ON v.id  = a.vendor_id
LEFT JOIN public.contracts       c  ON c.id  = bl.contract_id
LEFT JOIN public.variance_lines  vl ON vl.budget_line_id = bl.id
LEFT JOIN LATERAL (
  SELECT SUM(ch.budget_amount) AS total, count(*) AS cnt
    FROM public.budget_lines ch
   WHERE ch.parent_line_id = bl.id AND ch.line_type = 'variance' AND ch.deleted_at IS NULL
) var ON TRUE
LEFT JOIN LATERAL (
  SELECT SUM(pa.amount) FILTER (WHERE pa.status IN ('approved', 'sent_to_finance'))           AS spent,
         SUM(pa.amount) FILTER (WHERE pa.status IN ('pending', 'field_approved',
                                                    'awaiting_manager', 'awaiting_executive')) AS pending
    FROM public.payment_approvals pa
   WHERE pa.budget_line_id = bl.id
) pay ON TRUE
LEFT JOIN LATERAL (
  SELECT SUM(lc.amount) AS total, count(*) AS cnt
    FROM public.land_closings lc
   WHERE lc.budget_line_id = bl.id AND lc.status <> 'cancelled'
) cl ON TRUE
WHERE bl.deleted_at IS NULL;

COMMENT ON VIEW public.v_budget_lines IS
  'Budget tab read surface: one row per live budget line with task / trade / award / vendor / contract context and NUMERIC totals — variance_total, invoiced, committed (bid: award; internal T&M: categorised invoices; variance: amount once approved), spent (approved + sent-to-finance payments), pending_approval, remaining (= budget − spent), bid_vs_estimate, closings. security_invoker = true.';

REVOKE ALL ON public.v_budget_lines FROM PUBLIC, anon;
GRANT SELECT ON public.v_budget_lines TO authenticated, service_role;


CREATE OR REPLACE VIEW public.v_project_budget_summary
WITH (security_invoker = true) AS
SELECT
  p.id                                    AS project_id,
  p.name                                  AS project_name,
  p.budget_status,
  p.approved_budget_total,
  p.contingency_percent,
  p.budget_baselined_at,
  COALESCE(SUM(l.budget_amount), 0)                                                     AS total_budget,
  COALESCE(SUM(l.committed) FILTER (WHERE l.line_type <> 'contingency'), 0)             AS committed,
  COALESCE(SUM(l.spent), 0)                                                             AS spent,
  COALESCE(SUM(l.budget_amount), 0) - COALESCE(SUM(l.spent), 0)                         AS remaining,
  COALESCE(SUM(l.pending_approval), 0)                                                  AS pending_approval,
  COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_type = 'contingency'), 0)          AS contingency_now,
  (SELECT cb.approved_amount FROM public.contingency_buckets cb
    WHERE cb.project_id = p.id AND cb.bucket_kind = 'initial')                          AS contingency_at_baseline,
  COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_type = 'land'), 0)                 AS land_total,
  COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_type NOT IN ('land', 'contingency')), 0) AS contingency_base,
  count(l.id)                                                                           AS line_count,
  count(l.id) FILTER (WHERE NOT l.has_dates AND l.line_type NOT IN ('contingency', 'land')) AS lines_missing_dates,
  (SELECT count(*) FROM public.tasks t
    WHERE t.project_id = p.id AND t.deleted_at IS NULL
      AND NOT EXISTS (SELECT 1 FROM public.budget_lines b
                       WHERE b.task_id = t.id AND b.deleted_at IS NULL))                AS tasks_without_line,
  CASE WHEN p.budget_status = 'baselined'
       THEN COALESCE(SUM(l.budget_amount), 0) = p.approved_budget_total
       ELSE TRUE END                                                                    AS flat_ok
FROM public.projects p
LEFT JOIN public.v_budget_lines l ON l.project_id = p.id
WHERE p.deleted_at IS NULL
GROUP BY p.id;

COMMENT ON VIEW public.v_project_budget_summary IS
  'Per-project budget summary cards: total, committed, spent, remaining, pending approval, contingency now / at baseline, land total, contingency base, missing dates, tasks without a line, flat-budget check. security_invoker = true.';

REVOKE ALL ON public.v_project_budget_summary FROM PUBLIC, anon;
GRANT SELECT ON public.v_project_budget_summary TO authenticated, service_role;


-- ============================================================================
-- SECTION F: PRIVILEGES
-- ============================================================================

DO $$
DECLARE
  f TEXT;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'public.fn_create_project_budget(uuid, uuid, uuid, numeric)',
    'public.fn_reorder_budget_lines(uuid, uuid[], uuid)',
    'public.fn_remove_budget_line(uuid, uuid)',
    'public.fn_apply_budget_import(uuid, jsonb, uuid)',
    'public.fn_categorise_internal_invoice(uuid, uuid, uuid)',
    'private.fin_next_activity_position(uuid, text)',
    'private.fin_line_is_empty(uuid)'
  ] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role', f);
  END LOOP;
END $$;

REVOKE ALL ON FUNCTION public.fn_sync_task_budget_line()            FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_line_type_for_bid_type(TEXT)     FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.fin_line_invoiced(UUID)              FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.fin_line_type_for_bid_type(TEXT)  TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.fin_line_invoiced(UUID)           TO authenticated, service_role;


-- ============================================================================
-- SECTION G: STORAGE BUCKET finance-documents (private, no client policies)
-- ============================================================================
-- Files are reachable only through FastAPI (service_role) and 1-hour signed
-- URLs. No storage.objects policy is created for authenticated on purpose.

DO $$
BEGIN
  IF to_regclass('storage.buckets') IS NOT NULL THEN
    EXECUTE $q$
      INSERT INTO storage.buckets (id, name, public, file_size_limit)
      VALUES ('finance-documents', 'finance-documents', FALSE, 26214400)
      ON CONFLICT (id) DO NOTHING
    $q$;
  END IF;
END $$;


-- ============================================================================
-- SECTION H: VERSION MARKER
-- ============================================================================

INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.1.0 (20261118_financial_phase2)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;

COMMIT;

-- ============================================================================
-- END OF 001_budget_structure.sql
-- ============================================================================
