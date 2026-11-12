-- ============================================================================
-- BluOnX Financial Automation — Phase 1 · Module 1
-- 000  PRE-FLIGHT CHECKS (READ-ONLY — changes nothing)
-- ============================================================================
-- Run BEFORE 001_financial_foundation.sql, on dev and on production.
-- It returns ONE table. Every row should say OK (or INFO). Any row that says
-- STOP must be resolved before running 001.
--
-- (Supabase SQL editor shows only the result of the last statement, so all
--  checks are combined into one query.)
-- ============================================================================

WITH
new_tables(name) AS (
  VALUES ('budget_templates'),('budget_template_lines'),('budget_lines'),('land_closings'),
         ('contingency_buckets'),('contingency_ledger'),('variance_lines'),
         ('internal_invoices'),('payment_approvals'),('finance_handoffs'),
         ('escrows'),('property_taxes'),('accounting_periods'),('company_cash_items'),
         ('cash_flow_entries'),('financial_settings'),('financial_alerts'),
         ('user_roles'),('approval_delegations')
),
already AS (
  SELECT string_agg(n.name, ', ' ORDER BY n.name) AS names, count(*) AS cnt
    FROM new_tables n WHERE to_regclass('public.' || n.name) IS NOT NULL
),
email_types AS (
  SELECT string_agg(DISTINCT email_type, ', ' ORDER BY email_type) AS vals FROM public.email_log
),
email_check AS (
  SELECT string_agg(conname || ' = ' || pg_get_constraintdef(oid), ' | ') AS defs
    FROM pg_constraint
   WHERE conrelid = 'public.email_log'::regclass AND contype = 'c'
     AND pg_get_constraintdef(oid) ILIKE '%email_type%'
),
role_values AS (
  SELECT string_agg(role || ' × ' || cnt, ', ') AS vals,
         bool_and(role IN ('admin','project_manager')) AS all_known
    FROM (SELECT role, count(*) AS cnt FROM public.users GROUP BY role) x
)
SELECT * FROM (
  SELECT 1 AS seq,
         CASE WHEN current_setting('server_version_num')::int >= 150000 THEN 'OK' ELSE 'STOP' END AS status,
         'PostgreSQL version' AS check_name,
         version() AS detail
  UNION ALL
  SELECT 2, CASE WHEN to_regclass('public.users') IS NOT NULL AND to_regclass('public.projects') IS NOT NULL
                  AND to_regclass('public.tasks') IS NOT NULL AND to_regclass('public.awards') IS NOT NULL
                  AND to_regclass('public.contracts') IS NOT NULL AND to_regclass('public.email_log') IS NOT NULL
                 THEN 'OK' ELSE 'STOP' END,
         'Bid Management schema (v3.9) present', 'users, projects, tasks, awards, contracts, email_log'
  UNION ALL
  SELECT 3, CASE WHEN to_regprocedure('public.fn_set_updated_at()') IS NOT NULL THEN 'OK' ELSE 'STOP' END,
         'fn_set_updated_at() exists', 'reused by the updated_at triggers'
  UNION ALL
  SELECT 4, CASE WHEN to_regprocedure('private.is_active_user()') IS NOT NULL THEN 'OK' ELSE 'STOP' END,
         'private.is_active_user() exists (rls_policies.sql applied)', 'reused by the new RLS policies'
  UNION ALL
  SELECT 5, CASE WHEN to_regprocedure('public.fn_handle_new_auth_user()') IS NOT NULL THEN 'OK' ELSE 'STOP' END,
         'fn_handle_new_auth_user() exists', 'will be extended (backward compatible)'
  UNION ALL
  SELECT 6, CASE WHEN EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_on_auth_user_created') THEN 'OK' ELSE 'INFO' END,
         'Auth profile trigger installed on auth.users', 'trg_on_auth_user_created'
  UNION ALL
  SELECT 7, CASE WHEN a.cnt = 0 THEN 'OK'
                 WHEN a.cnt = 19 AND to_regclass('public.financial_settings') IS NOT NULL THEN 'INFO'
                 ELSE 'STOP' END,
         'Financial tables already present',
         CASE WHEN a.cnt = 0 THEN 'none — fresh install'
              WHEN a.cnt = 19 THEN 'all 19 present — 001 was run before; re-running is safe'
              ELSE a.cnt || ' of 19 present (' || a.names || ') — unexpected partial state or name clash' END
    FROM already a
  UNION ALL
  SELECT 8, 'INFO', 'email_log.email_type values in use (all are kept by 001)', COALESCE(e.vals, '(table empty)')
    FROM email_types e
  UNION ALL
  SELECT 9, CASE WHEN c.defs IS NULL THEN 'INFO' ELSE 'OK' END,
         'Current email_type CHECK (will be replaced by a superset)', COALESCE(c.defs, 'no CHECK found')
    FROM email_check c
  UNION ALL
  SELECT 10, CASE WHEN COALESCE(r.all_known, TRUE) THEN 'OK' ELSE 'STOP' END,
         'users.role values (must be admin / project_manager only)', COALESCE(r.vals, '(no users)')
    FROM role_values r
  UNION ALL
  SELECT 11, CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns
                                WHERE table_schema = 'public' AND table_name = 'users'
                                  AND column_name IN ('is_employee','reports_to','backup_approver_id','approval_limit')
                                  AND NOT EXISTS (SELECT 1 FROM information_schema.tables
                                                   WHERE table_schema='public' AND table_name='user_roles'))
                  THEN 'STOP' ELSE 'OK' END,
         'No conflicting columns on users', 'is_employee / reports_to / backup_approver_id / approval_limit'
  UNION ALL
  SELECT 12, 'INFO', 'Row counts (unchanged by 001)',
         'users=' || (SELECT count(*) FROM public.users) ||
         ', projects=' || (SELECT count(*) FROM public.projects) ||
         ', tasks=' || (SELECT count(*) FROM public.tasks) ||
         ', awards=' || (SELECT count(*) FROM public.awards) ||
         ', contracts=' || (SELECT count(*) FROM public.contracts) ||
         ', email_log=' || (SELECT count(*) FROM public.email_log)
  UNION ALL
  SELECT 13, CASE WHEN EXISTS (SELECT 1 FROM pg_stat_activity
                                WHERE datname = current_database() AND state = 'active'
                                  AND pid <> pg_backend_pid() AND now() - query_start > interval '30 seconds')
                  THEN 'INFO' ELSE 'OK' END,
         'Long-running queries right now (could hold locks)',
         (SELECT count(*) FROM pg_stat_activity
           WHERE datname = current_database() AND state = 'active'
             AND pid <> pg_backend_pid() AND now() - query_start > interval '30 seconds') || ' active > 30 s'
) checks
ORDER BY seq;
