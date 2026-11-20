-- ============================================================================
-- BluOnX Financial Automation — Phase 3
-- 099  ROLLBACK CONTINGENCY ENGINE — DEV ONLY
-- ============================================================================
-- Removes everything 001_contingency_engine.sql added and restores the
-- Phase 1 top-up approval. Drops the bidding checkpoint columns, so the
-- checkpoint history on projects is LOST. Ledger rows, buckets and alerts are
-- kept (they belong to Phase 1).
-- ============================================================================

BEGIN;

DROP TRIGGER IF EXISTS trg_budget_lines_recalc_contingency   ON public.budget_lines;
DROP TRIGGER IF EXISTS trg_projects_recalc_draft_contingency ON public.projects;

DROP FUNCTION IF EXISTS public.fn_budget_lines_recalc_contingency();
DROP FUNCTION IF EXISTS public.fn_projects_recalc_draft_contingency();
DROP FUNCTION IF EXISTS public.fn_set_project_contingency_percent(uuid, numeric, uuid);
DROP FUNCTION IF EXISTS public.fn_complete_bidding(uuid, uuid, text);
DROP FUNCTION IF EXISTS public.fn_reopen_bidding(uuid, uuid);
DROP FUNCTION IF EXISTS private.fin_recalc_draft_contingency(uuid);
DROP FUNCTION IF EXISTS private.fin_contingency_snapshot(uuid);

DROP VIEW IF EXISTS public.v_contingency_ledger;

ALTER TABLE public.projects DROP CONSTRAINT IF EXISTS fk_projects_bidding_completed_by;
ALTER TABLE public.projects DROP COLUMN IF EXISTS bidding_completed_at;
ALTER TABLE public.projects DROP COLUMN IF EXISTS bidding_completed_by;
ALTER TABLE public.projects DROP COLUMN IF EXISTS bidding_contingency_left_pct;
ALTER TABLE public.projects DROP COLUMN IF EXISTS bidding_completion_note;

-- Phase 1 version of the executive top-up approval (no project Budget bump).
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

REVOKE ALL ON FUNCTION public.fn_approve_contingency_top_up(uuid, uuid, boolean, numeric, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_approve_contingency_top_up(uuid, uuid, boolean, numeric, text) TO service_role;

UPDATE public.financial_settings
   SET value = '"4.2.0 (20261119_financial_phase2_budget_envelope)"'::jsonb
 WHERE setting_key = 'schema_version';

COMMIT;
