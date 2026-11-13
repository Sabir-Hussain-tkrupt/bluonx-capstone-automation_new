-- ============================================================================
-- BluOnX Financial Automation — Phase 2 patch
-- 001  BUDGET ENVELOPE: project budget value, awards, contingency, remaining
-- ============================================================================
-- Version:  4.2.0
-- Date:     November 13, 2026
-- Requires: 20261111_financial_phase1 + 20261118_financial_phase2
-- ============================================================================
--
-- WHAT CHANGES
--   1. "Create budget" uses the project's own Budget value (projects.budget) as
--      the TOTAL budget when it is set:
--        contingency  = pct of the contingency base, where
--                       base = total − land − contingency
--                       ⇒ contingency = (total − land) × pct / (100 + pct)
--        Unallocated  = total − contingency − every other line (a balancing
--                       line, so the lines add up to the project budget)
--      Projects without a Budget value keep the Phase 2 behaviour
--      (total = sum of the lines, contingency = pct × base).
--   2. Tasks that are already awarded come in at their AWARD amount and count
--      as committed; lines whose contract is already executed come in locked
--      with the contract dates.
--   3. While a budget is a DRAFT, the Unallocated line absorbs every change to
--      the other lines (edits, imports, new tasks, awards), so the total stays
--      at the project budget.
--   4. Remaining = budget − committed per line, and on the project:
--        Remaining = total budget − contingency − committed.
--   5. fn_reset_draft_budget: start a draft budget over (admin).
--
-- SAFETY: additive / CREATE OR REPLACE only, idempotent, one transaction.
-- Baselined budgets are not touched. Existing draft budgets keep their lines
-- (use Reset draft budget to rebuild them with the new rules).
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $$
BEGIN
  IF to_regprocedure('public.fn_create_project_budget(uuid, uuid, uuid, numeric)') IS NULL THEN
    RAISE EXCEPTION 'Phase 2 (20261118_financial_phase2) must be applied first.';
  END IF;
END $$;


-- ============================================================================
-- SECTION A: 'unallocated' line subtype
-- ============================================================================
-- The budget_lines.line_subtype CHECK is widened (superset). The old
-- constraint is found by definition; its name is not guessed.
DO $$
DECLARE
  r RECORD;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint
              WHERE conname = 'chk_budget_lines_line_subtype'
                AND pg_get_constraintdef(oid) ILIKE '%unallocated%') THEN
    RETURN;
  END IF;
  FOR r IN
    SELECT conname FROM pg_constraint
     WHERE conrelid = 'public.budget_lines'::regclass AND contype = 'c'
       AND pg_get_constraintdef(oid) ILIKE '%line_subtype%'
  LOOP
    EXECUTE format('ALTER TABLE public.budget_lines DROP CONSTRAINT %I', r.conname);
  END LOOP;
  ALTER TABLE public.budget_lines ADD CONSTRAINT chk_budget_lines_line_subtype
    CHECK (line_subtype IS NULL OR line_subtype IN (
      'land_purchase', 'earnest_money', 'due_diligence', 'engineering',
      'escrow_bond_premium', 'escrow_repairs', 'property_tax', 'other', 'unallocated'));
END $$;

COMMENT ON COLUMN public.budget_lines.line_subtype IS
  'Finer classification: land_purchase, earnest_money, due_diligence, engineering, escrow_bond_premium, escrow_repairs, property_tax, other, unallocated (the balancing line that keeps a draft budget at the project''s Budget value).';

CREATE UNIQUE INDEX IF NOT EXISTS uq_budget_lines_one_unallocated_per_project
  ON public.budget_lines (project_id)
  WHERE line_subtype = 'unallocated' AND deleted_at IS NULL;


-- ============================================================================
-- SECTION B: fn_create_project_budget (same signature, new rules)
-- ============================================================================
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
  v_line      RECORD;
  v_award     RECORD;
  v_contract  RECORD;
  v_cont_id   UUID;
  v_cont_sort INTEGER;
  v_total     NUMERIC;
  v_land      NUMERIC;
  v_base      NUMERIC;
  v_cont      NUMERIC;
  v_others    NUMERIC;
  v_terms     INTEGER;
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
  v_terms := COALESCE((SELECT (value #>> '{}')::int FROM public.financial_settings
                        WHERE setting_key = 'default_payment_terms_days'), 30);
  -- The project's own Budget value is the total when it is set.
  v_total := CASE WHEN v_project.budget IS NOT NULL AND v_project.budget > 0 THEN v_project.budget END;

  UPDATE public.projects SET budget_status = 'draft', contingency_percent = v_pct WHERE id = p_project_id;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  CREATE TEMP TABLE IF NOT EXISTS _fin_slots (
    rnk INTEGER, line_type TEXT, name TEXT, section_name TEXT, trade_id UUID, template_line_id UUID
  ) ON COMMIT DROP;
  TRUNCATE _fin_slots;

  -- 1. Template rows: non-activity rows become lines, activity rows are slots.
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
        COALESCE(v_tl.default_payment_terms_days, v_terms),
        COALESCE(v_tl.default_cash_bucket, 'land'),
        v_tl.line_type IN ('land', 'contingency'),
        p_actor, p_actor
      );
    END IF;
  END LOOP;

  -- 2. Every live task becomes a line at its matching slot (name, then trade).
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
    IF NOT FOUND THEN
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
      COALESCE(v_task.budget_estimate, 0), v_terms, 'land', p_actor, p_actor
    );
  END LOOP;

  -- 3. Tasks already awarded come in at the award amount (committed); an
  --    executed contract locks the line and supplies its dates.
  FOR v_line IN
    SELECT * FROM public.budget_lines
     WHERE project_id = p_project_id AND deleted_at IS NULL
       AND line_type = 'bid_activity' AND task_id IS NOT NULL
  LOOP
    SELECT * INTO v_award FROM public.awards
     WHERE task_id = v_line.task_id AND status IN ('pending_acceptance', 'accepted')
     ORDER BY awarded_at DESC LIMIT 1;
    CONTINUE WHEN NOT FOUND;

    SELECT * INTO v_contract FROM public.contracts
     WHERE award_id = v_award.id AND status IN ('executed', 'active', 'completed')
     ORDER BY created_at DESC LIMIT 1;

    UPDATE public.budget_lines
       SET pre_award_budget_amount = budget_amount,
           budget_amount           = v_award.award_amount,
           committed_amount        = v_award.award_amount,
           award_id                = v_award.id,
           is_locked               = (v_contract.id IS NOT NULL),
           locked_at               = CASE WHEN v_contract.id IS NOT NULL THEN NOW() END,
           locked_by               = CASE WHEN v_contract.id IS NOT NULL THEN p_actor END,
           lock_reason             = CASE WHEN v_contract.id IS NOT NULL THEN 'Contract executed' END,
           contract_id             = v_contract.id,
           anticipated_start_date  = CASE WHEN v_contract.id IS NOT NULL
                                            AND (v_contract.end_date IS NULL OR v_contract.start_date IS NULL
                                                 OR v_contract.end_date >= v_contract.start_date)
                                          THEN COALESCE(v_contract.start_date, anticipated_start_date)
                                          ELSE anticipated_start_date END,
           anticipated_end_date    = CASE WHEN v_contract.id IS NOT NULL
                                            AND (v_contract.end_date IS NULL OR v_contract.start_date IS NULL
                                                 OR v_contract.end_date >= v_contract.start_date)
                                          THEN COALESCE(v_contract.end_date, anticipated_end_date)
                                          ELSE anticipated_end_date END
     WHERE id = v_line.id;
  END LOOP;

  -- 4. Contingency line (always exists).
  SELECT id, sort_order INTO v_cont_id, v_cont_sort FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL;
  IF v_cont_id IS NULL THEN
    v_cont_sort := (v_rank + 2) * 1000;
    INSERT INTO public.budget_lines (project_id, line_type, name, section_name, sort_order,
                                     budget_amount, is_payment_exempt, created_by, updated_by)
    VALUES (p_project_id, 'contingency', 'Contingency', 'Contingency', v_cont_sort, 0, TRUE, p_actor, p_actor)
    RETURNING id INTO v_cont_id;
  END IF;

  SELECT COALESCE(SUM(budget_amount) FILTER (WHERE line_type = 'land'), 0),
         COALESCE(SUM(budget_amount) FILTER (WHERE line_type NOT IN ('land', 'contingency')), 0)
    INTO v_land, v_others
    FROM public.budget_lines
   WHERE project_id = p_project_id AND deleted_at IS NULL;

  IF v_total IS NOT NULL THEN
    -- base = total − land − contingency and contingency = pct × base
    v_cont := round(GREATEST(v_total - v_land, 0) * v_pct / (100 + v_pct), 2);
  ELSE
    v_base := v_others;
    v_cont := round(v_base * v_pct / 100, 2);
  END IF;

  UPDATE public.budget_lines SET budget_amount = v_cont WHERE id = v_cont_id;

  -- 5. Balancing line so the lines add up to the project's Budget value.
  IF v_total IS NOT NULL AND v_total - v_land - v_cont - v_others > 0 THEN
    INSERT INTO public.budget_lines (
      project_id, line_type, line_subtype, name, description, section_name, sort_order,
      budget_amount, payment_terms_days, cash_bucket, created_by, updated_by
    ) VALUES (
      p_project_id, 'soft_cost', 'unallocated', 'Unallocated budget',
      'Part of the project budget not yet assigned to a line. While the budget is a draft it grows or shrinks automatically as other lines change.',
      'Unallocated', v_cont_sort - 1,
      v_total - v_land - v_cont - v_others, v_terms, 'land', p_actor, p_actor
    );
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN QUERY
    SELECT * FROM public.budget_lines
     WHERE project_id = p_project_id AND deleted_at IS NULL
     ORDER BY sort_order;
END;
$$;

COMMENT ON FUNCTION public.fn_create_project_budget(UUID, UUID, UUID, NUMERIC) IS
  'Creates a DRAFT budget. Total = the project''s Budget value when set (else the sum of the lines). Template rows + every live task (at its template slot); awarded tasks come in at their award amount as committed, executed contracts locked; contingency = (total − land) × pct / (100 + pct) when the total is fixed, else pct × base; an Unallocated line balances the lines to the total. none → draft. PT409 if a budget exists.';

REVOKE ALL ON FUNCTION public.fn_create_project_budget(uuid, uuid, uuid, numeric) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_create_project_budget(uuid, uuid, uuid, numeric) TO service_role;


-- ============================================================================
-- SECTION C: Draft budgets stay at the project budget (Unallocated absorbs)
-- ============================================================================
-- Any change to another line's effective amount in a DRAFT budget (edit,
-- import, new / deleted task, award, removed line) is offset on the Unallocated
-- line, floored at $0 (beyond that the budget simply exceeds the project
-- budget and the summary shows it). Baselined budgets: no-op (there the
-- flat-budget rule and contingency do this job).
CREATE OR REPLACE FUNCTION public.fn_budget_absorb_unallocated()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_status    TEXT;
  v_unalloc   public.budget_lines;
  v_old       NUMERIC := 0;
  v_new       NUMERIC := 0;
  v_delta     NUMERIC;
BEGIN
  IF NEW.line_subtype = 'unallocated' THEN
    RETURN NULL;
  END IF;

  SELECT budget_status INTO v_status FROM public.projects WHERE id = NEW.project_id;
  IF v_status IS DISTINCT FROM 'draft' THEN
    RETURN NULL;
  END IF;

  SELECT * INTO v_unalloc FROM public.budget_lines
   WHERE project_id = NEW.project_id AND line_subtype = 'unallocated' AND deleted_at IS NULL
   FOR UPDATE;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  IF TG_OP = 'UPDATE' AND OLD.deleted_at IS NULL THEN
    v_old := OLD.budget_amount;
  END IF;
  IF NEW.deleted_at IS NULL THEN
    v_new := NEW.budget_amount;
  END IF;
  v_delta := v_new - v_old;
  IF v_delta = 0 THEN
    RETURN NULL;
  END IF;

  UPDATE public.budget_lines
     SET budget_amount = GREATEST(v_unalloc.budget_amount - v_delta, 0)
   WHERE id = v_unalloc.id;

  RETURN NULL;
END;
$$;

COMMENT ON FUNCTION public.fn_budget_absorb_unallocated() IS
  'Draft budgets only: offsets every change to another line on the Unallocated line (floored at 0) so the budget stays at the project''s Budget value.';

DROP TRIGGER IF EXISTS trg_budget_lines_absorb_unallocated ON public.budget_lines;
CREATE TRIGGER trg_budget_lines_absorb_unallocated
  AFTER INSERT OR UPDATE OF budget_amount, deleted_at ON public.budget_lines
  FOR EACH ROW EXECUTE FUNCTION public.fn_budget_absorb_unallocated();

REVOKE ALL ON FUNCTION public.fn_budget_absorb_unallocated() FROM PUBLIC, anon, authenticated;


-- ============================================================================
-- SECTION D: fn_reset_draft_budget — start a draft budget over
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_reset_draft_budget(
  p_project_id UUID,
  p_actor      UUID
)
RETURNS SETOF public.projects
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
BEGIN
  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.budget_status <> 'draft' THEN
    RAISE EXCEPTION 'Only a draft budget can be reset (this one is %)', v_project.budget_status USING ERRCODE = 'PT409';
  END IF;
  IF EXISTS (SELECT 1 FROM public.internal_invoices i
               JOIN public.budget_lines l ON l.id = i.budget_line_id
              WHERE l.project_id = p_project_id AND i.deleted_at IS NULL
                AND i.status NOT IN ('rejected', 'cancelled'))
     OR EXISTS (SELECT 1 FROM public.payment_approvals
                 WHERE project_id = p_project_id AND status NOT IN ('rejected', 'cancelled'))
     OR EXISTS (SELECT 1 FROM public.land_closings
                 WHERE project_id = p_project_id AND status <> 'cancelled') THEN
    RAISE EXCEPTION 'This draft budget has invoices, payment approvals or land closings; cancel them before resetting.'
      USING ERRCODE = 'PT409';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  -- Status first, so the Unallocated trigger stops reacting.
  UPDATE public.projects SET budget_status = 'none' WHERE id = p_project_id RETURNING * INTO v_project;
  UPDATE public.budget_lines SET deleted_at = NOW(), updated_by = p_actor
   WHERE project_id = p_project_id AND deleted_at IS NULL;
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_project;
END;
$$;

COMMENT ON FUNCTION public.fn_reset_draft_budget(UUID, UUID) IS
  'Draft budgets only: retires every line (soft delete, kept for history) and returns the project to "no budget" so it can be created again from the template, the project budget and the current awards. Refused when invoices, approvals or land closings exist.';

REVOKE ALL ON FUNCTION public.fn_reset_draft_budget(uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_reset_draft_budget(uuid, uuid) TO service_role;


-- ============================================================================
-- SECTION E: Views — remaining = budget − committed; project figures
-- ============================================================================
-- Column lists are unchanged (new columns only at the end), so CREATE OR
-- REPLACE works on databases that already have the Phase 2 views.
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
  cm.committed               AS committed,
  COALESCE(pay.spent, 0)     AS spent,
  COALESCE(pay.pending, 0)   AS pending_approval,
  -- Not yet committed. Contingency is a reserve, not something to commit
  -- against, so it has no "remaining" of its own (NULL).
  CASE WHEN bl.line_type = 'contingency' THEN NULL
       ELSE bl.budget_amount - cm.committed END                              AS remaining,
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
  SELECT CASE bl.line_type
           WHEN 'internal_tm' THEN private.fin_line_invoiced(bl.id)
           WHEN 'variance'    THEN CASE WHEN vl.status = 'approved' THEN bl.budget_amount ELSE 0 END
           WHEN 'contingency' THEN 0
           ELSE bl.committed_amount
         END AS committed
) cm ON TRUE
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
  'Budget tab read surface: one row per live line with task / trade / award / vendor / contract context and NUMERIC totals — committed (bid: award; internal T&M: categorised invoices; variance: amount once approved; contingency: 0), spent, pending_approval, remaining (= budget − committed; NULL for contingency), bid_vs_estimate, closings. security_invoker = true.';


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
  COALESCE(SUM(l.committed), 0)                                                         AS committed,
  COALESCE(SUM(l.spent), 0)                                                             AS spent,
  -- Remaining = total budget − contingency − committed
  COALESCE(SUM(l.budget_amount), 0)
    - COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_type = 'contingency'), 0)
    - COALESCE(SUM(l.committed), 0)                                                     AS remaining,
  COALESCE(SUM(l.pending_approval), 0)                                                  AS pending_approval,
  COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_type = 'contingency'), 0)          AS contingency_now,
  (SELECT cb.approved_amount FROM public.contingency_buckets cb
    WHERE cb.project_id = p.id AND cb.bucket_kind = 'initial')                          AS contingency_at_baseline,
  COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_type = 'land'), 0)                 AS land_total,
  COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_type NOT IN ('land', 'contingency')), 0) AS contingency_base,
  count(l.id)                                                                           AS line_count,
  count(l.id) FILTER (WHERE NOT l.has_dates AND l.line_type NOT IN ('contingency', 'land')
                        AND COALESCE(l.line_subtype, '') <> 'unallocated')             AS lines_missing_dates,
  (SELECT count(*) FROM public.tasks t
    WHERE t.project_id = p.id AND t.deleted_at IS NULL
      AND NOT EXISTS (SELECT 1 FROM public.budget_lines b
                       WHERE b.task_id = t.id AND b.deleted_at IS NULL))                AS tasks_without_line,
  CASE WHEN p.budget_status = 'baselined'
       THEN COALESCE(SUM(l.budget_amount), 0) = p.approved_budget_total
       ELSE TRUE END                                                                    AS flat_ok,
  -- v4.2 additions (end of the column list)
  p.budget                                                                              AS project_budget,
  COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_subtype = 'unallocated'), 0)       AS unallocated,
  CASE WHEN p.budget IS NOT NULL
       THEN COALESCE(SUM(l.budget_amount), 0) - p.budget END                            AS over_project_budget
FROM public.projects p
LEFT JOIN public.v_budget_lines l ON l.project_id = p.id
WHERE p.deleted_at IS NULL
GROUP BY p.id;

COMMENT ON VIEW public.v_project_budget_summary IS
  'Per-project budget summary: total budget, committed, spent, remaining (= total − contingency − committed), pending approval, contingency now / at baseline, land, contingency base, missing dates, tasks without a line, flat-budget check, the project''s own Budget value, the Unallocated amount and how far the lines are over / under the project budget. security_invoker = true.';

REVOKE ALL ON public.v_budget_lines, public.v_project_budget_summary FROM PUBLIC, anon;
GRANT SELECT ON public.v_budget_lines, public.v_project_budget_summary TO authenticated, service_role;


-- ============================================================================
-- SECTION F: VERSION MARKER
-- ============================================================================
INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.2.0 (20261119_financial_phase2_budget_envelope)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;

COMMIT;
