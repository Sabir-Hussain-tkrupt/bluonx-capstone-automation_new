-- ============================================================================
-- BluOnX Financial Automation — Phase 6
-- 002  VERIFY PAYMENT APPROVALS (read-only). Every row must say PASS.
-- ============================================================================
WITH checks AS (
  SELECT 1 AS seq, 'P01 new payment columns' AS check_id,
         (SELECT count(*) = 7 FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'payment_approvals'
             AND column_name IN ('gross_amount', 'work_confirmed_by', 'work_confirmed_at', 'confirmed_by_external',
                                 'executive_required', 'resubmitted_from', 'approved_at')) AS ok
  UNION ALL
  SELECT 2, 'P02 payment history table with RLS',
         COALESCE((SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass('public.payment_approval_events')), FALSE)
  UNION ALL
  SELECT 3, 'P03 procedures exist',
         to_regprocedure('public.fn_request_payment(uuid, uuid, text, numeric, text)') IS NOT NULL
         AND to_regprocedure('public.fn_payment_approval_step(uuid, uuid, text, text, text, uuid, text, boolean)') IS NOT NULL
         AND to_regprocedure('public.fn_reject_payment(uuid, uuid, text)') IS NOT NULL
         AND to_regprocedure('public.fn_resubmit_payment(uuid, uuid, text)') IS NOT NULL
         AND to_regprocedure('public.fn_cancel_payment(uuid, uuid, text)') IS NOT NULL
         AND to_regprocedure('public.fn_mark_finance_handoff(uuid, boolean, uuid, text, text)') IS NOT NULL
  UNION ALL
  SELECT 4, 'P04 views exist',
         to_regclass('public.v_payment_approvals') IS NOT NULL AND to_regclass('public.v_finance_handoffs') IS NOT NULL
  UNION ALL
  SELECT 5, 'P05 history is append-only',
         (SELECT count(*) = 2 FROM pg_trigger WHERE NOT tgisinternal
            AND tgname IN ('trg_payment_approval_events_immutable', 'trg_payment_approval_events_no_truncate'))
  UNION ALL
  SELECT 6, 'P06 two-person constraints still in place',
         (SELECT count(*) = 2 FROM pg_constraint
           WHERE conname IN ('chk_payment_approvals_two_person_manager', 'chk_payment_approvals_two_person_executive'))
  UNION ALL
  SELECT 7, 'P07 procedures only callable by the backend',
         NOT has_function_privilege('authenticated', 'public.fn_payment_approval_step(uuid, uuid, text, text, text, uuid, text, boolean)', 'EXECUTE')
         AND has_function_privilege('service_role', 'public.fn_payment_approval_step(uuid, uuid, text, text, text, uuid, text, boolean)', 'EXECUTE')
         AND has_function_privilege('service_role', 'public.fn_mark_finance_handoff(uuid, boolean, uuid, text, text)', 'EXECUTE')
  UNION ALL
  SELECT 8, 'P08 settings exist',
         (SELECT count(*) = 5 FROM public.financial_settings
           WHERE setting_key IN ('po_number_format', 'po_number_format_contract', 'quickbooks_expense_account',
                                 'executive_approval_threshold', 'land_team_emails'))
  UNION ALL
  SELECT 9, 'P09 schema version is 4.7.0',
         (SELECT value #>> '{}' LIKE '4.7.0%' FROM public.financial_settings WHERE setting_key = 'schema_version')
)
SELECT seq, check_id, CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS result FROM checks ORDER BY seq;
