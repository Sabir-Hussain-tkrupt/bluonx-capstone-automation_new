-- ============================================================================
-- BluOnX Financial Automation — Phase 2 · Module 2
-- Development Seed Data — template-driven budget + internal invoices
-- ============================================================================
-- ⚠️  100% SYNTHETIC TEST DATA — NEVER RUN IN PRODUCTION
-- ⚠️  Refuses to run unless financial_settings.environment = "development".
--
-- Depends: 20261111_financial_phase1 + 20261118_financial_phase2 applied.
--
-- Creates project "Demo · Template Budget" the way the app does it:
--   • 4 tasks (Clearing, Grading, Sanitary sewer — competitive; Attorney — internal)
--   • fn_create_project_budget at 10% → every task becomes a line in template order
--   • land lines filled through fn_apply_budget_import (as an Excel import would)
--   • a phased land closing pair, then baseline
--   • a task added AFTER baseline (appears as a $0 line automatically)
--   • two attorney invoices: one within the allowance, one over it (overage →
--     variance funded from contingency, two pending approval requests)
-- Re-running: stops politely if the demo project exists.
-- ============================================================================

BEGIN;

DO $seed$
DECLARE
  v_env     TEXT;
  u_admin   UUID;
  u_fm      UUID;
  v_trade   UUID;
  p         UUID;
  t_att     UUID;
  l_land    UUID;
  l_earnest UUID;
  l_att     UUID;
  v_inv     UUID;
  v_lines   JSONB;
BEGIN
  SELECT value #>> '{}' INTO v_env FROM public.financial_settings WHERE setting_key = 'environment';
  IF v_env IS DISTINCT FROM 'development' THEN
    RAISE EXCEPTION 'Refusing to seed: financial_settings.environment is "%" (must be "development").', COALESCE(v_env, 'missing');
  END IF;
  IF EXISTS (SELECT 1 FROM public.projects WHERE name = 'Demo · Template Budget' AND deleted_at IS NULL) THEN
    RAISE NOTICE 'Demo · Template Budget already exists — nothing to do.';
    RETURN;
  END IF;

  SELECT id INTO u_admin FROM public.users WHERE role = 'admin' AND is_active AND deleted_at IS NULL ORDER BY created_at LIMIT 1;
  IF u_admin IS NULL THEN
    RAISE EXCEPTION 'Create an admin user first.';
  END IF;
  -- The Phase 1 seed's field manager if present, otherwise the admin.
  SELECT id INTO u_fm FROM public.users WHERE email = 'demo.fieldmanager@example.test';
  u_fm := COALESCE(u_fm, u_admin);

  SELECT id INTO v_trade FROM public.trades WHERE is_active ORDER BY name LIMIT 1;
  IF v_trade IS NULL THEN
    INSERT INTO public.trades (name, phase) VALUES ('Demo Site Work', 'development') RETURNING id INTO v_trade;
  END IF;

  INSERT INTO public.projects (name, description, city, state, status, created_by, manager_id, field_manager_id, business_entity)
  VALUES ('Demo · Template Budget', 'Phase 2 demo: budget created from the standard template.', 'Wentzville', 'MO',
          'active', u_admin, u_admin, u_fm, 'bluonx')
  RETURNING id INTO p;

  INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by) VALUES
    (p, v_trade, 'Clearing',       'development', 'competitive', 20000, 1, u_admin),
    (p, v_trade, 'Grading',        'development', 'competitive', 30000, 2, u_admin),
    (p, v_trade, 'Sanitary sewer', 'development', 'competitive',  9000, 3, u_admin);
  INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
    VALUES (p, v_trade, 'Attorney', 'due_diligence', 'internal', 3000, 4, u_admin) RETURNING id INTO t_att;

  PERFORM public.fn_create_project_budget(p, u_admin, NULL, 10);

  SELECT id INTO l_land    FROM public.budget_lines WHERE project_id = p AND line_subtype = 'land_purchase' AND deleted_at IS NULL;
  SELECT id INTO l_earnest FROM public.budget_lines WHERE project_id = p AND line_subtype = 'earnest_money' AND deleted_at IS NULL;
  SELECT id INTO l_att     FROM public.budget_lines WHERE task_id = t_att AND deleted_at IS NULL;

  -- As an Excel import would: land amounts + dates on the existing lines, one new soft cost.
  v_lines := jsonb_build_array(
    jsonb_build_object('line_id', l_land, 'name', 'Land purchase', 'budget_amount', 250000,
                       'anticipated_start_date', '2027-01-15', 'anticipated_end_date', '2027-01-15'),
    jsonb_build_object('line_id', l_earnest, 'name', 'Earnest money', 'budget_amount', 10000,
                       'anticipated_start_date', '2026-12-01', 'anticipated_end_date', '2026-12-01'),
    jsonb_build_object('name', 'Boundary survey', 'line_type', 'soft_cost', 'section_name', 'Soft costs',
                       'budget_amount', 4250.50, 'anticipated_start_date', '2027-01-04', 'anticipated_end_date', '2027-01-15')
  );
  PERFORM public.fn_apply_budget_import(p, v_lines, u_admin);

  INSERT INTO public.land_closings (project_id, budget_line_id, closing_sequence, acres, amount, planned_closing_date, created_by)
  VALUES (p, l_land, 1, 40, 100000, DATE '2027-01-15', u_admin),
         (p, l_land, 2, 60, 150000, DATE '2028-06-15', u_admin);

  PERFORM public.fn_baseline_project_budget(p, u_admin);

  -- A task added after baseline shows up as a $0 line on its own.
  INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
  VALUES (p, v_trade, 'Paving', 'development', 'competitive', 40000, 5, u_admin);

  -- Attorney invoices: $2,000 fits the $3,000 line; $1,500 is $500 over → variance.
  INSERT INTO public.internal_invoices (project_id, payee_name, invoice_number, invoice_date, amount, file_path, file_name, uploaded_by)
  VALUES (p, 'Demo Law Partners', 'INV-2001', DATE '2027-01-20', 2000, 'demo/' || p || '/INV-2001.pdf', 'INV-2001.pdf', u_fm)
  RETURNING id INTO v_inv;
  PERFORM public.fn_categorise_internal_invoice(v_inv, l_att, u_fm);

  INSERT INTO public.internal_invoices (project_id, payee_name, invoice_number, invoice_date, amount, file_path, file_name, uploaded_by)
  VALUES (p, 'Demo Law Partners', 'INV-2002', DATE '2027-02-20', 1500, 'demo/' || p || '/INV-2002.pdf', 'INV-2002.pdf', u_fm)
  RETURNING id INTO v_inv;
  PERFORM public.fn_categorise_internal_invoice(v_inv, l_att, u_fm);

  -- One more invoice left uncategorised, to try the Invoices tab.
  INSERT INTO public.internal_invoices (project_id, payee_name, invoice_number, invoice_date, amount, file_path, file_name, uploaded_by)
  VALUES (p, 'Demo Title Co.', 'T-77', DATE '2027-03-01', 750, 'demo/' || p || '/T-77.pdf', 'T-77.pdf', u_fm);

  RAISE NOTICE 'Seeded Demo · Template Budget (%)', p;
END
$seed$;

COMMIT;

SELECT project_name, budget_status, approved_budget_total, total_budget, contingency_now, line_count, flat_ok
  FROM v_project_budget_summary WHERE project_name = 'Demo · Template Budget';
