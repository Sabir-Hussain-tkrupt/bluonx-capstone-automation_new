-- ============================================================================
-- BluOnX Financial Automation — Phase 5
-- 002  VERIFY CONTINGENCY HEALTH (read-only). Every row must say PASS.
-- ============================================================================
WITH checks AS (
  SELECT 1 AS seq, 'H01 new project columns' AS check_id,
         (SELECT count(*) = 5 FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'projects'
             AND column_name IN ('groundbreaking_at', 'groundbreaking_by', 'status_before_hold',
                                 'long_tail_reserve_updated_at', 'long_tail_reserve_updated_by')) AS ok
  UNION ALL
  SELECT 2, 'H02 new alert columns',
         (SELECT count(*) = 7 FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'financial_alerts'
             AND column_name IN ('discussed_with', 'conversation_notes', 'hold_lifted_by', 'hold_lifted_at',
                                 'hold_lift_reason', 'notified_at', 'escalated_at'))
  UNION ALL
  SELECT 3, 'H03 procedures exist',
         to_regprocedure('public.fn_project_health_inputs(uuid)') IS NOT NULL
         AND to_regprocedure('public.fn_record_groundbreaking(uuid, uuid)') IS NOT NULL
         AND to_regprocedure('public.fn_sync_financial_alerts(uuid, jsonb)') IS NOT NULL
         AND to_regprocedure('public.fn_decide_financial_alert(uuid, uuid, text, text, uuid, text)') IS NOT NULL
         AND to_regprocedure('public.fn_lift_financial_hold(uuid, uuid, text)') IS NOT NULL
  UNION ALL
  SELECT 4, 'H04 hold and reserve triggers exist',
         (SELECT count(*) = 6 FROM pg_trigger WHERE NOT tgisinternal
            AND tgname IN ('trg_projects_guard_health', 'trg_bid_packages_block_on_hold', 'trg_awards_block_on_hold',
                           'trg_payment_approvals_block_on_hold_ins', 'trg_payment_approvals_block_on_hold_upd',
                           'trg_finance_handoffs_block_on_hold'))
  UNION ALL
  SELECT 5, 'H05 Phase 4 guardrail trigger retired',
         NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_contingency_ledger_guardrails')
  UNION ALL
  SELECT 6, 'H06 view v_financial_alerts exists', to_regclass('public.v_financial_alerts') IS NOT NULL
  UNION ALL
  SELECT 7, 'H07 procedures only callable by the backend',
         NOT has_function_privilege('authenticated', 'public.fn_decide_financial_alert(uuid, uuid, text, text, uuid, text)', 'EXECUTE')
         AND NOT has_function_privilege('authenticated', 'public.fn_lift_financial_hold(uuid, uuid, text)', 'EXECUTE')
         AND has_function_privilege('service_role', 'public.fn_sync_financial_alerts(uuid, jsonb)', 'EXECUTE')
         AND has_function_privilege('service_role', 'public.fn_project_health_inputs(uuid)', 'EXECUTE')
  UNION ALL
  SELECT 8, 'H08 settings exist',
         (SELECT count(*) = 3 FROM public.financial_settings
           WHERE setting_key IN ('contingency_near_zero_percent', 'alert_escalation_days', 'alert_recipients'))
  UNION ALL
  SELECT 9, 'H09 inputs can be read for every baselined project',
         NOT EXISTS (SELECT 1 FROM public.projects p
                      WHERE p.budget_status = 'baselined' AND p.deleted_at IS NULL
                        AND public.fn_project_health_inputs(p.id) ->> 'contingency' IS NULL)
  UNION ALL
  SELECT 10, 'H10 schema version is 4.6.0',
         (SELECT value #>> '{}' LIKE '4.6.0%' FROM public.financial_settings WHERE setting_key = 'schema_version')
)
SELECT seq, check_id, CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS result FROM checks ORDER BY seq;
