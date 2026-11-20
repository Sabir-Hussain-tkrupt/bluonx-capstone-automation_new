-- ============================================================================
-- BluOnX Financial Automation — Phase 3 hotfix
-- 003  Grant EXECUTE on the two private contingency helpers
-- ============================================================================
-- Only needed on databases where the first version of 001 was already run
-- ("permission denied for function fin_recalc_draft_contingency" when the
-- contingency % or a land line changes on a draft budget). The current 001
-- already contains these grants. Re-runnable, no data.
-- ============================================================================

BEGIN;

REVOKE ALL ON FUNCTION private.fin_contingency_snapshot(uuid)        FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.fin_recalc_draft_contingency(uuid)    FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.fin_contingency_snapshot(uuid)     TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.fin_recalc_draft_contingency(uuid) TO authenticated, service_role;

COMMIT;
