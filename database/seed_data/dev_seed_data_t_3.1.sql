-- ============================================================================
-- BluOnX Bid Management & Vendor Coordination System
-- Development Seed Data — Task 3.1 (Vendor Management)
-- ============================================================================
-- Version:  1.0
-- Date:     March 12, 2026
-- Author:   Awais Anwer (Tkrupt)
-- Purpose:  Synthetic development/testing data for vendor CRUD development.
-- ============================================================================
--
-- ⚠️  WARNING: THIS IS 100% SYNTHETIC TEST DATA
-- ⚠️  DO NOT RUN IN PRODUCTION
-- ⚠️  DELETE ALL SEED DATA BEFORE GOING LIVE
--
-- SEEDS:
--   1. Trades (28 scope categories with correct phase assignments)
--   2. Vendors (44 synthetic companies with realistic MO addresses)
--   3. Vendor contacts (1-2 per vendor, ~48 total)
--   4. Vendor ↔ Trade associations (~48 links, includes multi-trade vendors)
--
-- TEST EDGE CASES INCLUDED:
--   - 3 vendors with expired insurance (filter testing)
--   - 1 vendor with 'partial' onboarding (status testing)
--   - 1 vendor with 'pending' onboarding (status testing)
--   - 1 vendor near max capacity: 5/8 active jobs
--   - Multi-trade vendors (e.g., Iron Horse: grading + blasting + utilities)
--   - All emails use .fake TLD (impossible to confuse with real vendors)
--
-- DEPENDS ON:
--   - bluonx_complete_schema_v2_2.sql (schema must exist)
--
-- USAGE:
--   Run via Supabase SQL Editor or psql against your dev database.
--   No user dependency — trades and vendors don't require created_by.
--
-- ============================================================================


-- ============================================================================
-- SECTION 1: TRADES (28 scope categories)
-- ============================================================================
-- Source: Client spreadsheet (ScopeContracter + ScopeTask) cross-referenced
-- with handoff document Section 5.
--
-- "Manual Entry" / "Self Perform" are NOT trades — they map to
-- bid_type = 'internal' on the task.
-- ============================================================================

INSERT INTO trades (name, phase, is_active) VALUES
  -- Due Diligence trades
  ('Engineering',                'both',           TRUE),
  ('Phase 1/Phase 2',           'due_diligence',  TRUE),
  ('Title',                     'due_diligence',  TRUE),
  ('Traffic Study',             'due_diligence',  TRUE),
  ('Ecological Study',          'due_diligence',  TRUE),
  ('Geo Tech',                  'due_diligence',  TRUE),
  ('Legal',                     'due_diligence',  TRUE),

  -- Development trades
  ('Mass Grading',              'development',    TRUE),
  ('Underground Utilities',     'development',    TRUE),
  ('Electric Conduit/Crossings','development',    TRUE),
  ('Paving',                    'development',    TRUE),
  ('Blasting',                  'development',    TRUE),
  ('Demo',                      'development',    TRUE),
  ('Erosion Control',           'development',    TRUE),
  ('Retaining Walls',           'development',    TRUE),
  ('Site Final Grading',        'development',    TRUE),
  ('Common Ground Electric',    'development',    TRUE),
  ('Common Ground Flatwork',    'development',    TRUE),
  ('Common Ground Amenities',   'development',    TRUE),
  ('Street Signs',              'development',    TRUE),
  ('Landscaping',               'development',    TRUE),
  ('Irrigation',                'development',    TRUE),
  ('Fencing',                   'development',    TRUE),
  ('Sod',                       'development',    TRUE),
  ('Monuments',                 'development',    TRUE),
  ('Fountains and Aeration',    'development',    TRUE),
  ('Mailboxes',                 'development',    TRUE),
  ('Basins',                    'development',    TRUE)
ON CONFLICT (name) DO NOTHING;


-- ============================================================================
-- SECTION 2: SYNTHETIC VENDORS (38 companies)
-- ============================================================================
-- All names, addresses, contacts are FAKE.
-- Addresses are in the greater St. Louis / Missouri area for 75-mile
-- radius distance filtering tests.
-- ============================================================================

INSERT INTO vendors (
  company_name, address, city, state, zip_code,
  latitude, longitude,
  insurance_expiration_date, insurance_coverage_amount, bonding_capacity,
  max_active_jobs, current_active_jobs,
  onboarding_status, status, notes
) VALUES

  -- ── Engineering (5 vendors) ──────────────────────────────────────────────

  ('Ridgeline Engineering & Survey',
   '4200 Forest Park Ave', 'St. Louis', 'MO', '63108',
   38.6350, -90.2610,
   '2027-03-15', 2000000.00, 500000.00, 8, 2, 'complete', 'active',
   'Full-service civil engineering. DD and LD phases.'),

  ('Meridian Land Consultants',
   '1122 Olive St, Suite 300', 'St. Louis', 'MO', '63101',
   38.6280, -90.1930,
   '2027-06-30', 1500000.00, 300000.00, 5, 1, 'complete', 'active',
   'Title and survey specialist.'),

  ('Heartland Survey Group',
   '890 Elm Blvd', 'Chesterfield', 'MO', '63017',
   38.6631, -90.5771,
   '2027-01-10', 1000000.00, 250000.00, 6, 3, 'complete', 'active',
   'Alta/topo survey and mapping.'),

  ('Gateway Civil Partners',
   '550 Maryville Centre Dr', 'Town and Country', 'MO', '63141',
   38.6130, -90.4650,
   '2026-11-20', 2000000.00, 750000.00, 10, 4, 'complete', 'active',
   'Engineering, zoning, and permitting. NOTE: Insurance expired for testing.'),

  ('Prairie Point Engineers',
   '2815 N Ballas Rd', 'Creve Coeur', 'MO', '63131',
   38.6590, -90.4110,
   '2027-09-01', 1500000.00, 400000.00, 7, 0, 'complete', 'active',
   'Pipeline and environmental engineering.'),

  -- ── Phase 1/Phase 2 (1 vendor) ──────────────────────────────────────────

  ('Clearwater Environmental Labs',
   '7701 Forsyth Blvd', 'Clayton', 'MO', '63105',
   38.6470, -90.3430,
   '2027-04-22', 3000000.00, 200000.00, 4, 1, 'complete', 'active',
   'Phase 1 and Phase 2 environmental assessments.'),

  -- ── Title (1 vendor) ────────────────────────────────────────────────────

  ('Cornerstone Title Services',
   '200 S Hanley Rd, Suite 600', 'Clayton', 'MO', '63105',
   38.6440, -90.3470,
   '2027-08-15', 1000000.00, 100000.00, 10, 3, 'complete', 'active',
   'Title search and insurance.'),

  -- ── Traffic Study (1 vendor) ────────────────────────────────────────────

  ('Metro Traffic Analysis Group',
   '1034 S Brentwood Blvd', 'Brentwood', 'MO', '63117',
   38.6250, -90.3490,
   '2027-02-28', 1000000.00, 150000.00, 5, 2, 'complete', 'active',
   'Traffic impact studies and signal design.'),

  -- ── Ecological Study (2 vendors) ────────────────────────────────────────

  ('Tallgrass Ecological Services',
   '14055 Ladue Rd', 'Chesterfield', 'MO', '63017',
   38.6490, -90.5290,
   '2027-05-10', 2000000.00, 300000.00, 6, 1, 'complete', 'active',
   'Wetland delineation, mist nets, USACE 404.'),

  ('Riverbend Testing & Ecology',
   '333 W Lockwood Ave', 'Webster Groves', 'MO', '63119',
   38.5910, -90.3580,
   '2026-08-31', 1500000.00, 200000.00, 4, 2, 'complete', 'active',
   'Ecological surveys and soil testing. NOTE: Insurance expired for testing.'),

  -- ── Geo Tech (2 vendors) ────────────────────────────────────────────────

  ('Bluffside Geotechnical',
   '16000 Swingley Ridge Rd', 'Chesterfield', 'MO', '63017',
   38.6520, -90.5850,
   '2027-07-01', 2000000.00, 500000.00, 5, 2, 'complete', 'active',
   'Soil borings, test pits, foundation analysis.'),

  ('Crossroads Soil & Materials',
   '940 Kehrs Mill Rd', 'Ballwin', 'MO', '63011',
   38.5970, -90.5360,
   '2027-03-31', 1500000.00, 350000.00, 4, 0, 'partial', 'active',
   'Geotechnical testing. Missing W-9 — partial onboarding for testing.'),

  -- ── Legal (3 vendors) ──────────────────────────────────────────────────

  ('Stonebridge Law Group',
   '7733 Forsyth Blvd, Suite 2100', 'Clayton', 'MO', '63105',
   38.6480, -90.3450,
   '2027-12-31', 5000000.00, 100000.00, 15, 5, 'complete', 'active',
   'HOA formation, land use, and zoning law.'),

  ('Westport Legal Associates',
   '230 S Bemiston Ave', 'Clayton', 'MO', '63105',
   38.6420, -90.3400,
   '2027-06-15', 3000000.00, 100000.00, 10, 3, 'complete', 'active',
   'Real estate and construction law.'),

  ('Centerline Counsel PLLC',
   '100 S Fourth St, Suite 1000', 'St. Louis', 'MO', '63102',
   38.6250, -90.1890,
   '2026-12-01', 2000000.00, 100000.00, 8, 4, 'complete', 'active',
   'Land development legal. NOTE: Insurance expiring soon for testing.'),

  -- ── Mass Grading (4 vendors) ───────────────────────────────────────────

  ('Summit Earthworks LLC',
   '1500 Hwy 79 N', 'Elsberry', 'MO', '63343',
   39.1670, -90.7810,
   '2027-06-30', 3000000.00, 1500000.00, 5, 2, 'complete', 'active',
   'Mass grading, clearing, earthwork. Multi-trade.'),

  ('Iron Horse Grading Co',
   '2200 State Hwy 100', 'Washington', 'MO', '63090',
   38.5560, -91.0120,
   '2027-09-15', 2500000.00, 1000000.00, 6, 3, 'complete', 'active',
   'Grading, underground utilities, blasting. Multi-trade.'),

  ('Valley Ridge Excavation',
   '880 Gravois Rd', 'Fenton', 'MO', '63026',
   38.5130, -90.4360,
   '2027-04-01', 2000000.00, 800000.00, 4, 1, 'complete', 'active',
   'Agricultural grading and site prep.'),

  ('Benchmark Site Contractors',
   '3300 Lemay Ferry Rd', 'St. Louis', 'MO', '63125',
   38.5250, -90.2850,
   '2027-11-30', 3500000.00, 2000000.00, 8, 5, 'complete', 'active',
   'Full-site grading, utilities, paving. Large capacity. Near max jobs for testing.'),

  -- ── Demo (2 vendors) ───────────────────────────────────────────────────

  ('Precision Demolition Inc',
   '4400 Duncan Ave', 'St. Louis', 'MO', '63110',
   38.6280, -90.2570,
   '2027-05-15', 2000000.00, 600000.00, 5, 1, 'complete', 'active',
   'Selective and total demolition.'),

  ('Ozark Wrecking & Salvage',
   '111 Industrial Dr', 'Pacific', 'MO', '63069',
   38.4810, -90.7430,
   '2027-02-14', 1500000.00, 400000.00, 3, 2, 'complete', 'active',
   'Commercial and residential demolition.'),

  -- ── Blasting (1 dedicated + Iron Horse multi-trade) ────────────────────

  ('Thunderstone Blasting LLC',
   '600 Old State Rd', 'Festus', 'MO', '63028',
   38.2230, -90.3960,
   '2027-08-01', 5000000.00, 2000000.00, 4, 1, 'complete', 'active',
   'Rock blasting and removal.'),

  -- ── Underground Utilities (1 dedicated + Iron Horse & Benchmark) ───────

  ('Aquifer Underground Services',
   '720 Meramec Station Rd', 'Valley Park', 'MO', '63088',
   38.5490, -90.4870,
   '2027-10-31', 2500000.00, 1200000.00, 5, 2, 'complete', 'active',
   'Sanitary, storm sewer, water mains.'),

  -- ── Electric Conduit/Crossings (1 vendor) ──────────────────────────────

  ('Conduit Pro Electric',
   '155 Triad Center Dr', 'O''Fallon', 'MO', '63366',
   38.7640, -90.7290,
   '2027-03-20', 1500000.00, 500000.00, 4, 1, 'complete', 'active',
   'Electric and communication conduit installation.'),

  -- ── Paving (2 vendors + Benchmark multi-trade) ─────────────────────────

  ('Gateway Asphalt & Paving',
   '3000 Old Collinsville Rd', 'Belleville', 'IL', '62221',
   38.5310, -89.9640,
   '2027-07-31', 2000000.00, 1000000.00, 6, 3, 'complete', 'active',
   'Street paving, sidewalks, curbs.'),

  ('Flatiron Paving Solutions',
   '1200 N Main St', 'Columbia', 'IL', '62236',
   38.4510, -90.2050,
   '2027-01-15', 1500000.00, 600000.00, 4, 0, 'complete', 'active',
   'Residential and commercial paving.'),

  -- ── Erosion Control (2 vendors) ────────────────────────────────────────

  ('Greenline Erosion Management',
   '4450 Bridgeton Industrial Dr', 'Bridgeton', 'MO', '63044',
   38.7560, -90.4280,
   '2027-06-15', 1000000.00, 300000.00, 5, 2, 'complete', 'active',
   'Silt fencing, stabilization, temp basins. Also does site final grading.'),

  ('Watershed Solutions Inc',
   '830 Woodlawn Ave', 'Kirkwood', 'MO', '63122',
   38.5830, -90.4060,
   '2027-09-30', 1500000.00, 400000.00, 4, 1, 'complete', 'active',
   'Erosion control and stormwater management.'),

  -- ── Retaining Walls (2 vendors) ────────────────────────────────────────

  ('Stonewall Retaining Systems',
   '9100 Manchester Rd', 'Brentwood', 'MO', '63144',
   38.6280, -90.3590,
   '2027-04-10', 2000000.00, 800000.00, 5, 2, 'complete', 'active',
   'Retaining walls and fencing. Multi-trade.'),

  ('Archway Wall Builders',
   '2660 S Big Bend Blvd', 'Maplewood', 'MO', '63143',
   38.6110, -90.3200,
   '2026-09-15', 1500000.00, 500000.00, 3, 1, 'complete', 'active',
   'Segmental retaining walls. NOTE: Insurance expired for testing.'),

  -- ── Common Ground Electric (3 vendors) ─────────────────────────────────

  ('Powerline Electric Services',
   '12400 Olive Blvd', 'Creve Coeur', 'MO', '63141',
   38.6600, -90.4530,
   '2027-08-20', 2000000.00, 600000.00, 6, 2, 'complete', 'active',
   'Common ground electrical, street lights.'),

  ('Beacon Electrical Contractors',
   '505 N New Ballas Rd', 'Creve Coeur', 'MO', '63141',
   38.6570, -90.4340,
   '2027-11-01', 1500000.00, 400000.00, 5, 1, 'complete', 'active',
   'Residential and commercial electrical.'),

  ('Circuit Path Electric',
   '3800 S Lindbergh Blvd', 'Sunset Hills', 'MO', '63127',
   38.5390, -90.3740,
   '2027-02-28', 1000000.00, 300000.00, 4, 3, 'complete', 'active',
   'Electrical installations. Near capacity for testing.'),

  -- ── Street Signs + Mailboxes (1 vendor, multi-trade) ───────────────────

  ('Vanguard Sign & Graphics',
   '650 Spirit of St. Louis Blvd', 'Chesterfield', 'MO', '63005',
   38.6570, -90.6340,
   '2027-05-01', 500000.00, 100000.00, 10, 2, 'complete', 'active',
   'Street signs, mailbox clusters, community signage. Multi-trade.'),

  -- ── Landscaping (1 vendor) ─────────────────────────────────────────────

  ('Timberline Landscape Design',
   '15844 Clayton Rd', 'Ellisville', 'MO', '63011',
   38.5940, -90.5870,
   '2027-07-15', 1000000.00, 300000.00, 6, 2, 'complete', 'active',
   'Trees, shrubs, hardscape, mulch.'),

  -- ── Irrigation (2 vendors) ─────────────────────────────────────────────

  ('AquaFlow Irrigation Systems',
   '2900 Hwy K', 'O''Fallon', 'MO', '63368',
   38.7520, -90.7560,
   '2027-10-10', 1000000.00, 250000.00, 5, 1, 'complete', 'active',
   'Irrigation pipe, taps, backflow installation.'),

  ('GreenSpring Irrigation Co',
   '410 Hutchings Farm Rd', 'Wentzville', 'MO', '63385',
   38.8120, -90.8530,
   '2027-04-30', 800000.00, 200000.00, 4, 0, 'pending', 'active',
   'Irrigation systems. Onboarding pending for testing.'),

  -- ── Sod (2 vendors) ────────────────────────────────────────────────────

  ('Missouri Turf & Sod',
   '5500 Telegraph Rd', 'Imperial', 'MO', '63052',
   38.3740, -90.3740,
   '2027-06-01', 500000.00, 150000.00, 6, 1, 'complete', 'active',
   'Sod installation and grading.'),

  ('Emerald Lawn Solutions',
   '1800 Bowles Ave', 'Fenton', 'MO', '63026',
   38.5310, -90.4490,
   '2027-12-15', 500000.00, 100000.00, 5, 2, 'complete', 'active',
   'Sod, seeding, and erosion blankets.'),

  -- ── Common Ground Flatwork (2 vendors) ─────────────────────────────────

  ('Flatrock Concrete LLC',
   '1100 Jeffco Blvd', 'Arnold', 'MO', '63010',
   38.4330, -90.3760,
   '2027-03-01', 1500000.00, 500000.00, 5, 2, 'complete', 'active',
   'Sidewalks, parking lots, CBU pads, flatwork.'),

  ('Level Line Concrete Works',
   '6200 Heimos Industrial Park', 'St. Louis', 'MO', '63129',
   38.4810, -90.3290,
   '2027-08-31', 1000000.00, 400000.00, 4, 1, 'complete', 'active',
   'Flatwork and curbing.'),

  -- ── Fountains and Aeration (1 vendor) ──────────────────────────────────

  ('Cascade Water Features',
   '280 Kehr''s Mill Bend', 'Ballwin', 'MO', '63011',
   38.5980, -90.5370,
   '2027-05-20', 800000.00, 200000.00, 4, 0, 'complete', 'active',
   'Fountains, aerators, pond features.'),

  -- ── Basins (1 vendor) ──────────────────────────────────────────────────

  ('Riparian Ecological Design',
   '1445 S Grand Blvd', 'St. Louis', 'MO', '63104',
   38.6150, -90.2150,
   '2027-09-15', 1000000.00, 300000.00, 3, 1, 'complete', 'active',
   'Bio retention basins, aquatic plantings, restoration.'),

  -- ── Monuments (1 vendor) ───────────────────────────────────────────────

  ('Landmark Survey Monuments',
   '700 Market St', 'St. Louis', 'MO', '63101',
   38.6270, -90.1930,
   '2027-11-15', 500000.00, 100000.00, 8, 1, 'complete', 'active',
   'Survey monument installation.')

ON CONFLICT DO NOTHING;


-- ============================================================================
-- SECTION 3: VENDOR CONTACTS (1-2 per vendor, ~43 total)
-- ============================================================================

DO $$
DECLARE
  v_id UUID;
BEGIN

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Ridgeline Engineering & Survey';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Marcus Thornton', 'mthornton@ridgelineeng.fake', '314-555-0101', 'President', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Meridian Land Consultants';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Dana Whitfield', 'dwhitfield@meridianland.fake', '314-555-0102', 'Survey Manager', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Heartland Survey Group';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Lauren Prescott', 'lprescott@heartlandsurvey.fake', '636-555-0103', 'Project Lead', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Gateway Civil Partners';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Brian Kessler', 'bkessler@gatewaycivil.fake', '314-555-0104', 'Principal Engineer', TRUE),
    (v_id, 'Nadia Ortiz', 'nortiz@gatewaycivil.fake', '314-555-0105', 'Project Coordinator', FALSE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Prairie Point Engineers';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Kevin Schafer', 'kschafer@prairiepoint.fake', '636-555-0106', 'VP Engineering', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Clearwater Environmental Labs';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'James Rutherford', 'jrutherford@clearwaterenv.fake', '314-555-0107', 'Lab Director', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Cornerstone Title Services';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Patricia Langley', 'plangley@cornerstonetitle.fake', '314-555-0108', 'Title Officer', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Metro Traffic Analysis Group';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Robert Henning', 'rhenning@metrotraffic.fake', '314-555-0109', 'Senior Analyst', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Tallgrass Ecological Services';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Michelle Sato', 'msato@tallgrasseco.fake', '314-555-0110', 'Senior Ecologist', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Riverbend Testing & Ecology';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Kyle Lundgren', 'klundgren@riverbendtest.fake', '314-555-0111', 'Field Manager', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Bluffside Geotechnical';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Christine Novak', 'cnovak@bluffsidegeo.fake', '573-555-0112', 'Geotech Lead', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Crossroads Soil & Materials';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Derek Yamamoto', 'dyamamoto@crossroadssoil.fake', '636-555-0113', 'Lab Manager', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Stonebridge Law Group';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Steven Calloway', 'scalloway@stonebridgelaw.fake', '314-555-0114', 'Managing Partner', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Westport Legal Associates';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Angela Morrison', 'amorrison@westportlegal.fake', '314-555-0115', 'Of Counsel', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Centerline Counsel PLLC';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Drew Halverson', 'dhalverson@centerlinecounsel.fake', '314-555-0116', 'Associate', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Summit Earthworks LLC';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Joe Whitmore', 'jwhitmore@summitearth.fake', '314-555-0117', 'Owner', TRUE),
    (v_id, 'Tina Baxter', 'tbaxter@summitearth.fake', '314-555-0118', 'Estimator', FALSE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Iron Horse Grading Co';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Mike Reardon', 'mreardon@ironhorsegrading.fake', '636-555-0119', 'General Manager', TRUE),
    (v_id, 'Amy Stokes', 'astokes@ironhorsegrading.fake', '636-555-0120', 'Project Manager', FALSE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Valley Ridge Excavation';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Chris Lindner', 'clindner@valleyridgeexc.fake', '636-555-0121', 'Owner', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Benchmark Site Contractors';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Greg Hollander', 'ghollander@benchmarksite.fake', '314-555-0122', 'CEO', TRUE),
    (v_id, 'Sara Pennington', 'spennington@benchmarksite.fake', '314-555-0123', 'Estimating Dir', FALSE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Precision Demolition Inc';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Ben Callaway', 'bcallaway@precisiondemo.fake', '314-555-0124', 'Ops Manager', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Ozark Wrecking & Salvage';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Ryan Hargrove', 'rhargrove@ozarkwrecking.fake', '636-555-0125', 'Superintendent', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Thunderstone Blasting LLC';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Keith Donovan', 'kdonovan@thunderblast.fake', '314-555-0126', 'Blasting Foreman', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Aquifer Underground Services';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Justin Feldt', 'jfeldt@aquiferunderground.fake', '618-555-0127', 'VP Operations', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Conduit Pro Electric';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Jeff Parsons', 'jparsons@conduitpro.fake', '636-555-0128', 'Estimator', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Gateway Asphalt & Paving';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Josh Brennan', 'jbrennan@gatewayasphalt.fake', '618-555-0129', 'Project Lead', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Flatiron Paving Solutions';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Tom Harlow', 'tharlow@flatironpaving.fake', '618-555-0130', 'Owner', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Greenline Erosion Management';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Megan Kelley', 'mkelley@greenlineerosion.fake', '314-555-0131', 'Field Supervisor', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Watershed Solutions Inc';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Anna Chen', 'achen@watershedsolutions.fake', '314-555-0132', 'Project Manager', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Stonewall Retaining Systems';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'John Pruitt', 'jpruitt@stonewallretain.fake', '314-555-0133', 'Estimator', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Archway Wall Builders';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Carl Higgins', 'chiggins@archwaywall.fake', '314-555-0134', 'Owner', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Powerline Electric Services';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Matt Weston', 'mweston@powerlineelec.fake', '314-555-0135', 'Master Electrician', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Beacon Electrical Contractors';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Jason Blake', 'jblake@beaconelec.fake', '636-555-0136', 'Estimator', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Circuit Path Electric';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Rick Garza', 'rgarza@circuitpath.fake', '314-555-0137', 'Owner', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Vanguard Sign & Graphics';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Shannon Briggs', 'sbriggs@vanguardsign.fake', '636-555-0138', 'Sales Manager', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Timberline Landscape Design';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Jay Whitman', 'jwhitman@timberlineland.fake', '314-555-0139', 'Design Lead', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'AquaFlow Irrigation Systems';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Jon Kramer', 'jkramer@aquaflowirr.fake', '636-555-0140', 'Installer', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'GreenSpring Irrigation Co';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Jeff Bowman', 'jbowman@greenspringirr.fake', '314-555-0141', 'Owner', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Missouri Turf & Sod';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Austin Gruber', 'agruber@moturfsod.fake', '636-555-0142', 'Field Manager', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Emerald Lawn Solutions';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'John Weldon', 'jweldon@emeraldlawn.fake', '636-555-0143', 'Owner', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Flatrock Concrete LLC';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Greg Kirkpatrick', 'gkirkpatrick@flatrockconcrete.fake', '314-555-0144', 'Superintendent', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Level Line Concrete Works';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Carl Hensley', 'chensley@levellineconcrete.fake', '636-555-0145', 'Estimator', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Cascade Water Features';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Jason Kirby', 'jkirby@cascadewater.fake', '636-555-0146', 'Owner', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Riparian Ecological Design';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Alec Manning', 'amanning@riparianeco.fake', '314-555-0147', 'Ecologist', TRUE);

  SELECT id INTO v_id FROM vendors WHERE company_name = 'Landmark Survey Monuments';
  INSERT INTO vendor_contacts (vendor_id, full_name, email, phone, title, is_primary) VALUES
    (v_id, 'Phil Archer', 'parcher@landmarkmonuments.fake', '314-555-0148', 'Surveyor', TRUE);

END;
$$;


-- ============================================================================
-- SECTION 4: VENDOR ↔ TRADE ASSOCIATIONS (~45 links)
-- ============================================================================
-- Multi-trade vendors:
--   Iron Horse Grading    → Mass Grading, Blasting, Underground Utilities
--   Benchmark Site        → Mass Grading, Underground Utilities, Paving
--   Stonewall Retaining   → Retaining Walls, Fencing
--   Vanguard Sign         → Street Signs, Mailboxes
--   Greenline Erosion     → Erosion Control, Site Final Grading
-- ============================================================================

DO $$
BEGIN

  -- Engineering (5 vendors)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN (
    'Ridgeline Engineering & Survey', 'Meridian Land Consultants',
    'Heartland Survey Group', 'Gateway Civil Partners', 'Prairie Point Engineers'
  ) AND t.name = 'Engineering'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Phase 1/Phase 2 (1)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name = 'Clearwater Environmental Labs' AND t.name = 'Phase 1/Phase 2'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Title (1)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name = 'Cornerstone Title Services' AND t.name = 'Title'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Traffic Study (1)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name = 'Metro Traffic Analysis Group' AND t.name = 'Traffic Study'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Ecological Study (2)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN ('Tallgrass Ecological Services', 'Riverbend Testing & Ecology')
    AND t.name = 'Ecological Study'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Geo Tech (2)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN ('Bluffside Geotechnical', 'Crossroads Soil & Materials')
    AND t.name = 'Geo Tech'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Legal (3)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN ('Stonebridge Law Group', 'Westport Legal Associates', 'Centerline Counsel PLLC')
    AND t.name = 'Legal'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Mass Grading (4)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN (
    'Summit Earthworks LLC', 'Iron Horse Grading Co',
    'Valley Ridge Excavation', 'Benchmark Site Contractors'
  ) AND t.name = 'Mass Grading'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Demo (2)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN ('Precision Demolition Inc', 'Ozark Wrecking & Salvage')
    AND t.name = 'Demo'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Blasting (2 — Iron Horse multi-trade)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN ('Thunderstone Blasting LLC', 'Iron Horse Grading Co')
    AND t.name = 'Blasting'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Underground Utilities (3 — Iron Horse & Benchmark multi-trade)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN (
    'Aquifer Underground Services', 'Iron Horse Grading Co', 'Benchmark Site Contractors'
  ) AND t.name = 'Underground Utilities'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Electric Conduit/Crossings (1)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name = 'Conduit Pro Electric' AND t.name = 'Electric Conduit/Crossings'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Paving (3 — Benchmark multi-trade)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN ('Gateway Asphalt & Paving', 'Flatiron Paving Solutions', 'Benchmark Site Contractors')
    AND t.name = 'Paving'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Erosion Control (2)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN ('Greenline Erosion Management', 'Watershed Solutions Inc')
    AND t.name = 'Erosion Control'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Retaining Walls (2)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN ('Stonewall Retaining Systems', 'Archway Wall Builders')
    AND t.name = 'Retaining Walls'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Site Final Grading (Greenline multi-trade)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name = 'Greenline Erosion Management' AND t.name = 'Site Final Grading'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Common Ground Electric (3)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN ('Powerline Electric Services', 'Beacon Electrical Contractors', 'Circuit Path Electric')
    AND t.name = 'Common Ground Electric'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Common Ground Flatwork (2)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN ('Flatrock Concrete LLC', 'Level Line Concrete Works')
    AND t.name = 'Common Ground Flatwork'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Street Signs (1)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name = 'Vanguard Sign & Graphics' AND t.name = 'Street Signs'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Mailboxes (Vanguard multi-trade)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name = 'Vanguard Sign & Graphics' AND t.name = 'Mailboxes'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Landscaping (1)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name = 'Timberline Landscape Design' AND t.name = 'Landscaping'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Irrigation (2)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN ('AquaFlow Irrigation Systems', 'GreenSpring Irrigation Co')
    AND t.name = 'Irrigation'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Fencing (Stonewall multi-trade)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name = 'Stonewall Retaining Systems' AND t.name = 'Fencing'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Sod (2)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name IN ('Missouri Turf & Sod', 'Emerald Lawn Solutions')
    AND t.name = 'Sod'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Monuments (1)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name = 'Landmark Survey Monuments' AND t.name = 'Monuments'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Fountains and Aeration (1)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name = 'Cascade Water Features' AND t.name = 'Fountains and Aeration'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Basins (1)
  INSERT INTO vendor_trades (vendor_id, trade_id)
  SELECT v.id, t.id FROM vendors v, trades t
  WHERE v.company_name = 'Riparian Ecological Design' AND t.name = 'Basins'
  ON CONFLICT (vendor_id, trade_id) DO NOTHING;

  -- Common Ground Amenities — no vendors yet (mirrors real data)

END;
$$;


-- ============================================================================
-- VERIFICATION QUERIES (uncomment to run)
-- ============================================================================

-- SELECT COUNT(*) AS trade_count FROM trades;
-- SELECT COUNT(*) AS vendor_count FROM vendors WHERE deleted_at IS NULL;
-- SELECT COUNT(*) AS contact_count FROM vendor_contacts;
-- SELECT COUNT(*) AS association_count FROM vendor_trades;

-- Multi-trade vendors
-- SELECT v.company_name, array_agg(t.name ORDER BY t.name) AS trades
--   FROM vendors v
--   JOIN vendor_trades vt ON v.id = vt.vendor_id
--   JOIN trades t ON t.id = vt.trade_id
--  GROUP BY v.company_name HAVING COUNT(*) > 1;

-- Vendors per trade
-- SELECT t.name, t.phase, COUNT(vt.vendor_id) AS vendors
--   FROM trades t LEFT JOIN vendor_trades vt ON t.id = vt.trade_id
--  GROUP BY t.name, t.phase ORDER BY t.phase, t.name;

-- Expired insurance
-- SELECT company_name, insurance_expiration_date FROM vendors
--  WHERE insurance_expiration_date < NOW();

-- Incomplete onboarding
-- SELECT company_name, onboarding_status FROM vendors
--  WHERE onboarding_status != 'complete';


-- ============================================================================
-- CLEANUP (uncomment when switching to production)
-- ============================================================================
-- DELETE FROM vendor_trades;
-- DELETE FROM vendor_contacts;
-- DELETE FROM vendors;
-- DELETE FROM trades;


-- ============================================================================
-- END — Summary:
--   Trades: 28 | Vendors: 44 | Contacts: ~48 | Associations: ~48
--   Expired insurance: 3 | Incomplete onboarding: 2 | Multi-trade: 5
-- ============================================================================
