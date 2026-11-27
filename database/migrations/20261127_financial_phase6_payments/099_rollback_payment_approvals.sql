-- ============================================================================
-- BluOnX Financial Automation — Phase 6
-- 099  ROLLBACK PAYMENT APPROVALS — DEV ONLY
-- ============================================================================
-- Drops what 001 added. The payment history and the new payment columns are
-- LOST; payment_approvals rows, hand-offs and cash-flow entries are kept.
-- ============================================================================

BEGIN;

DROP VIEW IF EXISTS public.v_payment_approvals;
DROP VIEW IF EXISTS public.v_finance_handoffs;
DROP FUNCTION IF EXISTS public.fn_request_payment(uuid, uuid, text, numeric, text);
DROP FUNCTION IF EXISTS public.fn_payment_approval_step(uuid, uuid, text, text, text, uuid, text, boolean);
DROP FUNCTION IF EXISTS public.fn_reject_payment(uuid, uuid, text);
DROP FUNCTION IF EXISTS public.fn_resubmit_payment(uuid, uuid, text);
DROP FUNCTION IF EXISTS public.fn_cancel_payment(uuid, uuid, text);
DROP FUNCTION IF EXISTS public.fn_mark_finance_handoff(uuid, boolean, uuid, text, text);
DROP FUNCTION IF EXISTS private.fin_payment_event(public.payment_approvals, text, uuid, text, uuid);
DROP FUNCTION IF EXISTS private.fin_rollup_line_approval(uuid);
DROP FUNCTION IF EXISTS private.fin_next_po_number(text);
DROP FUNCTION IF EXISTS private.fin_line_contract(uuid);
DROP FUNCTION IF EXISTS private.fin_effective_limit(uuid);
DROP FUNCTION IF EXISTS private.fin_is_approver(uuid);
DROP TABLE IF EXISTS public.payment_approval_events;
DROP FUNCTION IF EXISTS public.fn_block_payment_event_mutation();

ALTER TABLE public.payment_approvals
  DROP COLUMN IF EXISTS resubmitted_from, DROP COLUMN IF EXISTS gross_amount,
  DROP COLUMN IF EXISTS work_confirmed_by, DROP COLUMN IF EXISTS work_confirmed_at,
  DROP COLUMN IF EXISTS confirmed_by_external, DROP COLUMN IF EXISTS executive_required,
  DROP COLUMN IF EXISTS approved_at;
ALTER TABLE public.finance_handoffs DROP COLUMN IF EXISTS handoff_error;

DELETE FROM public.financial_settings WHERE setting_key IN ('po_number_format_contract', 'quickbooks_expense_account');
UPDATE public.financial_settings
   SET value = '"4.6.0 (20261126_financial_phase5_health)"'::jsonb
 WHERE setting_key = 'schema_version';

COMMIT;
