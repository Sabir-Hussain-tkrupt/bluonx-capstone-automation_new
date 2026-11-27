-- ============================================================================
-- BluOnX Financial Automation — Phase 5 · Module 5
-- 001  CONTINGENCY HEALTH GUARDRAIL & ALERTS (schema change script)
-- ============================================================================
-- Version:  4.6.0
-- Date:     November 26, 2026
-- Requires: Phases 1-4 (last: 20261125_financial_phase4_variances)
-- Engine:   PostgreSQL 15+ (Supabase)
-- ============================================================================
--
-- WHAT THIS SCRIPT DOES
--   5.1 fn_project_health_inputs: one consistent read of every number the
--       Python calculation needs. fn_record_groundbreaking.
--   5.2 fn_sync_financial_alerts: opens / refreshes / resolves alerts from the
--       calculated checks. Replaces the Phase 4 SQL guardrail trigger, so only
--       one engine decides when an alert fires.
--   5.3 Long-tail reserve: can be raised any time, lowered only before
--       groundbreaking or once the project is completed.
--   5.4 fn_decide_financial_alert (proceed / hold), fn_lift_financial_hold, and
--       triggers that block new bid packages, awards, approvals and payments
--       while a project is on hold.
--   5.5 Columns that record which alerts were emailed and escalated.
--
-- SAFETY: additive / CREATE OR REPLACE, idempotent, one transaction. Drops only
-- the Phase 4 guardrail trigger and its two helper functions (no data).
-- Rows written: the schema_version marker and missing settings (existing
-- settings are never overwritten).
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $$
BEGIN
  IF to_regclass('public.variance_events') IS NULL THEN
    RAISE EXCEPTION 'Phases 1 to 4 must be applied first.';
  END IF;
END $$;

-- ============================================================================
-- SECTION A: COLUMNS
-- ============================================================================
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS groundbreaking_at            TIMESTAMPTZ;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS groundbreaking_by            UUID REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS status_before_hold           VARCHAR(20);
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS long_tail_reserve_updated_at TIMESTAMPTZ;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS long_tail_reserve_updated_by UUID REFERENCES public.users(id) ON DELETE SET NULL;

COMMENT ON COLUMN public.projects.contingency_at_groundbreaking IS 'Contingency when groundbreaking was recorded: denominator of contingency left %. NULL = not recorded yet; the initial contingency at baseline is used.';
COMMENT ON COLUMN public.projects.groundbreaking_at             IS 'When groundbreaking was recorded (fn_record_groundbreaking).';
COMMENT ON COLUMN public.projects.status_before_hold            IS 'Status to return to when a financial hold is lifted.';

ALTER TABLE public.financial_alerts ADD COLUMN IF NOT EXISTS discussed_with     UUID REFERENCES public.users(id) ON DELETE RESTRICT;
ALTER TABLE public.financial_alerts ADD COLUMN IF NOT EXISTS conversation_notes TEXT;
ALTER TABLE public.financial_alerts ADD COLUMN IF NOT EXISTS hold_lifted_by     UUID REFERENCES public.users(id) ON DELETE RESTRICT;
ALTER TABLE public.financial_alerts ADD COLUMN IF NOT EXISTS hold_lifted_at     TIMESTAMPTZ;
ALTER TABLE public.financial_alerts ADD COLUMN IF NOT EXISTS hold_lift_reason   TEXT;
ALTER TABLE public.financial_alerts ADD COLUMN IF NOT EXISTS notified_at        TIMESTAMPTZ;
ALTER TABLE public.financial_alerts ADD COLUMN IF NOT EXISTS escalated_at       TIMESTAMPTZ;

COMMENT ON COLUMN public.financial_alerts.discussed_with     IS 'Field manager the deciding manager spoke with.';
COMMENT ON COLUMN public.financial_alerts.conversation_notes IS 'What the field manager and the manager discussed.';
COMMENT ON COLUMN public.financial_alerts.notified_at        IS 'When the alert was sent (in-app + email). NULL = not sent yet; the daily sweep sends it.';
COMMENT ON COLUMN public.financial_alerts.escalated_at       IS 'When the executives were told.';


-- ============================================================================
-- SECTION B: 5.2 ONE ENGINE (retire the Phase 4 SQL guardrails)
-- ============================================================================
DROP TRIGGER IF EXISTS trg_contingency_ledger_guardrails ON public.contingency_ledger;
DROP FUNCTION IF EXISTS public.fn_ledger_recalc_guardrails();
DROP FUNCTION IF EXISTS private.fin_recalc_guardrails(uuid);

-- Same function as Phase 1, but the hold message names the project.
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
    RAISE EXCEPTION 'Project "%" is on hold; financial changes are blocked until the hold is lifted.', v_project.name
      USING ERRCODE = 'PT409';
  END IF;
  RETURN v_project;
END;
$$;


-- ============================================================================
-- SECTION C: 5.1 INPUTS FOR THE CALCULATION
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_project_health_inputs(p_project_id UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  SELECT jsonb_build_object(
    'project_id',            p.id,
    'project_name',          p.name,
    'status',                p.status,
    'budget_status',         p.budget_status,
    'archived',              p.archived_at IS NOT NULL,
    'manager_id',            p.manager_id,
    'field_manager_id',      p.field_manager_id,
    'groundbreaking_at',     p.groundbreaking_at,
    'reserve',               p.long_tail_reserve_amount,
    'contingency',           (SELECT b.budget_amount FROM public.budget_lines b
                               WHERE b.project_id = p.id AND b.line_type = 'contingency' AND b.deleted_at IS NULL),
    'contingency_base',      COALESCE(p.contingency_at_groundbreaking,
                               (SELECT cb.approved_amount FROM public.contingency_buckets cb
                                 WHERE cb.project_id = p.id AND cb.bucket_kind = 'initial')),
    'total_budget',          (SELECT COALESCE(SUM(b.budget_amount), 0) FROM public.budget_lines b
                               WHERE b.project_id = p.id AND b.deleted_at IS NULL),
    'lines',                 (SELECT COALESCE(jsonb_agg(jsonb_build_object(
                                'committed',   b.committed_amount,
                                'approved',    COALESCE(pay.approved, 0),
                                'sent',        COALESCE(pay.sent, 0),
                                'land_closed', COALESCE(lc.closed, 0))), '[]'::jsonb)
                               FROM public.budget_lines b
                               LEFT JOIN LATERAL (
                                 SELECT SUM(x.amount) FILTER (WHERE x.status = 'approved')        AS approved,
                                        SUM(x.amount) FILTER (WHERE x.status = 'sent_to_finance') AS sent
                                   FROM public.payment_approvals x WHERE x.budget_line_id = b.id
                               ) pay ON TRUE
                               LEFT JOIN LATERAL (
                                 SELECT SUM(y.amount) AS closed FROM public.land_closings y
                                  WHERE y.budget_line_id = b.id AND y.status = 'closed'
                               ) lc ON TRUE
                              WHERE b.project_id = p.id AND b.deleted_at IS NULL AND b.line_type <> 'contingency'),
    'milestones_total',      ms.total,
    'milestones_completed',  ms.done,
    'near_zero_percent',     COALESCE((SELECT (value #>> '{}')::numeric FROM public.financial_settings
                                        WHERE setting_key = 'contingency_near_zero_percent'), 5)
  )
  FROM public.projects p
  CROSS JOIN LATERAL (
    SELECT count(*) AS total, count(*) FILTER (WHERE m.status = 'completed') AS done
      FROM public.milestones m
      JOIN public.tasks t ON t.id = m.task_id
     WHERE t.project_id = p.id AND t.deleted_at IS NULL AND m.status <> 'cancelled'
  ) ms
  WHERE p.id = p_project_id AND p.deleted_at IS NULL;
$$;

COMMENT ON FUNCTION public.fn_project_health_inputs(UUID) IS
  'Every number the health calculation (app/services/financial_health.py) needs, read in one statement.';

CREATE OR REPLACE FUNCTION public.fn_record_groundbreaking(p_project_id UUID, p_actor UUID)
RETURNS SETOF public.projects
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
  v_cont    NUMERIC;
BEGIN
  IF NOT (private.user_has_role(p_actor, 'project_manager') OR private.user_has_role(p_actor, 'executive')
          OR private.user_has_role(p_actor, 'admin')) THEN
    RAISE EXCEPTION 'Only a project manager, executive or admin can record groundbreaking.' USING ERRCODE = 'PT403';
  END IF;
  v_project := private.fin_lock_project(p_project_id, TRUE, FALSE);
  IF v_project.groundbreaking_at IS NOT NULL THEN
    RAISE EXCEPTION 'Groundbreaking is already recorded for this project.' USING ERRCODE = 'PT409';
  END IF;
  SELECT budget_amount INTO v_cont FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL;
  IF COALESCE(v_cont, 0) <= 0 THEN
    RAISE EXCEPTION 'Groundbreaking needs contingency above $0, because later checks are measured against it.'
      USING ERRCODE = 'PT422';
  END IF;
  UPDATE public.projects
     SET contingency_at_groundbreaking = v_cont, groundbreaking_at = NOW(), groundbreaking_by = p_actor
   WHERE id = p_project_id RETURNING * INTO v_project;
  RETURN NEXT v_project;
END;
$$;


-- ============================================================================
-- SECTION D: 5.2 / 5.3 ALERT SYNC
-- ============================================================================
-- p_checks: [{type, active, severity, left_pct, work_left_pct, remaining, reserve, message}]
--   no live alert       → open one
--   open                → refresh its numbers
--   OK to proceed given → stays quiet until contingency drops below the amount
--                         it was decided at, then a new decision is needed
--   on hold             → untouched until the hold is lifted
--   no longer active    → resolved
CREATE OR REPLACE FUNCTION public.fn_sync_financial_alerts(p_project_id UUID, p_checks JSONB)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  c         JSONB;
  v_alert   public.financial_alerts;
  v_type    TEXT;
  v_remain  NUMERIC;
  v_new     UUID;
  v_found   BOOLEAN;
  v_opened  JSONB := '[]'::jsonb;
BEGIN
  PERFORM private.fin_lock_project(p_project_id, FALSE, FALSE);

  FOR c IN SELECT value FROM jsonb_array_elements(p_checks) LOOP
    v_type   := c ->> 'type';
    v_remain := (c ->> 'remaining')::numeric;

    IF NOT (c ->> 'active')::boolean THEN
      UPDATE public.financial_alerts SET status = 'resolved', resolved_at = NOW()
       WHERE project_id = p_project_id AND alert_type = v_type
         AND status IN ('open', 'acknowledged', 'proceed_approved');
      CONTINUE;
    END IF;

    SELECT * INTO v_alert FROM public.financial_alerts
     WHERE project_id = p_project_id AND alert_type = v_type
       AND status IN ('open', 'acknowledged', 'proceed_approved', 'on_hold')
     ORDER BY created_at DESC LIMIT 1;
    v_found := FOUND;

    IF v_found AND v_alert.status IN ('open', 'acknowledged') THEN
      UPDATE public.financial_alerts
         SET severity = c ->> 'severity', contingency_left_pct = (c ->> 'left_pct')::numeric,
             work_left_pct = (c ->> 'work_left_pct')::numeric, contingency_remaining = v_remain,
             reserve_required = (c ->> 'reserve')::numeric, message = c ->> 'message'
       WHERE id = v_alert.id;
      CONTINUE;
    END IF;
    IF v_found AND (v_alert.status = 'on_hold'
                    OR v_remain >= COALESCE(v_alert.contingency_remaining, v_remain)) THEN
      CONTINUE;
    END IF;
    IF v_found THEN
      UPDATE public.financial_alerts SET status = 'superseded' WHERE id = v_alert.id;
    END IF;

    INSERT INTO public.financial_alerts (
      project_id, alert_type, severity, contingency_left_pct, work_left_pct,
      contingency_remaining, reserve_required, message
    ) VALUES (
      p_project_id, v_type, c ->> 'severity', (c ->> 'left_pct')::numeric, (c ->> 'work_left_pct')::numeric,
      v_remain, (c ->> 'reserve')::numeric, c ->> 'message'
    ) RETURNING id INTO v_new;
    v_opened := v_opened || to_jsonb(v_new);
  END LOOP;

  RETURN v_opened;
END;
$$;

COMMENT ON FUNCTION public.fn_sync_financial_alerts(UUID, JSONB) IS
  'Brings a project''s guardrail alerts in line with the calculated checks. Returns the ids of newly opened alerts.';


-- ============================================================================
-- SECTION E: 5.4 DECISION AND HOLD
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_decide_financial_alert(
  p_alert_id       UUID,
  p_actor          UUID,
  p_decision       TEXT,
  p_reason         TEXT,
  p_discussed_with UUID,
  p_notes          TEXT
)
RETURNS SETOF public.financial_alerts
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_alert   public.financial_alerts;
  v_project public.projects;
BEGIN
  IF p_decision IS NULL OR p_decision NOT IN ('proceed', 'hold') THEN
    RAISE EXCEPTION 'The decision must be proceed or hold.' USING ERRCODE = 'PT422';
  END IF;
  IF btrim(COALESCE(p_reason, '')) = '' THEN
    RAISE EXCEPTION 'A decision needs a reason.' USING ERRCODE = 'PT422';
  END IF;
  IF btrim(COALESCE(p_notes, '')) = '' THEN
    RAISE EXCEPTION 'Record what was discussed with the field manager.' USING ERRCODE = 'PT422';
  END IF;
  IF NOT (private.user_has_role(p_actor, 'project_manager') OR private.user_has_role(p_actor, 'executive')
          OR private.user_has_role(p_actor, 'admin')) THEN
    RAISE EXCEPTION 'Only a project manager, executive or admin can decide this alert.' USING ERRCODE = 'PT403';
  END IF;

  SELECT * INTO v_alert FROM public.financial_alerts WHERE id = p_alert_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Alert not found' USING ERRCODE = 'PT404';
  END IF;
  IF v_alert.alert_type = 'bidding_checkpoint' THEN
    RAISE EXCEPTION 'The bidding checkpoint has no proceed / hold decision.' USING ERRCODE = 'PT422';
  END IF;

  v_project := private.fin_lock_project(v_alert.project_id, FALSE, FALSE);
  SELECT * INTO v_alert FROM public.financial_alerts WHERE id = p_alert_id FOR UPDATE;
  IF v_alert.status NOT IN ('open', 'acknowledged') THEN
    RAISE EXCEPTION 'This alert is already decided or resolved.' USING ERRCODE = 'PT409';
  END IF;
  IF v_project.archived_at IS NOT NULL OR v_project.status IN ('completed', 'cancelled') THEN
    RAISE EXCEPTION 'This project is closed or archived.' USING ERRCODE = 'PT409';
  END IF;

  -- The conversation is between two people, one of them a field manager.
  IF p_discussed_with IS NULL OR p_discussed_with = p_actor
     OR NOT EXISTS (SELECT 1 FROM public.users WHERE id = p_discussed_with AND is_active AND deleted_at IS NULL) THEN
    RAISE EXCEPTION 'Choose the field manager you spoke with (someone other than yourself).' USING ERRCODE = 'PT422';
  END IF;
  IF p_discussed_with IS DISTINCT FROM v_project.field_manager_id
     AND NOT private.user_has_role(p_discussed_with, 'field_manager') THEN
    RAISE EXCEPTION 'The person you spoke with must be a field manager.' USING ERRCODE = 'PT422';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  -- One conversation settles every open guardrail alert of the project.
  UPDATE public.financial_alerts
     SET status             = CASE WHEN p_decision = 'proceed' THEN 'proceed_approved' ELSE 'on_hold' END,
         decision           = p_decision,
         decision_reason    = btrim(p_reason),
         decided_by         = p_actor,
         decided_at         = NOW(),
         discussed_with     = p_discussed_with,
         conversation_notes = btrim(p_notes)
   WHERE project_id = v_project.id AND status IN ('open', 'acknowledged')
     AND alert_type <> 'bidding_checkpoint';

  IF p_decision = 'hold' AND v_project.status <> 'on_hold' THEN
    UPDATE public.projects SET status_before_hold = status, status = 'on_hold' WHERE id = v_project.id;
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN QUERY SELECT * FROM public.financial_alerts WHERE id = p_alert_id;
END;
$$;

COMMENT ON FUNCTION public.fn_decide_financial_alert(UUID, UUID, TEXT, TEXT, UUID, TEXT) IS
  'Manager''s OK-to-proceed or hold, with the reason and the field manager conversation. Hold moves the project to on_hold.';

CREATE OR REPLACE FUNCTION public.fn_lift_financial_hold(p_project_id UUID, p_actor UUID, p_reason TEXT)
RETURNS SETOF public.projects
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
BEGIN
  IF btrim(COALESCE(p_reason, '')) = '' THEN
    RAISE EXCEPTION 'Lifting the hold needs a reason.' USING ERRCODE = 'PT422';
  END IF;
  IF NOT (private.user_has_role(p_actor, 'project_manager') OR private.user_has_role(p_actor, 'executive')
          OR private.user_has_role(p_actor, 'admin')) THEN
    RAISE EXCEPTION 'Only a project manager, executive or admin can lift the hold.' USING ERRCODE = 'PT403';
  END IF;

  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.archived_at IS NOT NULL THEN
    RAISE EXCEPTION 'This project is archived. Unarchive it first.' USING ERRCODE = 'PT409';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.financial_alerts WHERE project_id = p_project_id AND status = 'on_hold') THEN
    RAISE EXCEPTION 'This project has no financial hold.' USING ERRCODE = 'PT409';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  -- Lifting is an OK to proceed at today's contingency: a further drop alerts again.
  UPDATE public.financial_alerts
     SET status = 'proceed_approved', hold_lifted_by = p_actor, hold_lifted_at = NOW(),
         hold_lift_reason = btrim(p_reason),
         contingency_remaining = COALESCE((SELECT budget_amount FROM public.budget_lines
                                            WHERE project_id = p_project_id AND line_type = 'contingency'
                                              AND deleted_at IS NULL), contingency_remaining)
   WHERE project_id = p_project_id AND status = 'on_hold';
  UPDATE public.projects
     SET status = CASE WHEN status = 'on_hold' THEN COALESCE(status_before_hold, 'active') ELSE status END,
         status_before_hold = NULL
   WHERE id = p_project_id RETURNING * INTO v_project;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_project;
END;
$$;

-- Project guard: a financial hold is lifted only through the procedure, and the
-- long-tail reserve is released only at project close.
CREATE OR REPLACE FUNCTION public.fn_guard_project_health()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  IF NOT private.fin_write_authorized()
     AND NEW.status IS DISTINCT FROM OLD.status AND OLD.status = 'on_hold'
     AND EXISTS (SELECT 1 FROM public.financial_alerts WHERE project_id = OLD.id AND status = 'on_hold') THEN
    RAISE EXCEPTION 'This project is on a financial hold. Lift the hold from its financial alert, with a reason.'
      USING ERRCODE = 'PT409';
  END IF;
  IF COALESCE(NEW.long_tail_reserve_amount, 0) < COALESCE(OLD.long_tail_reserve_amount, 0)
     AND OLD.groundbreaking_at IS NOT NULL AND NEW.status <> 'completed' THEN
    RAISE EXCEPTION 'The long-tail reserve can only be released when the project is completed.' USING ERRCODE = 'PT409';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_projects_guard_health ON public.projects;
CREATE TRIGGER trg_projects_guard_health
  BEFORE UPDATE OF status, long_tail_reserve_amount ON public.projects
  FOR EACH ROW EXECUTE FUNCTION public.fn_guard_project_health();

-- On hold = no new bid packages, awards, approvals or payments. Two functions,
-- because bid packages / awards reach the project through their task.
CREATE OR REPLACE FUNCTION public.fn_block_on_hold_task()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_status TEXT;
BEGIN
  -- FOR SHARE: waits for a hold that is being placed right now.
  SELECT p.status INTO v_status FROM public.projects p
   WHERE p.id = (SELECT t.project_id FROM public.tasks t WHERE t.id = NEW.task_id) FOR SHARE;
  IF v_status = 'on_hold' THEN
    RAISE EXCEPTION 'This project is on hold. New bid packages, awards, approvals and payments are blocked until the hold is lifted.'
      USING ERRCODE = 'PT409';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_block_on_hold_payment()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_status TEXT;
BEGIN
  SELECT p.status INTO v_status FROM public.projects p WHERE p.id = NEW.project_id FOR SHARE;
  IF v_status = 'on_hold' THEN
    RAISE EXCEPTION 'This project is on hold. New bid packages, awards, approvals and payments are blocked until the hold is lifted.'
      USING ERRCODE = 'PT409';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_bid_packages_block_on_hold ON public.bid_packages;
CREATE TRIGGER trg_bid_packages_block_on_hold BEFORE INSERT ON public.bid_packages
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_on_hold_task();
DROP TRIGGER IF EXISTS trg_awards_block_on_hold ON public.awards;
CREATE TRIGGER trg_awards_block_on_hold BEFORE INSERT ON public.awards
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_on_hold_task();
DROP TRIGGER IF EXISTS trg_payment_approvals_block_on_hold_ins ON public.payment_approvals;
CREATE TRIGGER trg_payment_approvals_block_on_hold_ins BEFORE INSERT ON public.payment_approvals
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_on_hold_payment();
-- Rejecting and cancelling stay possible on a held project.
DROP TRIGGER IF EXISTS trg_payment_approvals_block_on_hold_upd ON public.payment_approvals;
CREATE TRIGGER trg_payment_approvals_block_on_hold_upd BEFORE UPDATE OF status ON public.payment_approvals
  FOR EACH ROW
  WHEN (NEW.status IS DISTINCT FROM OLD.status AND NEW.status NOT IN ('pending', 'rejected', 'cancelled'))
  EXECUTE FUNCTION public.fn_block_on_hold_payment();
DROP TRIGGER IF EXISTS trg_finance_handoffs_block_on_hold ON public.finance_handoffs;
CREATE TRIGGER trg_finance_handoffs_block_on_hold BEFORE INSERT ON public.finance_handoffs
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_on_hold_payment();


-- ============================================================================
-- SECTION F: READ SURFACE
-- ============================================================================
CREATE OR REPLACE VIEW public.v_financial_alerts
WITH (security_invoker = true) AS
SELECT a.id, a.project_id, p.name AS project_name, p.status AS project_status,
       p.manager_id, p.field_manager_id, p.archived_at AS project_archived_at,
       a.alert_type, a.severity, a.status, a.contingency_left_pct, a.work_left_pct,
       a.contingency_remaining, a.reserve_required, a.message,
       a.decision, a.decision_reason, a.decided_by, du.full_name AS decided_by_name, a.decided_at,
       a.discussed_with, wu.full_name AS discussed_with_name, a.conversation_notes,
       a.hold_lifted_by, lu.full_name AS hold_lifted_by_name, a.hold_lifted_at, a.hold_lift_reason,
       a.notified_at, a.escalated_at, a.resolved_at, a.created_at, a.updated_at
  FROM public.financial_alerts a
  JOIN public.projects p ON p.id = a.project_id AND p.deleted_at IS NULL
  LEFT JOIN public.users du ON du.id = a.decided_by
  LEFT JOIN public.users wu ON wu.id = a.discussed_with
  LEFT JOIN public.users lu ON lu.id = a.hold_lifted_by;

COMMENT ON VIEW public.v_financial_alerts IS
  'Financial alerts with project and people names. security_invoker = true.';


-- ============================================================================
-- SECTION G: PRIVILEGES
-- ============================================================================
REVOKE ALL ON public.v_financial_alerts FROM PUBLIC, anon;
GRANT SELECT ON public.v_financial_alerts TO authenticated, service_role;

REVOKE ALL ON FUNCTION public.fn_project_health_inputs(uuid)                                   FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_record_groundbreaking(uuid, uuid)                             FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_sync_financial_alerts(uuid, jsonb)                            FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_decide_financial_alert(uuid, uuid, text, text, uuid, text)    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_lift_financial_hold(uuid, uuid, text)                         FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_guard_project_health()                                        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_block_on_hold_task()                                          FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_block_on_hold_payment()                                       FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_project_health_inputs(uuid)                                TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_record_groundbreaking(uuid, uuid)                          TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_sync_financial_alerts(uuid, jsonb)                         TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_decide_financial_alert(uuid, uuid, text, text, uuid, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_lift_financial_hold(uuid, uuid, text)                      TO service_role;


-- ============================================================================
-- SECTION H: SETTINGS AND VERSION MARKER
-- ============================================================================
INSERT INTO public.financial_settings (setting_key, value, description) VALUES
  ('contingency_near_zero_percent', '5'::jsonb, 'Contingency left % at or below which the urgent near-zero alert fires.'),
  ('alert_escalation_days', '2'::jsonb, 'Days an alert may stay undecided before the executives are emailed.'),
  ('alert_recipients', '{"warning": [], "urgent": [], "critical": []}'::jsonb, 'Emails per alert severity, besides the project''s manager and field manager.')
ON CONFLICT (setting_key) DO NOTHING;

INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.6.0 (20261126_financial_phase5_health)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;

COMMIT;
