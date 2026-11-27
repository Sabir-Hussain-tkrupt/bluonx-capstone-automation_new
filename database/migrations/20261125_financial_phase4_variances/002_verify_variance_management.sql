-- ============================================================================
-- BluOnX Financial Automation — Phase 4
-- 002  VERIFY VARIANCE MANAGEMENT (read-only). Every row must say PASS.
-- ============================================================================
WITH checks AS (
  SELECT 1 AS seq, 'V01 variance history table with RLS' AS check_id,
         COALESCE((SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass('public.variance_events')), FALSE) AS ok
  UNION ALL
  SELECT 2, 'V02 variance procedures exist',
         to_regprocedure('public.fn_create_variance(uuid, text, numeric, uuid, uuid, uuid, date, date)') IS NOT NULL
         AND to_regprocedure('public.fn_edit_variance(uuid, numeric, text, uuid, uuid, uuid, text)') IS NOT NULL
         AND to_regprocedure('public.fn_approve_variance(uuid, uuid, text)') IS NOT NULL
         AND to_regprocedure('public.fn_reject_variance(uuid, uuid, text)') IS NOT NULL
  UNION ALL
  SELECT 3, 'V03 history and guardrail triggers exist',
         (SELECT count(*) = 4 FROM pg_trigger WHERE NOT tgisinternal
            AND tgname IN ('trg_variance_lines_created_event', 'trg_variance_events_immutable',
                           'trg_variance_events_no_truncate', 'trg_contingency_ledger_guardrails'))
  UNION ALL
  SELECT 4, 'V04 view v_variances exists', to_regclass('public.v_variances') IS NOT NULL
  UNION ALL
  SELECT 5, 'V05 every variance has its created event',
         NOT EXISTS (SELECT 1 FROM public.variance_lines v
                      WHERE NOT EXISTS (SELECT 1 FROM public.variance_events e
                                         WHERE e.variance_id = v.id AND e.event_type = 'created'))
  UNION ALL
  SELECT 6, 'V06 creator can never approve (constraint)',
         EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_variance_lines_not_self_approved')
  UNION ALL
  SELECT 7, 'V07 procedures only callable by the backend',
         NOT has_function_privilege('authenticated', 'public.fn_approve_variance(uuid, uuid, text)', 'EXECUTE')
         AND NOT has_function_privilege('authenticated', 'public.fn_edit_variance(uuid, numeric, text, uuid, uuid, uuid, text)', 'EXECUTE')
         AND has_function_privilege('service_role', 'public.fn_approve_variance(uuid, uuid, text)', 'EXECUTE')
         AND has_function_privilege('service_role', 'private.fin_recalc_guardrails(uuid)', 'EXECUTE')
         AND has_function_privilege('service_role', 'private.fin_route_manager(uuid, uuid, uuid[])', 'EXECUTE')
  UNION ALL
  SELECT 8, 'V08 baselined budgets are still flat',
         NOT EXISTS (SELECT 1 FROM public.projects p
                      WHERE p.budget_status = 'baselined' AND p.deleted_at IS NULL
                        AND p.approved_budget_total <> (SELECT COALESCE(SUM(b.budget_amount), 0) FROM public.budget_lines b
                                                         WHERE b.project_id = p.id AND b.deleted_at IS NULL))
  UNION ALL
  SELECT 9, 'V09 schema version is 4.5.0',
         (SELECT value #>> '{}' LIKE '4.5.0%' FROM public.financial_settings WHERE setting_key = 'schema_version')
)
SELECT seq, check_id, CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS result FROM checks ORDER BY seq;
