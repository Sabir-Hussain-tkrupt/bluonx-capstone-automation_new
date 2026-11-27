-- ============================================================================
-- BluOnX Financial Automation — Phase 5
-- 099  ROLLBACK CONTINGENCY HEALTH — DEV ONLY
-- ============================================================================
-- Drops what 001 added and restores the Phase 4 guardrail trigger. Decisions
-- stay in financial_alerts; the conversation, hold and groundbreaking columns
-- are LOST. Lift any financial hold first.
-- ============================================================================

BEGIN;

DROP VIEW IF EXISTS public.v_financial_alerts;
DROP TRIGGER IF EXISTS trg_projects_guard_health               ON public.projects;
DROP TRIGGER IF EXISTS trg_bid_packages_block_on_hold          ON public.bid_packages;
DROP TRIGGER IF EXISTS trg_awards_block_on_hold                ON public.awards;
DROP TRIGGER IF EXISTS trg_payment_approvals_block_on_hold_ins ON public.payment_approvals;
DROP TRIGGER IF EXISTS trg_payment_approvals_block_on_hold_upd ON public.payment_approvals;
DROP TRIGGER IF EXISTS trg_finance_handoffs_block_on_hold      ON public.finance_handoffs;
DROP FUNCTION IF EXISTS public.fn_guard_project_health();
DROP FUNCTION IF EXISTS public.fn_block_on_hold_task();
DROP FUNCTION IF EXISTS public.fn_block_on_hold_payment();
DROP FUNCTION IF EXISTS public.fn_project_health_inputs(uuid);
DROP FUNCTION IF EXISTS public.fn_record_groundbreaking(uuid, uuid);
DROP FUNCTION IF EXISTS public.fn_sync_financial_alerts(uuid, jsonb);
DROP FUNCTION IF EXISTS public.fn_decide_financial_alert(uuid, uuid, text, text, uuid, text);
DROP FUNCTION IF EXISTS public.fn_lift_financial_hold(uuid, uuid, text);

UPDATE public.projects SET contingency_at_groundbreaking = NULL WHERE contingency_at_groundbreaking IS NOT NULL;
ALTER TABLE public.projects
  DROP COLUMN IF EXISTS groundbreaking_at, DROP COLUMN IF EXISTS groundbreaking_by,
  DROP COLUMN IF EXISTS status_before_hold,
  DROP COLUMN IF EXISTS long_tail_reserve_updated_at, DROP COLUMN IF EXISTS long_tail_reserve_updated_by;
ALTER TABLE public.financial_alerts
  DROP COLUMN IF EXISTS discussed_with, DROP COLUMN IF EXISTS conversation_notes,
  DROP COLUMN IF EXISTS hold_lifted_by, DROP COLUMN IF EXISTS hold_lifted_at, DROP COLUMN IF EXISTS hold_lift_reason,
  DROP COLUMN IF EXISTS notified_at, DROP COLUMN IF EXISTS escalated_at;

DELETE FROM public.financial_settings WHERE setting_key = 'alert_escalation_days';

-- Phase 4 version
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

REVOKE ALL ON FUNCTION private.fin_recalc_guardrails(uuid)  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_ledger_recalc_guardrails() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.fin_recalc_guardrails(uuid) TO service_role;

UPDATE public.financial_settings
   SET value = '"4.5.0 (20261125_financial_phase4_variances)"'::jsonb
 WHERE setting_key = 'schema_version';

COMMIT;
