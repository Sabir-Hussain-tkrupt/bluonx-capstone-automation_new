-- ============================================================================
-- BluOnX Financial Automation — Phase 3
-- 002  VERIFY CONTINGENCY ENGINE (read-only: no data is written)
-- ============================================================================
-- Run AFTER 001_contingency_engine.sql. Safe on production. Every row must
-- say PASS.
-- ============================================================================

WITH checks AS (
  SELECT 1 AS seq, 'C01 bidding checkpoint columns on projects' AS check_id,
         (SELECT count(*) = 4 FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'projects'
             AND column_name IN ('bidding_completed_at', 'bidding_completed_by',
                                 'bidding_contingency_left_pct', 'bidding_completion_note')) AS ok,
         NULL::text AS detail
  UNION ALL
  SELECT 2, 'C02 contingency procedures exist',
         to_regprocedure('public.fn_set_project_contingency_percent(uuid, numeric, uuid)') IS NOT NULL
         AND to_regprocedure('public.fn_complete_bidding(uuid, uuid, text)') IS NOT NULL
         AND to_regprocedure('public.fn_reopen_bidding(uuid, uuid)') IS NOT NULL
         AND to_regprocedure('private.fin_contingency_snapshot(uuid)') IS NOT NULL
         AND to_regprocedure('private.fin_recalc_draft_contingency(uuid)') IS NOT NULL,
         NULL
  UNION ALL
  SELECT 3, 'C03 draft recalculation triggers exist',
         (SELECT count(*) = 2 FROM pg_trigger
           WHERE NOT tgisinternal
             AND tgname IN ('trg_budget_lines_recalc_contingency', 'trg_projects_recalc_draft_contingency')),
         NULL
  UNION ALL
  SELECT 4, 'C04 recalc runs after the Unallocated trigger (name order)',
         'trg_budget_lines_absorb_unallocated' < 'trg_budget_lines_recalc_contingency',
         NULL
  UNION ALL
  SELECT 5, 'C05 ledger view has direction, source line and user',
         (SELECT count(*) = 4 FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'v_contingency_ledger'
             AND column_name IN ('direction', 'source_line_name', 'actor_name', 'balance_after')),
         NULL
  UNION ALL
  SELECT 6, 'C06 top-up approval also raises the project Budget value',
         (SELECT prosrc ILIKE '%budget + v_amount%' FROM pg_proc
           WHERE oid = to_regprocedure('public.fn_approve_contingency_top_up(uuid, uuid, boolean, numeric, uuid)')
              OR oid = to_regprocedure('public.fn_approve_contingency_top_up(uuid, uuid, boolean, numeric, text)')
           LIMIT 1),
         NULL
  UNION ALL
  SELECT 7, 'C07 top-up approval still executive-only',
         (SELECT prosrc ILIKE '%user_has_role(p_approver, ''executive'')%' FROM pg_proc
           WHERE oid = to_regprocedure('public.fn_approve_contingency_top_up(uuid, uuid, boolean, numeric, text)')),
         NULL
  UNION ALL
  SELECT 8, 'C08 procedures not callable by authenticated users',
         NOT has_function_privilege('authenticated', 'public.fn_complete_bidding(uuid, uuid, text)', 'EXECUTE')
         AND NOT has_function_privilege('authenticated', 'public.fn_set_project_contingency_percent(uuid, numeric, uuid)', 'EXECUTE')
         AND has_function_privilege('service_role', 'public.fn_complete_bidding(uuid, uuid, text)', 'EXECUTE'),
         NULL
  UNION ALL
  SELECT 9, 'C09 contingency settings present',
         (SELECT count(*) = 5 FROM public.financial_settings
           WHERE setting_key IN ('default_contingency_percent', 'bidding_target_contingency_percent',
                                 'bidding_escalation_percent', 'finance_emails', 'sales_emails')),
         (SELECT string_agg(setting_key || '=' || value::text, ', ' ORDER BY setting_key)
            FROM public.financial_settings
           WHERE setting_key IN ('default_contingency_percent', 'bidding_target_contingency_percent',
                                 'bidding_escalation_percent'))
  UNION ALL
  SELECT 10, 'C10 schema version is 4.4.0',
         (SELECT value #>> '{}' LIKE '4.4.0%' FROM public.financial_settings WHERE setting_key = 'schema_version'),
         (SELECT value #>> '{}' FROM public.financial_settings WHERE setting_key = 'schema_version')
)
SELECT seq, check_id, CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS result, detail
  FROM checks
 ORDER BY seq;
