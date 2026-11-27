-- ============================================================================
-- BluOnX Financial Automation — Phase 7
-- 002  VERIFY LONG-TAIL ITEMS (read-only). Every row must say PASS.
-- ============================================================================
WITH checks AS (
  SELECT 1 AS seq, 'L01 new tables with RLS' AS check_id,
         (SELECT count(*) = 3 FROM pg_class WHERE relrowsecurity
            AND oid IN (to_regclass('public.jurisdictions'), to_regclass('public.escrow_defects'),
                        to_regclass('public.escrow_events'))) AS ok
  UNION ALL
  SELECT 2, 'L02 new escrow and tax columns',
         (SELECT count(*) = 12 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'escrows'
             AND column_name IN ('jurisdiction_id', 'repair_estimate', 'premium_frequency', 'premium_total',
                                 'works_built_date', 'inspection_date', 'inspection_notes', 'signoff_date', 'signoff_by',
                                 'expected_release_date', 'bond_reminder_sent_for', 'document_name'))
         AND (SELECT count(*) = 5 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'property_taxes'
             AND column_name IN ('jurisdiction_id', 'assessed_value', 'tax_rate_percent', 'reminded_days', 'paid_at'))
  UNION ALL
  SELECT 3, 'L03 procedures exist',
         to_regprocedure('public.fn_save_escrow(uuid, uuid, uuid, jsonb)') IS NOT NULL
         AND to_regprocedure('public.fn_escrow_transition(uuid, uuid, text, date, text, text)') IS NOT NULL
         AND to_regprocedure('public.fn_save_escrow_defect(uuid, uuid, uuid, text, text, numeric, text)') IS NOT NULL
         AND to_regprocedure('public.fn_renew_escrow_bond(uuid, uuid, date, numeric)') IS NOT NULL
         AND to_regprocedure('public.fn_set_property_tax_year(uuid, uuid, integer, uuid, text, numeric, numeric, numeric, numeric, text)') IS NOT NULL
         AND to_regprocedure('public.fn_update_property_tax(uuid, uuid, numeric, numeric, date, text, numeric)') IS NOT NULL
         AND to_regprocedure('public.fn_set_tax_sold_portion(uuid, uuid, numeric, integer)') IS NOT NULL
  UNION ALL
  SELECT 4, 'L04 ledger accepts long-tail movements',
         EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_contingency_ledger_movement_type'
                    AND pg_get_constraintdef(oid) LIKE '%long_tail%')
  UNION ALL
  SELECT 5, 'L05 views exist', to_regclass('public.v_escrows') IS NOT NULL AND to_regclass('public.v_property_taxes') IS NOT NULL
  UNION ALL
  SELECT 6, 'L06 procedures only callable by the backend',
         NOT has_function_privilege('authenticated', 'public.fn_save_escrow(uuid, uuid, uuid, jsonb)', 'EXECUTE')
         AND has_function_privilege('service_role', 'public.fn_save_escrow(uuid, uuid, uuid, jsonb)', 'EXECUTE')
  UNION ALL
  SELECT 7, 'L07 baselined budgets are still flat',
         NOT EXISTS (SELECT 1 FROM public.projects p
                      WHERE p.budget_status = 'baselined' AND p.deleted_at IS NULL
                        AND p.approved_budget_total <> (SELECT COALESCE(SUM(b.budget_amount), 0) FROM public.budget_lines b
                                                         WHERE b.project_id = p.id AND b.deleted_at IS NULL))
  UNION ALL
  SELECT 8, 'L08 schema version is 4.8.0',
         (SELECT value #>> '{}' LIKE '4.8.0%' FROM public.financial_settings WHERE setting_key = 'schema_version')
)
SELECT seq, check_id, CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS result FROM checks ORDER BY seq;
