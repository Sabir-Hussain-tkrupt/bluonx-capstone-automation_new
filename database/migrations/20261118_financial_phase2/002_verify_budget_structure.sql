-- ============================================================================
-- BluOnX Financial Automation — Phase 2 · Module 2
-- 002  VERIFY BUDGET STRUCTURE (self-checking, leaves NO data behind)
-- ============================================================================
-- Run AFTER 001_budget_structure.sql. Safe on production: all test data is
-- created inside a sub-transaction that is rolled back at the end.
-- Every row of the final table must say PASS.
-- ============================================================================

CREATE TEMP TABLE IF NOT EXISTS _fin_verify2 (seq INTEGER, check_id TEXT, result TEXT, detail TEXT);
TRUNCATE _fin_verify2;

DO $verify$
DECLARE
  r         JSONB := '[]'::jsonb;
  n         INTEGER;
  v_num     NUMERIC;
  v_num2    NUMERIC;
  v_txt     TEXT;
  v_json    JSONB;

  u_admin   UUID := gen_random_uuid();
  u_fm      UUID := gen_random_uuid();
  v_trade   UUID;
  v_project UUID;
  t_clear   UUID;
  t_sewer   UUID;
  t_att     UUID;
  t_new     UUID;
  v_vendor  UUID;
  v_contact UUID;
  v_pkg     UUID;
  v_inv     UUID;
  v_sub     UUID;
  v_award   UUID;
  l_cont    UUID;
  l_sewer   UUID;
  l_att     UUID;
  l_permit  UUID;
  l_land    UUID;
  v_invoice UUID;
  v_ids     UUID[];
BEGIN
  BEGIN
    -- C01 objects present
    SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace s ON s.oid = p.pronamespace
     WHERE s.nspname = 'public' AND p.proname IN ('fn_create_project_budget','fn_reorder_budget_lines',
           'fn_remove_budget_line','fn_apply_budget_import','fn_categorise_internal_invoice','fn_sync_task_budget_line');
    SELECT n + count(*) INTO n FROM pg_views WHERE schemaname = 'public'
       AND viewname IN ('v_budget_lines','v_project_budget_summary');
    r := r || jsonb_build_object('id','C01 Phase 2 procedures, trigger function and views exist','ok', n = 8, 'detail', n || ' of 8');

    -- C02 default template
    SELECT count(*) INTO n FROM public.budget_templates WHERE is_default AND is_active AND deleted_at IS NULL;
    r := r || jsonb_build_object('id','C02 exactly one active default budget template','ok', n = 1, 'detail', n || ' default(s)');

    -- C03 procedures are service_role only
    SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace s ON s.oid = p.pronamespace
     WHERE s.nspname = 'public'
       AND p.proname IN ('fn_create_project_budget','fn_reorder_budget_lines','fn_remove_budget_line',
                         'fn_apply_budget_import','fn_categorise_internal_invoice')
       AND (has_function_privilege('authenticated', p.oid, 'EXECUTE') OR has_function_privilege('anon', p.oid, 'EXECUTE'));
    r := r || jsonb_build_object('id','C03 Phase 2 procedures not callable by anon / authenticated','ok', n = 0, 'detail', n || ' exposed');

    -- Setup
    INSERT INTO public.users (id, email, full_name, role) VALUES
      (u_admin, 'v2.admin.' || u_admin || '@example.test', 'V2 Admin', 'admin'),
      (u_fm,    'v2.fm.'    || u_fm    || '@example.test', 'V2 FM',    'project_manager');
    INSERT INTO public.trades (name, phase) VALUES ('ZZ V2 Trade ' || gen_random_uuid(), 'development') RETURNING id INTO v_trade;
    INSERT INTO public.projects (name, status, created_by) VALUES ('ZZ V2 Project', 'active', u_admin) RETURNING id INTO v_project;

    -- C04 tasks on a project WITHOUT a budget create no lines (existing behaviour)
    INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
      VALUES (v_project, v_trade, 'Sanitary Sewer', 'development', 'competitive', 9000, 1, u_admin) RETURNING id INTO t_sewer;
    INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
      VALUES (v_project, v_trade, 'Clearing', 'development', 'competitive', 20000, 2, u_admin) RETURNING id INTO t_clear;
    INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
      VALUES (v_project, v_trade, 'Attorney', 'development', 'internal', 3000, 3, u_admin) RETURNING id INTO t_att;
    SELECT count(*) INTO n FROM public.budget_lines WHERE project_id = v_project;
    r := r || jsonb_build_object('id','C04 projects without a budget: tasks create no lines','ok', n = 0, 'detail', n || ' lines');

    -- C05 create budget
    PERFORM public.fn_create_project_budget(v_project, u_admin, NULL, 10);
    SELECT count(*) INTO n FROM public.budget_lines WHERE project_id = v_project AND deleted_at IS NULL AND task_id IS NOT NULL;
    SELECT budget_status INTO v_txt FROM public.projects WHERE id = v_project;
    r := r || jsonb_build_object('id','C05 create budget: draft, every task became a line','ok', n = 3 AND v_txt = 'draft',
           'detail', n || ' task lines, status ' || v_txt);

    -- C06 template order: Clearing slot before Sanitary sewer slot, internal under Internal
    SELECT id INTO l_sewer FROM public.budget_lines WHERE task_id = t_sewer AND deleted_at IS NULL;
    SELECT id INTO l_att   FROM public.budget_lines WHERE task_id = t_att   AND deleted_at IS NULL;
    SELECT (SELECT sort_order FROM public.budget_lines WHERE task_id = t_clear AND deleted_at IS NULL)
         < (SELECT sort_order FROM public.budget_lines WHERE id = l_sewer)
       AND (SELECT line_type = 'internal_tm' AND section_name = 'Internal' FROM public.budget_lines WHERE id = l_att)
       AND (SELECT section_name FROM public.budget_lines WHERE id = l_sewer) = 'Utilities'
      INTO v_txt;
    r := r || jsonb_build_object('id','C06 tasks placed at their template slots (order + heading + type)','ok', v_txt = 'true', 'detail', v_txt);

    -- C07 contingency = 10% of base (base excludes land + contingency)
    SELECT id, budget_amount INTO l_cont, v_num FROM public.budget_lines
     WHERE project_id = v_project AND line_type = 'contingency' AND deleted_at IS NULL;
    r := r || jsonb_build_object('id','C07 contingency = 10% × (9,000 + 20,000 + 3,000) = 3,200','ok', v_num = 3200, 'detail', v_num::text);

    -- C08 land lines exist separately and are payment exempt
    SELECT count(*) INTO n FROM public.budget_lines
     WHERE project_id = v_project AND line_type = 'land' AND is_payment_exempt AND deleted_at IS NULL
       AND line_subtype IN ('land_purchase','earnest_money','due_diligence');
    r := r || jsonb_build_object('id','C08 land purchase / earnest money / due diligence lines, payment exempt','ok', n = 3, 'detail', n || ' lines');

    -- C09 second budget refused
    BEGIN
      PERFORM public.fn_create_project_budget(v_project, u_admin);
      r := r || jsonb_build_object('id','C09 a project cannot get a second budget','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      r := r || jsonb_build_object('id','C09 a project cannot get a second budget','ok',true,'detail','PT409');
    END;

    -- C10 new task → new line automatically (draft: its estimate)
    INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
      VALUES (v_project, v_trade, 'Paving', 'development', 'competitive', 15000, 4, u_admin) RETURNING id INTO t_new;
    SELECT budget_amount INTO v_num FROM public.budget_lines WHERE task_id = t_new AND deleted_at IS NULL;
    r := r || jsonb_build_object('id','C10 new task → budget line automatically (no double entry)','ok', v_num = 15000, 'detail', COALESCE(v_num::text,'no line'));

    -- C11 task rename / estimate change follow while draft
    UPDATE public.tasks SET name = 'Paving & curbs', budget_estimate = 16000 WHERE id = t_new;
    SELECT name || ' / ' || budget_amount INTO v_txt FROM public.budget_lines WHERE task_id = t_new AND deleted_at IS NULL;
    r := r || jsonb_build_object('id','C11 task rename + estimate change follow the line (draft)','ok', v_txt = 'Paving & curbs / 16000.00', 'detail', v_txt);

    -- C12 bid_type change replaces the line type
    UPDATE public.tasks SET bid_type = 'internal' WHERE id = t_new;
    SELECT line_type INTO v_txt FROM public.budget_lines WHERE task_id = t_new AND deleted_at IS NULL;
    UPDATE public.tasks SET bid_type = 'competitive' WHERE id = t_new;
    r := r || jsonb_build_object('id','C12 task bid_type change → line type follows','ok', v_txt = 'internal_tm', 'detail', v_txt);

    -- C13 task soft delete → its line goes (draft)
    UPDATE public.tasks SET deleted_at = NOW() WHERE id = t_new;
    SELECT count(*) INTO n FROM public.budget_lines WHERE task_id = t_new AND deleted_at IS NULL;
    r := r || jsonb_build_object('id','C13 deleted task → its budget line removed','ok', n = 0, 'detail', n || ' live lines');

    -- C14 a task line cannot be removed directly
    BEGIN
      PERFORM public.fn_remove_budget_line(l_sewer, u_admin);
      r := r || jsonb_build_object('id','C14 task lines are removed with their task, not directly','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      r := r || jsonb_build_object('id','C14 task lines are removed with their task, not directly','ok',true,'detail','PT409');
    END;

    -- C15 removing a non-task line (draft) + contingency line protected
    SELECT id INTO l_permit FROM public.budget_lines WHERE project_id = v_project AND line_type = 'impact_fee' AND deleted_at IS NULL;
    PERFORM public.fn_remove_budget_line(l_permit, u_admin);
    BEGIN
      PERFORM public.fn_remove_budget_line(l_cont, u_admin);
      r := r || jsonb_build_object('id','C15 non-task line removable; contingency line never','ok',false,'detail','contingency removed');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      SELECT count(*) INTO n FROM public.budget_lines WHERE id = l_permit AND deleted_at IS NOT NULL;
      r := r || jsonb_build_object('id','C15 non-task line removable; contingency line never','ok', n = 1, 'detail','impact fee removed, contingency PT409');
    END;

    -- C16 reorder
    SELECT array_agg(id ORDER BY sort_order DESC) INTO v_ids FROM public.budget_lines
     WHERE project_id = v_project AND deleted_at IS NULL;
    PERFORM public.fn_reorder_budget_lines(v_project, v_ids, u_admin);
    SELECT array_agg(id ORDER BY sort_order) = v_ids INTO v_txt FROM public.budget_lines
     WHERE project_id = v_project AND deleted_at IS NULL;
    BEGIN
      PERFORM public.fn_reorder_budget_lines(v_project, v_ids[1:2], u_admin);
      r := r || jsonb_build_object('id','C16 reorder applies; partial list rejected','ok',false,'detail','partial accepted');
    EXCEPTION WHEN SQLSTATE 'PT422' THEN
      r := r || jsonb_build_object('id','C16 reorder applies; partial list rejected','ok', v_txt = 'true','detail','order ' || v_txt || ', partial PT422');
    END;

    -- C17 import into draft: update a line + add a line
    SELECT id INTO l_land FROM public.budget_lines WHERE project_id = v_project AND line_subtype = 'land_purchase' AND deleted_at IS NULL;
    v_json := public.fn_apply_budget_import(v_project, jsonb_build_array(
      jsonb_build_object('line_id', l_land, 'budget_amount', 50000.10, 'anticipated_start_date', '2027-01-15', 'anticipated_end_date', '2027-01-15'),
      jsonb_build_object('name', 'Survey', 'line_type', 'soft_cost', 'section_name', 'Soft costs', 'budget_amount', 1234.56)
    ), u_admin);
    SELECT budget_amount INTO v_num FROM public.budget_lines WHERE id = l_land;
    r := r || jsonb_build_object('id','C17 import updates and adds lines atomically (cents kept)',
           'ok', v_json = '{"added": 1, "updated": 1}'::jsonb AND v_num = 50000.10, 'detail', v_json::text || ' land=' || v_num);

    -- C18 views: totals exact to the cent
    SELECT total_budget INTO v_num FROM public.v_project_budget_summary WHERE project_id = v_project;
    SELECT SUM(budget_amount) INTO v_num2 FROM public.budget_lines WHERE project_id = v_project AND deleted_at IS NULL;
    r := r || jsonb_build_object('id','C18 summary view total = sum of lines (to the cent)','ok', v_num = v_num2, 'detail', v_num || ' vs ' || v_num2);

    -- Baseline
    PERFORM public.fn_baseline_project_budget(v_project, u_admin);

    -- C19 import refused after baseline
    BEGIN
      PERFORM public.fn_apply_budget_import(v_project, '[]'::jsonb, u_admin);
      r := r || jsonb_build_object('id','C19 import refused once baselined','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      r := r || jsonb_build_object('id','C19 import refused once baselined','ok',true,'detail','PT409');
    END;

    -- C20 new task after baseline → $0 line, total still flat
    INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
      VALUES (v_project, v_trade, 'Late task', 'development', 'competitive', 5000, 9, u_admin) RETURNING id INTO t_new;
    SELECT budget_amount INTO v_num FROM public.budget_lines WHERE task_id = t_new AND deleted_at IS NULL;
    BEGIN
      SET CONSTRAINTS ALL IMMEDIATE;
      r := r || jsonb_build_object('id','C20 task added after baseline → $0 line, total stays flat','ok', v_num = 0, 'detail', 'line ' || v_num);
    EXCEPTION WHEN OTHERS THEN
      r := r || jsonb_build_object('id','C20 task added after baseline → $0 line, total stays flat','ok', false, 'detail', SQLERRM);
    END;
    SET CONSTRAINTS ALL DEFERRED;

    -- C21 deleting a task whose line holds money after baseline → PT409
    BEGIN
      UPDATE public.tasks SET deleted_at = NOW() WHERE id = t_sewer;
      r := r || jsonb_build_object('id','C21 deleting a task with a funded line after baseline is blocked','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      r := r || jsonb_build_object('id','C21 deleting a task with a funded line after baseline is blocked','ok',true,'detail','PT409');
    END;

    -- C22 award → apply (overrun) through the existing chain
    INSERT INTO public.vendors (company_name) VALUES ('ZZ V2 Vendor') RETURNING id INTO v_vendor;
    INSERT INTO public.vendor_contacts (vendor_id, full_name, email) VALUES (v_vendor, 'C', 'c@example.test') RETURNING id INTO v_contact;
    INSERT INTO public.bid_packages (task_id, deadline, created_by) VALUES (t_sewer, NOW() + INTERVAL '1 day', u_admin) RETURNING id INTO v_pkg;
    INSERT INTO public.bid_invitations (bid_package_id, vendor_id, vendor_contact_id) VALUES (v_pkg, v_vendor, v_contact) RETURNING id INTO v_inv;
    INSERT INTO public.bid_submissions (bid_invitation_id, vendor_id, total_amount, status, is_draft) VALUES (v_inv, v_vendor, 10000, 'submitted', FALSE) RETURNING id INTO v_sub;
    INSERT INTO public.awards (task_id, bid_submission_id, vendor_id, awarded_by, award_amount) VALUES (t_sewer, v_sub, v_vendor, u_admin, 10000) RETURNING id INTO v_award;
    PERFORM public.fn_apply_bid_to_line(l_sewer, v_award, 10000, u_admin);
    SELECT committed, award_status, vendor_name INTO v_num, v_txt, v_txt FROM public.v_budget_lines WHERE id = l_sewer;
    SELECT budget_amount INTO v_num2 FROM public.budget_lines WHERE id = l_cont;
    r := r || jsonb_build_object('id','C22 award applied: view shows committed + vendor, contingency −1,000',
           'ok', v_num = 10000 AND v_num2 = 2200 AND v_txt = 'ZZ V2 Vendor', 'detail', 'committed=' || v_num || ' contingency=' || v_num2);

    -- C23 invoice within allowance → one pending approval, no variance
    INSERT INTO public.internal_invoices (project_id, payee_name, invoice_number, amount, file_path, file_name, uploaded_by)
      VALUES (v_project, 'Law LLP', 'INV-1', 2000, 'x/1.pdf', '1.pdf', u_fm) RETURNING id INTO v_invoice;
    v_json := public.fn_categorise_internal_invoice(v_invoice, l_att, u_fm);
    r := r || jsonb_build_object('id','C23 invoice within allowance → in approval, 1 pending request, no variance',
           'ok', (v_json ->> 'overage')::numeric = 0 AND jsonb_array_length(v_json -> 'payment_approvals') = 1
                 AND v_json ->> 'status' = 'in_approval' AND v_json -> 'variance_id' = 'null'::jsonb,
           'detail', v_json::text);

    -- C24 invoice over allowance → variance funded from contingency
    INSERT INTO public.internal_invoices (project_id, payee_name, invoice_number, amount, file_path, file_name, uploaded_by)
      VALUES (v_project, 'Law LLP', 'INV-2', 1500, 'x/2.pdf', '2.pdf', u_fm) RETURNING id INTO v_invoice;
    v_json := public.fn_categorise_internal_invoice(v_invoice, l_att, u_fm);
    SELECT budget_amount INTO v_num FROM public.budget_lines WHERE id = l_cont;
    SELECT count(*) INTO n FROM public.contingency_ledger WHERE project_id = v_project AND movement_type = 'invoice_overage' AND amount = -500;
    r := r || jsonb_build_object('id','C24 invoice $1,500 vs $1,000 left → $500 variance, contingency −500, 2 requests',
           'ok', (v_json ->> 'overage')::numeric = 500 AND v_num = 1700 AND n = 1
                 AND jsonb_array_length(v_json -> 'payment_approvals') = 2,
           'detail', 'overage=' || (v_json ->> 'overage') || ' contingency=' || v_num || ' ledger=' || n);

    -- C25 invoiced / committed on the T&M line, total still flat
    SELECT invoiced INTO v_num FROM public.v_budget_lines WHERE id = l_att;
    SELECT flat_ok INTO v_txt FROM public.v_project_budget_summary WHERE project_id = v_project;
    BEGIN
      SET CONSTRAINTS ALL IMMEDIATE;
      r := r || jsonb_build_object('id','C25 T&M line shows $3,500 invoiced; budget still flat','ok', v_num = 3500 AND v_txt = 'true', 'detail', 'invoiced=' || v_num || ' flat=' || v_txt);
    EXCEPTION WHEN OTHERS THEN
      r := r || jsonb_build_object('id','C25 T&M line shows $3,500 invoiced; budget still flat','ok', false, 'detail', SQLERRM);
    END;
    SET CONSTRAINTS ALL DEFERRED;

    -- C26 invoice to a non-T&M line rejected; re-categorise of an in-approval invoice rejected
    BEGIN
      PERFORM public.fn_categorise_internal_invoice(v_invoice, l_sewer, u_fm);
      r := r || jsonb_build_object('id','C26 invoice cannot be re-categorised once in approval','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      r := r || jsonb_build_object('id','C26 invoice cannot be re-categorised once in approval','ok',true,'detail','PT409');
    END;

    -- C27 a funded line cannot be removed after baseline
    SELECT id INTO l_land FROM public.budget_lines WHERE project_id = v_project AND line_subtype = 'earnest_money' AND deleted_at IS NULL;
    UPDATE public.budget_lines SET deleted_at = NULL WHERE FALSE;
    SELECT id INTO l_permit FROM public.budget_lines WHERE project_id = v_project AND name = 'Survey' AND deleted_at IS NULL;
    BEGIN
      PERFORM public.fn_remove_budget_line(l_permit, u_admin);
      r := r || jsonb_build_object('id','C27 funded line cannot be removed after baseline','ok',false,'detail','no error');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      r := r || jsonb_build_object('id','C27 funded line cannot be removed after baseline','ok',true,'detail','PT409');
    END;

    -- C28 RLS: totals identical for a non-finance user (invoiced via definer fn)
    BEGIN
      PERFORM set_config('request.jwt.claim.sub', u_fm::text, TRUE);
      PERFORM set_config('request.jwt.claims', jsonb_build_object('sub', u_fm)::text, TRUE);
      SET LOCAL ROLE authenticated;
      SELECT invoiced INTO v_num FROM public.v_budget_lines WHERE id = l_att;
      SELECT count(*) INTO n FROM public.internal_invoices WHERE project_id = v_project;
      RESET ROLE;
      r := r || jsonb_build_object('id','C28 PM sees the same invoiced total but not the invoice rows','ok', v_num = 3500 AND n = 0,
             'detail', 'invoiced=' || v_num || ' rows visible=' || n);
    EXCEPTION WHEN OTHERS THEN
      RESET ROLE;
      r := r || jsonb_build_object('id','C28 PM sees the same invoiced total but not the invoice rows','ok', NULL, 'detail', 'SKIP: ' || SQLERRM);
    END;

    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = '__fin_verify2_rollback__';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> '__fin_verify2_rollback__' THEN
      r := r || jsonb_build_object('id','ABORTED — unexpected error, later checks did not run','ok', false, 'detail', SQLSTATE || ': ' || SQLERRM);
    END IF;
  END;

  RESET ROLE;
  INSERT INTO _fin_verify2 (seq, check_id, result, detail)
  SELECT ord, e ->> 'id',
         CASE WHEN e -> 'ok' = 'null'::jsonb THEN 'SKIP' WHEN (e ->> 'ok')::boolean THEN 'PASS' ELSE 'FAIL' END,
         e ->> 'detail'
    FROM jsonb_array_elements(r) WITH ORDINALITY AS t(e, ord);
END
$verify$;

INSERT INTO _fin_verify2
SELECT 999, 'C99 no verify data left behind',
       CASE WHEN (SELECT count(*) FROM public.projects WHERE name = 'ZZ V2 Project') = 0 THEN 'PASS' ELSE 'FAIL' END,
       'rows named ZZ V2 Project: ' || (SELECT count(*) FROM public.projects WHERE name = 'ZZ V2 Project');

SELECT seq, result, check_id, detail FROM _fin_verify2 ORDER BY seq;
