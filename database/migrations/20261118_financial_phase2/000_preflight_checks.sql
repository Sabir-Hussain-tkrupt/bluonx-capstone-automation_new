-- ============================================================================
-- BluOnX Financial Automation — Phase 2 · Module 2
-- 000  PRE-FLIGHT CHECKS (READ-ONLY — changes nothing)
-- ============================================================================
-- Run BEFORE 001_budget_structure.sql. Every row should be OK or INFO.
-- Any STOP must be resolved first.
-- ============================================================================

SELECT * FROM (
  SELECT 1 AS seq,
         CASE WHEN to_regclass('public.budget_lines') IS NOT NULL
               AND to_regclass('public.contingency_ledger') IS NOT NULL
               AND to_regprocedure('public.fn_baseline_project_budget(uuid,uuid)') IS NOT NULL
              THEN 'OK' ELSE 'STOP' END AS status,
         'Phase 1 financial foundation applied' AS check_name,
         COALESCE((SELECT value #>> '{}' FROM public.financial_settings WHERE setting_key = 'schema_version'), 'missing') AS detail
  UNION ALL
  SELECT 2, CASE WHEN to_regclass('public.v_budget_lines') IS NULL THEN 'OK' ELSE 'INFO' END,
         'Phase 2 already applied?',
         CASE WHEN to_regclass('public.v_budget_lines') IS NULL THEN 'no — fresh apply'
              ELSE 'yes — re-running 001 is safe' END
  UNION ALL
  SELECT 3, CASE WHEN to_regclass('public.task_templates') IS NOT NULL THEN 'OK' ELSE 'INFO' END,
         'task_templates table present', 'optional; used for template ↔ task-template links'
  UNION ALL
  SELECT 4, CASE WHEN to_regclass('storage.buckets') IS NOT NULL THEN 'OK' ELSE 'INFO' END,
         'Supabase storage schema present',
         CASE WHEN to_regclass('storage.buckets') IS NULL THEN 'create bucket finance-documents (private) in the dashboard'
              WHEN EXISTS (SELECT 1 FROM storage.buckets WHERE id = 'finance-documents') THEN 'finance-documents already exists'
              ELSE 'finance-documents will be created (private)' END
  UNION ALL
  SELECT 5, 'INFO', 'Budget templates',
         (SELECT count(*) FROM public.budget_templates WHERE deleted_at IS NULL) || ' template(s), '
         || (SELECT count(*) FROM public.budget_templates WHERE is_default AND is_active AND deleted_at IS NULL)
         || ' default — a default is created only if none exists'
  UNION ALL
  SELECT 6, 'INFO', 'Projects with a budget (task sync applies to these only)',
         (SELECT count(*) FROM public.projects WHERE budget_status <> 'none' AND deleted_at IS NULL) || ' of '
         || (SELECT count(*) FROM public.projects WHERE deleted_at IS NULL)
  UNION ALL
  SELECT 7, CASE WHEN EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_tasks_sync_budget_line') THEN 'INFO' ELSE 'OK' END,
         'Task sync trigger', 'trg_tasks_sync_budget_line on tasks'
) c ORDER BY seq;
