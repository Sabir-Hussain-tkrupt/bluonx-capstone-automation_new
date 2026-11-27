-- ============================================================================
-- BluOnX Financial Automation — Phase 7
-- 099  ROLLBACK LONG-TAIL ITEMS — DEV ONLY
-- ============================================================================
-- Drops what 001 added: jurisdictions, defects, escrow history and the new
-- columns are LOST. Escrows, property taxes, their budget lines, ledger rows
-- and cash-flow rows are kept (existing 'long_tail' ledger rows stay: the old
-- movement-type rule is added NOT VALID, so it only applies to new rows).
-- ============================================================================

BEGIN;

DROP VIEW IF EXISTS public.v_escrows;
DROP VIEW IF EXISTS public.v_property_taxes;
DROP FUNCTION IF EXISTS public.fn_save_escrow(uuid, uuid, uuid, jsonb);
DROP FUNCTION IF EXISTS public.fn_escrow_transition(uuid, uuid, text, date, text, text);
DROP FUNCTION IF EXISTS public.fn_save_escrow_defect(uuid, uuid, uuid, text, text, numeric, text);
DROP FUNCTION IF EXISTS public.fn_renew_escrow_bond(uuid, uuid, date, numeric);
DROP FUNCTION IF EXISTS public.fn_set_property_tax_year(uuid, uuid, int, uuid, text, numeric, numeric, numeric, numeric, text);
DROP FUNCTION IF EXISTS public.fn_update_property_tax(uuid, uuid, numeric, numeric, date, text, numeric);
DROP FUNCTION IF EXISTS public.fn_set_tax_sold_portion(uuid, uuid, numeric, int);
DROP FUNCTION IF EXISTS private.fin_sync_escrow(uuid, uuid);
DROP FUNCTION IF EXISTS private.fin_sync_tax_line(uuid, uuid);
DROP FUNCTION IF EXISTS private.fin_refresh_long_tail_cash(uuid);
DROP FUNCTION IF EXISTS private.fin_escrow_event(public.escrows, text, uuid, text);
DROP FUNCTION IF EXISTS private.fin_set_long_tail_amount(uuid, numeric, uuid, text);
DROP FUNCTION IF EXISTS private.fin_new_long_tail_line(uuid, text, text, uuid);
DROP FUNCTION IF EXISTS private.fin_can(uuid, text[]);
DROP TABLE IF EXISTS public.escrow_events;
DROP FUNCTION IF EXISTS public.fn_block_escrow_event_mutation();
DROP TABLE IF EXISTS public.escrow_defects;

ALTER TABLE public.escrows
  DROP COLUMN IF EXISTS jurisdiction_id, DROP COLUMN IF EXISTS repair_estimate, DROP COLUMN IF EXISTS premium_frequency,
  DROP COLUMN IF EXISTS premium_total, DROP COLUMN IF EXISTS works_built_date, DROP COLUMN IF EXISTS inspection_date,
  DROP COLUMN IF EXISTS inspection_notes, DROP COLUMN IF EXISTS signoff_date, DROP COLUMN IF EXISTS signoff_by,
  DROP COLUMN IF EXISTS expected_release_date, DROP COLUMN IF EXISTS bond_reminder_sent_for, DROP COLUMN IF EXISTS document_name;
ALTER TABLE public.property_taxes
  DROP COLUMN IF EXISTS jurisdiction_id, DROP COLUMN IF EXISTS assessed_value, DROP COLUMN IF EXISTS tax_rate_percent,
  DROP COLUMN IF EXISTS reminded_days, DROP COLUMN IF EXISTS paid_at;
DROP TABLE IF EXISTS public.jurisdictions;

ALTER TABLE public.contingency_ledger DROP CONSTRAINT IF EXISTS chk_contingency_ledger_movement_type;
ALTER TABLE public.contingency_ledger ADD CONSTRAINT chk_contingency_ledger_movement_type
  CHECK (movement_type IN ('initial_funding', 'bid_overrun', 'bid_savings', 'bid_reversal',
                           'variance_created', 'variance_adjusted', 'variance_cancelled', 'top_up', 'invoice_overage')) NOT VALID;

DELETE FROM public.financial_settings WHERE setting_key = 'bond_renewal_reminder_days';
UPDATE public.financial_settings
   SET value = '"4.7.0 (20261127_financial_phase6_payments)"'::jsonb
 WHERE setting_key = 'schema_version';

-- fn_project_health_inputs keeps its Phase 7 body; it still works without the
-- new columns only if escrows.status / property_taxes exist (they do).
COMMIT;
