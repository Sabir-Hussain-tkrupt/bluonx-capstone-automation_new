-- ============================================================================
-- BluOnX Financial Automation — Phase 2 · Module 2
-- 099  ROLLBACK (removes ONLY what 20261118 001 added) — DEV ONLY
-- ============================================================================
-- Removes the Phase 2 procedures, views, task sync trigger and helpers.
-- Data in Phase 1 tables (budget lines, invoices, templates …) is KEPT; the
-- default template row and the finance-documents bucket are kept as well
-- (delete them by hand if you really want to).
--
-- Safety latch — uncomment and run together with the file:
--   SELECT set_config('bluonx.confirm_financial_rollback', 'yes', false);
-- ============================================================================

-- SELECT set_config('bluonx.confirm_financial_rollback', 'yes', false);

BEGIN;

DO $$
BEGIN
  IF COALESCE(current_setting('bluonx.confirm_financial_rollback', TRUE), '') <> 'yes' THEN
    RAISE EXCEPTION 'Rollback not confirmed. Uncomment the set_config line at the top of 099 and run again.';
  END IF;
END $$;

DROP TRIGGER IF EXISTS trg_tasks_sync_budget_line ON public.tasks;

DROP VIEW IF EXISTS public.v_project_budget_summary;
DROP VIEW IF EXISTS public.v_budget_lines;

DROP FUNCTION IF EXISTS public.fn_sync_task_budget_line();
DROP FUNCTION IF EXISTS public.fn_create_project_budget(uuid, uuid, uuid, numeric);
DROP FUNCTION IF EXISTS public.fn_reorder_budget_lines(uuid, uuid[], uuid);
DROP FUNCTION IF EXISTS public.fn_remove_budget_line(uuid, uuid);
DROP FUNCTION IF EXISTS public.fn_apply_budget_import(uuid, jsonb, uuid);
DROP FUNCTION IF EXISTS public.fn_categorise_internal_invoice(uuid, uuid, uuid);
DROP FUNCTION IF EXISTS private.fin_next_activity_position(uuid, text);
DROP FUNCTION IF EXISTS private.fin_line_is_empty(uuid);
DROP FUNCTION IF EXISTS private.fin_line_invoiced(uuid);
DROP FUNCTION IF EXISTS private.fin_line_type_for_bid_type(text);

UPDATE public.financial_settings
   SET value = '"4.0.0 (20261111_financial_phase1)"'::jsonb
 WHERE setting_key = 'schema_version';

COMMIT;
