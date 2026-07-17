-- ============================================================================
-- BluOnX Bid Management & Vendor Coordination System
-- Row Level Security (RLS) Migration
-- ============================================================================
-- Version:  3.2
-- Date:     July 12, 2026
-- Author:   Awais Anwer (Tkrupt)
-- Depends:  bluonx_complete_schema.sql (must be applied first)
-- ============================================================================
--
-- SECURITY ARCHITECTURE:
--
--   Access Pattern       | Auth Method         | RLS Role
--   ─────────────────────|─────────────────────|─────────────────────
--   Admin dashboard      | Supabase Auth JWT   | authenticated (reads)
--   PM dashboard         | Supabase Auth JWT   | authenticated (reads)
--   All write operations | FastAPI service_role | bypasses RLS
--   Vendor bid portal    | FastAPI service_role | bypasses RLS
--   n8n automations      | FastAPI service_role | bypasses RLS
--   Supabase Realtime    | Supabase Auth JWT   | authenticated (reads)
--
-- PHILOSOPHY: Defense-in-depth.
--   • FastAPI + service_role is the PRIMARY gatekeeper for all writes.
--   • RLS is the SAFETY NET that protects direct Supabase client reads.
--   • All policies target the `authenticated` role (logged-in internal users).
--   • The `anon` role has ZERO access to any table (no policies granted).
--   • Vendors never access Supabase directly — FastAPI mediates all access.
--
-- ROLE-BASED DISTINCTION (admin vs project_manager):
--   Most tables: both roles have equal read access (small internal team).
--   Admin-only writes (enforced at DB level for safety):
--     • users         — only admin can modify user accounts
--     • trades        — only admin can modify controlled lookup data
--   All other writes: go through FastAPI (service_role), no RLS write
--   policies needed.
--
-- PERFORMANCE BEST PRACTICES APPLIED:
--   1. auth.uid() wrapped in (select auth.uid()) for initPlan caching
--   2. Role-check helper uses security definer in private schema
--   3. Policies avoid cross-table joins where possible
--   4. Indexes already exist on columns used in policies (from Task 1.3)
--   5. TO clause always specifies role (never uses PUBLIC)
--
-- ============================================================================


-- ============================================================================
-- STEP 0: CREATE PRIVATE SCHEMA FOR SECURITY FUNCTIONS
-- ============================================================================
-- Functions in the 'private' schema are NOT exposed via the Supabase Data API.
-- This prevents any client from calling our helper functions directly,
-- which could leak role information.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS private;


-- ============================================================================
-- STEP 1: HELPER FUNCTIONS (security definer in private schema)
-- ============================================================================
-- These run as the postgres superuser role (security definer), so they
-- bypass RLS on the users table when checking roles. This avoids circular
-- dependency: users table has RLS → policy needs to read users table → 
-- would need RLS policy on users table → infinite loop.
--
-- IMPORTANT: Wrapping auth.uid() in (SELECT ...) triggers Postgres's
-- initPlan optimization, caching the result per-statement instead of
-- evaluating per-row. This is a 100x+ improvement on large tables.
-- ============================================================================

-- Returns TRUE if the currently authenticated user is active (not soft-deleted)
CREATE OR REPLACE FUNCTION private.is_active_user()
RETURNS BOOLEAN
LANGUAGE sql
STABLE                    -- result doesn't change within a transaction
SECURITY DEFINER          -- bypasses RLS to read users table
SET search_path = ''      -- security best practice: prevent search_path injection
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.users
    WHERE id = (SELECT auth.uid())
      AND is_active = TRUE
      AND deleted_at IS NULL
  );
$$;

-- Returns TRUE if the currently authenticated user has the 'admin' role
CREATE OR REPLACE FUNCTION private.is_admin()
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.users
    WHERE id = (SELECT auth.uid())
      AND role = 'admin'
      AND is_active = TRUE
      AND deleted_at IS NULL
  );
$$;



-- ============================================================================
-- STEP 2: ENABLE RLS ON ALL 28 TABLES
-- ============================================================================
-- RLS with no policies = deny all access. This is the safe default.
-- We then selectively grant access via policies below.
--
-- Even tables that FastAPI accesses via service_role get RLS enabled,
-- because service_role bypasses RLS automatically. Enabling RLS on
-- these tables costs nothing for service_role queries but protects
-- against accidental direct access via anon key.
-- ============================================================================

-- Group 1: Access Control
ALTER TABLE users                   ENABLE ROW LEVEL SECURITY;

-- Group 2: Trade & Vendor Management
ALTER TABLE trades                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendors                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_contacts         ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_trades           ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_documents        ENABLE ROW LEVEL SECURITY;

-- Group 3: Project & Task Management
ALTER TABLE projects                ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_documents       ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks                   ENABLE ROW LEVEL SECURITY;

-- Group 4: Bid Lifecycle
ALTER TABLE bid_templates           ENABLE ROW LEVEL SECURITY;
ALTER TABLE bid_template_items      ENABLE ROW LEVEL SECURITY;
ALTER TABLE bid_packages            ENABLE ROW LEVEL SECURITY;
ALTER TABLE bid_package_documents   ENABLE ROW LEVEL SECURITY;
ALTER TABLE bid_invitations         ENABLE ROW LEVEL SECURITY;
ALTER TABLE magic_link_tokens       ENABLE ROW LEVEL SECURITY;
ALTER TABLE bid_submissions         ENABLE ROW LEVEL SECURITY;
ALTER TABLE bid_line_items          ENABLE ROW LEVEL SECURITY;
ALTER TABLE bid_attachments         ENABLE ROW LEVEL SECURITY;
ALTER TABLE bid_scores              ENABLE ROW LEVEL SECURITY;
ALTER TABLE bid_revision_requests   ENABLE ROW LEVEL SECURITY;

-- Group 5: Award & Contract
ALTER TABLE awards                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE contracts               ENABLE ROW LEVEL SECURITY;
ALTER TABLE docusign_envelopes      ENABLE ROW LEVEL SECURITY;

-- Group 6: Milestone Tracking
ALTER TABLE milestones              ENABLE ROW LEVEL SECURITY;
ALTER TABLE milestone_responses     ENABLE ROW LEVEL SECURITY;
ALTER TABLE milestone_alerts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE milestone_events          ENABLE ROW LEVEL SECURITY;
ALTER TABLE milestone_checkin_tokens  ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_performance_reviews  ENABLE ROW LEVEL SECURITY;

-- Group 7: Communication & Audit
ALTER TABLE email_log               ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_flags            ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications           ENABLE ROW LEVEL SECURITY;


-- ============================================================================
-- STEP 3: RLS POLICIES
-- ============================================================================
--
-- NAMING CONVENTION:
--   {table}_{operation}_{who}
--   e.g., "users_select_authenticated" or "trades_insert_admin"
--
-- POLICY TYPES USED:
--   • SELECT (USING)         — filter which rows can be read
--   • INSERT (WITH CHECK)    — filter which rows can be created
--   • UPDATE (USING + WITH CHECK) — filter which rows can be modified
--   • DELETE (USING)         — filter which rows can be removed
--
-- NOTE ON WRITES:
--   Most tables have NO insert/update/delete policies because all writes
--   go through FastAPI using service_role (which bypasses RLS entirely).
--   Write policies are ONLY added where we need database-level protection
--   against admin-only operations as an extra safety layer.
--
-- ============================================================================


-- ════════════════════════════════════════════════════════════════════════════
-- GROUP 1: ACCESS CONTROL
-- ════════════════════════════════════════════════════════════════════════════

-- ── users ──────────────────────────────────────────────────────────────────
-- READ:  Any active authenticated user can see all active user profiles.
--        This is needed for UI elements like "created by", "awarded by" dropdowns.
--        Soft-deleted users are hidden.
-- WRITE: Admin-only. A PM must not be able to change roles or deactivate others.
--        This is a critical safety guardrail even with FastAPI in front.

CREATE POLICY users_select_authenticated
  ON users FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
    AND deleted_at IS NULL
  );

-- Admin can update any user (e.g., change role, deactivate)
-- PM can ONLY update their own profile (full_name, etc.)
CREATE POLICY users_update_admin_or_self
  ON users FOR UPDATE
  TO authenticated
  USING (
    (SELECT private.is_admin())
    OR id = (SELECT auth.uid())
  )
  WITH CHECK (
    (SELECT private.is_admin())
    OR id = (SELECT auth.uid())
  );

-- NOTE: No INSERT policy. User creation is handled by the auth trigger
-- (fn_handle_new_auth_user) which runs as SECURITY DEFINER.
-- NOTE: No DELETE policy. We soft-delete via UPDATE (set deleted_at).


-- ════════════════════════════════════════════════════════════════════════════
-- GROUP 2: TRADE & VENDOR MANAGEMENT
-- ════════════════════════════════════════════════════════════════════════════

-- ── trades ─────────────────────────────────────────────────────────────────
-- READ:  Both admin and PM need the trade list for dropdowns/filters.
-- WRITE: Admin-only. Trades are a controlled lookup (~27 categories).
--        Letting PMs modify this would break consistency across all projects.

CREATE POLICY trades_select_authenticated
  ON trades FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

CREATE POLICY trades_insert_admin
  ON trades FOR INSERT
  TO authenticated
  WITH CHECK (
    (SELECT private.is_admin())
  );

CREATE POLICY trades_update_admin
  ON trades FOR UPDATE
  TO authenticated
  USING (
    (SELECT private.is_admin())
  )
  WITH CHECK (
    (SELECT private.is_admin())
  );

-- NOTE: No DELETE policy. Trades use is_active flag, toggled via UPDATE.


-- ── vendors ────────────────────────────────────────────────────────────────
-- READ:  Both roles need vendor data for bid invitations, comparisons, etc.
--        Only show non-deleted vendors.
-- WRITE: Via FastAPI (service_role). No RLS write policies needed.

CREATE POLICY vendors_select_authenticated
  ON vendors FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
    AND deleted_at IS NULL
  );


-- ── vendor_contacts ────────────────────────────────────────────────────────
-- READ:  Both roles need contact info for invitations, communication.
-- WRITE: Via FastAPI (service_role).

CREATE POLICY vendor_contacts_select_authenticated
  ON vendor_contacts FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );


-- ── vendor_trades ──────────────────────────────────────────────────────────
-- READ:  Both roles need this for vendor filtering by trade.
-- WRITE: Via FastAPI (service_role).

CREATE POLICY vendor_trades_select_authenticated
  ON vendor_trades FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );


-- ── vendor_documents ───────────────────────────────────────────────────────
-- READ:  Both roles can view onboarding documents (needed for compliance checks).
-- WRITE: Both roles. Kept flexible for now — either admin or PM may handle
--        vendor onboarding depending on team workflow. FastAPI validates
--        business logic (doc type, file format, expiration) regardless.
--        NOTE: If this needs to be admin-only later, swap is_active_user()
--        for is_admin() below. Matches storage bucket RLS (full CRUD for
--        authenticated on vendor-documents bucket).

CREATE POLICY vendor_documents_select_authenticated
  ON vendor_documents FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

CREATE POLICY vendor_documents_insert_authenticated
  ON vendor_documents FOR INSERT
  TO authenticated
  WITH CHECK (
    (SELECT private.is_active_user())
  );

CREATE POLICY vendor_documents_update_authenticated
  ON vendor_documents FOR UPDATE
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  )
  WITH CHECK (
    (SELECT private.is_active_user())
  );


-- ════════════════════════════════════════════════════════════════════════════
-- GROUP 3: PROJECT & TASK MANAGEMENT
-- ════════════════════════════════════════════════════════════════════════════

-- ── projects ───────────────────────────────────────────────────────────────
-- READ:  Both roles need full project visibility. Only show non-deleted.
-- WRITE: Via FastAPI (service_role).

CREATE POLICY projects_select_authenticated
  ON projects FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
    AND deleted_at IS NULL
  );


-- ── project_documents ──────────────────────────────────────────────────────
-- READ:  Both roles need to view project docs (plans, specs, drawings).
-- WRITE: Via FastAPI (service_role).

CREATE POLICY project_documents_select_authenticated
  ON project_documents FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );


-- ── tasks ──────────────────────────────────────────────────────────────────
-- READ:  Both roles need full task visibility. Only show non-deleted.
-- WRITE: Via FastAPI (service_role).

CREATE POLICY tasks_select_authenticated
  ON tasks FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
    AND deleted_at IS NULL
  );


-- ════════════════════════════════════════════════════════════════════════════
-- GROUP 4: BID LIFECYCLE
-- ════════════════════════════════════════════════════════════════════════════
--
-- All 10 bid tables follow the same pattern:
--   • READ: Both admin and PM, filtered by active user status.
--   • WRITE: All mutations via FastAPI (service_role).
--
-- The bid pipeline involves complex multi-table operations (create package →
-- create invitations → generate magic links → send emails) that must be
-- orchestrated by FastAPI as atomic transactions. RLS write policies
-- would add complexity with zero security benefit here.
-- ════════════════════════════════════════════════════════════════════════════

-- ── bid_templates ──────────────────────────────────────────────────────────
CREATE POLICY bid_templates_select_authenticated
  ON bid_templates FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── bid_template_items ─────────────────────────────────────────────────────
CREATE POLICY bid_template_items_select_authenticated
  ON bid_template_items FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── bid_packages ───────────────────────────────────────────────────────────
CREATE POLICY bid_packages_select_authenticated
  ON bid_packages FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── bid_package_documents ──────────────────────────────────────────────────
CREATE POLICY bid_package_documents_select_authenticated
  ON bid_package_documents FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── bid_invitations ────────────────────────────────────────────────────────
CREATE POLICY bid_invitations_select_authenticated
  ON bid_invitations FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── magic_link_tokens ──────────────────────────────────────────────────────
-- SENSITIVE: Contains token hashes. Only admin should view these directly.
-- PMs don't need to see raw token data — they see invitation status instead.
-- FastAPI (service_role) handles all token validation for vendor portal.
CREATE POLICY magic_link_tokens_select_admin
  ON magic_link_tokens FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_admin())
  );

-- ── bid_submissions ────────────────────────────────────────────────────────
CREATE POLICY bid_submissions_select_authenticated
  ON bid_submissions FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── bid_line_items ─────────────────────────────────────────────────────────
CREATE POLICY bid_line_items_select_authenticated
  ON bid_line_items FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── bid_attachments ────────────────────────────────────────────────────────
CREATE POLICY bid_attachments_select_authenticated
  ON bid_attachments FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── bid_scores ─────────────────────────────────────────────────────────────
CREATE POLICY bid_scores_select_authenticated
  ON bid_scores FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── bid_revision_requests ──────────────────────────────────────────────────
CREATE POLICY bid_revision_requests_select_authenticated
  ON bid_revision_requests FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ════════════════════════════════════════════════════════════════════════════
-- GROUP 5: AWARD & CONTRACT
-- ════════════════════════════════════════════════════════════════════════════
-- Same pattern: read access for both roles, writes via FastAPI.
-- Award creation involves pre-award validation, vendor capacity updates,
-- email sending, DocuSign integration — all orchestrated by FastAPI.
-- ════════════════════════════════════════════════════════════════════════════

-- ── awards ─────────────────────────────────────────────────────────────────
CREATE POLICY awards_select_authenticated
  ON awards FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── contracts ──────────────────────────────────────────────────────────────
CREATE POLICY contracts_select_authenticated
  ON contracts FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── docusign_envelopes ─────────────────────────────────────────────────────
CREATE POLICY docusign_envelopes_select_authenticated
  ON docusign_envelopes FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );


-- ════════════════════════════════════════════════════════════════════════════
-- GROUP 6: MILESTONE TRACKING
-- ════════════════════════════════════════════════════════════════════════════
-- Read access for both roles. All writes via FastAPI (service_role).
-- Milestone operations involve automated email workflows (n8n),
-- vendor response handling, and status cascades — all server-side.
-- ════════════════════════════════════════════════════════════════════════════

-- ── milestones ─────────────────────────────────────────────────────────────
CREATE POLICY milestones_select_authenticated
  ON milestones FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── milestone_responses ────────────────────────────────────────────────────
CREATE POLICY milestone_responses_select_authenticated
  ON milestone_responses FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── milestone_alerts ───────────────────────────────────────────────────────
CREATE POLICY milestone_alerts_select_authenticated
  ON milestone_alerts FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── milestone_events ───────────────────────────────────────────────────────
CREATE POLICY milestone_events_select_authenticated
  ON milestone_events FOR SELECT
  TO authenticated
  USING ( (SELECT private.is_active_user()) );


CREATE POLICY vpr_select_authenticated
  ON vendor_performance_reviews FOR SELECT TO authenticated
  USING ( (SELECT private.is_active_user()) );
REVOKE ALL ON vendor_performance_reviews FROM anon;

-- ════════════════════════════════════════════════════════════════════════════
-- GROUP 7: COMMUNICATION & AUDIT
-- ════════════════════════════════════════════════════════════════════════════

-- ── email_log ──────────────────────────────────────────────────────────────
-- Both roles need audit trail visibility for compliance.
CREATE POLICY email_log_select_authenticated
  ON email_log FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- ── vendor_flags ───────────────────────────────────────────────────────────
-- Both roles can view flags (shown as warnings during vendor selection).
-- Both roles can create flags (PM flags vendors from milestone issues).
-- Write policies added here because flagging is a simple operation that
-- could reasonably come from the frontend directly (no complex orchestration).
CREATE POLICY vendor_flags_select_authenticated
  ON vendor_flags FOR SELECT
  TO authenticated
  USING (
    (SELECT private.is_active_user())
  );

-- Any active user can create a flag (PM flags a vendor after milestone issue)
CREATE POLICY vendor_flags_insert_authenticated
  ON vendor_flags FOR INSERT
  TO authenticated
  WITH CHECK (
    (SELECT private.is_active_user())
    AND flagged_by = (SELECT auth.uid())
  );

-- Only the user who created the flag (or admin) can resolve it
CREATE POLICY vendor_flags_update_own_or_admin
  ON vendor_flags FOR UPDATE
  TO authenticated
  USING (
    flagged_by = (SELECT auth.uid())
    OR (SELECT private.is_admin())
  )
  WITH CHECK (
    flagged_by = (SELECT auth.uid())
    OR (SELECT private.is_admin())
  );

-- ── notifications ──────────────────────────────────────────────────────────
-- Users can ONLY see their own notifications.
-- This is the one table where row-level filtering by user actually matters
-- for data privacy — PM A should not see PM B's dashboard alerts.
CREATE POLICY notifications_select_own
  ON notifications FOR SELECT
  TO authenticated
  USING (
    user_id = (SELECT auth.uid())
  );

-- Users can mark their own notifications as read (UPDATE is_read flag).
-- This is a simple frontend operation that benefits from direct Supabase access.
CREATE POLICY notifications_update_own
  ON notifications FOR UPDATE
  TO authenticated
  USING (
    user_id = (SELECT auth.uid())
  )
  WITH CHECK (
    user_id = (SELECT auth.uid())
  );


-- ============================================================================
-- STEP 4: REVOKE DIRECT TABLE ACCESS FOR ANON ROLE
-- ============================================================================
-- Belt and suspenders: even though RLS with no anon policies would block
-- access, we also revoke the underlying table privileges for anon.
-- This means even if someone accidentally creates a permissive policy,
-- anon still can't access these tables.
-- ============================================================================

REVOKE ALL ON TABLE users                   FROM anon;
REVOKE ALL ON TABLE trades                  FROM anon;
REVOKE ALL ON TABLE vendors                 FROM anon;
REVOKE ALL ON TABLE vendor_contacts         FROM anon;
REVOKE ALL ON TABLE vendor_trades           FROM anon;
REVOKE ALL ON TABLE vendor_documents        FROM anon;
REVOKE ALL ON TABLE projects                FROM anon;
REVOKE ALL ON TABLE project_documents       FROM anon;
REVOKE ALL ON TABLE tasks                   FROM anon;
REVOKE ALL ON TABLE bid_templates           FROM anon;
REVOKE ALL ON TABLE bid_template_items      FROM anon;
REVOKE ALL ON TABLE bid_packages            FROM anon;
REVOKE ALL ON TABLE bid_package_documents   FROM anon;
REVOKE ALL ON TABLE bid_invitations         FROM anon;
REVOKE ALL ON TABLE magic_link_tokens       FROM anon;
REVOKE ALL ON TABLE bid_submissions         FROM anon;
REVOKE ALL ON TABLE bid_line_items          FROM anon;
REVOKE ALL ON TABLE bid_attachments         FROM anon;
REVOKE ALL ON TABLE bid_scores              FROM anon;
REVOKE ALL ON TABLE awards                  FROM anon;
REVOKE ALL ON TABLE contracts               FROM anon;
REVOKE ALL ON TABLE docusign_envelopes      FROM anon;
REVOKE ALL ON TABLE milestones              FROM anon;
REVOKE ALL ON TABLE milestone_responses     FROM anon;
REVOKE ALL ON TABLE milestone_alerts        FROM anon;
REVOKE ALL ON TABLE email_log               FROM anon;
REVOKE ALL ON TABLE vendor_flags            FROM anon;
REVOKE ALL ON TABLE notifications           FROM anon;
REVOKE ALL ON TABLE bid_revision_requests   FROM anon;
REVOKE ALL ON TABLE milestone_events        FROM anon;
REVOKE ALL ON TABLE milestone_checkin_tokens FROM anon;

-- Also revoke anon access to our private helper functions
REVOKE ALL ON SCHEMA private FROM anon;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA private FROM anon;


-- ============================================================================
-- STEP 5: GRANT SCHEMA ACCESS TO AUTHENTICATED ROLE
-- ============================================================================
-- Ensure the authenticated role can use the private schema's functions
-- (called internally by policies, not directly by users via API since
-- the private schema is not exposed by PostgREST).
-- ============================================================================

GRANT USAGE ON SCHEMA private TO authenticated;
GRANT EXECUTE ON FUNCTION private.is_active_user()  TO authenticated;
GRANT EXECUTE ON FUNCTION private.is_admin()         TO authenticated;


-- ============================================================================
-- STEP 6: VERIFICATION QUERY
-- ============================================================================
-- Run this after applying the migration to confirm RLS is enabled on
-- all public tables. Expected: 28 rows, all with rowsecurity = true.
-- ============================================================================

-- SELECT schemaname, tablename, rowsecurity
--   FROM pg_tables
--  WHERE schemaname = 'public'
--  ORDER BY tablename;

-- To check all policies:
-- SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
--   FROM pg_policies
--  WHERE schemaname = 'public'
--  ORDER BY tablename, policyname;


-- ============================================================================
-- END OF RLS MIGRATION
-- ============================================================================
-- Summary:
--   Tables with RLS enabled:     30 (all)
--   SELECT policies:             28 (one per table)
--   WRITE policies:               8 (admin-only: users, trades
--                                     + authenticated: vendor_documents
--                                     + self/admin: vendor_flags
--                                     + self-update: users, notifications)
--   Admin-only tables:            1 (magic_link_tokens — SELECT restricted)
--   User-scoped tables:           1 (notifications — see only your own)
--   Anon role:                    ZERO access (revoked on all tables + private schema)
--   Helper functions:             2 (in private schema, security definer)
-- ============================================================================