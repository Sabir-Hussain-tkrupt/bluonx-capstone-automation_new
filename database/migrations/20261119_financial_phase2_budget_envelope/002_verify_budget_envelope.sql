-- ============================================================================
-- BluOnX Financial Automation — Phase 2 patch
-- 002  VERIFY BUDGET ENVELOPE (self-checking, leaves NO data behind)
-- ============================================================================
-- Run AFTER 001_budget_envelope.sql. Safe on production (rolls back).
-- Every row must say PASS.
-- ============================================================================

CREATE TEMP TABLE IF NOT EXISTS _fin_verify3 (seq INTEGER, check_id TEXT, result TEXT, detail TEXT);
TRUNCATE _fin_verify3;

DO $verify$
DECLARE
  r        JSONB := '[]'::jsonb;
  n        INTEGER;
  v_num    NUMERIC;
  v_num2   NUMERIC;
  v_txt    TEXT;
  s        RECORD;
  u        UUID := gen_random_uuid();
  v_trade  UUID;
  p        UUID;
  p2       UUID;
  t_clear  UUID;
  t_grade  UUID;
  t_sewer  UUID;
  v_vendor UUID;
  v_contact UUID;
  v_award  UUID;
  l_sewer  UUID;

  -- award chain helper values
  v_pkg UUID; v_inv UUID; v_sub UUID;
BEGIN
  BEGIN
    INSERT INTO public.users (id, email, full_name, role) VALUES (u, 'v3.' || u || '@example.test', 'V3 Admin', 'admin');
    INSERT INTO public.trades (name, phase) VALUES ('ZZ V3 Trade ' || gen_random_uuid(), 'development') RETURNING id INTO v_trade;
    INSERT INTO public.vendors (company_name) VALUES ('ZZ V3 Vendor') RETURNING id INTO v_vendor;
    INSERT INTO public.vendor_contacts (vendor_id, full_name, email) VALUES (v_vendor, 'C', 'c3@example.test') RETURNING id INTO v_contact;

    -- Project with a $500,000 Budget value
    INSERT INTO public.projects (name, status, budget, created_by) VALUES ('ZZ V3 Project', 'active', 500000, u) RETURNING id INTO p;
    INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
      VALUES (p, v_trade, 'Clearing', 'development', 'competitive', 20000, 1, u) RETURNING id INTO t_clear;
    INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
      VALUES (p, v_trade, 'Grading', 'development', 'competitive', 30000, 2, u) RETURNING id INTO t_grade;
    INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
      VALUES (p, v_trade, 'Sanitary sewer', 'development', 'competitive', 9000, 3, u) RETURNING id INTO t_sewer;
    INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
      VALUES (p, v_trade, 'Attorney', 'development', 'internal', 3000, 4, u);

    -- Clearing: awarded $22,000 and contract executed. Grading: awarded $28,000, not signed yet.
    INSERT INTO public.bid_packages (task_id, deadline, created_by) VALUES (t_clear, NOW() + INTERVAL '1 day', u) RETURNING id INTO v_pkg;
    INSERT INTO public.bid_invitations (bid_package_id, vendor_id, vendor_contact_id) VALUES (v_pkg, v_vendor, v_contact) RETURNING id INTO v_inv;
    INSERT INTO public.bid_submissions (bid_invitation_id, vendor_id, total_amount, status, is_draft) VALUES (v_inv, v_vendor, 22000, 'submitted', FALSE) RETURNING id INTO v_sub;
    INSERT INTO public.awards (task_id, bid_submission_id, vendor_id, awarded_by, award_amount, status)
      VALUES (t_clear, v_sub, v_vendor, u, 22000, 'accepted') RETURNING id INTO v_award;
    INSERT INTO public.contracts (award_id, vendor_id, task_id, contract_number, contract_amount, start_date, end_date, status)
      VALUES (v_award, v_vendor, t_clear, 'ZZ-V3-' || left(gen_random_uuid()::text, 8), 22000, DATE '2027-01-04', DATE '2027-01-29', 'executed');

    INSERT INTO public.bid_packages (task_id, deadline, created_by) VALUES (t_grade, NOW() + INTERVAL '1 day', u) RETURNING id INTO v_pkg;
    INSERT INTO public.bid_invitations (bid_package_id, vendor_id, vendor_contact_id) VALUES (v_pkg, v_vendor, v_contact) RETURNING id INTO v_inv;
    INSERT INTO public.bid_submissions (bid_invitation_id, vendor_id, total_amount, status, is_draft) VALUES (v_inv, v_vendor, 28000, 'submitted', FALSE) RETURNING id INTO v_sub;
    INSERT INTO public.awards (task_id, bid_submission_id, vendor_id, awarded_by, award_amount)
      VALUES (t_grade, v_sub, v_vendor, u, 28000);

    PERFORM public.fn_create_project_budget(p, u, NULL, 15);
    SELECT * INTO s FROM public.v_project_budget_summary WHERE project_id = p;

    -- C01 total = project budget
    r := r || jsonb_build_object('id','C01 total budget = the project''s Budget value ($500,000)',
           'ok', s.total_budget = 500000, 'detail', s.total_budget::text);

    -- C02 contingency = (500,000 − 0 land) × 15 / 115
    r := r || jsonb_build_object('id','C02 contingency = 15% of the base (total − land − contingency)',
           'ok', s.contingency_now = round(500000 * 15 / 115.0, 2),
           'detail', s.contingency_now::text || ' (base ' || (500000 - s.contingency_now)::text || ')');

    -- C03 awarded tasks come in at the award amount, committed
    SELECT budget_amount INTO v_num FROM public.budget_lines WHERE task_id = t_grade AND deleted_at IS NULL;
    r := r || jsonb_build_object('id','C03 awarded tasks use the award amount; committed = $50,000',
           'ok', v_num = 28000 AND s.committed = 50000, 'detail', 'grading=' || v_num || ' committed=' || s.committed);

    -- C04 executed contract → locked with contract dates
    SELECT is_locked::text || ' ' || anticipated_start_date || '→' || anticipated_end_date INTO v_txt
      FROM public.budget_lines WHERE task_id = t_clear AND deleted_at IS NULL;
    r := r || jsonb_build_object('id','C04 executed contract: line locked with the contract dates',
           'ok', v_txt = 'true 2027-01-04→2027-01-29', 'detail', v_txt);

    -- C05 remaining = total − contingency − committed
    r := r || jsonb_build_object('id','C05 remaining = total − contingency − committed',
           'ok', s.remaining = 500000 - s.contingency_now - 50000, 'detail', s.remaining::text);

    -- C06 unallocated balances the lines
    r := r || jsonb_build_object('id','C06 Unallocated line balances the lines to the project budget',
           'ok', s.unallocated = 500000 - s.contingency_now - (22000 + 28000 + 9000 + 3000) AND s.over_project_budget = 0,
           'detail', 'unallocated=' || s.unallocated || ' over=' || s.over_project_budget);

    -- C07 draft edits are absorbed by Unallocated; total stays at $500,000
    SELECT id INTO l_sewer FROM public.budget_lines WHERE task_id = t_sewer AND deleted_at IS NULL;
    UPDATE public.budget_lines SET budget_amount = 10000 WHERE id = l_sewer;
    INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
      VALUES (p, v_trade, 'Paving', 'development', 'competitive', 5000.50, 5, u);
    SELECT total_budget, unallocated INTO v_num, v_num2 FROM public.v_project_budget_summary WHERE project_id = p;
    r := r || jsonb_build_object('id','C07 draft edits + new task absorbed; total stays $500,000',
           'ok', v_num = 500000 AND v_num2 = s.unallocated - 1000 - 5000.50,
           'detail', 'total=' || v_num || ' unallocated=' || v_num2);

    -- C08 contingency has no own "remaining"; line remaining = budget − committed
    SELECT count(*) INTO n FROM public.v_budget_lines WHERE project_id = p AND line_type = 'contingency' AND remaining IS NULL;
    SELECT remaining INTO v_num FROM public.v_budget_lines WHERE task_id = t_grade;
    r := r || jsonb_build_object('id','C08 line remaining = budget − committed (contingency: none)',
           'ok', n = 1 AND v_num = 0, 'detail', 'contingency null=' || n || ' grading remaining=' || v_num);

    -- C09 baseline at the project budget; absorption stops after baseline
    PERFORM public.fn_baseline_project_budget(p, u);
    SELECT approved_budget_total INTO v_num FROM public.projects WHERE id = p;
    BEGIN
      SET CONSTRAINTS ALL IMMEDIATE;
      r := r || jsonb_build_object('id','C09 baseline lands exactly on the project budget',
             'ok', v_num = 500000, 'detail', v_num::text);
    EXCEPTION WHEN OTHERS THEN
      r := r || jsonb_build_object('id','C09 baseline lands exactly on the project budget','ok', false, 'detail', SQLERRM);
    END;
    SET CONSTRAINTS ALL DEFERRED;

    -- C10 project without a Budget value keeps the Phase 2 rule; no Unallocated
    INSERT INTO public.projects (name, status, created_by) VALUES ('ZZ V3 Project B', 'active', u) RETURNING id INTO p2;
    INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
      VALUES (p2, v_trade, 'Clearing', 'development', 'competitive', 20000, 1, u);
    PERFORM public.fn_create_project_budget(p2, u, NULL, 10);
    SELECT * INTO s FROM public.v_project_budget_summary WHERE project_id = p2;
    r := r || jsonb_build_object('id','C10 no project Budget value: contingency = 10% of lines, no Unallocated',
           'ok', s.contingency_now = 2000 AND s.unallocated = 0 AND s.total_budget = 22000,
           'detail', 'contingency=' || s.contingency_now || ' total=' || s.total_budget);

    -- C11 reset a draft, then create again
    PERFORM public.fn_reset_draft_budget(p2, u);
    SELECT count(*) INTO n FROM public.budget_lines WHERE project_id = p2 AND deleted_at IS NULL;
    SELECT budget_status INTO v_txt FROM public.projects WHERE id = p2;
    UPDATE public.projects SET budget = 30000 WHERE id = p2;
    PERFORM public.fn_create_project_budget(p2, u, NULL, 10);
    SELECT total_budget INTO v_num FROM public.v_project_budget_summary WHERE project_id = p2;
    r := r || jsonb_build_object('id','C11 reset draft → no lines, status none; recreate uses the new Budget value',
           'ok', n = 0 AND v_txt = 'none' AND v_num = 30000, 'detail', 'lines=' || n || ' status=' || v_txt || ' new total=' || v_num);

    -- C12 reset refused once baselined
    BEGIN
      PERFORM public.fn_reset_draft_budget(p, u);
      r := r || jsonb_build_object('id','C12 baselined budgets cannot be reset','ok', false, 'detail', 'no error');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      r := r || jsonb_build_object('id','C12 baselined budgets cannot be reset','ok', true, 'detail', 'PT409');
    END;

    -- C13 procedures are service_role only
    SELECT count(*) INTO n FROM pg_proc pr JOIN pg_namespace ns ON ns.oid = pr.pronamespace
     WHERE ns.nspname = 'public' AND pr.proname IN ('fn_create_project_budget', 'fn_reset_draft_budget')
       AND (has_function_privilege('authenticated', pr.oid, 'EXECUTE') OR has_function_privilege('anon', pr.oid, 'EXECUTE'));
    r := r || jsonb_build_object('id','C13 procedures not callable by anon / authenticated','ok', n = 0, 'detail', n || ' exposed');

    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = '__fin_verify3_rollback__';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> '__fin_verify3_rollback__' THEN
      r := r || jsonb_build_object('id','ABORTED — unexpected error, later checks did not run','ok', false, 'detail', SQLSTATE || ': ' || SQLERRM);
    END IF;
  END;

  INSERT INTO _fin_verify3 (seq, check_id, result, detail)
  SELECT ord, e ->> 'id', CASE WHEN (e ->> 'ok')::boolean THEN 'PASS' ELSE 'FAIL' END, e ->> 'detail'
    FROM jsonb_array_elements(r) WITH ORDINALITY AS t(e, ord);
END
$verify$;

INSERT INTO _fin_verify3
SELECT 999, 'C99 no verify data left behind',
       CASE WHEN (SELECT count(*) FROM public.projects WHERE name LIKE 'ZZ V3 Project%') = 0 THEN 'PASS' ELSE 'FAIL' END,
       'rows: ' || (SELECT count(*) FROM public.projects WHERE name LIKE 'ZZ V3 Project%');

SELECT seq, result, check_id, detail FROM _fin_verify3 ORDER BY seq;
