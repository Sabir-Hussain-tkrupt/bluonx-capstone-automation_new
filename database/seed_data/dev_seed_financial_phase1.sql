-- ============================================================================
-- BluOnX Financial Automation — Phase 1 · Module 1
-- Development Seed Data (discovery-call examples)
-- ============================================================================
-- Version:  1.0
-- Date:     November 11, 2026
-- Depends:  migrations/20261111_financial_phase1/001_financial_foundation.sql
--
-- ⚠️  100% SYNTHETIC TEST DATA — NEVER RUN IN PRODUCTION
-- ⚠️  Refuses to run unless financial_settings.environment = "development".
--     On the DEV project only, run this once first:
--       UPDATE financial_settings SET value = '"development"' WHERE setting_key = 'environment';
--
-- WHAT IT CREATES (all money movements go through the real procedures, so the
-- contingency ledger is genuine):
--
--   Demo users (public.users only — they cannot log in; shown as "pending" in
--   the dev user list):  Demo Manager, Demo Field Manager, Demo External Field
--   Manager (is_employee = false), Demo Executive (executive + project_manager
--   = two roles), Demo Finance.
--
--   Standard budget template (default) — land acquisition down to escrows and
--   property taxes.
--
--   Project 1 "Demo · $100k Discovery Budget"   (baselined)
--     Clearing $20k · Grading $30k · Sanitary sewer $9k · Water + storm $25k
--     Attorney (internal T&M) $3k · Permits $3k · Contingency $10k  = $100,000
--     Bids:  clearing 22,000 (−2,000) · grading 28,000 (+2,000) · sewer 10,000 (−1,000)
--     Clearing contract executed → line locked
--     Sanitary sewer variance: rock found $5,000 → actual $3,000 (+2,000 back)
--     Contingency 10,000 → 6,000; total still $100,000
--     Pending $4,000 top-up request; open guardrail alert (70% work left / 50%
--     contingency — Steve's example); attorney invoice; a field-approved payment
--
--   Project 2 "Demo · Land, Escrows & Property Tax"   (baselined)
--     Land purchase $400k with two phased closings (40 ac now, 60 ac later),
--     earnest money, due diligence, impact fee, escrow premium + repairs
--     lines, property tax line, contingency
--     Escrow "Roads to city" (bond $100k, posted) and
--     escrow "HOA landscaping, trails & benches" (cash $25k, planned)
--     Property tax 2027 + 2028 (estimated)
--
-- Re-running: if the demo projects already exist the script stops politely.
-- ============================================================================

BEGIN;

DO $seed$
DECLARE
  -- Fixed ids so the demo users are stable across re-seeds.
  u_mgr   CONSTANT UUID := 'f1000000-0000-4000-8000-000000000001';
  u_fm    CONSTANT UUID := 'f1000000-0000-4000-8000-000000000002';
  u_xfm   CONSTANT UUID := 'f1000000-0000-4000-8000-000000000003';
  u_exec  CONSTANT UUID := 'f1000000-0000-4000-8000-000000000004';
  u_fin   CONSTANT UUID := 'f1000000-0000-4000-8000-000000000005';

  v_env      TEXT;
  u_admin    UUID;
  v_trade    UUID;
  v_tmpl     UUID;
  p1         UUID;
  p2         UUID;
  v_vendor   UUID;
  v_contact  UUID;
  v_task     UUID;
  v_pkg      UUID;
  v_inv      UUID;
  v_sub      UUID;
  v_award    UUID;
  v_contract UUID;
  v_line     UUID;
  v_var      UUID;
  v_invoice  UUID;
  l_cont1    UUID;
  l_clear    UUID;
  l_sewer    UUID;
  l_att      UUID;
  l_land     UUID;
  l_prem     UUID;
  l_rep      UUID;
  l_tax      UUID;
  rec        RECORD;
BEGIN
  -- ── Safety latch ────────────────────────────────────────────────────────
  SELECT value #>> '{}' INTO v_env FROM public.financial_settings WHERE setting_key = 'environment';
  IF v_env IS DISTINCT FROM 'development' THEN
    RAISE EXCEPTION 'Refusing to seed: financial_settings.environment is "%" (must be "development"). This seed is for DEV only.',
      COALESCE(v_env, 'missing');
  END IF;

  IF EXISTS (SELECT 1 FROM public.projects WHERE name LIKE 'Demo · %' AND deleted_at IS NULL) THEN
    RAISE NOTICE 'Demo financial projects already exist — nothing to do.';
    RETURN;
  END IF;

  -- ── Users & roles ───────────────────────────────────────────────────────
  INSERT INTO public.users (id, email, full_name, role, is_employee, approval_limit) VALUES
    (u_mgr,  'demo.manager@example.test',      'Demo Manager',               'project_manager', TRUE,  25000),
    (u_fm,   'demo.fieldmanager@example.test', 'Demo Field Manager',         'project_manager', TRUE,  5000),
    (u_xfm,  'demo.external.fm@example.test',  'Demo External Field Manager','project_manager', FALSE, 0),
    (u_exec, 'demo.executive@example.test',    'Demo Executive',             'project_manager', TRUE,  NULL),
    (u_fin,  'demo.finance@example.test',      'Demo Finance',               'project_manager', TRUE,  NULL)
  ON CONFLICT (id) DO NOTHING;

  SELECT id INTO u_admin FROM public.users
   WHERE role = 'admin' AND is_active AND deleted_at IS NULL ORDER BY created_at LIMIT 1;
  u_admin := COALESCE(u_admin, u_mgr);

  UPDATE public.users SET reports_to = u_mgr, backup_approver_id = u_exec WHERE id IN (u_fm, u_xfm);
  UPDATE public.users SET reports_to = u_exec WHERE id = u_mgr;

  INSERT INTO public.user_roles (user_id, role, granted_by) VALUES
    (u_fm,   'field_manager', u_admin),
    (u_xfm,  'field_manager', u_admin),
    (u_exec, 'executive',     u_admin),
    (u_fin,  'finance',       u_admin)
  ON CONFLICT (user_id, role) WHERE revoked_at IS NULL DO NOTHING;

  INSERT INTO public.approval_delegations (delegator_user_id, delegate_user_id, starts_at, ends_at, reason, created_by)
  VALUES (u_mgr, u_exec, DATE '2027-07-01', DATE '2027-07-15', 'Manager on holiday', u_admin);

  -- ── Trade used by demo tasks ────────────────────────────────────────────
  SELECT id INTO v_trade FROM public.trades WHERE is_active ORDER BY name LIMIT 1;
  IF v_trade IS NULL THEN
    INSERT INTO public.trades (name, phase) VALUES ('Demo Site Work', 'development') RETURNING id INTO v_trade;
  END IF;

  -- ── Standard budget template ────────────────────────────────────────────
  IF NOT EXISTS (SELECT 1 FROM public.budget_templates WHERE is_default AND is_active AND deleted_at IS NULL) THEN
    INSERT INTO public.budget_templates (name, description, is_default, created_by)
    VALUES ('Standard development budget', 'Demo layout: land acquisition down to escrows and property taxes.', TRUE, u_admin)
    RETURNING id INTO v_tmpl;

    INSERT INTO public.budget_template_lines
      (budget_template_id, line_type, line_subtype, name, section_name, sort_order, default_cash_bucket)
    VALUES
      (v_tmpl, 'land',         'land_purchase',       'Land purchase',                 'Land',        10, 'land'),
      (v_tmpl, 'land',         'earnest_money',       'Earnest money',                 'Land',        20, 'land'),
      (v_tmpl, 'land',         'due_diligence',       'Due diligence',                 'Land',        30, 'land'),
      (v_tmpl, 'soft_cost',    'engineering',         'Engineering',                   'Soft costs',  40, 'land'),
      (v_tmpl, 'permit',       NULL,                  'Permits',                       'Soft costs',  50, 'land'),
      (v_tmpl, 'impact_fee',   NULL,                  'Impact fees',                   'Soft costs',  60, 'land'),
      (v_tmpl, 'bid_activity', NULL,                  'Clearing',                      'Site work',   70, 'land'),
      (v_tmpl, 'bid_activity', NULL,                  'Grading',                       'Site work',   80, 'land'),
      (v_tmpl, 'bid_activity', NULL,                  'Sanitary sewer',                'Utilities',   90, 'land'),
      (v_tmpl, 'bid_activity', NULL,                  'Water + storm',                 'Utilities',  100, 'land'),
      (v_tmpl, 'bid_activity', NULL,                  'Paving',                        'Roads',      110, 'land'),
      (v_tmpl, 'internal_tm',  NULL,                  'Attorney',                      'Internal',   120, 'land'),
      (v_tmpl, 'contingency',  NULL,                  'Contingency',                   'Contingency',200, 'land'),
      (v_tmpl, 'long_tail',    'escrow_bond_premium', 'Escrow bond / insurance premium','Long-tail', 300, 'land'),
      (v_tmpl, 'long_tail',    'escrow_repairs',      'Escrow repairs to city standard','Long-tail', 310, 'land'),
      (v_tmpl, 'long_tail',    'property_tax',        'Property tax',                  'Long-tail',  320, 'land');
  END IF;

  -- ── Vendor for the demo awards ──────────────────────────────────────────
  INSERT INTO public.vendors (company_name, city, state) VALUES ('Demo Earthworks LLC', 'St. Louis', 'MO')
    RETURNING id INTO v_vendor;
  INSERT INTO public.vendor_contacts (vendor_id, full_name, email, is_primary)
    VALUES (v_vendor, 'Dana Demo', 'dana@demo-earthworks.example.test', TRUE) RETURNING id INTO v_contact;

  -- ═══════════════════════ PROJECT 1: $100k discovery ═══════════════════════
  INSERT INTO public.projects (name, description, city, state, status, start_date, estimated_end_date,
                               created_by, manager_id, field_manager_id, business_entity,
                               contingency_percent, budget_status)
  VALUES ('Demo · $100k Discovery Budget',
          'Discovery-call worked example: $100k budget, bid variances, sanitary sewer rock variance.',
          'St. Louis', 'MO', 'active', DATE '2027-01-04', DATE '2027-06-30',
          u_admin, u_mgr, u_fm, 'bluonx', 15, 'draft')
  RETURNING id INTO p1;

  -- Tasks → budget lines (bid activities)
  FOR rec IN
    SELECT * FROM (VALUES
      ('Clearing',       20000::numeric, DATE '2027-01-04', DATE '2027-01-29', 70),
      ('Grading',        30000::numeric, DATE '2027-02-01', DATE '2027-03-31', 80),
      ('Sanitary sewer',  9000::numeric, DATE '2027-03-01', DATE '2027-03-31', 90),
      ('Water + storm',  25000::numeric, DATE '2027-04-01', DATE '2027-04-30', 100)
    ) AS t(name, est, s, e, ord)
  LOOP
    INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
      VALUES (p1, v_trade, rec.name, 'development', 'competitive', rec.est, rec.ord, u_admin) RETURNING id INTO v_task;
    INSERT INTO public.budget_lines (project_id, task_id, line_type, name, section_name, sort_order, budget_amount,
                                     anticipated_start_date, anticipated_end_date, created_by)
      VALUES (p1, v_task, 'bid_activity', rec.name,
              CASE WHEN rec.ord >= 90 THEN 'Utilities' ELSE 'Site work' END, rec.ord, rec.est, rec.s, rec.e, u_admin)
      RETURNING id INTO v_line;
    IF rec.name = 'Clearing'       THEN l_clear := v_line; END IF;
    IF rec.name = 'Sanitary sewer' THEN l_sewer := v_line; END IF;
  END LOOP;

  INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, budget_estimate, sort_order, created_by)
    VALUES (p1, v_trade, 'Attorney', 'development', 'internal', 3000, 120, u_admin) RETURNING id INTO v_task;
  INSERT INTO public.budget_lines (project_id, task_id, line_type, name, section_name, sort_order, budget_amount, created_by)
    VALUES (p1, v_task, 'internal_tm', 'Attorney', 'Internal', 120, 3000, u_admin) RETURNING id INTO l_att;

  INSERT INTO public.budget_lines (project_id, line_type, name, section_name, sort_order, budget_amount,
                                   anticipated_start_date, anticipated_end_date, created_by)
    VALUES (p1, 'permit', 'Permits', 'Soft costs', 50, 3000, DATE '2027-01-04', DATE '2027-01-04', u_admin);

  INSERT INTO public.budget_lines (project_id, line_type, name, section_name, sort_order, budget_amount,
                                   is_payment_exempt, created_by)
    VALUES (p1, 'contingency', 'Contingency', 'Contingency', 200, 10000, TRUE, u_admin) RETURNING id INTO l_cont1;

  PERFORM public.fn_baseline_project_budget(p1, u_admin);   -- total $100,000

  -- Awards (full bid chain per task, as the Bid Management System would create)
  FOR rec IN
    SELECT bl.id AS line_id, bl.task_id, bl.name,
           CASE bl.name WHEN 'Clearing' THEN 22000 WHEN 'Grading' THEN 28000 WHEN 'Sanitary sewer' THEN 10000 END::numeric AS bid
      FROM public.budget_lines bl
     WHERE bl.project_id = p1 AND bl.name IN ('Clearing', 'Grading', 'Sanitary sewer')
  LOOP
    INSERT INTO public.bid_packages (task_id, deadline, created_by, status)
      VALUES (rec.task_id, TIMESTAMPTZ '2026-12-15 17:00-06', u_admin, 'evaluating') RETURNING id INTO v_pkg;
    INSERT INTO public.bid_invitations (bid_package_id, vendor_id, vendor_contact_id, sent_at)
      VALUES (v_pkg, v_vendor, v_contact, TIMESTAMPTZ '2026-12-01 09:00-06') RETURNING id INTO v_inv;
    INSERT INTO public.bid_submissions (bid_invitation_id, vendor_id, total_amount, status, is_draft, submitted_at)
      VALUES (v_inv, v_vendor, rec.bid, 'submitted', FALSE, TIMESTAMPTZ '2026-12-10 12:00-06') RETURNING id INTO v_sub;
    INSERT INTO public.awards (task_id, bid_submission_id, vendor_id, awarded_by, award_amount)
      VALUES (rec.task_id, v_sub, v_vendor, u_mgr, rec.bid) RETURNING id INTO v_award;
    UPDATE public.tasks SET status = 'awarded' WHERE id = rec.task_id;

    PERFORM public.fn_apply_bid_to_line(rec.line_id, v_award, rec.bid, u_mgr);

    IF rec.name = 'Clearing' THEN
      UPDATE public.awards SET status = 'accepted' WHERE id = v_award;
      INSERT INTO public.contracts (award_id, vendor_id, task_id, contract_number, contract_amount,
                                    start_date, end_date, status, signed_at, payment_terms_days)
        VALUES (v_award, v_vendor, rec.task_id, 'DEMO-' || to_char(NOW(), 'YYMMDDHH24MISS') || '-CLR', rec.bid,
                DATE '2027-01-04', DATE '2027-01-29', 'executed', NOW(), 30)
        RETURNING id INTO v_contract;
      PERFORM public.fn_lock_budget_line(rec.line_id, v_contract, u_mgr);
    END IF;
  END LOOP;

  -- Sanitary sewer: rock found, $5,000 estimate → $3,000 actual
  SELECT id INTO v_var FROM public.fn_create_variance(
    l_sewer, 'Trade encountered rock in the sanitary sewer trench; PM approved up to $5,000',
    5000, u_fm, v_trade, v_vendor);
  PERFORM public.fn_adjust_variance(v_var, 3000, u_mgr, 'Actual cost came in at $3,000');

  -- Pending top-up request (executive decides later)
  PERFORM public.fn_request_contingency_top_up(p1, 4000, 'Additional rock expected along the water + storm run', u_mgr);

  -- Open guardrail alert — Steve's example (70% of work left, 50% contingency)
  INSERT INTO public.financial_alerts (project_id, alert_type, severity, contingency_left_pct, work_left_pct,
                                       contingency_remaining, message)
  VALUES (p1, 'contingency_health', 'warning', 50, 70, 5000,
          'This project has 70% of the work to go but only 50% of its contingency left. Manager: OK to proceed?');

  -- Attorney invoice + a field-approved payment on the locked clearing line
  INSERT INTO public.internal_invoices (project_id, budget_line_id, payee_name, invoice_number, invoice_date,
                                        amount, file_path, file_name, status, uploaded_by)
  VALUES (p1, l_att, 'Demo Law Partners', 'INV-1042', DATE '2027-02-05', 1200,
          'demo/' || p1 || '/INV-1042.pdf', 'INV-1042.pdf', 'categorised', u_fin)
  RETURNING id INTO v_invoice;

  INSERT INTO public.payment_approvals (project_id, budget_line_id, vendor_id, amount, payment_kind, status,
                                        requested_by, field_approved_by, field_approved_at, routed_to_user_id)
  VALUES (p1, l_clear, v_vendor, 22000, 'full', 'awaiting_manager',
          u_fm, u_fm, NOW(), u_mgr);

  -- ═══════════════════ PROJECT 2: land, escrows, property tax ═══════════════════
  INSERT INTO public.projects (name, description, city, state, status, start_date, estimated_end_date,
                               created_by, manager_id, field_manager_id, business_entity,
                               long_tail_reserve_amount, budget_status)
  VALUES ('Demo · Land, Escrows & Property Tax',
          'Phased land takedown, a city road escrow (bond), an HOA escrow (cash) and yearly property tax.',
          'O''Fallon', 'MO', 'planning', DATE '2027-01-15', DATE '2028-12-31',
          u_admin, u_mgr, u_xfm, 'bluonx', 20000, 'draft')
  RETURNING id INTO p2;

  INSERT INTO public.budget_lines (project_id, line_type, line_subtype, name, section_name, sort_order,
                                   budget_amount, is_payment_exempt, created_by)
  VALUES (p2, 'land', 'land_purchase', 'Land purchase (100 acres)', 'Land', 10, 400000, TRUE, u_admin)
  RETURNING id INTO l_land;

  INSERT INTO public.budget_lines (project_id, line_type, line_subtype, name, section_name, sort_order,
                                   budget_amount, is_payment_exempt, anticipated_start_date, anticipated_end_date, created_by)
  VALUES
    (p2, 'land',       'earnest_money', 'Earnest money', 'Land',       20, 10000, TRUE,  DATE '2026-12-01', DATE '2026-12-01', u_admin),
    (p2, 'land',       'due_diligence', 'Due diligence', 'Land',       30, 15000, TRUE,  DATE '2026-11-15', DATE '2027-01-10', u_admin),
    (p2, 'impact_fee', NULL,            'Impact fees',   'Soft costs', 60, 20000, FALSE, DATE '2027-03-01', DATE '2027-03-01', u_admin);

  INSERT INTO public.budget_lines (project_id, line_type, line_subtype, name, section_name, sort_order, budget_amount, created_by)
    VALUES (p2, 'long_tail', 'escrow_bond_premium', 'Escrow bond premium — roads', 'Long-tail', 300, 1500, u_admin)
    RETURNING id INTO l_prem;
  INSERT INTO public.budget_lines (project_id, line_type, line_subtype, name, section_name, sort_order, budget_amount, created_by)
    VALUES (p2, 'long_tail', 'escrow_repairs', 'Escrow repairs to city standard — roads', 'Long-tail', 310, 8000, u_admin)
    RETURNING id INTO l_rep;
  INSERT INTO public.budget_lines (project_id, line_type, line_subtype, name, section_name, sort_order, budget_amount, created_by)
    VALUES (p2, 'long_tail', 'property_tax', 'Property tax', 'Long-tail', 320, 12000, u_admin)
    RETURNING id INTO l_tax;
  INSERT INTO public.budget_lines (project_id, line_type, name, section_name, sort_order, budget_amount, is_payment_exempt, created_by)
    VALUES (p2, 'contingency', 'Contingency', 'Contingency', 200, 9000, TRUE, u_admin);

  INSERT INTO public.land_closings (project_id, budget_line_id, closing_sequence, acres, amount, planned_closing_date, created_by)
  VALUES (p2, l_land, 1, 40, 160000, DATE '2027-01-15', u_admin),
         (p2, l_land, 2, 60, 240000, DATE '2028-06-15', u_admin);

  INSERT INTO public.escrows (project_id, name, beneficiary, covered_areas, security_form, holder_type, holder_name,
                              secured_amount, premium_amount, bond_number, bond_expiry_date, status, posted_date,
                              premium_line_id, repair_line_id, created_by)
  VALUES (p2, 'Roads to city', 'city', ARRAY['roads'], 'bond', 'insurance_company', 'Demo Surety Co.',
          100000, 1500, 'BND-DEMO-001', DATE '2028-03-31', 'posted', DATE '2027-04-01',
          l_prem, l_rep, u_admin);

  INSERT INTO public.escrows (project_id, name, beneficiary, covered_areas, security_form, holder_type, holder_name,
                              secured_amount, status, created_by)
  VALUES (p2, 'HOA landscaping, trails & benches', 'hoa', ARRAY['landscaping', 'trails', 'benches'], 'cash',
          'bank', 'Demo Community Bank', 25000, 'planned', u_admin);

  INSERT INTO public.property_taxes (project_id, budget_line_id, tax_year, jurisdiction, installment_number, due_date,
                                     estimate_basis, estimated_amount, created_by)
  VALUES (p2, l_tax, 2027, 'St. Charles County', 1, DATE '2027-12-31', 'assessed_value', 6000, u_admin),
         (p2, l_tax, 2028, 'St. Charles County', 1, DATE '2028-12-31', 'prior_year_actual', 6000, u_admin);

  PERFORM public.fn_baseline_project_budget(p2, u_admin);

  RAISE NOTICE 'Seeded demo projects % and %', p1, p2;
END
$seed$;

COMMIT;

-- Quick look at what was created
SELECT p.name,
       p.budget_status,
       p.approved_budget_total,
       (SELECT budget_amount FROM budget_lines WHERE project_id = p.id AND line_type = 'contingency' AND deleted_at IS NULL) AS contingency_now,
       (SELECT count(*) FROM contingency_ledger WHERE project_id = p.id) AS ledger_rows
  FROM projects p
 WHERE p.name LIKE 'Demo · %'
 ORDER BY p.name;
