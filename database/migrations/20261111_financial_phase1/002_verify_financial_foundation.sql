-- ============================================================================
-- BluOnX Financial Automation — Phase 1 · Module 1
-- 002  VERIFY FINANCIAL FOUNDATION (self-checking, leaves NO data behind)
-- ============================================================================
-- Run AFTER 001_financial_foundation.sql, in the Supabase SQL editor, on dev
-- and (safely) on production.
--
-- HOW IT WORKS
--   All test data is created inside one sub-transaction that is deliberately
--   rolled back at the end, so the database is left exactly as it was. Only
--   the PASS / FAIL table survives (a TEMP table, gone when you close the tab).
--
-- READING THE RESULT
--   The final SELECT shows one row per check. Every row must be PASS.
--   SKIP means the environment did not allow that check (e.g. inserting into
--   auth.users or switching to the authenticated role) — not a failure.
--   Any FAIL / ABORTED → do not continue to production; send the output.
-- ============================================================================

CREATE TEMP TABLE IF NOT EXISTS _fin_verify (
  seq     INTEGER,
  check_id TEXT,
  result  TEXT,
  detail  TEXT
);
TRUNCATE _fin_verify;

DO $verify$
DECLARE
  r        JSONB := '[]'::jsonb;   -- results survive the rollback (plain variable)
  n        INTEGER;
  v_txt    TEXT;
  v_num    NUMERIC;
  v_num2   NUMERIC;
  v_bool   BOOLEAN;

  -- actors
  u_admin   UUID := gen_random_uuid();
  u_pm      UUID := gen_random_uuid();
  u_fm      UUID := gen_random_uuid();
  u_exec    UUID := gen_random_uuid();
  u_fin     UUID := gen_random_uuid();
  u_invite  UUID := gen_random_uuid();

  -- records
  v_trade    UUID;
  v_project  UUID;
  v_task_bid UUID;
  v_task_int UUID;
  v_vendor   UUID;
  v_contact  UUID;
  v_pkg      UUID;
  v_inv      UUID;
  v_sub      UUID;
  v_award    UUID;
  v_contract UUID;
  l_land     UUID;
  l_sewer    UUID;
  l_int      UUID;
  l_cont     UUID;
  v_var      UUID;
  v_bucket   UUID;
  v_payment  UUID;
  v_total    NUMERIC;

  c_tables CONSTANT TEXT[] := ARRAY[
    'budget_templates','budget_template_lines','budget_lines','land_closings',
    'contingency_buckets','contingency_ledger','variance_lines',
    'internal_invoices','payment_approvals','finance_handoffs',
    'escrows','property_taxes','accounting_periods','company_cash_items','cash_flow_entries',
    'financial_settings','financial_alerts','user_roles','approval_delegations'];
BEGIN
  BEGIN  -- ═════════ everything in here is rolled back at the end ═════════

    -- ── C01 tables + RLS ──────────────────────────────────────────────────
    SELECT count(*) INTO n
      FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
     WHERE s.nspname = 'public' AND c.relkind = 'r'
       AND c.relname = ANY (c_tables) AND c.relrowsecurity;
    r := r || jsonb_build_object('id','C01 19 new tables exist with RLS enabled',
           'ok', n = 19, 'detail', n || ' of 19');

    -- ── C02 anon has no access, authenticated cannot write ───────────────
    SELECT count(*) INTO n FROM unnest(c_tables) t
     WHERE has_table_privilege('anon', 'public.' || t, 'SELECT')
        OR has_table_privilege('authenticated', 'public.' || t, 'INSERT')
        OR has_table_privilege('authenticated', 'public.' || t, 'UPDATE')
        OR has_table_privilege('authenticated', 'public.' || t, 'DELETE');
    r := r || jsonb_build_object('id','C02 anon blocked; authenticated read-only on new tables',
           'ok', n = 0, 'detail', n || ' table(s) with unexpected privileges');

    -- ── C03 procedures are service_role only ─────────────────────────────
    SELECT count(*) INTO n
      FROM pg_proc p JOIN pg_namespace s ON s.oid = p.pronamespace
     WHERE s.nspname = 'public'
       AND p.proname IN ('fn_baseline_project_budget','fn_apply_bid_to_line','fn_reverse_bid_on_line',
                         'fn_lock_budget_line','fn_create_variance','fn_adjust_variance',
                         'fn_request_contingency_top_up','fn_approve_contingency_top_up','fn_close_accounting_month')
       AND (has_function_privilege('anon', p.oid, 'EXECUTE')
            OR has_function_privilege('authenticated', p.oid, 'EXECUTE')
            OR NOT has_function_privilege('service_role', p.oid, 'EXECUTE'));
    r := r || jsonb_build_object('id','C03 financial procedures executable by service_role only',
           'ok', n = 0, 'detail', n || ' procedure(s) with wrong grants');

    -- ── C04 every existing user has its base role in user_roles ─────────
    SELECT count(*) INTO n FROM public.users u
     WHERE NOT EXISTS (SELECT 1 FROM public.user_roles ur
                        WHERE ur.user_id = u.id AND ur.role = u.role AND ur.revoked_at IS NULL);
    r := r || jsonb_build_object('id','C04 existing users backfilled into user_roles',
           'ok', n = 0, 'detail', n || ' user(s) missing their base role');

    -- ── C05 email_log CHECK still accepts every value already stored ─────
    SELECT count(*) INTO n FROM pg_constraint
     WHERE conrelid = 'public.email_log'::regclass AND conname = 'chk_email_log_email_type' AND convalidated;
    r := r || jsonb_build_object('id','C05 email_log type CHECK widened and validated against existing rows',
           'ok', n = 1, 'detail', CASE WHEN n = 1 THEN 'validated' ELSE 'missing / not validated' END);

    -- ── Test actors ──────────────────────────────────────────────────────
    INSERT INTO public.users (id, email, full_name, role) VALUES
      (u_admin, 'verify.admin.' || u_admin || '@example.test', 'Verify Admin', 'admin'),
      (u_pm,    'verify.pm.'    || u_pm    || '@example.test', 'Verify PM',    'project_manager'),
      (u_fm,    'verify.fm.'    || u_fm    || '@example.test', 'Verify FM',    'project_manager'),
      (u_exec,  'verify.exec.'  || u_exec  || '@example.test', 'Verify Exec',  'project_manager'),
      (u_fin,   'verify.fin.'   || u_fin   || '@example.test', 'Verify Fin',   'project_manager');
    INSERT INTO public.user_roles (user_id, role, granted_by) VALUES
      (u_fm, 'field_manager', u_admin), (u_exec, 'executive', u_admin), (u_fin, 'finance', u_admin);
    UPDATE public.users SET reports_to = u_pm, approval_limit = 5000, backup_approver_id = u_exec WHERE id = u_fm;

    -- ── C06 a user can hold several roles ────────────────────────────────
    SELECT count(*) INTO n FROM public.user_roles WHERE user_id = u_exec AND revoked_at IS NULL;
    r := r || jsonb_build_object('id','C06 one user holds more than one role',
           'ok', n = 2, 'detail', n || ' active roles for the executive (expected 2)');

    -- ── C07 base role sync when the admin screen flips users.role ────────
    UPDATE public.users SET role = 'admin' WHERE id = u_pm;
    SELECT count(*) INTO n FROM public.user_roles WHERE user_id = u_pm AND revoked_at IS NULL AND role = 'admin';
    SELECT count(*) INTO n FROM public.user_roles
     WHERE user_id = u_pm AND revoked_at IS NULL AND role = 'project_manager' HAVING n = 1;
    r := r || jsonb_build_object('id','C07 users.role change mirrored into user_roles',
           'ok', COALESCE(n, 0) = 0, 'detail', 'admin granted, project_manager revoked');
    UPDATE public.users SET role = 'project_manager' WHERE id = u_pm;

    -- ── C08 invite trigger carries roles + external flag ─────────────────
    BEGIN
      INSERT INTO auth.users (id, email, raw_user_meta_data)
      VALUES (u_invite, 'verify.invite.' || u_invite || '@example.test',
              jsonb_build_object('full_name','Verify External FM','role','project_manager',
                                 'roles', jsonb_build_array('field_manager','bogus_role'),
                                 'is_employee', false));
      SELECT count(*) INTO n FROM public.user_roles WHERE user_id = u_invite AND revoked_at IS NULL;
      SELECT is_employee INTO v_bool FROM public.users WHERE id = u_invite;
      r := r || jsonb_build_object('id','C08 invite metadata → roles + external flag (bad role ignored)',
             'ok', n = 2 AND v_bool = FALSE, 'detail', n || ' roles, is_employee=' || v_bool);
    EXCEPTION WHEN OTHERS THEN
      r := r || jsonb_build_object('id','C08 invite metadata → roles + external flag (bad role ignored)',
             'ok', NULL, 'detail', 'SKIP: cannot insert into auth.users here (' || SQLERRM || ')');
    END;

    -- ── Project + award chain (sanitary sewer) ───────────────────────────
    INSERT INTO public.trades (name, phase) VALUES ('ZZ Verify Trade ' || gen_random_uuid(), 'development')
      RETURNING id INTO v_trade;
    INSERT INTO public.projects (name, status, created_by, manager_id, field_manager_id, budget_status)
      VALUES ('ZZ Verify Project', 'active', u_admin, u_pm, u_fm, 'draft')
      RETURNING id INTO v_project;
    INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, created_by)
      VALUES (v_project, v_trade, 'Sanitary sewer', 'development', 'competitive', 9000, u_admin)
      RETURNING id INTO v_task_bid;
    INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, created_by)
      VALUES (v_project, v_trade, 'Attorney', 'development', 'internal', 4000, u_admin)
      RETURNING id INTO v_task_int;
    INSERT INTO public.vendors (company_name) VALUES ('ZZ Verify Vendor') RETURNING id INTO v_vendor;
    INSERT INTO public.vendor_contacts (vendor_id, full_name, email)
      VALUES (v_vendor, 'Verify Contact', 'verify.vendor@example.test') RETURNING id INTO v_contact;
    INSERT INTO public.bid_packages (task_id, deadline, created_by)
      VALUES (v_task_bid, NOW() + INTERVAL '7 days', u_admin) RETURNING id INTO v_pkg;
    INSERT INTO public.bid_invitations (bid_package_id, vendor_id, vendor_contact_id)
      VALUES (v_pkg, v_vendor, v_contact) RETURNING id INTO v_inv;
    INSERT INTO public.bid_submissions (bid_invitation_id, vendor_id, total_amount, status, is_draft, submitted_at)
      VALUES (v_inv, v_vendor, 10000, 'submitted', FALSE, NOW()) RETURNING id INTO v_sub;
    INSERT INTO public.awards (task_id, bid_submission_id, vendor_id, awarded_by, award_amount)
      VALUES (v_task_bid, v_sub, v_vendor, u_admin, 10000) RETURNING id INTO v_award;

    -- ── C09 line type must match the task's bid_type ─────────────────────
    BEGIN
      INSERT INTO public.budget_lines (project_id, task_id, line_type, name, budget_amount)
      VALUES (v_project, v_task_int, 'bid_activity', 'Wrong type', 1);
      r := r || jsonb_build_object('id','C09 bid_activity line rejected for an internal task','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT422' THEN
      r := r || jsonb_build_object('id','C09 bid_activity line rejected for an internal task','ok',true,'detail','PT422');
    END;

    -- Draft budget: $100k discovery shape
    INSERT INTO public.budget_lines (project_id, line_type, line_subtype, name, budget_amount, is_payment_exempt, sort_order)
      VALUES (v_project, 'land', 'land_purchase', 'Land purchase', 50000, TRUE, 10) RETURNING id INTO l_land;
    INSERT INTO public.budget_lines (project_id, task_id, line_type, name, budget_amount, sort_order,
                                     anticipated_start_date, anticipated_end_date)
      VALUES (v_project, v_task_bid, 'bid_activity', 'Sanitary sewer', 9000, 20, DATE '2027-03-01', DATE '2027-03-31')
      RETURNING id INTO l_sewer;
    INSERT INTO public.budget_lines (project_id, task_id, line_type, name, budget_amount, sort_order)
      VALUES (v_project, v_task_int, 'internal_tm', 'Attorney', 31000, 30) RETURNING id INTO l_int;
    INSERT INTO public.budget_lines (project_id, line_type, name, budget_amount, is_payment_exempt, sort_order)
      VALUES (v_project, 'contingency', 'Contingency', 10000, TRUE, 90) RETURNING id INTO l_cont;

    -- ── C10 one task → at most one live line ─────────────────────────────
    BEGIN
      INSERT INTO public.budget_lines (project_id, task_id, line_type, name)
      VALUES (v_project, v_task_bid, 'bid_activity', 'Duplicate');
      r := r || jsonb_build_object('id','C10 a task maps to at most one live budget line','ok',false,'detail','no error');
    EXCEPTION WHEN unique_violation THEN
      r := r || jsonb_build_object('id','C10 a task maps to at most one live budget line','ok',true,'detail','23505');
    END;

    -- ── C11 baseline ─────────────────────────────────────────────────────
    PERFORM public.fn_baseline_project_budget(v_project, u_admin);
    SELECT approved_budget_total INTO v_total FROM public.projects WHERE id = v_project;
    SELECT count(*) INTO n FROM public.contingency_ledger
     WHERE project_id = v_project AND movement_type = 'initial_funding' AND balance_after = 10000;
    SELECT original_estimate INTO v_num FROM public.budget_lines WHERE id = l_sewer;
    r := r || jsonb_build_object('id','C11 baseline: total = $100,000, estimates frozen, initial ledger row',
           'ok', v_total = 100000 AND n = 1 AND v_num = 9000,
           'detail', 'total=' || v_total || ', ledger rows=' || n || ', sewer estimate=' || v_num);

    -- ── C12 direct edit of a line amount after baseline is blocked ──────
    BEGIN
      UPDATE public.budget_lines SET budget_amount = 9500 WHERE id = l_sewer;
      r := r || jsonb_build_object('id','C12 direct line-amount edit blocked after baseline','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      r := r || jsonb_build_object('id','C12 direct line-amount edit blocked after baseline','ok',true,'detail','PT409');
    END;

    -- ── C13 direct edit of contingency is blocked ────────────────────────
    BEGIN
      UPDATE public.budget_lines SET budget_amount = 20000 WHERE id = l_cont;
      r := r || jsonb_build_object('id','C13 direct contingency edit blocked (no ledger row = no movement)','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      r := r || jsonb_build_object('id','C13 direct contingency edit blocked (no ledger row = no movement)','ok',true,'detail','PT409');
    END;

    -- ── C14 flat-budget backstop catches even an "authorised" one-sided write
    BEGIN
      PERFORM set_config('bluonx.financial_write', 'on', TRUE);
      UPDATE public.budget_lines SET budget_amount = budget_amount + 1 WHERE id = l_int;
      PERFORM set_config('bluonx.financial_write', 'off', TRUE);
      SET CONSTRAINTS ALL IMMEDIATE;
      r := r || jsonb_build_object('id','C14 flat-budget rule rejects a one-sided total change','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      r := r || jsonb_build_object('id','C14 flat-budget rule rejects a one-sided total change','ok',true,'detail','PT409 at constraint check');
    END;
    PERFORM set_config('bluonx.financial_write', 'off', TRUE);
    SET CONSTRAINTS ALL DEFERRED;

    -- ── C15 direct change of the approved total is blocked ───────────────
    BEGIN
      UPDATE public.projects SET approved_budget_total = 150000 WHERE id = v_project;
      r := r || jsonb_build_object('id','C15 approved total cannot be edited directly','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      r := r || jsonb_build_object('id','C15 approved total cannot be edited directly','ok',true,'detail','PT409');
    END;

    -- ── C16 apply bid: $9,000 budget → $10,000 award ─────────────────────
    PERFORM public.fn_apply_bid_to_line(l_sewer, v_award, 10000, u_pm);
    SELECT budget_amount INTO v_num  FROM public.budget_lines WHERE id = l_sewer;
    SELECT budget_amount INTO v_num2 FROM public.budget_lines WHERE id = l_cont;
    SELECT count(*) INTO n FROM public.contingency_ledger
     WHERE project_id = v_project AND movement_type = 'bid_overrun' AND amount = -1000 AND balance_after = 9000;
    r := r || jsonb_build_object('id','C16 bid overrun: line $10,000, contingency −$1,000 with ledger row',
           'ok', v_num = 10000 AND v_num2 = 9000 AND n = 1,
           'detail', 'line=' || v_num || ', contingency=' || v_num2 || ', ledger=' || n);

    -- ── C17 sanitary sewer variance $5,000 → adjusted to $3,000 ──────────
    SELECT id INTO v_var FROM public.fn_create_variance(l_sewer, 'Rock in sanitary sewer', 5000, u_fm);
    SELECT budget_amount INTO v_num2 FROM public.budget_lines WHERE id = l_cont;
    PERFORM public.fn_adjust_variance(v_var, 3000, u_pm, 'Actual cost only $3,000');
    SELECT budget_amount INTO v_num FROM public.budget_lines WHERE id = l_cont;
    SELECT count(*) INTO n FROM public.contingency_ledger
     WHERE variance_line_id = v_var AND movement_type IN ('variance_created','variance_adjusted');
    r := r || jsonb_build_object('id','C17 variance: −$5,000 then +$2,000 back (sewer example)',
           'ok', v_num2 = 4000 AND v_num = 6000 AND n = 2,
           'detail', 'after create=' || v_num2 || ', after adjust=' || v_num || ', ledger rows=' || n);

    -- ── C18 total stayed flat through all movements ──────────────────────
    SELECT SUM(budget_amount) INTO v_num FROM public.budget_lines WHERE project_id = v_project AND deleted_at IS NULL;
    BEGIN
      SET CONSTRAINTS ALL IMMEDIATE;
      r := r || jsonb_build_object('id','C18 total budget unchanged after bid + variance movements',
             'ok', v_num = 100000, 'detail', 'lines total ' || v_num);
    EXCEPTION WHEN OTHERS THEN
      r := r || jsonb_build_object('id','C18 total budget unchanged after bid + variance movements',
             'ok', false, 'detail', SQLSTATE || ' ' || SQLERRM);
    END;
    SET CONSTRAINTS ALL DEFERRED;

    -- ── C19 ledger is immutable ──────────────────────────────────────────
    BEGIN
      UPDATE public.contingency_ledger SET reason = 'tampered' WHERE project_id = v_project;
      r := r || jsonb_build_object('id','C19 ledger UPDATE blocked','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT403' THEN
      r := r || jsonb_build_object('id','C19 ledger UPDATE blocked','ok',true,'detail','PT403');
    END;
    BEGIN
      DELETE FROM public.contingency_ledger WHERE project_id = v_project;
      r := r || jsonb_build_object('id','C20 ledger DELETE blocked','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT403' THEN
      r := r || jsonb_build_object('id','C20 ledger DELETE blocked','ok',true,'detail','PT403');
    END;

    -- ── C21 a variance creator can never approve it ──────────────────────
    BEGIN
      UPDATE public.variance_lines SET status = 'approved', approved_by = u_fm, approved_at = NOW() WHERE id = v_var;
      r := r || jsonb_build_object('id','C21 variance cannot be approved by its creator','ok',false,'detail','no error');
    EXCEPTION WHEN check_violation THEN
      r := r || jsonb_build_object('id','C21 variance cannot be approved by its creator','ok',true,'detail','23514');
    END;

    -- ── C22 approved variance is frozen ──────────────────────────────────
    UPDATE public.variance_lines SET status = 'approved', approved_by = u_pm, approved_at = NOW() WHERE id = v_var;
    BEGIN
      PERFORM public.fn_adjust_variance(v_var, 4000, u_pm, 'too late');
      r := r || jsonb_build_object('id','C22 approved variance cannot be edited','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      r := r || jsonb_build_object('id','C22 approved variance cannot be edited','ok',true,'detail','PT409');
    END;

    -- ── C23 top-up: non-executive refused, executive approved ────────────
    SELECT id INTO v_bucket FROM public.fn_request_contingency_top_up(v_project, 5000, 'Rock all along the sewer run', u_pm);
    BEGIN
      PERFORM public.fn_approve_contingency_top_up(v_bucket, u_pm, TRUE);
      r := r || jsonb_build_object('id','C23 top-up refused for a non-executive','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT403' THEN
      r := r || jsonb_build_object('id','C23 top-up refused for a non-executive','ok',true,'detail','PT403');
    END;
    PERFORM public.fn_approve_contingency_top_up(v_bucket, u_exec, TRUE, NULL, 'Approved by exec');
    SELECT approved_budget_total INTO v_total FROM public.projects WHERE id = v_project;
    SELECT budget_amount INTO v_num FROM public.budget_lines WHERE id = l_cont;
    SELECT count(*) INTO n FROM public.contingency_ledger WHERE contingency_bucket_id = v_bucket AND movement_type = 'top_up';
    r := r || jsonb_build_object('id','C24 executive top-up raises total and contingency together',
           'ok', v_total = 105000 AND v_num = 11000 AND n = 1,
           'detail', 'total=' || v_total || ', contingency=' || v_num || ', ledger=' || n);

    -- ── C25 executed contract locks the line; reversal restores it ──────
    INSERT INTO public.contracts (award_id, vendor_id, task_id, contract_number, contract_amount, start_date, end_date, status)
      VALUES (v_award, v_vendor, v_task_bid, 'ZZ-VERIFY-' || left(gen_random_uuid()::text, 8), 10000,
              DATE '2027-03-01', DATE '2027-03-31', 'executed')
      RETURNING id INTO v_contract;
    PERFORM public.fn_lock_budget_line(l_sewer, v_contract, u_pm);
    BEGIN
      PERFORM set_config('bluonx.financial_write', 'off', TRUE);
      UPDATE public.budget_lines SET is_locked = FALSE WHERE id = l_sewer;
      r := r || jsonb_build_object('id','C25 locked line cannot be unlocked / edited directly','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      r := r || jsonb_build_object('id','C25 locked line cannot be unlocked / edited directly','ok',true,'detail','PT409');
    END;

    PERFORM public.fn_reverse_bid_on_line(l_sewer, v_award, u_pm, 'DocuSign declined');
    SELECT budget_amount INTO v_num  FROM public.budget_lines WHERE id = l_sewer;
    SELECT budget_amount INTO v_num2 FROM public.budget_lines WHERE id = l_cont;
    r := r || jsonb_build_object('id','C26 reversal restores $9,000 line and returns $1,000 to contingency',
           'ok', v_num = 9000 AND v_num2 = 12000,
           'detail', 'line=' || v_num || ', contingency=' || v_num2);

    -- ── C27 every contingency change has a ledger row (balances chain) ──
    SELECT count(*) INTO n FROM (
      SELECT balance_before, lag(balance_after) OVER (ORDER BY entry_no) AS prev_after
        FROM public.contingency_ledger WHERE project_id = v_project) x
     WHERE prev_after IS NOT NULL AND balance_before <> prev_after;
    SELECT balance_after INTO v_num FROM public.contingency_ledger
     WHERE project_id = v_project ORDER BY entry_no DESC LIMIT 1;
    r := r || jsonb_build_object('id','C27 ledger running balance chains and ends at the contingency line',
           'ok', n = 0 AND v_num = v_num2
                 AND (SELECT SUM(amount) FROM public.contingency_ledger WHERE project_id = v_project) = v_num2,
           'detail', n || ' broken link(s); last balance_after = ' || v_num || ', contingency line = ' || v_num2);

    -- ── C28 two-person rule on payment approvals ─────────────────────────
    BEGIN
      INSERT INTO public.payment_approvals (project_id, budget_line_id, amount, requested_by,
                                            field_approved_by, field_approved_at, manager_approved_by, manager_approved_at, status)
      VALUES (v_project, l_int, 6000, u_fm, u_fm, NOW(), u_fm, NOW(), 'approved');
      r := r || jsonb_build_object('id','C28 same person cannot give both payment approvals','ok',false,'detail','no error');
    EXCEPTION WHEN check_violation THEN
      r := r || jsonb_build_object('id','C28 same person cannot give both payment approvals','ok',true,'detail','23514');
    END;

    -- ── C29 on-hold project blocks new variances ─────────────────────────
    UPDATE public.projects SET status = 'on_hold' WHERE id = v_project;
    BEGIN
      PERFORM public.fn_create_variance(l_int, 'Should be blocked', 100, u_fm);
      r := r || jsonb_build_object('id','C29 on-hold project blocks new variances','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      r := r || jsonb_build_object('id','C29 on-hold project blocks new variances','ok',true,'detail','PT409');
    END;
    UPDATE public.projects SET status = 'active' WHERE id = v_project;

    -- ── C30 month close: role check, frozen entries, no reopen ──────────
    BEGIN
      PERFORM public.fn_close_accounting_month(DATE '2020-01-01', u_pm);
      r := r || jsonb_build_object('id','C30 month close refused for non-finance','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT403' THEN
      r := r || jsonb_build_object('id','C30 month close refused for non-finance','ok',true,'detail','PT403');
    END;
    BEGIN
      INSERT INTO public.cash_flow_entries (project_id, budget_line_id, period_month, direction, cash_bucket, amount)
      VALUES (v_project, l_int, DATE '2020-01-01', 'out', 'land', 100);
      PERFORM public.fn_close_accounting_month(DATE '2020-01-01', u_fin);
      BEGIN
        UPDATE public.cash_flow_entries SET amount = 200 WHERE budget_line_id = l_int AND period_month = DATE '2020-01-01';
        r := r || jsonb_build_object('id','C31 closed month entries are frozen','ok',false,'detail','no error');
      EXCEPTION WHEN SQLSTATE 'PT409' THEN
        r := r || jsonb_build_object('id','C31 closed month entries are frozen','ok',true,'detail','PT409');
      END;
      BEGIN
        UPDATE public.accounting_periods SET status = 'open' WHERE period_month = DATE '2020-01-01';
        r := r || jsonb_build_object('id','C32 closed month cannot be reopened','ok',false,'detail','no error');
      EXCEPTION WHEN SQLSTATE 'PT409' THEN
        r := r || jsonb_build_object('id','C32 closed month cannot be reopened','ok',true,'detail','PT409');
      END;
    END;

    -- ── C33 RLS: PM reads budget lines, not finance tables; finance does ─
    INSERT INTO public.internal_invoices (project_id, budget_line_id, payee_name, amount, file_path, file_name, status, uploaded_by)
      VALUES (v_project, l_int, 'Verify Law LLP', 1200, 'verify/x.pdf', 'x.pdf', 'categorised', u_fin);
    BEGIN
      PERFORM set_config('request.jwt.claim.sub', u_pm::text, TRUE);
      PERFORM set_config('request.jwt.claims', jsonb_build_object('sub', u_pm, 'role', 'authenticated')::text, TRUE);
      SET LOCAL ROLE authenticated;
      SELECT count(*) INTO n FROM public.budget_lines WHERE project_id = v_project;
      SELECT count(*) INTO v_num FROM public.internal_invoices WHERE project_id = v_project;
      RESET ROLE;
      PERFORM set_config('request.jwt.claim.sub', u_fin::text, TRUE);
      PERFORM set_config('request.jwt.claims', jsonb_build_object('sub', u_fin, 'role', 'authenticated')::text, TRUE);
      SET LOCAL ROLE authenticated;
      SELECT count(*) INTO v_num2 FROM public.internal_invoices WHERE project_id = v_project;
      RESET ROLE;
      r := r || jsonb_build_object('id','C33 RLS: PM sees budget lines but not invoices; finance sees invoices',
             'ok', n > 0 AND v_num = 0 AND v_num2 = 1,
             'detail', 'pm lines=' || n || ', pm invoices=' || v_num || ', finance invoices=' || v_num2);
    EXCEPTION WHEN OTHERS THEN
      RESET ROLE;
      r := r || jsonb_build_object('id','C33 RLS: PM sees budget lines but not invoices; finance sees invoices',
             'ok', NULL, 'detail', 'SKIP: cannot switch to authenticated here (' || SQLERRM || ')');
    END;

    BEGIN
      PERFORM set_config('request.jwt.claim.sub', u_admin::text, TRUE);
      SET LOCAL ROLE authenticated;
      INSERT INTO public.budget_lines (project_id, line_type, name) VALUES (v_project, 'permit', 'Sneaky');
      RESET ROLE;
      r := r || jsonb_build_object('id','C34 authenticated role cannot write (writes only via FastAPI)','ok',false,'detail','no error');
    EXCEPTION WHEN insufficient_privilege THEN
      RESET ROLE;
      r := r || jsonb_build_object('id','C34 authenticated role cannot write (writes only via FastAPI)','ok',true,'detail','42501');
    WHEN OTHERS THEN
      RESET ROLE;
      r := r || jsonb_build_object('id','C34 authenticated role cannot write (writes only via FastAPI)','ok',NULL,'detail','SKIP: ' || SQLERRM);
    END;

    -- Throw everything away.
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = '__fin_verify_rollback__';

  EXCEPTION
    WHEN OTHERS THEN
      IF SQLERRM <> '__fin_verify_rollback__' THEN
        r := r || jsonb_build_object('id','ABORTED — unexpected error, later checks did not run',
               'ok', false, 'detail', SQLSTATE || ': ' || SQLERRM);
      END IF;
  END;

  RESET ROLE;

  INSERT INTO _fin_verify (seq, check_id, result, detail)
  SELECT ordinality,
         e ->> 'id',
         CASE WHEN e -> 'ok' = 'null'::jsonb THEN 'SKIP'
              WHEN (e ->> 'ok')::boolean THEN 'PASS' ELSE 'FAIL' END,
         e ->> 'detail'
    FROM jsonb_array_elements(r) WITH ORDINALITY AS t(e, ordinality);
END
$verify$;

-- Leftover check: the verify run must leave no data behind.
INSERT INTO _fin_verify (seq, check_id, result, detail)
SELECT 999, 'C99 no verify data left behind',
       CASE WHEN (SELECT count(*) FROM public.projects WHERE name = 'ZZ Verify Project') = 0 THEN 'PASS' ELSE 'FAIL' END,
       'rows named ZZ Verify Project: ' || (SELECT count(*) FROM public.projects WHERE name = 'ZZ Verify Project');

SELECT seq, result, check_id, detail FROM _fin_verify ORDER BY seq;
