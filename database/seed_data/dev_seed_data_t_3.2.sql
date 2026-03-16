-- ============================================================================
-- BluOnX Bid Management & Vendor Coordination System
-- Development Seed Data — Task 3.2 (Project Management)
-- ============================================================================
-- Version:  1.0
-- Date:     March 16, 2026
-- Author:   Awais Anwer (Tkrupt)
-- Purpose:  Synthetic project data for project CRUD development and testing.
-- ============================================================================
--
-- ⚠️  WARNING: THIS IS 100% SYNTHETIC TEST DATA
-- ⚠️  DO NOT RUN IN PRODUCTION
--
-- SEEDS:
--   6 projects covering all 5 statuses + budget/date variety
--
-- TEST EDGE CASES:
--   - All 5 statuses represented (planning, active, on_hold, completed, cancelled)
--   - Budget range from $85K to $4.2M
--   - One project with no budget (NULL — early planning stage)
--   - One completed project with past dates
--   - One cancelled project
--   - Addresses in MO/IL area within 75-mile radius of seed vendors
--   - 2 active projects for typical working-state testing
--
-- DEPENDS ON:
--   - bluonx_complete_schema_v2_2.sql (schema must exist)
--   - dev_seed_data_t_3.1.sql (trades + vendors should be seeded first)
--   - Test user must exist: d2c3a2ed-2443-4c47-a46b-2db3b4b60c73
--
-- NO project_documents seeded — those are uploaded via UI (Task 3.4).
--
-- ============================================================================
 
 
INSERT INTO projects (
  name, description, address, city, state, zip_code,
  latitude, longitude,
  budget, status, start_date, estimated_end_date,
  created_by
) VALUES
 
  -- ── Active projects (2) — typical working state ────────────────────────
 
  ('Sunset Hills Phase 2',
   'Single-family residential development. 120 lots across 85 acres. Full infrastructure including roads, utilities, grading, and common ground amenities.',
   '3400 Gravois Rd', 'Sunset Hills', 'MO', '63127',
   38.5380, -90.4070,
   2500000.00, 'active', '2026-03-01', '2026-09-30',
   'd2c3a2ed-2443-4c47-a46b-2db3b4b60c73'),
 
  ('Wildwood Creek Estates',
   'Luxury residential subdivision. 45 lots on 60 acres with significant rock removal and retaining wall work. Includes community pool and clubhouse site prep.',
   '18200 Manchester Rd', 'Wildwood', 'MO', '63038',
   38.5830, -90.6630,
   4200000.00, 'active', '2026-02-15', '2026-12-15',
   'd2c3a2ed-2443-4c47-a46b-2db3b4b60c73'),
 
  -- ── Planning (1) — early stage, no budget yet ──────────────────────────
 
  ('Chesterfield Commons',
   'Mixed-use development near Chesterfield Valley. Early due diligence phase — environmental and geotech studies pending.',
   '200 THF Blvd', 'Chesterfield', 'MO', '63005',
   38.6630, -90.6050,
   NULL, 'planning', NULL, NULL,
   'd2c3a2ed-2443-4c47-a46b-2db3b4b60c73'),
 
  -- ── On hold (1) — paused mid-project ───────────────────────────────────
 
  ('Eureka Ridge Development',
   'Residential subdivision paused due to permitting delays with the city. Phase 1 grading complete, Phase 2 on hold.',
   '5 Dreyer Ave', 'Eureka', 'MO', '63025',
   38.5020, -90.6280,
   1200000.00, 'on_hold', '2025-11-01', '2026-06-30',
   'd2c3a2ed-2443-4c47-a46b-2db3b4b60c73'),
 
  -- ── Completed (1) — past dates, for history/filter testing ─────────────
 
  ('Arnold Station Townhomes',
   'Townhome community infrastructure. 32 units. All milestones completed, final grading and sod done. Closeout complete.',
   '1350 Jeffco Blvd', 'Arnold', 'MO', '63010',
   38.4320, -90.3780,
   850000.00, 'completed', '2025-06-01', '2025-12-15',
   'd2c3a2ed-2443-4c47-a46b-2db3b4b60c73'),
 
  -- ── Cancelled (1) — for status filter testing ──────────────────────────
 
  ('Wentzville North Commercial',
   'Commercial pad site prep. Cancelled after buyer backed out during due diligence.',
   '1001 Pearce Blvd', 'Wentzville', 'MO', '63385',
   38.8110, -90.8530,
   85000.00, 'cancelled', '2025-09-01', '2025-11-30',
   'd2c3a2ed-2443-4c47-a46b-2db3b4b60c73')
 
ON CONFLICT DO NOTHING;
 
 
-- ============================================================================
-- VERIFICATION QUERIES (uncomment to run)
-- ============================================================================
 
-- Project count (expect 6)
-- SELECT COUNT(*) AS project_count FROM projects WHERE deleted_at IS NULL;
 
-- Status distribution
-- SELECT status, COUNT(*) FROM projects WHERE deleted_at IS NULL GROUP BY status;
 
-- Budget range
-- SELECT name, status, budget, start_date, estimated_end_date FROM projects
--  WHERE deleted_at IS NULL ORDER BY status, name;
 
 
-- ============================================================================
-- CLEANUP (uncomment when switching to production)
-- ============================================================================
-- DELETE FROM projects;
 
 
-- ============================================================================
-- END — Summary:
--   Projects: 6 (2 active, 1 planning, 1 on_hold, 1 completed, 1 cancelled)
--   Budget range: $85K – $4.2M (1 NULL for early planning)
--   Locations: All MO, within 75mi of seed vendors
-- ============================================================================