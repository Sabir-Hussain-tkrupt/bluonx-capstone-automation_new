-- ============================================================================
-- BluOnX Financial Automation — Phase 1 · Module 1
-- 099  ROLLBACK (removes ONLY what 001 added)
-- ============================================================================
-- ⚠️  DESTRUCTIVE FOR FINANCIAL DATA. Every row in the 19 financial tables and
--     the new columns on users / projects / contracts is permanently deleted.
--     Bid Management data (users, projects, tasks, awards, contracts, emails…)
--     is NOT touched — including bid-system rows the dev seed created (the
--     "Demo · …" projects, their tasks / bid packages / awards / contracts,
--     "Demo Earthworks LLC" and the demo.*@example.test users). Remove those
--     by hand on dev if you want a completely clean slate.
--
-- Use on DEVELOPMENT to start over. On PRODUCTION prefer leaving the unused
-- objects in place (they are harmless) or restoring from backup; run this only
-- after confirming there is no financial data worth keeping.
--
-- Safety latch: the script refuses to run unless you first execute, in the
-- same SQL editor run, the line below (uncomment it):
--
--   SELECT set_config('bluonx.confirm_financial_rollback', 'yes', false);
--
-- ============================================================================

-- SELECT set_config('bluonx.confirm_financial_rollback', 'yes', false);

BEGIN;

DO $$
BEGIN
  IF COALESCE(current_setting('bluonx.confirm_financial_rollback', TRUE), '') <> 'yes' THEN
    RAISE EXCEPTION 'Rollback not confirmed. Uncomment the set_config line at the top of 099 and run again.';
  END IF;
END $$;

SET LOCAL lock_timeout = '5s';

-- 1. Restore the v3.9 auth profile trigger function exactly.
CREATE OR REPLACE FUNCTION public.fn_handle_new_auth_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, email, full_name, role)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data ->> 'full_name', split_part(NEW.email, '@', 1)),
    COALESCE(NEW.raw_user_meta_data ->> 'role', 'project_manager')
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

-- 2. Triggers on existing tables.
DROP TRIGGER IF EXISTS trg_users_sync_base_role        ON public.users;
DROP TRIGGER IF EXISTS trg_projects_guard_budget_total ON public.projects;

-- 3. Procedures first (they return the new tables' row types).
DROP FUNCTION IF EXISTS public.fn_baseline_project_budget(uuid, uuid);
DROP FUNCTION IF EXISTS public.fn_apply_bid_to_line(uuid, uuid, numeric, uuid);
DROP FUNCTION IF EXISTS public.fn_reverse_bid_on_line(uuid, uuid, uuid, text);
DROP FUNCTION IF EXISTS public.fn_lock_budget_line(uuid, uuid, uuid);
DROP FUNCTION IF EXISTS public.fn_create_variance(uuid, text, numeric, uuid, uuid, uuid, date, date);
DROP FUNCTION IF EXISTS public.fn_adjust_variance(uuid, numeric, uuid, text);
DROP FUNCTION IF EXISTS public.fn_request_contingency_top_up(uuid, numeric, text, uuid);
DROP FUNCTION IF EXISTS public.fn_approve_contingency_top_up(uuid, uuid, boolean, numeric, text);
DROP FUNCTION IF EXISTS public.fn_close_accounting_month(date, uuid, text);
DROP FUNCTION IF EXISTS private.fin_move_contingency(uuid, numeric, text, uuid, text, uuid, uuid, uuid, uuid);
DROP FUNCTION IF EXISTS private.fin_lock_project(uuid, boolean, boolean);

-- 4. New tables (children first). No CASCADE, so nothing outside the list can be hit.
DROP TABLE IF EXISTS public.cash_flow_entries;
DROP TABLE IF EXISTS public.company_cash_items;
DROP TABLE IF EXISTS public.accounting_periods;
DROP TABLE IF EXISTS public.finance_handoffs;
DROP TABLE IF EXISTS public.payment_approvals;
DROP TABLE IF EXISTS public.internal_invoices;
DROP TABLE IF EXISTS public.property_taxes;
DROP TABLE IF EXISTS public.escrows;
ALTER TABLE IF EXISTS public.contingency_ledger DROP CONSTRAINT IF EXISTS fk_contingency_ledger_variance;
DROP TABLE IF EXISTS public.contingency_ledger;   -- immutability trigger blocks row DELETE, not DROP
DROP TABLE IF EXISTS public.variance_lines;
DROP TABLE IF EXISTS public.contingency_buckets;
DROP TABLE IF EXISTS public.land_closings;
DROP TABLE IF EXISTS public.budget_lines;
DROP TABLE IF EXISTS public.budget_template_lines;
DROP TABLE IF EXISTS public.budget_templates;
DROP TABLE IF EXISTS public.financial_alerts;
DROP TABLE IF EXISTS public.financial_settings;
DROP TABLE IF EXISTS public.approval_delegations;
DROP TABLE IF EXISTS public.user_roles;

-- 5. Trigger functions and helpers (their triggers went with the tables).
DROP FUNCTION IF EXISTS public.fn_block_contingency_ledger_mutation();
DROP FUNCTION IF EXISTS public.fn_guard_budget_lines();
DROP FUNCTION IF EXISTS public.fn_check_flat_budget_total();
DROP FUNCTION IF EXISTS public.fn_guard_project_budget_total();
DROP FUNCTION IF EXISTS public.fn_guard_contingency_buckets();
DROP FUNCTION IF EXISTS public.fn_guard_variance_lines();
DROP FUNCTION IF EXISTS public.fn_guard_accounting_periods();
DROP FUNCTION IF EXISTS public.fn_guard_cash_flow_closed_period();
DROP FUNCTION IF EXISTS public.fn_sync_user_base_role();
DROP FUNCTION IF EXISTS private.user_has_role(uuid, text);
DROP FUNCTION IF EXISTS private.has_any_role(text[]);
DROP FUNCTION IF EXISTS private.fin_write_authorized();

-- 6. New columns on existing tables (their constraints / indexes go with them).
ALTER TABLE public.users     DROP COLUMN IF EXISTS is_employee,
                             DROP COLUMN IF EXISTS reports_to,
                             DROP COLUMN IF EXISTS backup_approver_id,
                             DROP COLUMN IF EXISTS approval_limit;
ALTER TABLE public.projects  DROP COLUMN IF EXISTS manager_id,
                             DROP COLUMN IF EXISTS field_manager_id,
                             DROP COLUMN IF EXISTS contingency_percent,
                             DROP COLUMN IF EXISTS budget_status,
                             DROP COLUMN IF EXISTS approved_budget_total,
                             DROP COLUMN IF EXISTS budget_baselined_at,
                             DROP COLUMN IF EXISTS budget_baselined_by,
                             DROP COLUMN IF EXISTS contingency_at_groundbreaking,
                             DROP COLUMN IF EXISTS long_tail_reserve_amount,
                             DROP COLUMN IF EXISTS business_entity;
ALTER TABLE public.contracts DROP COLUMN IF EXISTS payment_terms_days,
                             DROP COLUMN IF EXISTS retainage_percent;

-- 7. email_log CHECK back to the v3.9 list, unless financial emails were
--    already logged (then the widened CHECK is kept, so no row is invalid).
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM public.email_log
     WHERE email_type NOT IN ('bid_invitation','bid_reminder','award_notification',
                              'decline_notification','milestone_alert','general')) THEN
    ALTER TABLE public.email_log DROP CONSTRAINT IF EXISTS chk_email_log_email_type;
    ALTER TABLE public.email_log ADD CONSTRAINT email_log_email_type_check
      CHECK (email_type IN ('bid_invitation','bid_reminder','award_notification',
                            'decline_notification','milestone_alert','general'));
  ELSE
    RAISE NOTICE 'Financial email types already logged — keeping the widened email_type CHECK.';
  END IF;
END $$;

-- 8. Schema grant 001 added (authenticated keeps its v3.3 grant).
REVOKE USAGE ON SCHEMA private FROM service_role;

-- 9. Comments 001 added to existing columns.
COMMENT ON COLUMN public.users.role                      IS NULL;
COMMENT ON COLUMN public.email_log.email_type            IS NULL;
COMMENT ON COLUMN public.notifications.notification_type IS NULL;

COMMIT;
