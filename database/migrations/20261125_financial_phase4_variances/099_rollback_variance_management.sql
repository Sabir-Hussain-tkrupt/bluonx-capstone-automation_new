-- ============================================================================
-- BluOnX Financial Automation — Phase 4
-- 099  ROLLBACK VARIANCE MANAGEMENT — DEV ONLY
-- ============================================================================
-- Drops what 001 added (the variance history is LOST) and restores the Phase 1
-- functions. Variances, ledger rows and payment approvals are kept.
-- ============================================================================

BEGIN;

DROP VIEW IF EXISTS public.v_variances;
DROP TRIGGER IF EXISTS trg_variance_lines_created_event  ON public.variance_lines;
DROP TRIGGER IF EXISTS trg_contingency_ledger_guardrails ON public.contingency_ledger;
DROP FUNCTION IF EXISTS public.fn_variance_created_event();
DROP FUNCTION IF EXISTS public.fn_ledger_recalc_guardrails();
DROP FUNCTION IF EXISTS public.fn_edit_variance(uuid, numeric, text, uuid, uuid, uuid, text);
DROP FUNCTION IF EXISTS public.fn_approve_variance(uuid, uuid, text);
DROP FUNCTION IF EXISTS public.fn_reject_variance(uuid, uuid, text);
DROP FUNCTION IF EXISTS private.fin_recalc_guardrails(uuid);
DROP FUNCTION IF EXISTS private.fin_route_manager(uuid, uuid, uuid[]);
DROP TABLE IF EXISTS public.variance_events;
DROP FUNCTION IF EXISTS public.fn_block_variance_event_mutation();

-- Phase 1 versions
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

UPDATE public.financial_settings
   SET value = '"4.4.0 (20261121_financial_phase3_contingency)"'::jsonb
 WHERE setting_key = 'schema_version';

COMMIT;
