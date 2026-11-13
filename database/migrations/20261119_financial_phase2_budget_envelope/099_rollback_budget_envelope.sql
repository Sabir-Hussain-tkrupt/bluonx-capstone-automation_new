-- ============================================================================
-- BluOnX Financial Automation — Phase 2 patch
-- 099  ROLLBACK the budget envelope patch — DEV ONLY
-- ============================================================================
-- Removes the Unallocated trigger, fn_reset_draft_budget and the patched
-- views. Budget data is kept (an existing "Unallocated budget" line stays as a
-- normal line).
--
-- AFTER running this, run 20261118_financial_phase2/001_budget_structure.sql
-- again: it restores the Phase 2 versions of fn_create_project_budget and the
-- two views.
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

DROP TRIGGER IF EXISTS trg_budget_lines_absorb_unallocated ON public.budget_lines;
DROP FUNCTION IF EXISTS public.fn_budget_absorb_unallocated();
DROP FUNCTION IF EXISTS public.fn_reset_draft_budget(uuid, uuid);
DROP INDEX IF EXISTS public.uq_budget_lines_one_unallocated_per_project;

-- The patched summary view has extra columns, so it must be dropped (not
-- replaced) before Phase 2's 001 can recreate the original.
DROP VIEW IF EXISTS public.v_project_budget_summary;
DROP VIEW IF EXISTS public.v_budget_lines;

UPDATE public.financial_settings
   SET value = '"4.1.0 (20261118_financial_phase2)"'::jsonb
 WHERE setting_key = 'schema_version';

COMMIT;
