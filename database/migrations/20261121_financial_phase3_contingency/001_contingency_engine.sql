-- ============================================================================
-- BluOnX Financial Automation — Phase 3 · Module 3
-- 001  CONTINGENCY ENGINE (schema change script)
-- ============================================================================
-- Version:  4.4.0
-- Date:     November 21, 2026
-- Requires: 20261111_financial_phase1, 20261118_financial_phase2,
--           20261119_financial_phase2_budget_envelope
-- Engine:   PostgreSQL 15+ (Supabase)
-- ============================================================================
--
-- WHAT THIS SCRIPT DOES
--   3.1 Contingency calculation
--       • private.fin_contingency_snapshot   — contingency, base, % left, targets
--       • private.fin_recalc_draft_contingency + two triggers: while the budget
--         is a DRAFT (before bidding) contingency is recalculated whenever the
--         base changes (land lines, the project Budget value, the project %).
--         contingency = (total − land) × pct / (100 + pct)  [fixed total]
--                     = pct × (all lines − land − contingency) [no total]
--       • fn_set_project_contingency_percent — admin sets the project % (draft
--         or before a budget exists; after baseline only a top-up adds money)
--   3.2 Bid variance — unchanged: fn_apply_bid_to_line (Phase 1) already moves
--       the bid difference into / out of contingency as a line update with a
--       ledger row; the baselined-budget guard stops savings moving elsewhere.
--   3.3 v_contingency_ledger — every movement with source line, direction,
--       user, bucket kind and running balance.
--   3.4 Bidding-complete checkpoint
--       • projects.bidding_completed_at / _by / _contingency_left_pct / _note
--       • fn_complete_bidding — snapshot, outcome, financial_alerts row when
--         below target (critical at or below the escalation %)
--       • fn_reopen_bidding   — admin undo
--   3.5 Top-ups — fn_approve_contingency_top_up now also raises the project's
--       Budget value, so the project and the budget show the same total.
--
-- SAFETY: additive / CREATE OR REPLACE only, idempotent, one transaction.
-- No data is inserted or changed. Settings already exist from Phase 1
-- (default_contingency_percent 15, bidding_target_contingency_percent 10,
-- bidding_escalation_percent 5, finance_emails, sales_emails).
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $$
BEGIN
  IF to_regclass('public.contingency_ledger') IS NULL
     OR to_regprocedure('public.fn_reset_draft_budget(uuid, uuid)') IS NULL THEN
    RAISE EXCEPTION 'Phase 1, Phase 2 and the 20261119 budget envelope patch must be applied first.';
  END IF;
END $$;


-- ============================================================================
-- SECTION A: projects — bidding checkpoint columns
-- ============================================================================
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS bidding_completed_at          TIMESTAMPTZ;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS bidding_completed_by          UUID;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS bidding_contingency_left_pct  DECIMAL(9,2);
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS bidding_completion_note       TEXT;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_projects_bidding_completed_by') THEN
    ALTER TABLE public.projects ADD CONSTRAINT fk_projects_bidding_completed_by
      FOREIGN KEY (bidding_completed_by) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
END $$;

COMMENT ON COLUMN public.projects.bidding_completed_at         IS 'When the project manager marked bidding complete (checkpoint). NULL = bidding still open. Set only by fn_complete_bidding.';
COMMENT ON COLUMN public.projects.bidding_completed_by         IS 'Who marked bidding complete.';
COMMENT ON COLUMN public.projects.bidding_contingency_left_pct IS 'Contingency left as % of the contingency base at the moment bidding was marked complete.';
COMMENT ON COLUMN public.projects.bidding_completion_note      IS 'Optional note entered when bidding was marked complete.';


-- ============================================================================
-- SECTION B: 3.1 CONTINGENCY CALCULATION
-- ============================================================================

-- B.1 Snapshot: contingency, base, % left and the checkpoint targets.
CREATE OR REPLACE FUNCTION private.fin_contingency_snapshot(p_project_id UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  WITH l AS (
    SELECT COALESCE(SUM(budget_amount) FILTER (WHERE line_type = 'contingency'), 0)                AS cont,
           COALESCE(SUM(budget_amount) FILTER (WHERE line_type NOT IN ('land', 'contingency')), 0) AS base,
           COALESCE(SUM(budget_amount) FILTER (WHERE line_type = 'land'), 0)                       AS land,
           COALESCE(SUM(budget_amount), 0)                                                         AS total
      FROM public.budget_lines
     WHERE project_id = p_project_id AND deleted_at IS NULL
  ),
  s AS (
    SELECT COALESCE((SELECT (value #>> '{}')::numeric FROM public.financial_settings
                      WHERE setting_key = 'bidding_target_contingency_percent'), 10) AS target,
           COALESCE((SELECT (value #>> '{}')::numeric FROM public.financial_settings
                      WHERE setting_key = 'bidding_escalation_percent'), 5)          AS esc
  )
  SELECT jsonb_build_object(
           'contingency',        l.cont,
           'base',               l.base,
           'land',               l.land,
           'total',              l.total,
           'left_percent',       CASE WHEN l.base > 0 THEN round(l.cont * 100 / l.base, 2) END,
           'target_percent',     s.target,
           'escalation_percent', s.esc)
    FROM l, s;
$$;

COMMENT ON FUNCTION private.fin_contingency_snapshot(UUID) IS
  'Contingency now, contingency base (total − land − contingency), % left (contingency ÷ base) and the bidding target / escalation % from financial_settings.';


-- B.2 Recalculate a DRAFT budget's contingency from its base.
CREATE OR REPLACE FUNCTION private.fin_recalc_draft_contingency(p_project_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
  v_line    public.budget_lines;
  v_pct     NUMERIC;
  v_total   NUMERIC;
  v_land    NUMERIC;
  v_others  NUMERIC;
  v_new     NUMERIC;
BEGIN
  SELECT * INTO v_project FROM public.projects WHERE id = p_project_id;
  IF NOT FOUND OR v_project.budget_status <> 'draft' OR v_project.bidding_completed_at IS NOT NULL THEN
    RETURN;
  END IF;

  SELECT * INTO v_line FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL
   FOR UPDATE;
  IF NOT FOUND THEN
    RETURN;
  END IF;

  v_pct := COALESCE(v_project.contingency_percent,
                    (SELECT (value #>> '{}')::numeric FROM public.financial_settings
                      WHERE setting_key = 'default_contingency_percent'),
                    15);
  v_total := CASE WHEN v_project.budget IS NOT NULL AND v_project.budget > 0 THEN v_project.budget END;

  SELECT COALESCE(SUM(budget_amount) FILTER (WHERE line_type = 'land'), 0),
         COALESCE(SUM(budget_amount) FILTER (WHERE line_type NOT IN ('land', 'contingency')), 0)
    INTO v_land, v_others
    FROM public.budget_lines
   WHERE project_id = p_project_id AND deleted_at IS NULL;

  IF v_total IS NOT NULL THEN
    -- base = total − land − contingency, contingency = pct × base
    v_new := round(GREATEST(v_total - v_land, 0) * v_pct / (100 + v_pct), 2);
  ELSE
    v_new := round(v_others * v_pct / 100, 2);
  END IF;

  IF v_new IS DISTINCT FROM v_line.budget_amount THEN
    -- The Unallocated trigger offsets this change, so the total stays put.
    UPDATE public.budget_lines SET budget_amount = v_new WHERE id = v_line.id;
  END IF;
END;
$$;

COMMENT ON FUNCTION private.fin_recalc_draft_contingency(UUID) IS
  'Draft budgets before bidding only: sets the contingency line to pct of the contingency base. Fixed total (project Budget set): (total − land) × pct / (100 + pct). Otherwise pct × (all lines − land − contingency). No-op for baselined budgets.';


-- B.3 Line trigger: a base change on a draft budget recalculates contingency.
CREATE OR REPLACE FUNCTION public.fn_budget_lines_recalc_contingency()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_status TEXT;
  v_budget NUMERIC;
BEGIN
  IF NEW.line_type = 'contingency' OR COALESCE(NEW.line_subtype, '') = 'unallocated' THEN
    RETURN NULL;
  END IF;

  SELECT budget_status, budget INTO v_status, v_budget FROM public.projects WHERE id = NEW.project_id;
  IF v_status IS DISTINCT FROM 'draft' THEN
    RETURN NULL;
  END IF;

  -- With a fixed total only land moves the base (other lines trade with
  -- Unallocated); without one, every line is part of the base.
  IF v_budget IS NOT NULL AND v_budget > 0 AND NEW.line_type <> 'land' THEN
    RETURN NULL;
  END IF;

  PERFORM private.fin_recalc_draft_contingency(NEW.project_id);
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_budget_lines_recalc_contingency ON public.budget_lines;
CREATE TRIGGER trg_budget_lines_recalc_contingency
  AFTER INSERT OR UPDATE OF budget_amount, deleted_at ON public.budget_lines
  FOR EACH ROW EXECUTE FUNCTION public.fn_budget_lines_recalc_contingency();

COMMENT ON FUNCTION public.fn_budget_lines_recalc_contingency() IS
  'Draft budgets: after a base line changes, recalculates contingency (fin_recalc_draft_contingency). Fires after trg_budget_lines_absorb_unallocated (alphabetical), so Unallocated absorbs both changes.';


-- B.4 Project trigger: Budget value or contingency % changed on a draft.
CREATE OR REPLACE FUNCTION public.fn_projects_recalc_draft_contingency()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_unalloc public.budget_lines;
BEGIN
  IF NEW.budget_status IS DISTINCT FROM 'draft' OR NEW.bidding_completed_at IS NOT NULL THEN
    RETURN NULL;
  END IF;

  -- A new project Budget value moves the total: Unallocated takes the change
  -- first, then contingency is recalculated from the new total.
  IF NEW.budget IS DISTINCT FROM OLD.budget
     AND COALESCE(OLD.budget, 0) > 0 AND COALESCE(NEW.budget, 0) > 0 THEN
    SELECT * INTO v_unalloc FROM public.budget_lines
     WHERE project_id = NEW.id AND line_subtype = 'unallocated' AND deleted_at IS NULL
     FOR UPDATE;
    IF FOUND THEN
      UPDATE public.budget_lines
         SET budget_amount = GREATEST(v_unalloc.budget_amount + (NEW.budget - OLD.budget), 0)
       WHERE id = v_unalloc.id;
    END IF;
  END IF;

  PERFORM private.fin_recalc_draft_contingency(NEW.id);
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_projects_recalc_draft_contingency ON public.projects;
CREATE TRIGGER trg_projects_recalc_draft_contingency
  AFTER UPDATE OF budget, contingency_percent ON public.projects
  FOR EACH ROW EXECUTE FUNCTION public.fn_projects_recalc_draft_contingency();

COMMENT ON FUNCTION public.fn_projects_recalc_draft_contingency() IS
  'Draft budgets: when the project Budget value or contingency % changes, Unallocated takes the change in total and contingency is recalculated.';


-- B.5 Admin: set the project contingency %.
CREATE OR REPLACE FUNCTION public.fn_set_project_contingency_percent(
  p_project_id UUID,
  p_percent    NUMERIC,
  p_actor      UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;
  IF p_percent IS NOT NULL AND (p_percent < 0 OR p_percent > 100) THEN
    RAISE EXCEPTION 'Contingency %% must be between 0 and 100 (got %)', p_percent USING ERRCODE = 'PT422';
  END IF;

  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.budget_status = 'baselined' THEN
    RAISE EXCEPTION 'The contingency %% is fixed once the budget is baselined. Raise contingency with an executive-approved top-up instead.'
      USING ERRCODE = 'PT409';
  END IF;

  UPDATE public.projects SET contingency_percent = p_percent WHERE id = p_project_id;

  RETURN private.fin_contingency_snapshot(p_project_id)
         || jsonb_build_object('contingency_percent', p_percent);
END;
$$;

COMMENT ON FUNCTION public.fn_set_project_contingency_percent(UUID, NUMERIC, UUID) IS
  'Sets projects.contingency_percent (NULL = the default from financial_settings) before a budget exists or while it is a draft; a draft budget''s contingency is recalculated at once. PT409 after baseline (use a top-up).';


-- ============================================================================
-- SECTION C: 3.3 CONTINGENCY LEDGER VIEW
-- ============================================================================
CREATE OR REPLACE VIEW public.v_contingency_ledger
WITH (security_invoker = true) AS
SELECT
  cl.id,
  cl.entry_no,
  cl.project_id,
  cl.contingency_line_id,
  cl.contingency_bucket_id,
  cb.bucket_kind,
  cl.movement_type,
  cl.amount,
  CASE WHEN cl.amount > 0 THEN 'in' WHEN cl.amount < 0 THEN 'out' ELSE 'none' END AS direction,
  cl.balance_before,
  cl.balance_after,
  cl.source_budget_line_id,
  sl.name       AS source_line_name,
  sl.line_type  AS source_line_type,
  cl.variance_line_id,
  cl.award_id,
  cl.actor_user_id,
  u.full_name   AS actor_name,
  u.email       AS actor_email,
  cl.reason,
  cl.created_at
FROM public.contingency_ledger cl
LEFT JOIN public.contingency_buckets cb ON cb.id = cl.contingency_bucket_id
LEFT JOIN public.budget_lines        sl ON sl.id = cl.source_budget_line_id
LEFT JOIN public.users               u  ON u.id  = cl.actor_user_id;

COMMENT ON VIEW public.v_contingency_ledger IS
  'Contingency ledger read surface: every movement with its source line, direction (in / out), user, bucket kind and running balance (balance_after). Order by entry_no. security_invoker = true.';

GRANT SELECT ON public.v_contingency_ledger TO authenticated, service_role;


-- ============================================================================
-- SECTION D: 3.4 BIDDING-COMPLETE CHECKPOINT
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_complete_bidding(
  p_project_id UUID,
  p_actor      UUID,
  p_note       TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project  public.projects;
  v_snap     JSONB;
  v_left     NUMERIC;
  v_target   NUMERIC;
  v_esc      NUMERIC;
  v_outcome  TEXT;
  v_severity TEXT;
  v_alert    UUID;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.budget_status <> 'baselined' THEN
    RAISE EXCEPTION 'Baseline the budget before marking bidding complete, so bid differences are measured against contingency.'
      USING ERRCODE = 'PT409';
  END IF;
  IF v_project.bidding_completed_at IS NOT NULL THEN
    RAISE EXCEPTION 'Bidding is already marked complete for this project.' USING ERRCODE = 'PT409';
  END IF;

  v_snap   := private.fin_contingency_snapshot(p_project_id);
  v_left   := (v_snap ->> 'left_percent')::numeric;
  v_target := (v_snap ->> 'target_percent')::numeric;
  v_esc    := (v_snap ->> 'escalation_percent')::numeric;

  v_outcome := CASE
                 WHEN v_left IS NULL     THEN 'no_base'
                 WHEN v_left <= v_esc    THEN 'escalated'
                 WHEN v_left <  v_target THEN 'below_target'
                 ELSE 'on_target'
               END;

  -- One open checkpoint alert per project: an older one is superseded.
  UPDATE public.financial_alerts
     SET status = 'superseded', updated_at = NOW()
   WHERE project_id = p_project_id AND alert_type = 'bidding_checkpoint' AND status = 'open';

  IF v_outcome IN ('escalated', 'below_target') THEN
    v_severity := CASE WHEN v_outcome = 'escalated' THEN 'critical' ELSE 'warning' END;
    INSERT INTO public.financial_alerts (
      project_id, alert_type, severity, contingency_left_pct, contingency_remaining, message
    ) VALUES (
      p_project_id, 'bidding_checkpoint', v_severity, v_left, (v_snap ->> 'contingency')::numeric,
      format('Bidding complete with %s%% contingency left (target %s%%, escalation at %s%%).', v_left, v_target, v_esc)
    )
    RETURNING id INTO v_alert;
  END IF;

  -- Above target: recorded only. Contingency is never released early.
  UPDATE public.projects
     SET bidding_completed_at         = NOW(),
         bidding_completed_by         = p_actor,
         bidding_contingency_left_pct = v_left,
         bidding_completion_note      = NULLIF(btrim(COALESCE(p_note, '')), '')
   WHERE id = p_project_id;

  RETURN v_snap || jsonb_build_object('outcome', v_outcome, 'severity', v_severity, 'alert_id', v_alert);
END;
$$;

COMMENT ON FUNCTION public.fn_complete_bidding(UUID, UUID, TEXT) IS
  'Bidding-complete checkpoint (baselined budgets): records who / when and the contingency left % of the base. Below target → warning alert; at or below the escalation % (or negative) → critical alert for executive escalation; at or above target → recorded only, nothing released. Returns the snapshot and the outcome.';


CREATE OR REPLACE FUNCTION public.fn_reopen_bidding(
  p_project_id UUID,
  p_actor      UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;
  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.bidding_completed_at IS NULL THEN
    RAISE EXCEPTION 'Bidding is not marked complete for this project.' USING ERRCODE = 'PT409';
  END IF;

  UPDATE public.financial_alerts
     SET status = 'resolved', resolved_at = NOW(), updated_at = NOW()
   WHERE project_id = p_project_id AND alert_type = 'bidding_checkpoint' AND status = 'open';

  UPDATE public.projects
     SET bidding_completed_at = NULL, bidding_completed_by = NULL,
         bidding_contingency_left_pct = NULL, bidding_completion_note = NULL
   WHERE id = p_project_id;

  RETURN private.fin_contingency_snapshot(p_project_id);
END;
$$;

COMMENT ON FUNCTION public.fn_reopen_bidding(UUID, UUID) IS
  'Admin undo of the bidding-complete checkpoint: clears the completion and resolves its open alert.';


-- ============================================================================
-- SECTION E: 3.5 TOP-UP APPROVAL also raises the project Budget value
-- ============================================================================
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

    -- The ONLY path (besides baseline) that changes the approved total. The
    -- project's Budget value follows, so both show the same total.
    UPDATE public.projects
       SET approved_budget_total = approved_budget_total + v_amount,
           budget                = CASE WHEN budget IS NOT NULL THEN budget + v_amount ELSE budget END
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
  'A13: executive-only (PT403 otherwise). Approve: contingency line + amount, projects.approved_budget_total + amount (the only way the total grows after baseline) and the project Budget value + amount, top_up ledger row tied to the bucket. Reject: decision recorded, no money moves.';


-- ============================================================================
-- SECTION F: PRIVILEGES
-- ============================================================================
-- The private helpers run inside triggers as the CALLING role, so the roles
-- that write budgets need EXECUTE (the private schema is not exposed by the API).
REVOKE ALL ON FUNCTION private.fin_contingency_snapshot(uuid)                  FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.fin_recalc_draft_contingency(uuid)              FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.fin_contingency_snapshot(uuid)               TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.fin_recalc_draft_contingency(uuid)           TO authenticated, service_role;
REVOKE ALL ON FUNCTION public.fn_budget_lines_recalc_contingency()             FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_projects_recalc_draft_contingency()           FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_set_project_contingency_percent(uuid, numeric, uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_complete_bidding(uuid, uuid, text)            FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_reopen_bidding(uuid, uuid)                    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_approve_contingency_top_up(uuid, uuid, boolean, numeric, text) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.fn_set_project_contingency_percent(uuid, numeric, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_complete_bidding(uuid, uuid, text)            TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_reopen_bidding(uuid, uuid)                    TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_approve_contingency_top_up(uuid, uuid, boolean, numeric, text) TO service_role;


-- ============================================================================
-- SECTION G: VERSION MARKER
-- ============================================================================
INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.4.0 (20261121_financial_phase3_contingency)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;

COMMIT;

-- ============================================================================
-- END OF 001_contingency_engine.sql
-- ============================================================================
