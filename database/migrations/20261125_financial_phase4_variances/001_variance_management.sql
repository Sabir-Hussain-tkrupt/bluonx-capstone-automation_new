-- ============================================================================
-- BluOnX Financial Automation — Phase 4 · Module 4
-- 001  VARIANCE LINE MANAGEMENT (schema change script)
-- ============================================================================
-- Version:  4.5.0
-- Date:     November 25, 2026
-- Requires: Phases 1-3 (last: 20261121_financial_phase3_contingency)
-- Engine:   PostgreSQL 15+ (Supabase)
-- ============================================================================
--
-- WHAT THIS SCRIPT DOES
--   4.1 fn_create_variance (Phase 1) is reused unchanged.
--   4.2 fn_adjust_variance: same money rules, plus history, approval restart and
--       422 messages; fn_edit_variance edits amount + details in one call.
--       Guardrails are recalculated on every contingency ledger row.
--   4.3 fn_approve_variance / fn_reject_variance: own payment approval,
--       approval limit, routing to a manager, two-person rule.
--   4.4 variance_events (append-only history) and view v_variances.
--   4.5 Locked bids and approved variances: refused with PT422.
--
-- SAFETY: additive / CREATE OR REPLACE only, idempotent, one transaction.
-- The only rows written: one "created" history event per variance that already
-- exists (e.g. invoice overages) and the schema_version marker.
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $$
BEGIN
  IF to_regclass('public.variance_lines') IS NULL
     OR to_regprocedure('private.fin_contingency_snapshot(uuid)') IS NULL THEN
    RAISE EXCEPTION 'Phases 1, 2 and 3 must be applied first.';
  END IF;
END $$;

-- ============================================================================
-- SECTION A: variance_events (append-only history)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.variance_events (
  id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  event_no       BIGINT        GENERATED ALWAYS AS IDENTITY UNIQUE,
  variance_id    UUID          NOT NULL REFERENCES public.variance_lines(id) ON DELETE RESTRICT,
  project_id     UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  event_type     VARCHAR(30)   NOT NULL
                               CHECK (event_type IN ('created', 'amount_changed', 'details_changed', 'resubmitted',
                                                     'routed_to_manager', 'approved', 'rejected', 'cancelled')),
  amount_before  DECIMAL(15,2),
  amount_after   DECIMAL(15,2),
  actor_user_id  UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  note           TEXT,
  created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_variance_events_variance ON public.variance_events (variance_id, event_no);
CREATE INDEX IF NOT EXISTS idx_variance_events_project  ON public.variance_events (project_id);

COMMENT ON TABLE public.variance_events IS
  'Append-only history of a variance: estimate, edits, approvals, rejection, cancellation. Order by event_no.';

CREATE OR REPLACE FUNCTION public.fn_block_variance_event_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  RAISE EXCEPTION 'Variance history is append-only and cannot be changed.' USING ERRCODE = 'PT403';
END;
$$;

DROP TRIGGER IF EXISTS trg_variance_events_immutable ON public.variance_events;
CREATE TRIGGER trg_variance_events_immutable
  BEFORE UPDATE OR DELETE ON public.variance_events
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_variance_event_mutation();

DROP TRIGGER IF EXISTS trg_variance_events_no_truncate ON public.variance_events;
CREATE TRIGGER trg_variance_events_no_truncate
  BEFORE TRUNCATE ON public.variance_events
  FOR EACH STATEMENT EXECUTE FUNCTION public.fn_block_variance_event_mutation();

-- Every variance starts its history, whichever procedure created it
-- (fn_create_variance or an invoice overage).
CREATE OR REPLACE FUNCTION public.fn_variance_created_event()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_after, actor_user_id, note)
  VALUES (NEW.id, NEW.project_id, 'created', NEW.estimated_amount, NEW.created_by, NEW.description);
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_variance_lines_created_event ON public.variance_lines;
CREATE TRIGGER trg_variance_lines_created_event
  AFTER INSERT ON public.variance_lines
  FOR EACH ROW EXECUTE FUNCTION public.fn_variance_created_event();

INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_after, actor_user_id, note, created_at)
SELECT v.id, v.project_id, 'created', v.estimated_amount, v.created_by, v.description, v.created_at
  FROM public.variance_lines v
 WHERE NOT EXISTS (SELECT 1 FROM public.variance_events e WHERE e.variance_id = v.id AND e.event_type = 'created');


-- ============================================================================
-- SECTION B: GUARDRAIL RECALCULATION (after every contingency movement)
-- ============================================================================
-- left % = contingency now ÷ contingency funded (initial + approved top-ups).
CREATE OR REPLACE FUNCTION private.fin_recalc_guardrails(p_project_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_cont    NUMERIC;
  v_funded  NUMERIC;
  v_left    NUMERIC;
  v_near    NUMERIC;
  v_type    TEXT;
  v_active  BOOLEAN;
  v_msg     TEXT;
BEGIN
  SELECT budget_amount INTO v_cont FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL;
  IF v_cont IS NULL THEN
    RETURN;
  END IF;

  SELECT COALESCE(SUM(approved_amount), 0) INTO v_funded
    FROM public.contingency_buckets WHERE project_id = p_project_id AND status = 'approved';
  v_near := COALESCE((SELECT (value #>> '{}')::numeric FROM public.financial_settings
                       WHERE setting_key = 'contingency_near_zero_percent'), 5);
  -- Clamped to the DECIMAL(7,2) alert column.
  v_left := CASE WHEN v_funded > 0
                 THEN GREATEST(LEAST(round(v_cont * 100 / v_funded, 2), 99999.99), -99999.99) END;

  FOREACH v_type IN ARRAY ARRAY['contingency_near_zero', 'contingency_negative'] LOOP
    IF v_type = 'contingency_negative' THEN
      v_active := v_cont < 0;
      v_msg    := format('Contingency is negative: %s.', v_cont);
    ELSE
      v_active := v_cont >= 0 AND v_left IS NOT NULL AND v_left <= v_near;
      v_msg    := format('Contingency is nearly used up: %s left (%s%% of the funded contingency, alert at %s%%).',
                         v_cont, v_left, v_near);
    END IF;

    IF v_active THEN
      UPDATE public.financial_alerts
         SET contingency_left_pct = v_left, contingency_remaining = v_cont, message = v_msg
       WHERE project_id = p_project_id AND alert_type = v_type
         AND status IN ('open', 'acknowledged', 'proceed_approved', 'on_hold');
      IF NOT FOUND THEN
        INSERT INTO public.financial_alerts (project_id, alert_type, severity, contingency_left_pct, contingency_remaining, message)
        VALUES (p_project_id, v_type,
                CASE WHEN v_type = 'contingency_negative' THEN 'critical' ELSE 'urgent' END,
                v_left, v_cont, v_msg);
      END IF;
    ELSE
      UPDATE public.financial_alerts SET status = 'resolved', resolved_at = NOW()
       WHERE project_id = p_project_id AND alert_type = v_type
         AND status IN ('open', 'acknowledged', 'proceed_approved', 'on_hold');
    END IF;
  END LOOP;
END;
$$;

COMMENT ON FUNCTION private.fin_recalc_guardrails(UUID) IS
  'Opens / refreshes / resolves the near-zero and negative contingency alerts of a project.';

CREATE OR REPLACE FUNCTION public.fn_ledger_recalc_guardrails()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  PERFORM private.fin_recalc_guardrails(NEW.project_id);
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_contingency_ledger_guardrails ON public.contingency_ledger;
CREATE TRIGGER trg_contingency_ledger_guardrails
  AFTER INSERT ON public.contingency_ledger
  FOR EACH ROW EXECUTE FUNCTION public.fn_ledger_recalc_guardrails();


-- ============================================================================
-- SECTION C: 4.5 LOCK RULES (Phase 1 functions; locked / frozen = PT422)
-- ============================================================================
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
        OLD.id USING ERRCODE = 'PT422';
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
      USING ERRCODE = 'PT422';
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
    RAISE EXCEPTION 'Budget line % is locked (contract executed). Locked bid amounts cannot be edited; use a variance.', v_line.id USING ERRCODE = 'PT422';
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


-- ============================================================================
-- SECTION D: 4.2 EDIT / CANCEL
-- ============================================================================
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
    RAISE EXCEPTION 'This variance is % and can no longer be changed. Create a new variance instead.', v_variance.status
      USING ERRCODE = 'PT422';
  END IF;

  v_delta := p_new_amount - v_line.budget_amount;

  -- An invoice overage is the invoice's own amount: it cannot drift from it.
  IF v_delta <> 0 AND EXISTS (SELECT 1 FROM public.payment_approvals
                               WHERE budget_line_id = v_line.id AND internal_invoice_id IS NOT NULL) THEN
    RAISE EXCEPTION 'This variance comes from an invoice, so its amount cannot be changed or cancelled here.'
      USING ERRCODE = 'PT422';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  -- A changed amount restarts the approval: earlier sign-offs were for the old one.
  IF v_delta <> 0 THEN
    UPDATE public.payment_approvals SET status = 'cancelled'
     WHERE budget_line_id = v_line.id AND status IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive');
    UPDATE public.budget_lines SET approval_state = 'not_requested'
     WHERE id = v_line.id AND approval_state <> 'not_requested';
  END IF;

  IF p_new_amount = 0 THEN
    -- Cancel: return the full amount, retire the line.
    UPDATE public.budget_lines
       SET budget_amount = 0, deleted_at = NOW(), updated_by = p_actor
     WHERE id = v_line.id;

    UPDATE public.variance_lines SET status = 'cancelled'
     WHERE id = p_variance_id RETURNING * INTO v_variance;

    IF v_delta <> 0 THEN
      PERFORM private.fin_move_contingency(
        v_variance.project_id, -v_delta, 'variance_cancelled', p_actor,
        COALESCE(p_reason, 'Variance cancelled'), v_line.id, p_variance_id, NULL, NULL);
    END IF;
    INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_before, amount_after, actor_user_id, note)
    VALUES (p_variance_id, v_variance.project_id, 'cancelled', v_line.budget_amount, 0, p_actor, p_reason);
  ELSIF v_delta <> 0 THEN
    UPDATE public.budget_lines
       SET budget_amount = p_new_amount, updated_by = p_actor
     WHERE id = v_line.id;

    PERFORM private.fin_move_contingency(
      v_variance.project_id, -v_delta, 'variance_adjusted', p_actor,
      COALESCE(p_reason, format('Variance adjusted %s → %s', v_line.budget_amount, p_new_amount)),
      v_line.id, p_variance_id, NULL, NULL);
    INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_before, amount_after, actor_user_id, note)
    VALUES (p_variance_id, v_variance.project_id, 'amount_changed', v_line.budget_amount, p_new_amount, p_actor, p_reason);

    SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id;
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_variance;
END;
$$;

COMMENT ON FUNCTION public.fn_adjust_variance(UUID, NUMERIC, UUID, TEXT) IS
  'Changes a not-yet-approved variance amount; the difference flows back to (or out of) contingency with a ledger row and a history event, and any approval in progress restarts. 0 cancels. Approved / cancelled = PT422.';


-- Amount and details together, in one transaction. A rejected variance goes
-- back to pending approval when it is edited.
CREATE OR REPLACE FUNCTION public.fn_edit_variance(
  p_variance_id UUID,
  p_amount      NUMERIC,
  p_description TEXT,
  p_trade_id    UUID,
  p_vendor_id   UUID,
  p_actor       UUID,
  p_reason      TEXT DEFAULT NULL
)
RETURNS SETOF public.variance_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_old  public.variance_lines;
  v_new  public.variance_lines;
BEGIN
  IF p_amount IS NULL OR p_amount <= 0 THEN
    RAISE EXCEPTION 'Variance amount must be greater than zero. To drop the variance, cancel it.' USING ERRCODE = 'PT422';
  END IF;
  IF btrim(COALESCE(p_description, '')) = '' THEN
    RAISE EXCEPTION 'A variance needs a description' USING ERRCODE = 'PT422';
  END IF;

  -- Locks, checks the status, moves the money.
  PERFORM * FROM public.fn_adjust_variance(p_variance_id, p_amount, p_actor, p_reason);
  SELECT * INTO v_old FROM public.variance_lines WHERE id = p_variance_id;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  UPDATE public.variance_lines
     SET description      = btrim(p_description),
         trade_id         = p_trade_id,
         vendor_id        = p_vendor_id,
         status           = 'pending_approval',
         rejected_by      = NULL,
         rejected_at      = NULL,
         rejection_reason = NULL
   WHERE id = p_variance_id
   RETURNING * INTO v_new;

  IF v_old.description IS DISTINCT FROM v_new.description
     OR v_old.trade_id IS DISTINCT FROM v_new.trade_id
     OR v_old.vendor_id IS DISTINCT FROM v_new.vendor_id THEN
    UPDATE public.budget_lines
       SET name = left('Variance: ' || v_new.description, 255), description = v_new.description, updated_by = p_actor
     WHERE id = v_new.budget_line_id;
    -- A first sign-off was for the old details: start the approval again.
    -- (A pending invoice request has no sign-off yet, so it stays.)
    UPDATE public.payment_approvals SET status = 'cancelled'
     WHERE budget_line_id = v_new.budget_line_id AND status IN ('field_approved', 'awaiting_manager', 'awaiting_executive');
    UPDATE public.payment_approvals SET vendor_id = v_new.vendor_id
     WHERE budget_line_id = v_new.budget_line_id AND status = 'pending' AND internal_invoice_id IS NULL;
    INSERT INTO public.variance_events (variance_id, project_id, event_type, actor_user_id, note)
    VALUES (p_variance_id, v_new.project_id, 'details_changed', p_actor, p_reason);
  END IF;

  UPDATE public.budget_lines SET approval_state = 'not_requested', updated_by = p_actor
   WHERE id = v_new.budget_line_id AND approval_state <> 'not_requested'
     AND NOT EXISTS (SELECT 1 FROM public.payment_approvals pa
                      WHERE pa.budget_line_id = v_new.budget_line_id
                        AND pa.status IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive'));

  IF v_old.status = 'rejected' THEN
    INSERT INTO public.variance_events (variance_id, project_id, event_type, actor_user_id, note)
    VALUES (p_variance_id, v_new.project_id, 'resubmitted', p_actor, p_reason);
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_new;
END;
$$;

COMMENT ON FUNCTION public.fn_edit_variance(UUID, NUMERIC, TEXT, UUID, UUID, UUID, TEXT) IS
  'Edits a not-yet-approved variance (amount, description, trade, vendor) in one transaction; a rejected one returns to pending approval.';


-- ============================================================================
-- SECTION E: 4.3 APPROVE FOR PAYMENT / REJECT
-- ============================================================================
-- Who gets the second approval: the person's manager, else the project's
-- manager. Each is replaced by an active delegate or, when unavailable, by the
-- standing backup. NULL = nobody specific: any manager may approve.
CREATE OR REPLACE FUNCTION private.fin_route_manager(p_from_user UUID, p_project_id UUID, p_exclude UUID[])
RETURNS UUID
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_manager   UUID;
  v_candidate UUID;
BEGIN
  FOREACH v_manager IN ARRAY ARRAY[
    (SELECT reports_to FROM public.users WHERE id = p_from_user),
    (SELECT manager_id FROM public.projects WHERE id = p_project_id)
  ] LOOP
    CONTINUE WHEN v_manager IS NULL;
    FOREACH v_candidate IN ARRAY ARRAY[
      (SELECT delegate_user_id FROM public.approval_delegations
        WHERE delegator_user_id = v_manager AND revoked_at IS NULL
          AND NOW() >= starts_at AND NOW() < ends_at
        ORDER BY created_at DESC LIMIT 1),
      v_manager,
      (SELECT backup_approver_id FROM public.users WHERE id = v_manager)
    ] LOOP
      IF v_candidate IS NOT NULL AND NOT (v_candidate = ANY (p_exclude))
         AND EXISTS (SELECT 1 FROM public.users
                      WHERE id = v_candidate AND is_active AND deleted_at IS NULL) THEN
        RETURN v_candidate;
      END IF;
    END LOOP;
  END LOOP;
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_approve_variance(
  p_variance_id UUID,
  p_actor       UUID,
  p_note        TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_variance  public.variance_lines;
  v_line      public.budget_lines;
  v_pa        public.payment_approvals;
  v_manager   BOOLEAN;
  v_field     BOOLEAN;
  v_limit     NUMERIC;
  v_second    BOOLEAN;
  v_routed    UUID;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;
  SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id;
  IF NOT FOUND OR v_variance.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Variance % not found', p_variance_id USING ERRCODE = 'PT404';
  END IF;

  PERFORM private.fin_lock_project(v_variance.project_id, TRUE, TRUE);
  SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id FOR UPDATE;
  SELECT * INTO v_line     FROM public.budget_lines   WHERE id = v_variance.budget_line_id FOR UPDATE;

  IF v_variance.status <> 'pending_approval' THEN
    RAISE EXCEPTION 'This variance is % and cannot be approved.', replace(v_variance.status, '_', ' ') USING ERRCODE = 'PT422';
  END IF;
  IF p_actor = v_variance.created_by THEN
    RAISE EXCEPTION 'You created this variance, so a different person must approve it.' USING ERRCODE = 'PT403';
  END IF;

  v_manager := private.user_has_role(p_actor, 'project_manager') OR private.user_has_role(p_actor, 'executive')
               OR private.user_has_role(p_actor, 'admin');
  v_field   := private.user_has_role(p_actor, 'field_manager');

  SELECT * INTO v_pa FROM public.payment_approvals
   WHERE budget_line_id = v_line.id
     AND status IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive')
   ORDER BY created_at DESC LIMIT 1 FOR UPDATE;
  v_second := COALESCE(v_pa.status = 'awaiting_manager', FALSE);

  IF v_second THEN
    IF p_actor = v_pa.field_approved_by THEN
      RAISE EXCEPTION 'You gave the first approval, so a manager must give the second one.' USING ERRCODE = 'PT403';
    END IF;
    IF NOT v_manager AND p_actor IS DISTINCT FROM v_pa.routed_to_user_id THEN
      RAISE EXCEPTION 'This amount is above the field manager limit and needs a manager''s approval.' USING ERRCODE = 'PT403';
    END IF;
  ELSIF NOT (v_manager OR v_field) THEN
    RAISE EXCEPTION 'Only a field manager, project manager, executive or admin can approve a variance.' USING ERRCODE = 'PT403';
  END IF;

  -- Personal limit first; a field manager without one gets the default.
  SELECT approval_limit INTO v_limit FROM public.users WHERE id = p_actor;
  IF v_limit IS NULL AND NOT v_manager THEN
    v_limit := COALESCE((SELECT (value #>> '{}')::numeric FROM public.financial_settings
                          WHERE setting_key = 'default_field_approval_limit'), 5000);
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  IF v_pa.id IS NULL THEN
    INSERT INTO public.payment_approvals (
      project_id, budget_line_id, internal_invoice_id, vendor_id, amount, payment_kind, status, requested_by
    ) VALUES (
      v_variance.project_id, v_line.id,
      (SELECT internal_invoice_id FROM public.payment_approvals
        WHERE budget_line_id = v_line.id AND internal_invoice_id IS NOT NULL ORDER BY created_at DESC LIMIT 1),
      v_variance.vendor_id, v_line.budget_amount, 'full', 'pending', v_variance.created_by
    ) RETURNING * INTO v_pa;
  END IF;

  IF NOT v_second AND v_limit IS NOT NULL AND v_line.budget_amount > v_limit THEN
    v_routed := private.fin_route_manager(p_actor, v_variance.project_id, ARRAY[p_actor, v_variance.created_by]);
    UPDATE public.payment_approvals
       SET status = 'awaiting_manager', field_approved_by = p_actor, field_approved_at = NOW(),
           routed_to_user_id = v_routed, comments = COALESCE(p_note, comments)
     WHERE id = v_pa.id RETURNING * INTO v_pa;
    UPDATE public.budget_lines SET approval_state = 'field_approved', updated_by = p_actor WHERE id = v_line.id;
    INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_after, actor_user_id, note)
    VALUES (p_variance_id, v_variance.project_id, 'routed_to_manager', v_line.budget_amount, p_actor, p_note);
  ELSE
    UPDATE public.payment_approvals
       SET status                = 'approved',
           vendor_id             = COALESCE(vendor_id, v_variance.vendor_id),
           field_approved_by     = CASE WHEN v_second OR v_manager THEN field_approved_by ELSE p_actor END,
           field_approved_at     = CASE WHEN v_second OR v_manager THEN field_approved_at ELSE NOW() END,
           manager_approved_by   = CASE WHEN v_second OR v_manager THEN p_actor ELSE manager_approved_by END,
           manager_approved_at   = CASE WHEN v_second OR v_manager THEN NOW() ELSE manager_approved_at END,
           expected_payment_date = CURRENT_DATE + v_line.payment_terms_days,
           comments              = COALESCE(p_note, comments)
     WHERE id = v_pa.id RETURNING * INTO v_pa;
    UPDATE public.variance_lines
       SET status = 'approved', approved_by = p_actor, approved_at = NOW()
     WHERE id = p_variance_id RETURNING * INTO v_variance;
    UPDATE public.budget_lines
       SET approval_state = CASE WHEN v_second OR v_manager THEN 'manager_approved' ELSE 'field_approved' END,
           updated_by = p_actor
     WHERE id = v_line.id;
    INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_after, actor_user_id, note)
    VALUES (p_variance_id, v_variance.project_id, 'approved', v_line.budget_amount, p_actor, p_note);
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN jsonb_build_object(
    'variance_id', p_variance_id, 'status', v_variance.status, 'payment_status', v_pa.status,
    'payment_approval_id', v_pa.id, 'routed_to_user_id', v_pa.routed_to_user_id, 'limit', v_limit);
END;
$$;

COMMENT ON FUNCTION public.fn_approve_variance(UUID, UUID, TEXT) IS
  'Approve for payment, independent of the parent bid line. The creator can never approve. Above the approver''s limit the first approval is recorded and the request is routed to a manager (a different person). Final approval freezes the variance.';


CREATE OR REPLACE FUNCTION public.fn_reject_variance(
  p_variance_id UUID,
  p_actor       UUID,
  p_reason      TEXT
)
RETURNS SETOF public.variance_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_variance public.variance_lines;
  v_line     public.budget_lines;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;
  IF btrim(COALESCE(p_reason, '')) = '' THEN
    RAISE EXCEPTION 'A rejection needs a reason' USING ERRCODE = 'PT422';
  END IF;
  SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id;
  IF NOT FOUND OR v_variance.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Variance % not found', p_variance_id USING ERRCODE = 'PT404';
  END IF;

  PERFORM private.fin_lock_project(v_variance.project_id, TRUE, FALSE);
  SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id FOR UPDATE;
  SELECT * INTO v_line     FROM public.budget_lines   WHERE id = v_variance.budget_line_id FOR UPDATE;

  IF v_variance.status <> 'pending_approval' THEN
    RAISE EXCEPTION 'This variance is % and cannot be rejected.', replace(v_variance.status, '_', ' ') USING ERRCODE = 'PT422';
  END IF;
  IF p_actor = v_variance.created_by THEN
    RAISE EXCEPTION 'You created this variance: edit or cancel it instead of rejecting it.' USING ERRCODE = 'PT403';
  END IF;
  IF NOT (private.user_has_role(p_actor, 'field_manager') OR private.user_has_role(p_actor, 'project_manager')
          OR private.user_has_role(p_actor, 'executive') OR private.user_has_role(p_actor, 'admin')
          OR EXISTS (SELECT 1 FROM public.payment_approvals
                      WHERE budget_line_id = v_line.id AND status = 'awaiting_manager' AND routed_to_user_id = p_actor)) THEN
    RAISE EXCEPTION 'Only a field manager, project manager, executive or admin can reject a variance.' USING ERRCODE = 'PT403';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  UPDATE public.payment_approvals
     SET status = 'rejected', rejected_by = p_actor, rejected_at = NOW(), rejection_reason = btrim(p_reason)
   WHERE budget_line_id = v_line.id AND status IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive');
  UPDATE public.budget_lines SET approval_state = 'rejected', updated_by = p_actor WHERE id = v_line.id;
  UPDATE public.variance_lines
     SET status = 'rejected', rejected_by = p_actor, rejected_at = NOW(), rejection_reason = btrim(p_reason)
   WHERE id = p_variance_id RETURNING * INTO v_variance;
  INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_after, actor_user_id, note)
  VALUES (p_variance_id, v_variance.project_id, 'rejected', v_line.budget_amount, p_actor, btrim(p_reason));

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_variance;
END;
$$;

COMMENT ON FUNCTION public.fn_reject_variance(UUID, UUID, TEXT) IS
  'Sends a variance back with a reason. The amount stays reserved until the variance is edited (back to pending approval) or cancelled (returned to contingency).';


-- ============================================================================
-- SECTION F: 4.4 READ SURFACE
-- ============================================================================
CREATE OR REPLACE VIEW public.v_variances
WITH (security_invoker = true) AS
SELECT
  v.id, v.project_id, p.name AS project_name, v.budget_line_id, v.parent_budget_line_id,
  pl.name AS parent_line_name, pl.line_type AS parent_line_type, pl.budget_amount AS parent_budget_amount,
  pl.is_locked AS parent_is_locked, pl.approval_state AS parent_approval_state,
  v.trade_id, t.name AS trade_name, v.vendor_id, vd.company_name AS vendor_name,
  v.description, v.estimated_amount, bl.budget_amount AS amount, v.status,
  bl.payment_terms_days,
  v.created_by, cu.full_name AS created_by_name, v.created_at, v.updated_at,
  v.approved_by, au.full_name AS approved_by_name, v.approved_at,
  v.rejected_by, ru.full_name AS rejected_by_name, v.rejected_at, v.rejection_reason,
  pa.id AS payment_approval_id,
  -- A resubmitted variance has no request yet: its old rejection is history.
  CASE WHEN pa.status = 'rejected' AND v.status = 'pending_approval' THEN 'not_requested'
       ELSE COALESCE(pa.status, 'not_requested') END AS payment_status,
  pa.field_approved_by, fu.full_name AS field_approved_by_name,
  pa.routed_to_user_id, mu.full_name AS routed_to_name,
  pa.expected_payment_date,
  inv.id AS internal_invoice_id
FROM public.variance_lines v
JOIN public.projects          p  ON p.id  = v.project_id AND p.deleted_at IS NULL
JOIN public.budget_lines      bl ON bl.id = v.budget_line_id
JOIN public.budget_lines      pl ON pl.id = v.parent_budget_line_id
LEFT JOIN public.trades       t  ON t.id  = v.trade_id
LEFT JOIN public.vendors      vd ON vd.id = v.vendor_id
LEFT JOIN public.users        cu ON cu.id = v.created_by
LEFT JOIN public.users        au ON au.id = v.approved_by
LEFT JOIN public.users        ru ON ru.id = v.rejected_by
LEFT JOIN LATERAL (
  SELECT * FROM public.payment_approvals x
   WHERE x.budget_line_id = v.budget_line_id AND x.status <> 'cancelled'
   ORDER BY x.created_at DESC LIMIT 1
) pa ON TRUE
LEFT JOIN LATERAL (
  SELECT x.internal_invoice_id AS id FROM public.payment_approvals x
   WHERE x.budget_line_id = v.budget_line_id AND x.internal_invoice_id IS NOT NULL LIMIT 1
) inv ON TRUE
LEFT JOIN public.users        fu ON fu.id = pa.field_approved_by
LEFT JOIN public.users        mu ON mu.id = pa.routed_to_user_id
WHERE v.deleted_at IS NULL;

COMMENT ON VIEW public.v_variances IS
  'Variances with project, parent line, trade, vendor, people, current amount and own payment status. security_invoker = true.';


-- ============================================================================
-- SECTION G: PRIVILEGES
-- ============================================================================
REVOKE ALL ON public.v_variances FROM PUBLIC, anon;
GRANT SELECT ON public.v_variances TO authenticated, service_role;

-- Run inside triggers / procedures as the calling role.
REVOKE ALL ON FUNCTION private.fin_recalc_guardrails(uuid)             FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_route_manager(uuid, uuid, uuid[])   FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.fin_recalc_guardrails(uuid)           TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_route_manager(uuid, uuid, uuid[]) TO service_role;

REVOKE ALL ON FUNCTION public.fn_block_variance_event_mutation()       FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_variance_created_event()              FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_ledger_recalc_guardrails()            FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_adjust_variance(uuid, numeric, uuid, text)                        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_edit_variance(uuid, numeric, text, uuid, uuid, uuid, text)        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_approve_variance(uuid, uuid, text)                                FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_reject_variance(uuid, uuid, text)                                 FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_adjust_variance(uuid, numeric, uuid, text)                     TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_edit_variance(uuid, numeric, text, uuid, uuid, uuid, text)     TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_approve_variance(uuid, uuid, text)                             TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_reject_variance(uuid, uuid, text)                              TO service_role;


-- ============================================================================
-- SECTION H: VERSION MARKER
-- ============================================================================
INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.5.0 (20261125_financial_phase4_variances)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;


-- ============================================================================
-- VARIANCE HISTORY RLS (v4.5 — migration 20261125_financial_phase4_variances)
-- ============================================================================
-- Any active user reads; rows are written only by the variance procedures.
ALTER TABLE public.variance_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.variance_events FROM anon, authenticated;
GRANT SELECT ON TABLE public.variance_events TO authenticated;
GRANT ALL ON TABLE public.variance_events TO service_role;

DROP POLICY IF EXISTS variance_events_select_authenticated ON public.variance_events;
CREATE POLICY variance_events_select_authenticated
  ON public.variance_events FOR SELECT TO authenticated
  USING ((SELECT private.is_active_user()));

COMMIT;
