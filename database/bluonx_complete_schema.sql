-- ============================================================================
-- BluOnX Bid Management & Vendor Coordination System
-- Complete Database Schema — PostgreSQL / Supabase
-- ============================================================================
-- Version:  4.8
-- Date:     November 11, 2026
-- Author:   Awais Anwer (Tkrupt)
-- Tables:   58 (34 bid management + 24 financial, see Section 9)
-- Engine:   PostgreSQL via Supabase
-- ============================================================================
--
-- TABLE GROUPS:
--   1. Access Control            (1 table)
--   2. Trade & Vendor Management (5 tables)
--   3. Project & Task Management (3 tables)
--   4. Bid Lifecycle             (11 tables)
--   5. Award & Contract          (3 tables)
--   6. Milestone Tracking        (6 tables)
--   7. Communication & Audit     (3 tables)
--   8. System Configuration       (2 tables)
--   9. Budget Structure           (4 tables)  ┐
--  10. Contingency                (3 tables)  │
--  11. Payments & Finance         (3 tables)  │ Financial Automation
--  12. Long-tail Items            (2 tables)  │ (Section 9, v4.0)
--  13. Cash Flow                  (3 tables)  │
--  14. Settings, Alerts & Roles   (4 tables)  ┘
--
-- CONVENTIONS:
--   • All PKs are UUID (gen_random_uuid)
--   • Timestamps use TIMESTAMPTZ (timezone-aware)
--   • Soft deletes via deleted_at on core entities (users, vendors, projects, tasks)
--   • Status fields use CHECK constraints (not enums — easier to extend)
--   • ON DELETE RESTRICT on most FKs (audit-safe; we soft-delete, never hard-delete)
--   • ON DELETE CASCADE only on tightly-coupled child rows (line items, attachments)
--   • ON DELETE SET NULL on optional/advisory FKs (flags, scores)
--
-- ============================================================================


-- ============================================================================
-- EXTENSIONS
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()


-- ============================================================================
-- SECTION 1: REUSABLE HELPER FUNCTIONS
-- ============================================================================

-- Generic trigger function: auto-set updated_at on every UPDATE
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- SECTION 2: TABLE DEFINITIONS
-- ============================================================================


-- ========================================
-- GROUP 1: ACCESS CONTROL
-- ========================================

-- Users (extends Supabase auth.users)
-- Password hashing, email verification, sessions, and last_sign_in
-- are fully managed by Supabase Auth. This table stores app-specific profile data.
-- The id is NOT auto-generated — it is set to match auth.users.id on insert.
CREATE TABLE users (
  id            UUID          PRIMARY KEY,
  email         VARCHAR(255)  NOT NULL UNIQUE,
  full_name     VARCHAR(255)  NOT NULL,
  role          VARCHAR(20)   NOT NULL CHECK (role IN ('admin', 'project_manager')),
  is_active     BOOLEAN       NOT NULL DEFAULT TRUE,
  invited_by    UUID          REFERENCES users(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at    TIMESTAMPTZ
);

COMMENT ON TABLE  users           IS 'Internal user profiles extending Supabase auth.users.';
COMMENT ON COLUMN users.id        IS 'Matches auth.users.id — set on insert, not auto-generated.';
COMMENT ON COLUMN users.invited_by IS 'Admin who sent the invite. NULL for the bootstrap admin and any dashboard-seeded user.';
COMMENT ON COLUMN users.deleted_at IS 'Soft delete. NULL = active record.';


-- ========================================
-- GROUP 2: TRADE & VENDOR MANAGEMENT
-- ========================================

-- Trades: controlled lookup (~27 scope categories)
CREATE TABLE trades (
  id          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  name        VARCHAR(100)  NOT NULL UNIQUE,
  phase       VARCHAR(20)   NOT NULL CHECK (phase IN ('due_diligence', 'development', 'both')),
  is_active   BOOLEAN       NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  trades       IS 'Controlled list of trade/scope categories. Filters task dropdowns by phase.';
COMMENT ON COLUMN trades.phase IS '"both" = appears in Due Diligence and Development phase dropdowns (e.g., Engineering).';


-- Vendors: company-level records (soft-deleted)
CREATE TABLE vendors (
  id                         UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  company_name               VARCHAR(255)  NOT NULL,
  address                    TEXT,
  city                       VARCHAR(100),
  state                      VARCHAR(50),
  zip_code                   VARCHAR(20),
  latitude                   DECIMAL(10,7),
  longitude                  DECIMAL(10,7),
  insurance_expiration_date  DATE,
  insurance_coverage_amount  DECIMAL(15,2) CHECK (insurance_coverage_amount >= 0),
  bonding_capacity           DECIMAL(15,2) CHECK (bonding_capacity >= 0),
  max_active_jobs            INTEGER       CHECK (max_active_jobs >= 0),
  current_active_jobs        INTEGER       NOT NULL DEFAULT 0 CHECK (current_active_jobs >= 0),
  onboarding_status          VARCHAR(20)   NOT NULL DEFAULT 'pending'
                                           CHECK (onboarding_status IN ('pending', 'partial', 'complete')),
  status                     VARCHAR(20)   NOT NULL DEFAULT 'active'
                                           CHECK (status IN ('active', 'inactive', 'suspended')),
  notes                      TEXT,
  created_at                 TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at                 TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at                 TIMESTAMPTZ
);

COMMENT ON TABLE  vendors                    IS 'Vendor companies. Soft-deleted, never hard-deleted.';
COMMENT ON COLUMN vendors.latitude           IS 'Geocoded from address via Google Maps API for distance filtering.';
COMMENT ON COLUMN vendors.longitude          IS 'Geocoded from address via Google Maps API for distance filtering.';
COMMENT ON COLUMN vendors.current_active_jobs IS 'Maintained by DB triggers on award/contract status changes.';
COMMENT ON COLUMN vendors.onboarding_status  IS 'Managed manually by PM. pending → partial → complete.';


-- Vendor contacts: multiple per vendor company
CREATE TABLE vendor_contacts (
  id          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  vendor_id   UUID          NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,
  full_name   VARCHAR(255)  NOT NULL,
  email       VARCHAR(255)  NOT NULL,
  phone       VARCHAR(50),
  title       VARCHAR(100),
  is_primary  BOOLEAN       NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE vendor_contacts IS 'Individual contacts within a vendor company. Bid invitations target contacts.';


-- Vendor ↔ Trade junction (many-to-many)
CREATE TABLE vendor_trades (
  id          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  vendor_id   UUID          NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,
  trade_id    UUID          NOT NULL REFERENCES trades(id) ON DELETE RESTRICT,
  created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  UNIQUE (vendor_id, trade_id)
);

COMMENT ON TABLE vendor_trades IS 'Many-to-many: vendors ↔ trades. Powers auto-filtering in bid invitation flow.';


-- Vendor onboarding documents (uploaded by admin)
CREATE TABLE vendor_documents (
  id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  vendor_id       UUID          NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,
  document_type   VARCHAR(30)   NOT NULL
                                CHECK (document_type IN ('w9', 'insurance_certificate', 'master_trade_agreement')),
  file_name       VARCHAR(255)  NOT NULL,
  file_path       TEXT          NOT NULL,
  file_size       BIGINT,
  expiration_date DATE,
  status          VARCHAR(20)   NOT NULL DEFAULT 'valid'
                                CHECK (status IN ('valid', 'expired', 'pending_review')),
  uploaded_by     UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  uploaded_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  vendor_documents                IS 'Three required onboarding docs: W-9, Insurance Certificate, Master Trade Agreement.';
COMMENT ON COLUMN vendor_documents.file_path      IS 'Reference path in Supabase Storage (vendor-documents bucket).';
COMMENT ON COLUMN vendor_documents.expiration_date IS 'Applicable to insurance certificates. NULL for non-expiring docs.';


-- ========================================
-- GROUP 3: PROJECT & TASK MANAGEMENT
-- ========================================

-- Projects
CREATE TABLE projects (
  id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  name                VARCHAR(255)  NOT NULL,
  description         TEXT,
  address             TEXT,
  city                VARCHAR(100),
  state               VARCHAR(50),
  zip_code            VARCHAR(20),
  latitude            DECIMAL(10,7),
  longitude           DECIMAL(10,7),
  budget              DECIMAL(15,2) CHECK (budget >= 0),
  status              VARCHAR(20)   NOT NULL DEFAULT 'planning'
                                    CHECK (status IN ('planning', 'active', 'on_hold', 'completed', 'cancelled')),
  start_date          DATE,
  estimated_end_date  DATE,
  archived_at         TIMESTAMPTZ,
  archived_by         UUID          REFERENCES users(id) ON DELETE SET NULL,
  created_by          UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at          TIMESTAMPTZ
);

COMMENT ON TABLE  projects           IS 'Construction projects. Soft-deleted.';
COMMENT ON COLUMN projects.latitude  IS 'Geocoded from address. Used to calc distance to vendor locations.';
COMMENT ON COLUMN projects.longitude IS 'Geocoded from address. Used to calc distance to vendor locations.';
COMMENT ON COLUMN projects.archived_at IS 'When project was archived. NULL = not archived. Separate from deleted_at (soft delete).';
COMMENT ON COLUMN projects.archived_by IS 'User who archived the project. NULL when not archived.';


-- Project-level documents (civil plans, drawings, specs)
CREATE TABLE project_documents (
  id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID          NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  file_name     VARCHAR(255)  NOT NULL,
  file_path     TEXT          NOT NULL,
  file_type     VARCHAR(255),
  file_size     BIGINT,
  document_kind VARCHAR(20)   NOT NULL DEFAULT 'reference' CHECK (document_kind IN ('reference', 'scope_of_work')),
  uploaded_by   UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  uploaded_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  project_documents           IS 'Docs uploaded at project level. Shared to vendors via bid_package_documents.';
COMMENT ON COLUMN project_documents.file_path IS 'Reference path in Supabase Storage (project-documents bucket).';
COMMENT ON COLUMN project_documents.document_kind IS 'reference = general project doc, selectable into bid packages. scope_of_work = per-package SoW uploaded during bid-package creation (referenced by bid_packages.scope_of_work_document_id); filtered OUT of the selectable reference pool.';


-- Tasks (one task = one trade = one award = one contract)
CREATE TABLE tasks (
  id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID          NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  trade_id        UUID          NOT NULL REFERENCES trades(id) ON DELETE RESTRICT,
  name            VARCHAR(255)  NOT NULL,
  description     TEXT,
  phase           VARCHAR(20)   NOT NULL CHECK (phase IN ('due_diligence', 'development')),
  bid_type        VARCHAR(20)   NOT NULL CHECK (bid_type IN ('competitive', 'direct_assign', 'internal')),
  budget_estimate DECIMAL(15,2) CHECK (budget_estimate >= 0),
  sort_order      INTEGER       NOT NULL DEFAULT 0,
  status          VARCHAR(20)   NOT NULL DEFAULT 'draft'
                                CHECK (status IN ('draft', 'bidding', 'evaluating', 'awarded',
                                                  'in_progress', 'completed', 'cancelled')),
  created_by      UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at      TIMESTAMPTZ
);

COMMENT ON TABLE  tasks              IS 'Fundamental work unit. 1 task = 1 trade = 1 award = 1 contract. Soft-deleted.';
COMMENT ON COLUMN tasks.phase        IS 'due_diligence or development. Filters the trade dropdown for this task.';
COMMENT ON COLUMN tasks.bid_type     IS 'competitive = full pipeline, direct_assign = PM picks vendor, internal = budget line only.';
COMMENT ON COLUMN tasks.sort_order   IS 'Numeric ordering for chronological display and budgeting views.';


-- ========================================
-- GROUP 4: BID LIFECYCLE
-- ========================================

-- Bid templates: defines bid format per trade
CREATE TABLE bid_templates (
  id           UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  trade_id     UUID          REFERENCES trades(id) ON DELETE RESTRICT,
  name         VARCHAR(255)  NOT NULL,
  is_lump_sum  BOOLEAN       NOT NULL DEFAULT TRUE,
  created_by   UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  bid_templates             IS 'Defines bid format per trade: lump sum vs. structured line items.';
COMMENT ON COLUMN bid_templates.is_lump_sum IS 'TRUE = vendor submits one total. FALSE = vendor fills predefined line items.';


-- Bid template items: predefined rows for structured bids
CREATE TABLE bid_template_items (
  id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_template_id   UUID          NOT NULL REFERENCES bid_templates(id) ON DELETE CASCADE,
  description       VARCHAR(255)  NOT NULL,
  item_type         VARCHAR(20)   NOT NULL CHECK (item_type IN ('lump_sum', 'unit_price')),
  unit_of_measure   VARCHAR(50),
  sort_order        INTEGER       NOT NULL DEFAULT 0
);

COMMENT ON TABLE bid_template_items IS 'Predefined line item rows for structured bid templates. Vendors fill in qty/prices.';


-- Bid packages: one bidding round per task (supports rebidding)
CREATE TABLE bid_packages (
  id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id       UUID          NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
  round_number  INTEGER       NOT NULL DEFAULT 1,
  deadline      TIMESTAMPTZ   NOT NULL,
  instructions  TEXT,
  desired_start_date  DATE,
  scope_of_work_document_id UUID REFERENCES project_documents(id) ON DELETE RESTRICT,
  status        VARCHAR(20)   NOT NULL DEFAULT 'open'
                              CHECK (status IN ('open', 'closed', 'evaluating', 'cancelled')),

  bid_template_id UUID        REFERENCES bid_templates(id) ON DELETE RESTRICT,
  created_by    UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  cancelled_by  UUID          REFERENCES users(id) ON DELETE SET NULL,
  cancelled_at  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  bid_packages              IS 'A bidding round for a task. Multiple rounds via round_number for rebidding. RULE: must not be created for tasks with bid_type = internal (enforced at application layer).';
COMMENT ON COLUMN bid_packages.round_number IS 'Auto-set by trigger: round 1 = first attempt, round 2 = rebid, etc.';
COMMENT ON COLUMN bid_packages.scope_of_work_document_id IS 'PM-uploaded Scope of Work for this round (a project_documents row, document_kind=scope_of_work, project-documents bucket). One SoW per package; not re-uploaded on per-vendor revision. Mandatory at the application layer (required request field + service check); nullable in-DB only to avoid backfilling pre-feature rows. ON DELETE RESTRICT protects it as a contract record.';
COMMENT ON COLUMN bid_packages.instructions IS 'Optional PM-supplied bid-submission instructions shown to vendors in the bid portal and invitation email. Distinct from tasks.description (scope of work). Examples: include mobilization as separate line item, bid held firm for 30 days, unit prices all-inclusive.';
COMMENT ON COLUMN bid_packages.desired_start_date IS 'PM-communicated target start date for this bidding round. NULL = flexible/none; timeline dimension neutralized in scoring when NULL.';
COMMENT ON COLUMN bid_packages.cancelled_by IS 'Who voided this round (status = cancelled). NULL for every other status. ON DELETE SET NULL (not RESTRICT like created_by) so removing a user never blocks the row; the UI falls back to showing cancelled_at alone. NOTE: this is the SECOND FK from bid_packages to users, so a bare users(...) PostgREST embed on this table is ambiguous — resolve the name with an explicit lookup instead.';
COMMENT ON COLUMN bid_packages.cancelled_at IS 'When the round was voided. Paired with cancelled_by; both set together by the cancel action and never written by any other path.';

-- Junction: project documents shared with a bid package
CREATE TABLE bid_package_documents (
  id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_package_id        UUID        NOT NULL REFERENCES bid_packages(id) ON DELETE CASCADE,
  project_document_id   UUID        NOT NULL REFERENCES project_documents(id) ON DELETE RESTRICT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE (bid_package_id, project_document_id)
);

COMMENT ON TABLE bid_package_documents IS 'Links project docs to bid packages. PM selects which docs to include with invitations.';


-- Bid invitations: one per vendor per bid package
CREATE TABLE bid_invitations (
  id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_package_id    UUID          NOT NULL REFERENCES bid_packages(id) ON DELETE RESTRICT,
  vendor_id         UUID          NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,
  vendor_contact_id UUID          NOT NULL REFERENCES vendor_contacts(id) ON DELETE RESTRICT,
  status            VARCHAR(20)   NOT NULL DEFAULT 'sent'
                                  CHECK (status IN ('pending_send', 'sent', 'send_failed',
                                                    'opened', 'submitted', 'declined',
                                                    'expired', 'no_response')),
  sent_at           TIMESTAMPTZ,
  opened_at         TIMESTAMPTZ,
  responded_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  UNIQUE (bid_package_id, vendor_id)
);

COMMENT ON TABLE bid_invitations IS 'Individual invitation per vendor per bid package. Tracks delivery and response status.';
COMMENT ON COLUMN bid_invitations.status IS 'pending_send = row created, invitation email not yet sent; sent = email accepted by provider (sent_at set); send_failed = provider rejected the send (recoverable via Resend/Send Bid Link, which mints a fresh token). The pending_send/send_failed pair lets a partial bid-package creation leave a recoverable, non-misleading state instead of falsely reading sent. opened = vendor viewed the portal; submitted/declined = vendor outcomes. no_response is the SINGLE terminal "invited, did not bid" status. It is written by BOTH routes out of an open package: the shared deadline transition (lazy read-path + daily post-deadline job converge on it) and the PM manually closing bidding early (close_bidding). Both call the same helper so the two routes leave identical state. expired is retained in the CHECK for legacy rows only and is no longer written by any code path.';


-- Bid submissions: vendor's actual bid response
CREATE TABLE bid_submissions (
  id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_invitation_id   UUID          NOT NULL REFERENCES bid_invitations(id) ON DELETE RESTRICT,
  vendor_id           UUID          NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,
  total_amount        DECIMAL(15,2) CHECK (total_amount >= 0),
  status              VARCHAR(20)   NOT NULL DEFAULT 'draft'
                                    CHECK (status IN ('draft', 'submitted', 'under_review', 'accepted', 'rejected')),
  is_draft            BOOLEAN       NOT NULL DEFAULT TRUE,
  is_direct_assign    BOOLEAN       NOT NULL DEFAULT FALSE,
  submitted_at        TIMESTAMPTZ,
  vendor_notes        TEXT,
  proposed_start_date  DATE,
  sow_attested_name   VARCHAR(255),
  sow_attested_at     TIMESTAMPTZ,
  supersedes_submission_id UUID    REFERENCES bid_submissions(id) ON DELETE RESTRICT,
  is_superseded       BOOLEAN       NOT NULL DEFAULT FALSE,
  revision_number     INTEGER       NOT NULL DEFAULT 1 CHECK (revision_number >= 1),
  created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_bid_submissions_supersedes_not_self
    CHECK (supersedes_submission_id IS NULL OR supersedes_submission_id != id)
);

COMMENT ON TABLE  bid_submissions              IS 'Vendor bid response. One per invitation. Supports draft state for auto-save.';
COMMENT ON COLUMN bid_submissions.is_draft     IS 'TRUE while vendor is editing. Set FALSE on final submission.';
COMMENT ON COLUMN bid_submissions.is_direct_assign IS 'TRUE for synthetic submissions created via direct_assign flow. Distinguishes from competitive bids.';
COMMENT ON COLUMN bid_submissions.vendor_id    IS 'Denormalized for query perf. Enforced = bid_invitations.vendor_id by trigger.';
COMMENT ON COLUMN bid_submissions.supersedes_submission_id IS 'Chain pointer to the predecessor submission this row supersedes. NULL = original. RESTRICT delete (audit chain).';
COMMENT ON COLUMN bid_submissions.is_superseded IS 'TRUE when a newer revision exists. Trigger-maintained by fn_flip_superseded_on_revision_finalize.';
COMMENT ON COLUMN bid_submissions.revision_number IS 'Human-visible version number. 1 = original. Each revision increments by 1 (enforced by fn_enforce_supersession_chain).';
COMMENT ON COLUMN bid_submissions.proposed_start_date IS 'Vendor''s committed start date. Pre-filled with bid_packages.desired_start_date in the form; required on submit when a desired date exists. proposed <= desired = on time.';
COMMENT ON COLUMN bid_submissions.sow_attested_name IS 'Vendor-typed company name (CAPS) attesting they reviewed the package SoW and their bid reflects it. Saved on the draft; required at submit (unconditional). Re-typed fresh on every revision (never prefilled).';
COMMENT ON COLUMN bid_submissions.sow_attested_at IS 'Server-stamped UTC attestation timestamp. Set only at finalize (submit_bid), never on draft/autosave. Realized onto contracts.sow_signed_date at envelope-send for the awarded submission.';

-- Bid line items: pricing breakdown within a submission
CREATE TABLE bid_line_items (
  id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_submission_id   UUID          NOT NULL REFERENCES bid_submissions(id) ON DELETE CASCADE,
  description         VARCHAR(255)  NOT NULL,
  item_type           VARCHAR(20)   NOT NULL CHECK (item_type IN ('lump_sum', 'unit_price')),
  quantity            DECIMAL(12,2) CHECK (quantity >= 0),
  unit_of_measure     VARCHAR(50),
  unit_price          DECIMAL(15,2) CHECK (unit_price >= 0),
  lump_sum_amount     DECIMAL(15,2) CHECK (lump_sum_amount >= 0),
  line_total          DECIMAL(15,2) NOT NULL CHECK (line_total >= 0),
  sort_order          INTEGER       NOT NULL DEFAULT 0
);

COMMENT ON TABLE  bid_line_items            IS 'Pricing rows within a bid. Supports lump sum and unit pricing in same submission.';
COMMENT ON COLUMN bid_line_items.line_total IS 'qty × unit_price for unit items, or lump_sum_amount for lump sum items.';


-- Bid attachments: documents submitted with the bid
CREATE TABLE bid_attachments (
  id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_submission_id   UUID          NOT NULL REFERENCES bid_submissions(id) ON DELETE CASCADE,
  file_name           VARCHAR(255)  NOT NULL,
  file_path           TEXT          NOT NULL,
  file_type           VARCHAR(255),
  file_size           BIGINT,
  uploaded_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  bid_attachments           IS 'Docs vendors upload with bids (updated W-9, signed Scope of Work).';
COMMENT ON COLUMN bid_attachments.file_path IS 'Path in Supabase Storage (bid-attachments bucket).';


-- Bid scores: computed weighted scores per submission
CREATE TABLE bid_scores (
  id                    UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_submission_id     UUID          NOT NULL UNIQUE REFERENCES bid_submissions(id) ON DELETE CASCADE,
  price_score           DECIMAL(5,2)  CHECK (price_score       BETWEEN 0 AND 100),
  compliance_score      DECIMAL(5,2)  CHECK (compliance_score  BETWEEN 0 AND 100),
  performance_score     DECIMAL(5,2)  CHECK (performance_score BETWEEN 0 AND 100),
  capacity_score        DECIMAL(5,2)  CHECK (capacity_score    BETWEEN 0 AND 100),
  timeline_score        DECIMAL(5,2)  CHECK (timeline_score    BETWEEN 0 AND 100),
  total_weighted_score  DECIMAL(5,2)  CHECK (total_weighted_score BETWEEN 0 AND 100),
  scoring_metadata      JSONB,
  scored_at             TIMESTAMPTZ,
  scored_by             UUID          REFERENCES users(id) ON DELETE SET NULL
);

COMMENT ON TABLE  bid_scores                    IS 'Weighted scores per bid submission. One score record per submission.';
COMMENT ON COLUMN bid_scores.scored_by          IS 'NULL = system-generated score. Non-NULL = manually adjusted by a user.';
COMMENT ON COLUMN bid_scores.scoring_metadata   IS 'JSONB snapshot of scoring breakdown and weights used at time of scoring.';


-- ────────────────────────────────────────────────────────────────────────────
-- bid_revision_requests: PM-initiated request asking a single vendor to
-- revise their submitted bid. Lifecycle: pending → submitted | declined |
-- expired | cancelled. One pending request per invitation at a time
-- (partial unique index). Multiple terminal-state rows coexist as history.
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE bid_revision_requests (
  id                      UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_invitation_id       UUID          NOT NULL REFERENCES bid_invitations(id) ON DELETE RESTRICT,
  original_submission_id  UUID          NOT NULL REFERENCES bid_submissions(id) ON DELETE RESTRICT,
  pm_note                 TEXT          NOT NULL CHECK (length(pm_note) > 0),
  revision_deadline       TIMESTAMPTZ   NOT NULL,
  status                  VARCHAR(20)   NOT NULL DEFAULT 'pending'
                                        CHECK (status IN ('pending', 'submitted', 'declined', 'expired', 'cancelled')),
  decline_reason          TEXT,
  requested_by            UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  requested_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  responded_at            TIMESTAMPTZ,
  created_at              TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  bid_revision_requests IS
  'PM-initiated revision request for a single vendor. Independent deadline (may outlive bid_packages.deadline). One pending row per invitation; terminal-state rows kept as audit history.';
COMMENT ON COLUMN bid_revision_requests.original_submission_id IS
  'Denormalized pointer to the submission being revised. The successor relationship lives on bid_submissions.supersedes_submission_id.';
COMMENT ON COLUMN bid_revision_requests.revision_deadline IS
  'Per-request deadline, independent of bid_packages.deadline.';
COMMENT ON COLUMN bid_revision_requests.decline_reason IS
  'Optional short note from vendor on decline.';


-- Magic link tokens for vendor bid portal access
CREATE TABLE magic_link_tokens (
  id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_invitation_id   UUID          NOT NULL REFERENCES bid_invitations(id) ON DELETE CASCADE,
  vendor_id           UUID          NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,
  token_hash          VARCHAR(255)  NOT NULL UNIQUE,
  expires_at          TIMESTAMPTZ   NOT NULL,
  used_at             TIMESTAMPTZ,
  is_used             BOOLEAN       NOT NULL DEFAULT FALSE,
  ip_address          INET,
  revoked_at          TIMESTAMPTZ,
  revoked_by          UUID          REFERENCES users(id) ON DELETE SET NULL,
  bid_revision_request_id UUID REFERENCES bid_revision_requests(id) ON DELETE RESTRICT,
  created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  magic_link_tokens            IS 'Secure single-use tokens for vendor bid portal auth. Hashed, never stored raw.';
COMMENT ON COLUMN magic_link_tokens.token_hash IS 'SHA-256 hash of the actual token. Raw token is emailed, never stored.';
COMMENT ON COLUMN magic_link_tokens.revoked_at IS 'When this token was hard-revoked (e.g., via Resend Bid Link). NULL = live. Validator rejects revoked tokens with 410.';
COMMENT ON COLUMN magic_link_tokens.revoked_by IS 'User who revoked this token. NULL when not revoked or when the revoking user is later deleted.';
COMMENT ON COLUMN magic_link_tokens.bid_revision_request_id IS 'Discriminator. NULL = initial bid invitation token. Non-NULL = revision token. Validator branches on this to bypass package-status check and to validate the revision request is still pending.';


-- ========================================
-- GROUP 5: AWARD & CONTRACT
-- ========================================

-- Awards: decision record (one active award per task, enforced by partial unique index)
CREATE TABLE awards (
  id                      UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id                 UUID          NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
  bid_submission_id       UUID          NOT NULL REFERENCES bid_submissions(id) ON DELETE RESTRICT,
  vendor_id               UUID          NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,
  awarded_by              UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  awarded_at              TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  award_amount            DECIMAL(15,2) NOT NULL CHECK (award_amount >= 0),
  instructions              TEXT,
  has_override            BOOLEAN       NOT NULL DEFAULT FALSE,
  override_justification  TEXT,
  validation_results      JSONB,
  contract_valid_days     INTEGER       NOT NULL DEFAULT 365
                                        CHECK (contract_valid_days >= 0),
  work_duration_days      INTEGER       CHECK (work_duration_days > 0),
  signer_id               UUID,
  status                  VARCHAR(30)   NOT NULL DEFAULT 'pending_acceptance'
                                        CHECK (status IN ('pending_acceptance', 'accepted',
                                                          'declined_by_vendor', 'cancelled')),
  created_at              TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  awards                        IS 'Award decision. Partial unique on task_id: one active award per task, history preserved. RULE: must not be created for tasks with bid_type = internal (enforced at application layer).';
COMMENT ON COLUMN awards.vendor_id              IS 'Denormalized for query perf. Enforced = bid_submissions.vendor_id by trigger.';
COMMENT ON COLUMN awards.has_override           IS 'TRUE if PM overrode validation warnings. override_justification required when TRUE.';
COMMENT ON COLUMN awards.validation_results     IS 'JSONB snapshot of all pre-award validation checks at time of award.';
COMMENT ON COLUMN awards.contract_valid_days    IS 'PM-set contract term length in days (parameter). Default 365 (1-year). Realized onto contracts.valid_until at execution.';
COMMENT ON COLUMN awards.work_duration_days     IS 'PM-set duration of the awarded work in days (parameter). Realized onto contracts.end_date at envelope-send as proposed_start + duration.';
COMMENT ON COLUMN awards.signer_id IS 'BluOnX signer chosen by the PM at award time. Becomes DocuSign routingOrder 1. NULL on awards created before this feature; envelope-send falls back to CONTRACT_OWNER_SIGNER_* settings.';


-- Contracts: one per accepted award
CREATE TABLE contracts (
  id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  award_id          UUID          NOT NULL UNIQUE REFERENCES awards(id) ON DELETE RESTRICT,
  vendor_id         UUID          NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,
  task_id           UUID          NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
  contract_number   VARCHAR(50)   NOT NULL UNIQUE,
  start_date        DATE,
  end_date          DATE,
  valid_until       DATE,
  sow_signed_date   DATE,
  contract_amount   DECIMAL(15,2) NOT NULL CHECK (contract_amount >= 0),
  payment_terms     TEXT,
  status            VARCHAR(20)   NOT NULL DEFAULT 'draft'
                                  CHECK (status IN ('draft', 'sent_for_signature', 'executed',
                                                    'active', 'completed', 'terminated')),
  signed_at         TIMESTAMPTZ,
  signer_name       VARCHAR(255),
  signer_email      VARCHAR(255),
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  contracts              IS 'Contract record. One per accepted award. Partial unique on task_id allows re-contracting. RULE: must not be created for tasks with bid_type = internal (enforced at application layer).';
COMMENT ON COLUMN contracts.vendor_id    IS 'Denormalized for query perf. Enforced = awards.vendor_id by trigger.';
COMMENT ON COLUMN contracts.task_id      IS 'Denormalized for query perf. Enforced = awards.task_id (via bid_submission) by trigger.';
COMMENT ON COLUMN contracts.valid_until  IS 'Realized contract expiry = signed_at + awards.contract_valid_days. NULL until the DocuSign completed webhook fires (execution-anchored).';
COMMENT ON COLUMN contracts.sow_signed_date IS 'Realized date the awarded vendor attested to the SoW = awarded bid_submissions.sow_attested_at::date. NULL until envelope-send copies it. Feeds the contract PDF "Date of signed scope of work" line.';
COMMENT ON COLUMN contracts.signer_name  IS 'Snapshot of the BluOnX signer name at envelope-send. Frozen: editing the contract_signers row later must not rewrite an executed contract.';
COMMENT ON COLUMN contracts.signer_email IS 'Snapshot of the BluOnX signer email at envelope-send. See signer_name.';

-- DocuSign envelope tracking
CREATE TABLE docusign_envelopes (
  id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_id       UUID          NOT NULL REFERENCES contracts(id) ON DELETE RESTRICT,
  envelope_id       VARCHAR(255)  NOT NULL UNIQUE,
  status            VARCHAR(20)   NOT NULL DEFAULT 'sent'
                                  CHECK (status IN ('sent', 'delivered', 'signed',
                                                    'completed', 'declined', 'voided')),
  sent_at           TIMESTAMPTZ,
  completed_at      TIMESTAMPTZ,
  document_url      TEXT,
  webhook_payload   JSONB,
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  docusign_envelopes                 IS 'DocuSign e-signature envelope tracking. Decoupled from contracts.';
COMMENT ON COLUMN docusign_envelopes.webhook_payload IS 'Full DocuSign webhook payload for debugging and audit.';


-- ========================================
-- GROUP 6: MILESTONE TRACKING
-- ========================================

-- Milestones: 2–5 per awarded task
CREATE TABLE milestones (
  id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id           UUID          NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
  contract_id       UUID          NOT NULL REFERENCES contracts(id) ON DELETE RESTRICT,
  name              VARCHAR(255)  NOT NULL,
  start_date        DATE          NOT NULL,
  end_date          DATE          NOT NULL,
  baseline_end_date DATE          NOT NULL,
  actual_start_date DATE,
  actual_end_date   DATE,
  status            VARCHAR(20)   NOT NULL DEFAULT 'scheduled'
                                  CHECK (status IN ('scheduled','in_progress','delayed','unresponsive','completed','cancelled')),
  cycle_number      INTEGER       NOT NULL DEFAULT 1,
  sort_order        INTEGER       NOT NULL DEFAULT 0,
  notes             TEXT,
  created_by        UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  milestones                    IS 'Work milestones for awarded tasks. Tracked via automated email check-ins. RULE: must not be created for tasks with bid_type = internal (enforced at application layer).';
COMMENT ON COLUMN milestones.task_id            IS 'Denormalized for query perf. Enforced = contracts.task_id by trigger.';
COMMENT ON COLUMN milestones.actual_start_date  IS 'Set when vendor confirms start. Compared with planned start_date.';
COMMENT ON COLUMN milestones.baseline_end_date IS 'The originally committed finish. Frozen once the plan is live; a reschedule moves end_date but never this. On-time = actual_end_date <= baseline_end_date. No baseline_start_date exists: reschedule is end-only and trg_milestones_guard_dates locks start_date once live, so start_date IS the committed start.';
COMMENT ON COLUMN milestones.cycle_number IS 'Generation counter. +1 on every reschedule. A check-in token is valid only while milestone_alerts.cycle_number = milestones.cycle_number; older cycles are stale by definition.';
COMMENT ON COLUMN milestones.start_date IS 'The committed start. Editable only while status = scheduled and no check-in has been sent (enforced by trg_milestones_guard_dates); immutable thereafter.';


-- Milestone alerts: milestone-specific email tracking
-- NOTE: email_log FK added via ALTER TABLE below (table ordering dependency)
CREATE TABLE milestone_alerts (
  id                    UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  milestone_id          UUID          NOT NULL REFERENCES milestones(id) ON DELETE RESTRICT,
  email_log_id          UUID,
  alert_type            VARCHAR(30)   NOT NULL
                                      CHECK (alert_type IN ('starting_soon', 'start_check', 'progress_check',
                                                            'completion_check', 'delay_alert',
                                                            'no_response_alert', 'completion_notification')),
  recipient_type        VARCHAR(20)   NOT NULL CHECK (recipient_type IN ('vendor', 'pm')),
  cycle_number          INTEGER,
  created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  milestone_alerts             IS 'Milestone-specific email tracking. References email_log for delivery details (no duplication).';
COMMENT ON COLUMN milestone_alerts.email_log_id IS 'FK to email_log. Delivery status lives there, milestone context lives here.';
COMMENT ON COLUMN milestone_alerts.cycle_number IS 'Milestone cycle this check-in was sent under. The token is stale when this != milestones.cycle_number.';


-- Milestone responses: vendor yes/no from email links (immutable audit)
CREATE TABLE milestone_responses (
  id                    UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  milestone_id          UUID          NOT NULL REFERENCES milestones(id) ON DELETE RESTRICT,
  response_type         VARCHAR(30)   NOT NULL
                                      CHECK (response_type IN ('start_confirmation', 'progress_check',
                                                                'completion_confirmation')),
  response_value        VARCHAR(10)   NOT NULL CHECK (response_value IN ('yes', 'no')),
  milestone_alert_id    UUID          NOT NULL REFERENCES milestone_alerts(id) ON DELETE RESTRICT,
  vendor_contact_id     UUID          NOT NULL REFERENCES vendor_contacts(id) ON DELETE RESTRICT,
  responded_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_milestone_responses_alert UNIQUE (milestone_alert_id)
);

COMMENT ON TABLE milestone_responses IS 'Logs every vendor email-link response. Immutable audit record.';
COMMENT ON COLUMN milestone_responses.milestone_alert_id IS 'Which check-in this answers. UNIQUE: one recorded response per alert (first-response-wins, enforced at the DB).';


-- Milestone events: append-only transition ledger (feeds the PM activity timeline)
CREATE TABLE milestone_events (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  milestone_id  UUID        NOT NULL REFERENCES milestones(id) ON DELETE CASCADE,

  from_status   VARCHAR(20),
  to_status     VARCHAR(20) NOT NULL,

  trigger_type  VARCHAR(30) NOT NULL
                CHECK (trigger_type IN ('creation','vendor_response','pm_action','system_no_response')),

  actor_user_id           UUID REFERENCES users(id)               ON DELETE SET NULL,
  actor_vendor_contact_id UUID REFERENCES vendor_contacts(id)     ON DELETE SET NULL,
  milestone_response_id   UUID REFERENCES milestone_responses(id) ON DELETE SET NULL,
  milestone_alert_id      UUID REFERENCES milestone_alerts(id)    ON DELETE SET NULL,

  cycle_number     INTEGER,
  working_end_date DATE,
  note             TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_milestone_events_actor CHECK (
       (trigger_type IN ('creation','pm_action')
          AND actor_user_id IS NOT NULL AND actor_vendor_contact_id IS NULL)
    OR (trigger_type = 'vendor_response'
          AND actor_vendor_contact_id IS NOT NULL AND actor_user_id IS NULL)
    OR (trigger_type = 'system_no_response'
          AND actor_user_id IS NULL AND actor_vendor_contact_id IS NULL)
  )
);

COMMENT ON TABLE  milestone_events IS 'Append-only audit ledger. One immutable row per milestone transition, written inside transition_milestone(). Feeds the unified PM activity timeline. UPDATE/DELETE blocked by trg_milestone_events_immutable.';
COMMENT ON COLUMN milestone_events.trigger_type IS 'Also determines the actor kind, so no separate actor_type column: creation/pm_action = user, vendor_response = vendor contact, system_no_response = scheduler.';
COMMENT ON COLUMN milestone_events.milestone_alert_id IS 'WHICH check-in this event relates to. Required even when milestone_response_id is NULL (a system_no_response event has no response row).';
COMMENT ON COLUMN milestone_events.working_end_date IS 'The plan at event time. The only date snapshotted: reschedule is end-only, and actual dates are write-once, so the milestone row stays authoritative for those.';

-- 
-- milestone_checkin_tokens
-- 
-- Same SHAPE as a bid magic link (hash, expiry, used/revoked audit, ip), but
-- native to the milestone world: its discriminator IS its reason to exist, so
-- milestone_alert_id is a plain NOT NULL FK — no nullable-FK gymnastics.

CREATE TABLE milestone_checkin_tokens (
  id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  milestone_alert_id UUID          NOT NULL REFERENCES milestone_alerts(id) ON DELETE CASCADE,
  milestone_id       UUID          NOT NULL REFERENCES milestones(id) ON DELETE CASCADE,
  vendor_contact_id  UUID          NOT NULL REFERENCES vendor_contacts(id) ON DELETE RESTRICT,
  cycle_number       INTEGER       NOT NULL,   -- the milestone cycle this token was minted under
  token_hash         VARCHAR(255)  NOT NULL UNIQUE,
  expires_at         TIMESTAMPTZ   NOT NULL,   -- 7-day hard expiry, independent of cycle staleness
  used_at            TIMESTAMPTZ,
  is_used            BOOLEAN       NOT NULL DEFAULT FALSE,
  ip_address         INET,
  revoked_at         TIMESTAMPTZ,
  created_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  -- One token per alert: an alert IS a single check-in send, so it has exactly
  -- one live link. (A resend under a new cycle is a new alert row.)
  CONSTRAINT uq_milestone_checkin_tokens_alert UNIQUE (milestone_alert_id)
);
COMMENT ON TABLE milestone_checkin_tokens IS 'Vendor magic-link tokens for milestone check-ins. One token per milestone_alert (one check). Validity = not used AND not revoked AND before expires_at AND cycle_number = milestones.cycle_number. Answering spends it; a reschedule (cycle bump) strands it.';
COMMENT ON COLUMN milestone_checkin_tokens.cycle_number IS 'The milestone cycle at mint time. A token is stale the moment milestones.cycle_number moves past it — this is the declarative staleness that needs no cleanup pass.';


-- Vendor performance reviews: one PM rating (1-5) per completed contract.
-- Human-set, never inferred. The ONLY input to the Phase 8 performance
-- dimension (vendor flags are out of product scope). Editable for corrections.
CREATE TABLE vendor_performance_reviews (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_id  UUID        NOT NULL UNIQUE REFERENCES contracts(id) ON DELETE RESTRICT,
  vendor_id    UUID        NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,  -- = contracts.vendor_id (trigger-enforced)
  rating       SMALLINT    NOT NULL CHECK (rating BETWEEN 1 AND 5),
  notes        TEXT,
  reviewed_by  UUID        REFERENCES users(id) ON DELETE SET NULL,  -- reviewer is context, not a structural parent: a departed user must not block or destroy the rating
  reviewed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- when the current rating was set (advances on edit)
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- when the review first existed (frozen)
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE vendor_performance_reviews IS
  'One PM rating (1-5) per completed contract. Human-set, never inferred. Aggregated by v_vendor_performance to feed the Phase 8 performance dimension. UNIQUE(contract_id) = one review per contract.';

CREATE INDEX idx_vpr_vendor_id ON vendor_performance_reviews (vendor_id);

-- ========================================
-- GROUP 7: COMMUNICATION & AUDIT
-- ========================================

-- Email log: master audit log for ALL system emails
CREATE TABLE email_log (
  id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  recipient_email   VARCHAR(255)  NOT NULL,
  recipient_type    VARCHAR(20)   NOT NULL CHECK (recipient_type IN ('vendor_contact', 'user')),
  email_type        VARCHAR(30)   NOT NULL
                                  CHECK (email_type IN ('bid_invitation', 'bid_reminder',
                                                        'award_notification', 'decline_notification',
                                                        'milestone_alert', 'general')),
  subject           VARCHAR(500),
  reference_type    VARCHAR(50),
  reference_id      UUID,
  provider_message_id VARCHAR(255),
  status            VARCHAR(20)   NOT NULL DEFAULT 'queued'
                                  CHECK (status IN ('queued', 'sent', 'delivered', 'bounced', 'failed', 'complained')),
  sent_at           TIMESTAMPTZ,
  opened_at         TIMESTAMPTZ,
  clicked_at        TIMESTAMPTZ,
  error_message     TEXT,
  retry_count       INTEGER       NOT NULL DEFAULT 0,
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  email_log                IS 'Master audit log for all system emails. Tracks delivery, opens, clicks.';
COMMENT ON COLUMN email_log.reference_type IS 'Polymorphic: table name (e.g., bid_invitations, milestones).';
COMMENT ON COLUMN email_log.reference_id   IS 'Polymorphic: row ID in the referenced table.';
COMMENT ON COLUMN email_log.provider_message_id IS 'Provider-side message id (e.g. SES MessageId) returned at send time. Join key the SNS webhook uses to correlate async delivery/bounce/complaint events back to this row. NULL until a send succeeds.';


-- Vendor flags: PM manually flags problematic vendors
CREATE TABLE vendor_flags (
  id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  vendor_id     UUID          NOT NULL REFERENCES vendors(id)    ON DELETE RESTRICT,
  flagged_by    UUID          NOT NULL REFERENCES users(id)      ON DELETE RESTRICT,
  reason        VARCHAR(20)   NOT NULL
                              CHECK (reason IN ('missed_deadline', 'poor_quality', 'unresponsive', 'other')),
  notes         TEXT,
  milestone_id  UUID          REFERENCES milestones(id) ON DELETE SET NULL,
  is_resolved   BOOLEAN       NOT NULL DEFAULT FALSE,
  resolved_at   TIMESTAMPTZ,
  resolved_by   UUID          REFERENCES users(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  vendor_flags              IS 'PM flags for problematic vendors. Shown as warnings during bid vendor selection.';
COMMENT ON COLUMN vendor_flags.milestone_id IS 'Optional link to the milestone that triggered the flag.';


-- In-app notifications for dashboard
CREATE TABLE notifications (
  id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title               VARCHAR(255)  NOT NULL,
  message             TEXT,
  notification_type   VARCHAR(30)   NOT NULL,
  reference_type      VARCHAR(50),
  reference_id        UUID,
  is_read             BOOLEAN       NOT NULL DEFAULT FALSE,
  created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  notifications                IS 'In-app notifications for dashboard badges and notification panels.';
COMMENT ON COLUMN notifications.reference_type IS 'Polymorphic: links notification to the relevant entity.';


-- ============================================================================
-- GROUP 8: SYSTEM CONFIGURATION
-- ========================================

-- Holidays: org-wide non-working days for business-day arithmetic.
-- Weekends are NOT stored here (hardcoded in fn_is_business_day). This table
-- holds only the dates a human recognizes as a holiday. Seeded annually from
-- the Python `holidays` package (source='seeded'), then admin-editable.
-- Consumed by the vendor responsiveness clock (the "3 working days then flag
-- unresponsive" rule) and by check-in reminder offsets.
CREATE TABLE holidays (
  id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  holiday_date  DATE          NOT NULL UNIQUE,
  name          VARCHAR(100)  NOT NULL,
  source        VARCHAR(20)   NOT NULL DEFAULT 'manual'
                              CHECK (source IN ('seeded', 'manual')),
  created_by    UUID          REFERENCES users(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_holidays_name_not_blank CHECK (btrim(name) <> '')
);

COMMENT ON TABLE  holidays IS 'Org-wide non-working days. Weekends are NOT stored here (hardcoded in fn_is_business_day). Drives the vendor responsiveness clock and check-in reminder offsets.';
COMMENT ON COLUMN holidays.source     IS '"seeded" = inserted by the annual reseed job from the Python holidays package. "manual" = added by an admin. The reseed job only ever touches seeded rows.';
COMMENT ON COLUMN holidays.created_by IS 'NULL for seeded rows (no human actor). SET NULL on user delete: the holiday outlives the admin who added it.';



CREATE TABLE contract_signers (
  id          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name   VARCHAR(255)  NOT NULL,
  email       VARCHAR(255)  NOT NULL UNIQUE,
  title       VARCHAR(100),
  user_id     UUID          REFERENCES users(id) ON DELETE SET NULL,
  is_active   BOOLEAN       NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_contract_signers_full_name_not_blank CHECK (btrim(full_name) <> ''),
  CONSTRAINT chk_contract_signers_email_not_blank     CHECK (btrim(email) <> '')
);

COMMENT ON TABLE  contract_signers           IS 'Admin-managed roster of people authorized to sign contracts on behalf of BluOnX. The PM selects one per award; that signer becomes DocuSign routingOrder 1. Replaces the single CONTRACT_OWNER_SIGNER_* env pair.';
COMMENT ON COLUMN contract_signers.email     IS 'Address DocuSign routes the routingOrder-1 signing request to. Need not correspond to any users row.';
COMMENT ON COLUMN contract_signers.title     IS 'Free text, shown in the award dropdown to disambiguate signers (e.g. "President, Land Division"). Carries the division distinction without modeling divisions.';
COMMENT ON COLUMN contract_signers.user_id   IS 'Optional link to an internal user account. Nullable and unused today: signers are not required to be system users. Present so a future link needs no migration.';
COMMENT ON COLUMN contract_signers.is_active IS 'Soft revoke. Inactive signers stay selectable-in-history but are hidden from the award dropdown. No hard delete: awards.signer_id is RESTRICT.';


-- ============================================================================
-- SECTION 3: DEFERRED FOREIGN KEYS
-- (for tables created before their referenced tables)
-- ============================================================================

-- milestone_alerts → email_log FK (email_log created after milestone_alerts)
ALTER TABLE milestone_alerts
  ADD CONSTRAINT fk_milestone_alerts_email_log
  FOREIGN KEY (email_log_id) REFERENCES email_log(id) ON DELETE SET NULL;


-- awards -> contract_signers FK (contract_signers created after awards)
ALTER TABLE awards
  ADD CONSTRAINT fk_awards_signer
  FOREIGN KEY (signer_id) REFERENCES contract_signers(id) ON DELETE RESTRICT;


-- ============================================================================
-- SECTION 4: PARTIAL UNIQUE INDEXES
-- (enforce one active record per task while preserving full history)
-- ============================================================================

-- Only ONE active/pending award per task at any time.
-- Declined or cancelled awards are historical records and don't block new awards.
CREATE UNIQUE INDEX idx_awards_one_active_per_task
  ON awards (task_id)
  WHERE status NOT IN ('declined_by_vendor', 'cancelled');

-- Only ONE active contract per task at any time.
-- Terminated contracts are historical and don't block new contracts.
CREATE UNIQUE INDEX idx_contracts_one_active_per_task
  ON contracts (task_id)
  WHERE status NOT IN ('terminated');

-- Only ONE current (non-superseded, non-draft) submission per invitation.
-- Allows historical (superseded) versions and concurrent drafts to coexist.
-- Replaces the column-level UNIQUE that existed in v2.30.
CREATE UNIQUE INDEX idx_bid_submissions_current_per_invitation
  ON bid_submissions (bid_invitation_id)
  WHERE is_superseded = FALSE AND is_draft = FALSE;

-- Only ONE pending revision request per invitation at a time.
-- Terminal-state rows (submitted/declined/expired/cancelled) coexist as history.
CREATE UNIQUE INDEX idx_bid_revision_requests_one_pending_per_invitation
  ON bid_revision_requests (bid_invitation_id)
  WHERE status = 'pending';


-- ============================================================================
-- SECTION 5: PERFORMANCE INDEXES
-- ============================================================================
-- PostgreSQL auto-indexes PK and UNIQUE columns.
-- Below: FK columns, common filter/sort columns, and composite patterns.

-- ---- Group 2: Trade & Vendor ----
CREATE INDEX idx_vendor_contacts_vendor_id         ON vendor_contacts (vendor_id);
CREATE INDEX idx_vendor_trades_trade_id            ON vendor_trades (trade_id);
CREATE INDEX idx_vendor_documents_vendor_id         ON vendor_documents (vendor_id);
CREATE INDEX idx_vendor_documents_type_status       ON vendor_documents (vendor_id, document_type, status);
CREATE INDEX idx_vendors_status                     ON vendors (status) WHERE deleted_at IS NULL;
CREATE INDEX idx_vendors_onboarding                 ON vendors (onboarding_status) WHERE deleted_at IS NULL;

-- ---- Group 3: Project & Task ----
CREATE INDEX idx_projects_status                    ON projects (status) WHERE deleted_at IS NULL;
CREATE INDEX idx_projects_created_by                ON projects (created_by);
CREATE INDEX idx_project_documents_project_id       ON project_documents (project_id);
CREATE INDEX idx_projects_archived                  ON projects (archived_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_tasks_project_id                   ON tasks (project_id);
CREATE INDEX idx_tasks_trade_id                     ON tasks (trade_id);
CREATE INDEX idx_tasks_project_status               ON tasks (project_id, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_tasks_phase                        ON tasks (phase) WHERE deleted_at IS NULL;

-- ---- Group 4: Bid Lifecycle ----
CREATE INDEX idx_bid_templates_trade_id             ON bid_templates (trade_id);
CREATE INDEX idx_bid_template_items_template_id     ON bid_template_items (bid_template_id);
CREATE INDEX idx_bid_packages_task_id               ON bid_packages (task_id);
CREATE INDEX idx_bid_packages_task_status           ON bid_packages (task_id, status);
CREATE INDEX idx_bid_invitations_bid_package_id     ON bid_invitations (bid_package_id);
CREATE INDEX idx_bid_invitations_vendor_id          ON bid_invitations (vendor_id);
CREATE INDEX idx_bid_invitations_status             ON bid_invitations (bid_package_id, status);
CREATE INDEX idx_magic_link_tokens_invitation_id    ON magic_link_tokens (bid_invitation_id);
CREATE INDEX idx_magic_link_tokens_active           ON magic_link_tokens (expires_at, is_used)
                                                    WHERE is_used = FALSE AND revoked_at IS NULL;
CREATE INDEX idx_bid_submissions_invitation_id      ON bid_submissions (bid_invitation_id);
CREATE INDEX idx_bid_submissions_vendor_id          ON bid_submissions (vendor_id);
CREATE INDEX idx_bid_submissions_status             ON bid_submissions (status);
CREATE INDEX idx_bid_line_items_submission_id       ON bid_line_items (bid_submission_id);
CREATE INDEX idx_bid_attachments_submission_id      ON bid_attachments (bid_submission_id);

-- Create later on when added bid_template_id foreign key to bid_packages
CREATE INDEX idx_bid_packages_bid_template_id       ON bid_packages (bid_template_id);

CREATE INDEX idx_bid_packages_sow_document          ON bid_packages (scope_of_work_document_id) WHERE scope_of_work_document_id IS NOT NULL;

-- ---- Group 5: Award & Contract ----
CREATE INDEX idx_awards_task_id                     ON awards (task_id);
CREATE INDEX idx_awards_vendor_id                   ON awards (vendor_id);
CREATE INDEX idx_awards_status                      ON awards (status);
CREATE INDEX idx_awards_signer_id                   ON awards (signer_id);
CREATE INDEX idx_contracts_vendor_id                ON contracts (vendor_id);
CREATE INDEX idx_contracts_task_id                  ON contracts (task_id);
CREATE INDEX idx_contracts_status                   ON contracts (status);
CREATE INDEX idx_docusign_envelopes_contract_id     ON docusign_envelopes (contract_id);

-- ---- Group 6: Milestone Tracking ----
CREATE INDEX idx_milestones_task_id                 ON milestones (task_id);
CREATE INDEX idx_milestones_contract_id             ON milestones (contract_id);
CREATE INDEX idx_milestones_status                  ON milestones (status);
CREATE INDEX idx_milestones_dates                   ON milestones (start_date, end_date, status);
CREATE INDEX idx_milestone_responses_milestone_id   ON milestone_responses (milestone_id);
CREATE INDEX idx_milestone_alerts_milestone_id      ON milestone_alerts (milestone_id);
CREATE INDEX idx_milestone_alerts_email_log_id      ON milestone_alerts (email_log_id);
CREATE INDEX idx_milestone_events_milestone ON milestone_events (milestone_id, created_at DESC);
CREATE INDEX idx_milestone_checkin_tokens_hash     ON milestone_checkin_tokens (token_hash);
CREATE INDEX idx_milestone_checkin_tokens_milestone ON milestone_checkin_tokens (milestone_id);

-- ---- Group 7: Communication & Audit ----
CREATE INDEX idx_email_log_type_status              ON email_log (email_type, status);
CREATE INDEX idx_email_log_reference                ON email_log (reference_type, reference_id);
CREATE INDEX idx_email_log_sent_at                  ON email_log (sent_at);
-- Serves the newest-first ordering of the paginated email-log surfaces
-- (v_vendor_email_log). sent_at is NULL until a send succeeds, so created_at is
-- the only column that orders every row, including queued and failed ones.
CREATE INDEX idx_email_log_created_at               ON email_log (created_at DESC);
CREATE INDEX idx_email_log_provider_message_id      ON email_log (provider_message_id);
CREATE INDEX idx_vendor_flags_vendor_id             ON vendor_flags (vendor_id);
CREATE INDEX idx_vendor_flags_unresolved            ON vendor_flags (vendor_id, is_resolved)
                                                    WHERE is_resolved = FALSE;
CREATE INDEX idx_notifications_user_unread          ON notifications (user_id, is_read)
                                                    WHERE is_read = FALSE;

-- ---- Group 8: System Configuration ----
CREATE INDEX idx_contract_signers_active  ON contract_signers (is_active) WHERE is_active = TRUE;
CREATE INDEX idx_contract_signers_user_id ON contract_signers (user_id) WHERE user_id IS NOT NULL;


-- ---- Group 4: Bid Lifecycle additions ----
CREATE INDEX idx_bid_revision_requests_invitation ON bid_revision_requests (bid_invitation_id);
CREATE INDEX idx_bid_revision_requests_status ON bid_revision_requests (status);
CREATE INDEX idx_bid_revision_requests_original_submission ON bid_revision_requests (original_submission_id);
CREATE INDEX idx_magic_link_tokens_revision_request ON magic_link_tokens (bid_revision_request_id) WHERE bid_revision_request_id IS NOT NULL;


-- ============================================================================
-- ============================================================================
--
--  SECTION 6: TRIGGERS & BUSINESS LOGIC FUNCTIONS
--
-- ============================================================================
-- ============================================================================


-- ────────────────────────────────────────────────────────────────────────────
-- 6.1  AUTO-UPDATE updated_at TIMESTAMPS
-- ────────────────────────────────────────────────────────────────────────────
-- Applied to every table that has an updated_at column.

CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_trades_updated_at
  BEFORE UPDATE ON trades FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_vendors_updated_at
  BEFORE UPDATE ON vendors FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_vendor_contacts_updated_at
  BEFORE UPDATE ON vendor_contacts FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_vendor_documents_updated_at
  BEFORE UPDATE ON vendor_documents FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_projects_updated_at
  BEFORE UPDATE ON projects FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_tasks_updated_at
  BEFORE UPDATE ON tasks FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_bid_templates_updated_at
  BEFORE UPDATE ON bid_templates FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_bid_packages_updated_at
  BEFORE UPDATE ON bid_packages FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_bid_invitations_updated_at
  BEFORE UPDATE ON bid_invitations FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_bid_submissions_updated_at
  BEFORE UPDATE ON bid_submissions FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_awards_updated_at
  BEFORE UPDATE ON awards FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_contracts_updated_at
  BEFORE UPDATE ON contracts FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_docusign_envelopes_updated_at
  BEFORE UPDATE ON docusign_envelopes FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_milestones_updated_at
  BEFORE UPDATE ON milestones FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_bid_revision_requests_updated_at
  BEFORE UPDATE ON bid_revision_requests FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_contract_signers_updated_at
  BEFORE UPDATE ON contract_signers FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.2  BID PACKAGE ROUND NUMBER AUTO-INCREMENT
-- ────────────────────────────────────────────────────────────────────────────
-- When a new bid_package is created for a task, round_number is set to
-- (current max round for that task) + 1. Ensures sequential round tracking.

CREATE OR REPLACE FUNCTION fn_set_bid_package_round_number()
RETURNS TRIGGER AS $$
BEGIN
  SELECT COALESCE(MAX(round_number), 0) + 1
    INTO NEW.round_number
    FROM bid_packages
   WHERE task_id = NEW.task_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bid_packages_round_number
  BEFORE INSERT ON bid_packages
  FOR EACH ROW EXECUTE FUNCTION fn_set_bid_package_round_number();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.3  SYNC BID INVITATION STATUS ON SUBMISSION
-- ────────────────────────────────────────────────────────────────────────────
-- When a bid_submission is created with or transitions to 'submitted',
-- automatically update the parent bid_invitation status and responded_at.
-- Handles both INSERT (draft or direct submit) and UPDATE (draft → submitted).
-- responded_at uses COALESCE so revisions do not overwrite the original
-- response timestamp. Original behavior is preserved for first-time submits.

CREATE OR REPLACE FUNCTION fn_sync_bid_invitation_on_submission()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.status = 'submitted' AND (OLD IS NULL OR OLD.status IS DISTINCT FROM 'submitted') THEN
    UPDATE bid_invitations
       SET status       = 'submitted',
           responded_at = COALESCE(responded_at, NOW())
     WHERE id = NEW.bid_invitation_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bid_submissions_sync_invitation
  AFTER INSERT OR UPDATE ON bid_submissions
  FOR EACH ROW EXECUTE FUNCTION fn_sync_bid_invitation_on_submission();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.4  VENDOR ONBOARDING STATUS SYNC (DISABLED)
-- ────────────────────────────────────────────────────────────────────────────
-- DECISION: Onboarding status is managed manually by the PM, not auto-synced
-- from documents. The PM may need to verify details beyond document presence
-- (e.g., confirm insurance with carrier, review W-9 for corrections).
-- This trigger is preserved here for potential future activation.

-- CREATE OR REPLACE FUNCTION fn_sync_vendor_onboarding_status()
-- RETURNS TRIGGER AS $$
-- DECLARE
--   v_vendor_id   UUID;
--   v_valid_count INTEGER;
--   v_new_status  VARCHAR(20);
-- BEGIN
--   v_vendor_id := COALESCE(NEW.vendor_id, OLD.vendor_id);
--   SELECT COUNT(DISTINCT document_type)
--     INTO v_valid_count
--     FROM vendor_documents
--    WHERE vendor_id = v_vendor_id
--      AND status = 'valid';
--   IF v_valid_count >= 3 THEN
--     v_new_status := 'complete';
--   ELSIF v_valid_count >= 1 THEN
--     v_new_status := 'partial';
--   ELSE
--     v_new_status := 'pending';
--   END IF;
--   UPDATE vendors
--      SET onboarding_status = v_new_status
--    WHERE id = v_vendor_id
--      AND onboarding_status IS DISTINCT FROM v_new_status;
--   RETURN COALESCE(NEW, OLD);
-- END;
-- $$ LANGUAGE plpgsql;

-- CREATE TRIGGER trg_vendor_documents_sync_onboarding
--   AFTER INSERT OR UPDATE OR DELETE ON vendor_documents
--   FOR EACH ROW EXECUTE FUNCTION fn_sync_vendor_onboarding_status();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.4a  DENORMALIZED FIELD CONSISTENCY: bid_submissions.vendor_id
-- ────────────────────────────────────────────────────────────────────────────
-- Ensures bid_submissions.vendor_id always matches the vendor_id on the
-- parent bid_invitation. Prevents data mismatch on denormalized FK.
--
-- BACKEND CONTRACT: The vendor never inserts into bid_submissions directly.
-- The API layer must always resolve vendor_id from the bid_invitation record
-- when creating a submission. Never trust client-supplied vendor_id.

CREATE OR REPLACE FUNCTION fn_enforce_submission_vendor_consistency()
RETURNS TRIGGER AS $$
DECLARE
  v_invitation_vendor_id UUID;
BEGIN
  SELECT vendor_id INTO v_invitation_vendor_id
    FROM bid_invitations
   WHERE id = NEW.bid_invitation_id;

  IF NEW.vendor_id IS DISTINCT FROM v_invitation_vendor_id THEN
    RAISE EXCEPTION 'bid_submissions.vendor_id (%) does not match bid_invitations.vendor_id (%) for invitation %',
      NEW.vendor_id, v_invitation_vendor_id, NEW.bid_invitation_id;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bid_submissions_enforce_vendor
  BEFORE INSERT OR UPDATE OF vendor_id ON bid_submissions
  FOR EACH ROW EXECUTE FUNCTION fn_enforce_submission_vendor_consistency();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.4b  DENORMALIZED FIELD CONSISTENCY: awards.vendor_id & awards.task_id
-- ────────────────────────────────────────────────────────────────────────────
-- Ensures awards.vendor_id matches bid_submissions.vendor_id AND
-- awards.task_id matches the chain: bid_submission → bid_invitation →
-- bid_package → task. Prevents awarding to wrong vendor or wrong task.

CREATE OR REPLACE FUNCTION fn_enforce_award_consistency()
RETURNS TRIGGER AS $$
DECLARE
  v_submission_vendor_id UUID;
  v_chain_task_id        UUID;
BEGIN
  -- Validate vendor_id: awards.vendor_id must match bid_submissions.vendor_id
  SELECT vendor_id INTO v_submission_vendor_id
    FROM bid_submissions
   WHERE id = NEW.bid_submission_id;

  IF NEW.vendor_id IS DISTINCT FROM v_submission_vendor_id THEN
    RAISE EXCEPTION 'awards.vendor_id (%) does not match bid_submissions.vendor_id (%) for submission %',
      NEW.vendor_id, v_submission_vendor_id, NEW.bid_submission_id;
  END IF;

  -- Validate task_id: walk bid_submission → bid_invitation → bid_package → task
  SELECT bp.task_id INTO v_chain_task_id
    FROM bid_submissions bs
    JOIN bid_invitations bi ON bi.id = bs.bid_invitation_id
    JOIN bid_packages    bp ON bp.id = bi.bid_package_id
   WHERE bs.id = NEW.bid_submission_id;

  IF NEW.task_id IS DISTINCT FROM v_chain_task_id THEN
    RAISE EXCEPTION 'awards.task_id (%) does not match bid chain task_id (%) for submission %',
      NEW.task_id, v_chain_task_id, NEW.bid_submission_id;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_awards_enforce_consistency
  BEFORE INSERT OR UPDATE OF vendor_id, task_id ON awards
  FOR EACH ROW EXECUTE FUNCTION fn_enforce_award_consistency();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.4c  DENORMALIZED FIELD CONSISTENCY: contracts.vendor_id & contracts.task_id
-- ────────────────────────────────────────────────────────────────────────────
-- Ensures contracts.vendor_id matches awards.vendor_id AND
-- contracts.task_id matches awards.task_id. Prevents contract mislinks.

CREATE OR REPLACE FUNCTION fn_enforce_contract_consistency()
RETURNS TRIGGER AS $$
DECLARE
  v_award_vendor_id UUID;
  v_award_task_id   UUID;
BEGIN
  SELECT vendor_id, task_id
    INTO v_award_vendor_id, v_award_task_id
    FROM awards
   WHERE id = NEW.award_id;

  IF NEW.vendor_id IS DISTINCT FROM v_award_vendor_id THEN
    RAISE EXCEPTION 'contracts.vendor_id (%) does not match awards.vendor_id (%) for award %',
      NEW.vendor_id, v_award_vendor_id, NEW.award_id;
  END IF;

  IF NEW.task_id IS DISTINCT FROM v_award_task_id THEN
    RAISE EXCEPTION 'contracts.task_id (%) does not match awards.task_id (%) for award %',
      NEW.task_id, v_award_task_id, NEW.award_id;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_contracts_enforce_consistency
  BEFORE INSERT OR UPDATE OF vendor_id, task_id ON contracts
  FOR EACH ROW EXECUTE FUNCTION fn_enforce_contract_consistency();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.4d  DENORMALIZED FIELD CONSISTENCY: milestones.task_id
-- ────────────────────────────────────────────────────────────────────────────
-- Ensures milestones.task_id always matches the task_id on the
-- parent contract. Prevents milestone-to-wrong-task mislinks.

CREATE OR REPLACE FUNCTION fn_enforce_milestone_task_consistency()
RETURNS TRIGGER AS $$
DECLARE
  v_contract_task_id UUID;
BEGIN
  SELECT task_id INTO v_contract_task_id
    FROM contracts
   WHERE id = NEW.contract_id;

  IF NEW.task_id IS DISTINCT FROM v_contract_task_id THEN
    RAISE EXCEPTION 'milestones.task_id (%) does not match contracts.task_id (%) for contract %',
      NEW.task_id, v_contract_task_id, NEW.contract_id;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_milestones_enforce_task
  BEFORE INSERT OR UPDATE OF task_id ON milestones
  FOR EACH ROW EXECUTE FUNCTION fn_enforce_milestone_task_consistency();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.5  VENDOR CAPACITY MANAGEMENT
-- ────────────────────────────────────────────────────────────────────────────
-- Two triggers maintain vendors.current_active_jobs:
--
--   A) Award accepted        → +1  (vendor commits to a new job)
--      Award revoked (cancelled/declined AFTER acceptance) → -1
--      BUT only if no contract already completed/terminated for this award
--      (prevents double-decrement)
--
--   B) Contract completed/terminated → -1  (job finished or cancelled)
--
-- GREATEST(..., 0) prevents negative values as a safety net.

-- 6.5a: Award status changes
CREATE OR REPLACE FUNCTION fn_manage_vendor_capacity_on_award()
RETURNS TRIGGER AS $$
BEGIN
  -- INCREMENT: award just accepted
  IF NEW.status = 'accepted' AND OLD.status IS DISTINCT FROM 'accepted' THEN
    UPDATE vendors
       SET current_active_jobs = current_active_jobs + 1
     WHERE id = NEW.vendor_id;
  END IF;

  -- DECREMENT: accepted award revoked (only if contract hasn't already handled it)
  IF OLD.status = 'accepted' AND NEW.status IN ('cancelled', 'declined_by_vendor') THEN
    -- Check: if a contract for this award was already completed/terminated,
    -- the contract trigger already decremented, so skip to avoid double-decrement.
    IF NOT EXISTS (
      SELECT 1 FROM contracts
       WHERE award_id = NEW.id
         AND status IN ('completed', 'terminated')
    ) THEN
      UPDATE vendors
         SET current_active_jobs = GREATEST(current_active_jobs - 1, 0)
       WHERE id = NEW.vendor_id;
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_awards_manage_vendor_capacity
  AFTER UPDATE ON awards
  FOR EACH ROW EXECUTE FUNCTION fn_manage_vendor_capacity_on_award();


-- 6.5b: Contract status changes
CREATE OR REPLACE FUNCTION fn_manage_vendor_capacity_on_contract()
RETURNS TRIGGER AS $$
BEGIN
  -- DECREMENT: contract completed or terminated (job is done)
  IF NEW.status IN ('completed', 'terminated')
     AND OLD.status NOT IN ('completed', 'terminated') THEN
    UPDATE vendors
       SET current_active_jobs = GREATEST(current_active_jobs - 1, 0)
     WHERE id = NEW.vendor_id;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_contracts_manage_vendor_capacity
  AFTER UPDATE ON contracts
  FOR EACH ROW EXECUTE FUNCTION fn_manage_vendor_capacity_on_contract();


-- 6.5c: Vendor performance review vendor_id consistency
-- Keeps vendor_performance_reviews.vendor_id in step with the contract's vendor
-- (mirrors the denormalized-FK guard pattern used on awards/milestones).
CREATE OR REPLACE FUNCTION fn_enforce_review_vendor_consistency()
RETURNS TRIGGER AS $$
DECLARE v_contract_vendor UUID;
BEGIN
  SELECT vendor_id INTO v_contract_vendor FROM contracts WHERE id = NEW.contract_id;
  IF v_contract_vendor IS NULL THEN
    RAISE EXCEPTION 'Contract % not found', NEW.contract_id USING ERRCODE = 'PT404';
  END IF;
  IF NEW.vendor_id <> v_contract_vendor THEN
    RAISE EXCEPTION 'vendor_id (%) does not match contract vendor (%)',
      NEW.vendor_id, v_contract_vendor USING ERRCODE = 'PT422';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers (their functions live in SECTION 1/6 respectively; fn_set_updated_at
-- already exists, fn_enforce_review_vendor_consistency is BLOCK B).
CREATE TRIGGER trg_vpr_vendor_consistency
  BEFORE INSERT OR UPDATE OF vendor_id, contract_id ON vendor_performance_reviews
  FOR EACH ROW EXECUTE FUNCTION fn_enforce_review_vendor_consistency();

CREATE TRIGGER trg_vpr_updated_at
  BEFORE UPDATE ON vendor_performance_reviews
  FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.6  SUPERSESSION CHAIN VALIDATOR
-- ────────────────────────────────────────────────────────────────────────────
-- Validates that any submission row with a non-NULL supersedes_submission_id
-- forms a well-shaped chain: predecessor exists, same bid_invitation, the
-- predecessor is finalized (not a draft), and revision_number is exactly
-- predecessor.revision_number + 1.
--
-- Fires only on INSERT or UPDATE of supersedes_submission_id / revision_number,
-- so the predecessor's own is_superseded flip does NOT re-trigger validation.

CREATE OR REPLACE FUNCTION fn_enforce_supersession_chain()
RETURNS TRIGGER AS $$
DECLARE
  v_predecessor RECORD;
BEGIN
  IF NEW.supersedes_submission_id IS NULL THEN
    RETURN NEW;
  END IF;

  SELECT bid_invitation_id, is_draft, revision_number
    INTO v_predecessor
    FROM bid_submissions
   WHERE id = NEW.supersedes_submission_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Supersedes_submission_id (%) references a non-existent submission', NEW.supersedes_submission_id;
  END IF;

  IF v_predecessor.bid_invitation_id != NEW.bid_invitation_id THEN
    RAISE EXCEPTION 'Supersession must stay within the same bid_invitation. predecessor=%, new=%',
      v_predecessor.bid_invitation_id, NEW.bid_invitation_id;
  END IF;

  IF v_predecessor.is_draft = TRUE THEN
    RAISE EXCEPTION 'Cannot supersede a draft submission (predecessor id = %)', NEW.supersedes_submission_id;
  END IF;

  IF NEW.revision_number != v_predecessor.revision_number + 1 THEN
    RAISE EXCEPTION 'revision_number must equal predecessor.revision_number + 1. Got: %, expected: %',
      NEW.revision_number, v_predecessor.revision_number + 1;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bid_submissions_enforce_supersession
  BEFORE INSERT OR UPDATE OF supersedes_submission_id, revision_number
  ON bid_submissions
  FOR EACH ROW EXECUTE FUNCTION fn_enforce_supersession_chain();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.7  PREDECESSOR-FLIP ON REVISION FINALIZE
-- ────────────────────────────────────────────────────────────────────────────
-- The load-bearing trigger for the per-vendor bid revision feature. When a
-- revision draft finalizes (is_draft TRUE → FALSE), flips the predecessor's
-- is_superseded to TRUE.
--
-- Critical: BEFORE UPDATE OF is_draft. The inner UPDATE (against the
-- predecessor) runs to completion inside the BEFORE trigger, including its
-- own index update. By the time Postgres checks the partial unique index
-- on the outer UPDATE, the predecessor has already been removed from the
-- index (is_superseded = TRUE no longer matches the predicate). The outer
-- UPDATE sees only one matching row for its bid_invitation_id — no conflict.
--
-- Recursion termination: the OF is_draft column filter prevents this trigger
-- from re-firing on the predecessor's own UPDATE (which only touches
-- is_superseded). The body's OLD.is_draft = TRUE guard is defense-in-depth.

CREATE OR REPLACE FUNCTION fn_flip_superseded_on_revision_finalize()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.supersedes_submission_id IS NOT NULL
     AND OLD.is_draft = TRUE
     AND NEW.is_draft = FALSE
     AND NEW.is_superseded = FALSE THEN

    UPDATE bid_submissions
       SET is_superseded = TRUE
     WHERE id = NEW.supersedes_submission_id
       AND is_superseded = FALSE;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bid_submissions_flip_superseded
  BEFORE UPDATE OF is_draft ON bid_submissions
  FOR EACH ROW EXECUTE FUNCTION fn_flip_superseded_on_revision_finalize();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.8  AUTO-CLOSE REVISION REQUEST ON FINALIZE
-- ────────────────────────────────────────────────────────────────────────────
-- When a revision finalizes, close the matching pending revision request
-- to status = 'submitted' in the same transaction.
--
-- AFTER UPDATE only (never INSERT) — the function body dereferences OLD.
-- Revisions are always created as drafts and finalized via UPDATE, so
-- UPDATE-only is sufficient.

CREATE OR REPLACE FUNCTION fn_close_revision_request_on_finalize()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.supersedes_submission_id IS NOT NULL
     AND OLD.is_draft = TRUE
     AND NEW.is_draft = FALSE
     AND NEW.status = 'submitted' THEN

    UPDATE bid_revision_requests
       SET status = 'submitted',
           responded_at = NOW()
     WHERE original_submission_id = NEW.supersedes_submission_id
       AND status = 'pending';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bid_submissions_close_revision_request
  AFTER UPDATE ON bid_submissions
  FOR EACH ROW EXECUTE FUNCTION fn_close_revision_request_on_finalize();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.9  SUPABASE AUTH → USER PROFILE CREATION
-- ────────────────────────────────────────────────────────────────────────────
-- Automatically creates a row in public.users when a new user signs up
-- via Supabase Auth. Uses SECURITY DEFINER because the trigger runs
-- in auth schema context but inserts into public schema.
--
-- The signup flow should pass full_name and role in raw_user_meta_data:
--   supabase.auth.signUp({ email, password, options: {
--     data: { full_name: '...', role: 'project_manager' }
--   }})

CREATE OR REPLACE FUNCTION fn_handle_new_auth_user()
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

-- v4.0: fn_handle_new_auth_user() is REPLACED in Section 9.E (E.12) to also
-- read optional `roles` / `is_employee` metadata. Same behaviour otherwise.
-- NOTE: This trigger is on auth.users (Supabase managed schema).
-- Run this AFTER the public schema is deployed.
CREATE TRIGGER trg_on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION fn_handle_new_auth_user();

  -- ────────────────────────────────────────────────────────────────────────────
-- 6.10  MILESTONE_EVENTS IMMUTABILITY
-- ────────────────────────────────────────────────────────────────────────────
-- The ledger IS the audit trail. Not even a service_role bug may rewrite it.

CREATE OR REPLACE FUNCTION fn_block_milestone_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'milestone_events is append-only (attempted % on event %)',
    TG_OP, COALESCE(OLD.id, NEW.id)
    USING ERRCODE = 'PT403';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_milestone_events_immutable
  BEFORE UPDATE OR DELETE ON milestone_events
  FOR EACH ROW EXECUTE FUNCTION fn_block_milestone_event_mutation();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.11  MILESTONE DATE GUARD (closes the backdoor-reschedule hole)
-- ────────────────────────────────────────────────────────────────────────────
-- Without this, a plain UPDATE on end_date would move the date WITHOUT bumping
-- cycle_number and WITHOUT writing a ledger event, leaving every outstanding
-- check-in token valid against a plan that no longer exists.
--
-- Live = status has left 'scheduled', OR any check-in email has been sent.
-- transition_milestone() sets a transaction-local flag to identify itself as the
-- legitimate writer; every other writer is blocked.

CREATE OR REPLACE FUNCTION fn_guard_milestone_dates()
RETURNS TRIGGER AS $$
DECLARE
  v_is_authoritative BOOLEAN;
  v_alerts_sent      BOOLEAN;
BEGIN
  IF NEW.start_date IS NOT DISTINCT FROM OLD.start_date
     AND NEW.end_date IS NOT DISTINCT FROM OLD.end_date THEN
    RETURN NEW;
  END IF;

  v_is_authoritative := COALESCE(
    current_setting('bluonx.milestone_transition', TRUE) = 'on', FALSE
  );
  IF v_is_authoritative THEN
    RETURN NEW;
  END IF;

  SELECT EXISTS (SELECT 1 FROM milestone_alerts WHERE milestone_id = OLD.id)
    INTO v_alerts_sent;

  IF OLD.status <> 'scheduled' OR v_alerts_sent THEN
    RAISE EXCEPTION
      'Dates are locked once the milestone is live (status=%, check-ins sent=%). Use reschedule.',
      OLD.status, v_alerts_sent
      USING ERRCODE = 'PT409';
  END IF;

  -- Still scheduled and never announced: a plan CORRECTION, not a slip.
  NEW.baseline_end_date := NEW.end_date;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_milestones_guard_dates
  BEFORE UPDATE OF start_date, end_date ON milestones
  FOR EACH ROW EXECUTE FUNCTION fn_guard_milestone_dates();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.12  HOLIDAY CALENDAR GUARDRAILS
-- ────────────────────────────────────────────────────────────────────────────
-- Three limits. None exist because an admin would act maliciously. They exist
-- because a bad bulk import or a date-range UI bug would silently stop every
-- vendor from ever being flagged, and nobody would notice for weeks.
--   1. Past dates frozen      - protects the integrity of milestone_events
--   2. Max 25 holidays / year - US federal is 11; 25 leaves generous headroom
--   3. Max 14 consecutive     - permits a shutdown week, blocks a shutdown month
-- "Today" is America/Chicago (matching v_milestone_overview); bare CURRENT_DATE
-- is UTC on Supabase and would reject a legitimate edit made 00:00-06:00 local.

CREATE OR REPLACE FUNCTION fn_holidays_guardrails()
RETURNS TRIGGER AS $$
DECLARE
  v_today      DATE := (NOW() AT TIME ZONE 'America/Chicago')::date;
  v_date       DATE;
  v_year_count INTEGER;
  v_run_start  DATE;
  v_run_end    DATE;
  v_run_len    INTEGER;
BEGIN
  v_date := COALESCE(NEW.holiday_date, OLD.holiday_date);

  IF v_date < v_today THEN
    RAISE EXCEPTION 'Cannot % a holiday on % (past dates are frozen; it may already have affected a responsiveness decision)',
      lower(TG_OP), v_date USING ERRCODE = 'PT422';
  END IF;

  IF TG_OP = 'UPDATE' AND OLD.holiday_date < v_today THEN
    RAISE EXCEPTION 'Cannot modify the holiday on % (past dates are frozen)',
      OLD.holiday_date USING ERRCODE = 'PT422';
  END IF;

  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;

  SELECT COUNT(*) INTO v_year_count
    FROM holidays
   WHERE EXTRACT(YEAR FROM holiday_date) = EXTRACT(YEAR FROM NEW.holiday_date)
     AND id <> NEW.id;

  IF v_year_count >= 25 THEN
    RAISE EXCEPTION 'Year % already has % holidays (max 25). Remove one before adding another.',
      EXTRACT(YEAR FROM NEW.holiday_date), v_year_count USING ERRCODE = 'PT422';
  END IF;

  -- Contiguous-run cap. Walk out from the new date across holidays AND weekends
  -- alike, since a Fri-to-Mon block is a 4-day closure in practice.
  v_run_start := NEW.holiday_date;
  LOOP
    EXIT WHEN NOT EXISTS (
      SELECT 1 FROM holidays WHERE holiday_date = v_run_start - 1 AND id <> NEW.id
    ) AND EXTRACT(DOW FROM v_run_start - 1) NOT IN (0, 6);
    v_run_start := v_run_start - 1;
  END LOOP;

  v_run_end := NEW.holiday_date;
  LOOP
    EXIT WHEN NOT EXISTS (
      SELECT 1 FROM holidays WHERE holiday_date = v_run_end + 1 AND id <> NEW.id
    ) AND EXTRACT(DOW FROM v_run_end + 1) NOT IN (0, 6);
    v_run_end := v_run_end + 1;
  END LOOP;

  v_run_len := (v_run_end - v_run_start) + 1;
  IF v_run_len > 14 THEN
    RAISE EXCEPTION 'This would create a % day closure from % to % (max 14 consecutive non-working days)',
      v_run_len, v_run_start, v_run_end USING ERRCODE = 'PT422';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_holidays_guardrails
  BEFORE INSERT OR UPDATE OR DELETE ON holidays
  FOR EACH ROW EXECUTE FUNCTION fn_holidays_guardrails();

CREATE TRIGGER trg_holidays_updated_at
  BEFORE UPDATE ON holidays FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();


-- ────────────────────────────────────────────────────────────────────────────
-- 6.13  BUSINESS-DAY ARITHMETIC (single source of calendar truth)
-- ────────────────────────────────────────────────────────────────────────────
-- Every consumer (APScheduler responsiveness sweep, reminder offsets) calls
-- these. No weekend/holiday-skipping date math should exist anywhere else.
-- STABLE, not IMMUTABLE: they read a table whose contents change.
-- Read-only helpers, so unlike the write RPCs in Section 7 they are granted to
-- authenticated as well as service_role. anon is revoked: anon has no SELECT
-- policy on holidays, would see zero rows, and answer TRUE for Christmas Day.

CREATE OR REPLACE FUNCTION fn_is_business_day(p_date DATE)
RETURNS BOOLEAN AS $$
  SELECT p_date IS NOT NULL
     AND EXTRACT(DOW FROM p_date) NOT IN (0, 6)
     AND NOT EXISTS (SELECT 1 FROM holidays WHERE holiday_date = p_date);
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION fn_is_business_day(DATE) IS 'TRUE when the date is neither a weekend nor a holiday. Weekends are hardcoded by design.';

CREATE OR REPLACE FUNCTION fn_add_business_days(p_start DATE, p_days INTEGER)
RETURNS DATE AS $$
DECLARE
  v_cursor    DATE    := p_start;
  v_remaining INTEGER := p_days;
  v_guard     INTEGER := 0;
BEGIN
  IF p_start IS NULL OR p_days IS NULL THEN
    RETURN NULL;
  END IF;
  IF p_days < 0 THEN
    RAISE EXCEPTION 'fn_add_business_days does not support negative offsets (got %)', p_days
      USING ERRCODE = 'PT422';
  END IF;

  WHILE v_remaining > 0 LOOP
    v_cursor := v_cursor + 1;
    IF fn_is_business_day(v_cursor) THEN
      v_remaining := v_remaining - 1;
    END IF;
    v_guard := v_guard + 1;
    IF v_guard > (p_days * 7) + 400 THEN
      RAISE EXCEPTION 'fn_add_business_days runaway from % (+% days). Check holidays for an implausible block.',
        p_start, p_days;
    END IF;
  END LOOP;

  RETURN v_cursor;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION fn_add_business_days(DATE, INTEGER) IS 'Advance a date by N business days. Inverse of fn_business_days_between. A check-in sent Friday with a 3 working-day window is due end of the following Wednesday.';

CREATE OR REPLACE FUNCTION fn_business_days_between(p_from DATE, p_to DATE)
RETURNS INTEGER AS $$
  SELECT CASE
    WHEN p_from IS NULL OR p_to IS NULL THEN NULL
    WHEN p_to <= p_from THEN 0
    ELSE (
      SELECT COUNT(*)::INTEGER
        FROM generate_series(p_from + 1, p_to, INTERVAL '1 day') AS d(day)
       WHERE fn_is_business_day(d.day::DATE)
    )
  END;
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION fn_business_days_between(DATE, DATE) IS 'Business days elapsed in (p_from, p_to]. Exact inverse of fn_add_business_days. Returns 0 when p_to <= p_from.';

REVOKE ALL ON FUNCTION fn_is_business_day(DATE)             FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION fn_add_business_days(DATE, INTEGER)  FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION fn_business_days_between(DATE, DATE)  FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION fn_is_business_day(DATE)             TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION fn_add_business_days(DATE, INTEGER)  TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION fn_business_days_between(DATE, DATE) TO authenticated, service_role;



-- ============================================================================
-- SECTION 7: APPLICATION RPC FUNCTIONS (callable via PostgREST /rpc)
-- ============================================================================
-- Unlike the trigger functions above, these are invoked directly by the
-- backend through db.rpc(). Each runs in a single implicit transaction, which
-- is how the app gets multi-statement atomicity that PostgREST otherwise can't
-- express (one statement per HTTP request).
-- ----------------------------------------------------------------------------

-- PRIVILEGE RULE (Supabase): GRANT alone is NOT sufficient. Supabase's default
-- privileges already grant EXECUTE on public functions to anon and authenticated,
-- so every write RPC needs BOTH:
--   REVOKE ALL   ON FUNCTION <fn>(<args>) FROM PUBLIC, anon, authenticated;
--   GRANT EXECUTE ON FUNCTION <fn>(<args>) TO service_role;
-- ----------------------------------------------------------------------------

-- 7.1  fn_create_award — atomic award write (Task 9.2 / fix #1)
-- ----------------------------------------------------------------------------
-- Inserts the award at 'pending_acceptance' AND flips the task to 'awarded' in
-- ONE transaction, so a partial failure can never leave a dangling award with
-- an un-flipped task. The pre-award validation gate (block / warn / override)
-- is enforced in Python BEFORE this is called; this function is the write only.
-- The existing BEFORE-INSERT consistency trigger (fn_enforce_award_consistency)
-- and the award capacity trigger still fire inside this transaction. A second
-- active award on the same task raises 23505 from idx_awards_one_active_per_task
-- and rolls the whole thing back (surfaced as a clean 409 by the service).

CREATE OR REPLACE FUNCTION fn_create_award(
  p_task_id                UUID,
  p_bid_submission_id      UUID,
  p_vendor_id              UUID,
  p_awarded_by             UUID,
  p_award_amount           NUMERIC,
  p_has_override           BOOLEAN,
  p_override_justification TEXT,
  p_instructions           TEXT,
  p_contract_valid_days    INTEGER,
  p_work_duration_days     INTEGER,
  p_validation_results     JSONB,
  p_signer_id              UUID
)
RETURNS SETOF awards AS $$
DECLARE
  v_award awards;
BEGIN
  INSERT INTO awards (
    task_id, bid_submission_id, vendor_id, awarded_by, award_amount,
    instructions, contract_valid_days, work_duration_days,
    has_override, override_justification, validation_results, status,
    signer_id
  ) VALUES (
    p_task_id, p_bid_submission_id, p_vendor_id, p_awarded_by, p_award_amount,
    p_instructions, COALESCE(p_contract_valid_days, 365), p_work_duration_days,
    p_has_override, p_override_justification, p_validation_results,
    'pending_acceptance',
    p_signer_id
  )
  RETURNING * INTO v_award;

  UPDATE tasks SET status = 'awarded' WHERE id = p_task_id;

  RETURN NEXT v_award;
END;
$$ LANGUAGE plpgsql;

-- Writes go through the service_role key (FastAPI write path); not exposed to
-- the authenticated role, which only ever reads.
REVOKE ALL ON FUNCTION fn_create_award(
  UUID, UUID, UUID, UUID, NUMERIC, BOOLEAN, TEXT, TEXT, INTEGER, INTEGER, JSONB, UUID
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION fn_create_award(
  UUID, UUID, UUID, UUID, NUMERIC, BOOLEAN, TEXT, TEXT, INTEGER, INTEGER, JSONB, UUID
) TO service_role;

-- 7.2  fn_create_bid_package_with_invitations — atomic bid-package write
-- ----------------------------------------------------------------------------
-- Creates the bid_packages row, its bid_package_documents, one bid_invitations
-- row per vendor (status 'pending_send', sent_at NULL), and one magic_link_tokens
-- row per invitation, then flips a draft task to 'bidding' -- all in ONE
-- transaction. Either the whole package exists or none of it does, so a failure
-- can never leave a partial package or orphan tokens (which previously caused
-- duplicate packages when the PM retried).
--
-- Validation (task/vendor/contact/document checks) runs in Python BEFORE this is
-- called; this function is the write only. Token HASHES are generated in Python
-- and passed in via p_vendors; the raw tokens never touch the DB. Emails are sent
-- AFTER this returns (a side effect that cannot live in a DB transaction); the
-- service then reconciles each invitation to 'sent' or 'send_failed'.
--
-- p_vendors is a JSONB array of objects:
--   {"vendor_id": uuid, "vendor_contact_id": uuid, "token_hash": text}
-- Every token shares the package deadline as its expires_at.
--
-- Returns JSONB: {bid_package_id, round_number, invitations:[{vendor_id, invitation_id}]}
-- so the service can match its in-memory raw tokens back to the new invitation ids.

CREATE OR REPLACE FUNCTION fn_create_bid_package_with_invitations(
  p_task_id                    UUID,
  p_deadline                   TIMESTAMPTZ,
  p_bid_template_id            UUID,
  p_created_by                 UUID,
  p_instructions               TEXT,
  p_desired_start_date         DATE,
  p_scope_of_work_document_id  UUID,
  p_project_document_ids       UUID[],
  p_vendors                    JSONB
)
RETURNS JSONB AS $$
DECLARE
  v_bid_package   bid_packages;
  v_doc_id        UUID;
  v_vendor        JSONB;
  v_invitation_id UUID;
  v_invitations   JSONB := '[]'::jsonb;
BEGIN
  -- 1. Bid package (round_number auto-set by trg_bid_packages_round_number)
  INSERT INTO bid_packages (
    task_id, deadline, bid_template_id, created_by,
    instructions, desired_start_date, scope_of_work_document_id, status
  ) VALUES (
    p_task_id, p_deadline, p_bid_template_id, p_created_by,
    p_instructions, p_desired_start_date, p_scope_of_work_document_id, 'open'
  )
  RETURNING * INTO v_bid_package;

  -- 2. Bid package documents
  IF p_project_document_ids IS NOT NULL THEN
    FOREACH v_doc_id IN ARRAY p_project_document_ids LOOP
      INSERT INTO bid_package_documents (bid_package_id, project_document_id)
      VALUES (v_bid_package.id, v_doc_id);
    END LOOP;
  END IF;

  -- 3. One invitation (not yet emailed) + one magic link token per vendor
  FOR v_vendor IN SELECT * FROM jsonb_array_elements(p_vendors) LOOP
    INSERT INTO bid_invitations (
      bid_package_id, vendor_id, vendor_contact_id, status, sent_at
    ) VALUES (
      v_bid_package.id,
      (v_vendor->>'vendor_id')::uuid,
      (v_vendor->>'vendor_contact_id')::uuid,
      'pending_send',
      NULL
    )
    RETURNING id INTO v_invitation_id;

    INSERT INTO magic_link_tokens (
      bid_invitation_id, vendor_id, token_hash, expires_at, is_used
    ) VALUES (
      v_invitation_id,
      (v_vendor->>'vendor_id')::uuid,
      v_vendor->>'token_hash',
      p_deadline,
      FALSE
    );

    v_invitations := v_invitations || jsonb_build_object(
      'vendor_id',     v_vendor->>'vendor_id',
      'invitation_id', v_invitation_id
    );
  END LOOP;

  -- 4. Move the task into 'bidding' only when it is still a draft
  UPDATE tasks SET status = 'bidding'
   WHERE id = p_task_id AND status = 'draft';

  RETURN jsonb_build_object(
    'bid_package_id', v_bid_package.id,
    'round_number',   v_bid_package.round_number,
    'invitations',    v_invitations
  );
END;
$$ LANGUAGE plpgsql;

REVOKE ALL ON FUNCTION fn_create_bid_package_with_invitations(
  UUID, TIMESTAMPTZ, UUID, UUID, TEXT, DATE, UUID, UUID[], JSONB
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION fn_create_bid_package_with_invitations(
  UUID, TIMESTAMPTZ, UUID, UUID, TEXT, DATE, UUID, UUID[], JSONB
) TO service_role;


-- ----------------------------------------------------------------------------
-- 7.2b fn_cancel_bid_package() — atomic round void + parent-task reconciliation
-- ----------------------------------------------------------------------------
-- Flips the package to 'cancelled' and, when that was the task's LAST live
-- round, returns the task to 'draft' — in ONE transaction. Previously these were
-- two facts and only the first was ever written: a cancelled sole round left the
-- task in 'bidding' with nothing to bid on, which blocks project archive and
-- delete and hides the "Start New Round" button (gated on status = 'draft').
--
-- 'draft' is the target because fn_create_bid_package_with_invitations (7.2
-- above) advances the task only WHERE status = 'draft'. Any other resting value
-- makes a later rebid a silent no-op, which is exactly how the old state looked
-- self-consistent without ever having been repaired.
--
-- NOTE: ALLOWED_TRANSITIONS in backend/app/routers/tasks.py has no
-- bidding -> draft edge. That map gates the PATCH endpoint only; nothing on the
-- cancel path reads it, and this bypass is deliberate. 'draft' is safe to land
-- on because every transition out of it is legal.
--
-- The revision cancel, token revoke and bid_invitations convergence stay in
-- Python ahead of this call (invitation_tracking_service.cancel_bid_package).
-- They are not the pair that produced the wrong state, and folding them in would
-- widen a pre-existing non-atomicity rather than close it.
--
-- The status guard mirrors the Python one exactly (open | evaluating), so
-- 'closed' is rejected here too, not only 'cancelled'. In practice the Python
-- guard rejects first and these PT codes are a concurrency backstop.

CREATE OR REPLACE FUNCTION fn_cancel_bid_package(
  p_bid_package_id UUID,
  p_cancelled_by   UUID
)
RETURNS SETOF bid_packages AS $$
DECLARE
  v_package   bid_packages;
  v_live_left INTEGER;
BEGIN
  SELECT * INTO v_package
    FROM bid_packages
   WHERE id = p_bid_package_id
   FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Bid package % not found', p_bid_package_id
      USING ERRCODE = 'PT404';
  END IF;

  IF v_package.status NOT IN ('open', 'evaluating') THEN
    RAISE EXCEPTION
      'Cannot cancel: the package is ''%''. Only open or evaluating packages can be cancelled.',
      v_package.status
      USING ERRCODE = 'PT409';
  END IF;

  UPDATE bid_packages
     SET status       = 'cancelled',
         cancelled_by = p_cancelled_by,
         cancelled_at = NOW(),
         updated_at   = NOW()
   WHERE id = p_bid_package_id
   RETURNING * INTO v_package;

  -- Siblings only: the row above is already 'cancelled', so it cannot count
  -- itself as the live round that keeps the task in 'bidding'.
  SELECT count(*) INTO v_live_left
    FROM bid_packages
   WHERE task_id = v_package.task_id
     AND status <> 'cancelled';

  -- The status = 'bidding' predicate is load-bearing: never stomp 'awarded',
  -- 'in_progress', or a value a PM set by hand.
  IF v_live_left = 0 THEN
    UPDATE tasks
       SET status     = 'draft',
           updated_at = NOW()
     WHERE id = v_package.task_id
       AND status = 'bidding';
  END IF;

  RETURN NEXT v_package;
END;
$$ LANGUAGE plpgsql;

REVOKE ALL ON FUNCTION fn_cancel_bid_package(UUID, UUID)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION fn_cancel_bid_package(UUID, UUID) TO service_role;



-- ----------------------------------------------------------------------------
-- 7.3 fn_create_milestone() — atomic create + creation event
-- ----------------------------------------------------------------------------
-- Freezes the baseline and writes the opening ledger entry in one transaction,
-- so a milestone can never exist without its creation event.
-- Contract resolution and date validation run in Python BEFORE this call; this
-- function is the write only. The existing fn_enforce_milestone_task_consistency
-- trigger still fires inside this transaction and backstops task_id/contract_id.

CREATE OR REPLACE FUNCTION fn_create_milestone(
  p_task_id     UUID,
  p_contract_id UUID,
  p_name        TEXT,
  p_start_date  DATE,
  p_end_date    DATE,
  p_notes       TEXT,
  p_sort_order  INTEGER,
  p_created_by  UUID
)
RETURNS SETOF milestones AS $$
DECLARE
  v_milestone milestones;
BEGIN
  INSERT INTO milestones (
    task_id, contract_id, name,
    start_date, end_date, baseline_end_date,
    status, cycle_number, sort_order, notes, created_by
  ) VALUES (
    p_task_id, p_contract_id, p_name,
    p_start_date, p_end_date,
    p_end_date,                        -- baseline frozen = the original committed finish
    'scheduled', 1, COALESCE(p_sort_order, 0), p_notes, p_created_by
  )
  RETURNING * INTO v_milestone;

  INSERT INTO milestone_events (
    milestone_id, from_status, to_status, trigger_type,
    actor_user_id, cycle_number, working_end_date, note
  ) VALUES (
    v_milestone.id, NULL, 'scheduled', 'creation',
    p_created_by, 1, p_end_date, 'Milestone created'
  );

  RETURN NEXT v_milestone;
END;
$$ LANGUAGE plpgsql;

REVOKE ALL   ON FUNCTION fn_create_milestone(UUID, UUID, TEXT, DATE, DATE, TEXT, INTEGER, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION fn_create_milestone(UUID, UUID, TEXT, DATE, DATE, TEXT, INTEGER, UUID) TO service_role;


-- ----------------------------------------------------------------------------
-- 7.4 transition_milestone() — THE single authoritative writer
-- ----------------------------------------------------------------------------
-- Every status change, from any actor (PM dashboard, vendor click handler,
-- daily scheduler), goes through here. Nothing else writes milestones.status.
--
--   1. FOR UPDATE row lock  -> concurrent clicks / job races serialize.
--                              First writer wins; the second re-reads the
--                              already-changed status, and its transition is
--                              no longer legal.
--   2. Legality check       -> any pair outside the transition table raises
--                              PT409. Callers decide what that means:
--                                PM action    -> 409 Conflict (a dead button is bad UX)
--                                vendor click -> resolve to the "already recorded" page
--                                scheduler    -> log and skip
--   3. Apply status, actual dates, and on reschedule the new end date + a cycle
--      bump, which staleness-kills every outstanding token at a stroke.
--   4. Write exactly ONE immutable milestone_events row.
--
-- PostgREST convention: SQLSTATE 'PT<nnn>' sets the HTTP status directly, so
-- PT404/PT409/PT422 surface as real 404/409/422 rather than opaque 500s.

CREATE OR REPLACE FUNCTION transition_milestone(
  p_milestone_id            UUID,
  p_action                  TEXT,             -- the authoritative intent (see table below)
  p_actor_user_id           UUID DEFAULT NULL,   -- required for pm_* actions
  p_actor_vendor_contact_id UUID DEFAULT NULL,   -- required for vendor_* actions
  p_milestone_response_id   UUID DEFAULT NULL,
  p_milestone_alert_id      UUID DEFAULT NULL,
  p_actual_start_date       DATE DEFAULT NULL,
  p_actual_end_date         DATE DEFAULT NULL,
  p_new_end_date            DATE DEFAULT NULL,   -- required for pm_reschedule
  p_note                    TEXT DEFAULT NULL
)
RETURNS SETOF milestones AS $$
DECLARE
  v_cur          milestones;
  v_result       milestones;
  v_target       TEXT;
  v_trigger_type TEXT;
  v_is_resched   BOOLEAN := (p_action = 'pm_reschedule');
  v_new_cycle    INTEGER;
  v_eff_start    DATE;
BEGIN
  -- 0. Known action?
  IF p_action NOT IN (
       'pm_mark_started','pm_mark_completed','pm_reschedule','pm_cancel',
       'vendor_start_yes','vendor_start_no',
       'vendor_progress_yes','vendor_progress_no',
       'vendor_completion_yes','vendor_completion_no',
       'system_no_response'
     ) THEN
    RAISE EXCEPTION 'Unknown milestone action: %', p_action USING ERRCODE = 'PT422';
  END IF;

  -- 1. Lock the row. Concurrent clicks / job races serialize here; first wins.
  SELECT * INTO v_cur FROM milestones WHERE id = p_milestone_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Milestone % not found', p_milestone_id USING ERRCODE = 'PT404';
  END IF;

  -- 2. THE TRANSITION TABLE. (current_status, action) -> target_status.
  --    Anything not listed is impossible. completed/cancelled are terminal.
  v_target := CASE
    -- PM actions -------------------------------------------------------------
    WHEN p_action = 'pm_mark_started'
         AND v_cur.status = 'scheduled'                                         THEN 'in_progress'
    -- scheduled included deliberately: recording already-finished work without
    -- inventing a start date. actual_start_date simply stays NULL.
    WHEN p_action = 'pm_mark_completed'
         AND v_cur.status IN ('scheduled','in_progress','delayed','unresponsive') THEN 'completed'
    WHEN p_action = 'pm_reschedule'
         AND v_cur.status IN ('in_progress','delayed','unresponsive')            THEN 'in_progress'
    WHEN p_action = 'pm_cancel'
         AND v_cur.status IN ('scheduled','in_progress','delayed','unresponsive') THEN 'cancelled'

    -- Vendor responses (unresponsive included = a late reply resolving silence)
    WHEN p_action = 'vendor_start_yes'
         AND v_cur.status IN ('scheduled','unresponsive')                        THEN 'in_progress'
    WHEN p_action = 'vendor_start_no'
         AND v_cur.status IN ('scheduled','unresponsive')                        THEN 'delayed'
    WHEN p_action = 'vendor_progress_yes'
         AND v_cur.status IN ('in_progress','unresponsive')                      THEN 'in_progress'
    WHEN p_action = 'vendor_progress_no'
         AND v_cur.status IN ('in_progress','unresponsive')                      THEN 'delayed'
    WHEN p_action = 'vendor_completion_yes'
         AND v_cur.status IN ('in_progress','unresponsive')                      THEN 'completed'
    WHEN p_action = 'vendor_completion_no'
         AND v_cur.status IN ('in_progress','unresponsive')                      THEN 'delayed'

    -- Scheduler --------------------------------------------------------------
    WHEN p_action = 'system_no_response'
         AND v_cur.status IN ('scheduled','in_progress')                         THEN 'unresponsive'

    ELSE NULL
  END;

  IF v_target IS NULL THEN
    RAISE EXCEPTION 'Action "%" is not allowed on a milestone in status "%" (milestone %)',
      p_action, v_cur.status, p_milestone_id
      USING ERRCODE = 'PT409';
  END IF;

  -- 3. trigger_type and actor are implied by the action; no caller may disagree.
  v_trigger_type := CASE
    WHEN p_action LIKE 'pm\_%'     THEN 'pm_action'
    WHEN p_action LIKE 'vendor\_%' THEN 'vendor_response'
    ELSE 'system_no_response'
  END;

  IF v_trigger_type = 'pm_action' AND p_actor_user_id IS NULL THEN
    RAISE EXCEPTION 'p_actor_user_id is required for action %', p_action USING ERRCODE = 'PT422';
  END IF;
  IF v_trigger_type = 'vendor_response' AND p_actor_vendor_contact_id IS NULL THEN
    RAISE EXCEPTION 'p_actor_vendor_contact_id is required for action %', p_action USING ERRCODE = 'PT422';
  END IF;

  -- 4. Action-specific date guards.
  IF v_is_resched THEN
    IF p_new_end_date IS NULL THEN
      RAISE EXCEPTION 'p_new_end_date is required for pm_reschedule' USING ERRCODE = 'PT422';
    END IF;
    IF p_new_end_date < v_cur.start_date THEN
      RAISE EXCEPTION 'New end date (%) precedes start date (%)',
        p_new_end_date, v_cur.start_date USING ERRCODE = 'PT422';
    END IF;
  ELSIF p_new_end_date IS NOT NULL THEN
    RAISE EXCEPTION 'p_new_end_date is only valid for pm_reschedule (got action %)', p_action
      USING ERRCODE = 'PT422';
  END IF;

  v_eff_start := COALESCE(p_actual_start_date, v_cur.actual_start_date);
  IF p_actual_end_date IS NOT NULL
     AND v_eff_start IS NOT NULL
     AND p_actual_end_date < v_eff_start THEN
    RAISE EXCEPTION 'actual_end_date (%) precedes actual_start_date (%)',
      p_actual_end_date, v_eff_start USING ERRCODE = 'PT422';
  END IF;

  -- 5. Apply. Only a reschedule bumps the cycle, which staleness-kills every
  --    outstanding check-in token for this milestone at a stroke.
  v_new_cycle := v_cur.cycle_number + (CASE WHEN v_is_resched THEN 1 ELSE 0 END);

  -- Identify this txn as the authoritative date writer for trg_milestones_guard_dates.
  PERFORM set_config('bluonx.milestone_transition', 'on', TRUE);

  UPDATE milestones
     SET status            = v_target,
         cycle_number      = v_new_cycle,
         end_date          = COALESCE(p_new_end_date,      end_date),
         actual_start_date = COALESCE(p_actual_start_date, actual_start_date),
         actual_end_date   = COALESCE(p_actual_end_date,   actual_end_date)
   WHERE id = p_milestone_id
   RETURNING * INTO v_result;
  -- baseline_end_date is deliberately untouched: a reschedule moves the working
  -- plan, the original commitment stands, and that gap IS the drift.

  PERFORM set_config('bluonx.milestone_transition', 'off', TRUE);

  -- 6. One immutable ledger row.
  INSERT INTO milestone_events (
    milestone_id, from_status, to_status, trigger_type,
    actor_user_id, actor_vendor_contact_id,
    milestone_response_id, milestone_alert_id,
    cycle_number, working_end_date, note
  ) VALUES (
    p_milestone_id, v_cur.status, v_target, v_trigger_type,
    p_actor_user_id, p_actor_vendor_contact_id,
    p_milestone_response_id, p_milestone_alert_id,
    v_new_cycle, v_result.end_date, p_note
  );

  RETURN NEXT v_result;
END;
$$ LANGUAGE plpgsql;

REVOKE ALL ON FUNCTION transition_milestone(UUID, TEXT, UUID, UUID, UUID, UUID, DATE, DATE, DATE, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION transition_milestone(UUID, TEXT, UUID, UUID, UUID, UUID, DATE, DATE, DATE, TEXT) TO service_role;


-- ----------------------------------------------------------------------------
-- fn_record_milestone_response — atomic vendor check-in recorder (Phase 10.2)
-- ----------------------------------------------------------------------------
-- Records a milestone_responses row, runs transition_milestone(), and spends the
-- token in ONE transaction (supabase-py has no client transactions). The response
-- INSERT runs first, so UNIQUE(milestone_alert_id) is the first-response-wins gate;
-- a transition PT409 (illegal action / milestone moved terminal) propagates and
-- rolls the response INSERT back, so there is never an orphan response without an
-- event. Vendor identity (p_vendor_contact_id) comes from the vendor JWT only.

CREATE OR REPLACE FUNCTION fn_record_milestone_response(
  p_milestone_alert_id  UUID,
  p_response_value      TEXT,            -- 'yes' | 'no'
  p_vendor_contact_id   UUID,
  p_today               DATE             -- business-timezone "today"
)
RETURNS TABLE (
  outcome           TEXT,               -- 'recorded' | 'already_answered'
  recorded_value    TEXT,               -- 'yes' | 'no'
  recorded_at       TIMESTAMPTZ,
  milestone_status  TEXT
) AS $$
DECLARE
  v_alert        milestone_alerts;
  v_ms           milestones;
  v_action       TEXT;
  v_resp_type    TEXT;
  v_resp_id      UUID;
  v_existing     milestone_responses;
  v_status       TEXT;
  v_actual_start DATE;
  v_actual_end   DATE;
BEGIN
  IF p_response_value NOT IN ('yes', 'no') THEN
    RAISE EXCEPTION 'Invalid response value: %', p_response_value USING ERRCODE = 'PT422';
  END IF;

  -- Lock the alert; concurrent clicks serialize here and at the response UNIQUE.
  SELECT * INTO v_alert FROM milestone_alerts WHERE id = p_milestone_alert_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Milestone alert % not found', p_milestone_alert_id USING ERRCODE = 'PT404';
  END IF;

  SELECT * INTO v_ms FROM milestones WHERE id = v_alert.milestone_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Milestone % not found', v_alert.milestone_id USING ERRCODE = 'PT404';
  END IF;

  -- Cycle staleness: a reschedule bumped the cycle and stranded this link.
  IF v_alert.cycle_number IS DISTINCT FROM v_ms.cycle_number THEN
    RAISE EXCEPTION 'Check-in is stale (alert cycle % <> milestone cycle %)',
      v_alert.cycle_number, v_ms.cycle_number USING ERRCODE = 'PT409';
  END IF;

  -- Derive action + response_type from the alert kind × value.
  v_action := CASE v_alert.alert_type
    WHEN 'start_check'      THEN 'vendor_start_'      || p_response_value
    WHEN 'progress_check'   THEN 'vendor_progress_'   || p_response_value
    WHEN 'completion_check' THEN 'vendor_completion_' || p_response_value
    ELSE NULL
  END;
  IF v_action IS NULL THEN
    RAISE EXCEPTION 'Alert type % is not a vendor check-in', v_alert.alert_type USING ERRCODE = 'PT422';
  END IF;
  v_resp_type := CASE v_alert.alert_type
    WHEN 'start_check'      THEN 'start_confirmation'
    WHEN 'progress_check'   THEN 'progress_check'
    WHEN 'completion_check' THEN 'completion_confirmation'
  END;

  -- Actual dates set only on affirmative start / completion (never on 'no').
  v_actual_start := CASE WHEN v_action = 'vendor_start_yes'      THEN p_today ELSE NULL END;
  v_actual_end   := CASE WHEN v_action = 'vendor_completion_yes' THEN p_today ELSE NULL END;

  -- Record the answer. UNIQUE(milestone_alert_id) = first-response-wins.
  BEGIN
    INSERT INTO milestone_responses (
      milestone_id, response_type, response_value, milestone_alert_id, vendor_contact_id
    ) VALUES (
      v_alert.milestone_id, v_resp_type, p_response_value, p_milestone_alert_id, p_vendor_contact_id
    )
    RETURNING id INTO v_resp_id;
  EXCEPTION WHEN unique_violation THEN
    SELECT * INTO v_existing
      FROM milestone_responses WHERE milestone_alert_id = p_milestone_alert_id;
    SELECT status INTO v_status FROM milestones WHERE id = v_alert.milestone_id;
    outcome          := 'already_answered';
    recorded_value   := v_existing.response_value;
    recorded_at      := v_existing.responded_at;
    milestone_status := v_status;
    RETURN NEXT;
    RETURN;
  END;

  -- Authoritative state change (owns legality + ledger). A PT409 rolls back the
  -- response INSERT above.
  PERFORM transition_milestone(
    p_milestone_id            => v_alert.milestone_id,
    p_action                  => v_action,
    p_actor_user_id           => NULL,
    p_actor_vendor_contact_id => p_vendor_contact_id,
    p_milestone_response_id   => v_resp_id,
    p_milestone_alert_id      => p_milestone_alert_id,
    p_actual_start_date       => v_actual_start,
    p_actual_end_date         => v_actual_end,
    p_new_end_date            => NULL,
    p_note                    => 'Vendor answered ' || p_response_value || ' via check-in link'
  );

  UPDATE milestone_checkin_tokens
     SET is_used = TRUE, used_at = NOW()
   WHERE milestone_alert_id = p_milestone_alert_id;

  SELECT status INTO v_status FROM milestones WHERE id = v_alert.milestone_id;
  SELECT mr.responded_at INTO recorded_at
    FROM milestone_responses mr WHERE mr.id = v_resp_id;
  outcome          := 'recorded';
  recorded_value   := p_response_value;
  milestone_status := v_status;
  RETURN NEXT;
  RETURN;
END;
$$ LANGUAGE plpgsql;

REVOKE ALL ON FUNCTION fn_record_milestone_response(UUID, TEXT, UUID, DATE) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION fn_record_milestone_response(UUID, TEXT, UUID, DATE) TO service_role;


-- Mark a contract complete. Gated cross-row transition: only when every
-- milestone on the contract is done. Row-locked + re-checked inside the lock to
-- close the TOCTOU window (a milestone reopening, or a new one inserted, between
-- check and write). Same house pattern as transition_milestone().
CREATE OR REPLACE FUNCTION fn_mark_contract_complete(
  p_contract_id UUID
)
RETURNS SETOF contracts AS $$
DECLARE
  v_cur     contracts;
  v_open    INTEGER;
  v_result  contracts;
BEGIN
  SELECT * INTO v_cur FROM contracts WHERE id = p_contract_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Contract % not found', p_contract_id USING ERRCODE = 'PT404';
  END IF;

  IF v_cur.status = 'completed' THEN
    RAISE EXCEPTION 'Contract is already complete' USING ERRCODE = 'PT409';
  END IF;
  IF v_cur.status = 'terminated' THEN
    RAISE EXCEPTION 'A terminated contract cannot be completed' USING ERRCODE = 'PT409';
  END IF;

  SELECT COUNT(*) INTO v_open
    FROM milestones
   WHERE contract_id = p_contract_id
     AND status NOT IN ('completed','cancelled');

  IF v_open > 0 THEN
    RAISE EXCEPTION 'Contract has % milestone(s) still open; complete or cancel them first', v_open
      USING ERRCODE = 'PT409';
  END IF;

  UPDATE contracts SET status = 'completed'
   WHERE id = p_contract_id
   RETURNING * INTO v_result;

  RETURN NEXT v_result;
END;
$$ LANGUAGE plpgsql;

REVOKE ALL   ON FUNCTION fn_mark_contract_complete(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION fn_mark_contract_complete(UUID) TO service_role;


-- Insert a multi-day holiday shutdown atomically.
--
-- The obvious implementation — one multi-row INSERT — is quietly wrong. A
-- multi-row INSERT is ONE SQL command, and Postgres does not increment the
-- command counter between the rows of a single command, so a BEFORE ... FOR
-- EACH ROW trigger cannot see the siblings being inserted alongside it.
-- fn_holidays_guardrails would evaluate every row against the pre-batch state:
-- the 25/year cap would count as if none of the batch existed, and the
-- 14-consecutive walk would never see the run the batch is itself creating. A
-- bulk range could create exactly the closure the guardrails exist to prevent,
-- and report success.
--
-- Looping row-by-row fixes it: each INSERT is its own SPI command, plpgsql
-- increments the command counter between statements, and row N's trigger sees
-- rows 1..N-1. One implicit transaction, so any rejection rolls the whole range
-- back — there is no partial import to clean up.
CREATE OR REPLACE FUNCTION fn_create_holiday_range(
  p_start      DATE,
  p_end        DATE,
  p_name       TEXT,
  p_created_by UUID
)
RETURNS SETOF holidays AS $$
DECLARE
  v_cursor DATE    := p_start;
  v_row    holidays;
  v_count  INTEGER := 0;
BEGIN
  IF p_start IS NULL OR p_end IS NULL THEN
    RAISE EXCEPTION 'A holiday range needs both a start and an end date.'
      USING ERRCODE = 'PT422';
  END IF;

  IF p_end < p_start THEN
    RAISE EXCEPTION 'The end date (%) cannot be before the start date (%).', p_end, p_start
      USING ERRCODE = 'PT422';
  END IF;

  -- Sanity ceiling only. The 14-consecutive guardrail is the real limit and will
  -- reject anything close to this; this exists so a fat-fingered decade-long
  -- range fails immediately instead of looping thousands of times first.
  IF (p_end - p_start) > 30 THEN
    RAISE EXCEPTION 'A holiday range cannot span more than 31 days (got % days).',
      (p_end - p_start) + 1 USING ERRCODE = 'PT422';
  END IF;

  IF btrim(COALESCE(p_name, '')) = '' THEN
    RAISE EXCEPTION 'A holiday needs a name.' USING ERRCODE = 'PT422';
  END IF;

  WHILE v_cursor <= p_end LOOP
    -- Weekends are skipped SILENTLY rather than rejected. They are already
    -- non-working days, storing them would inflate the contiguous-run count
    -- against its own cap, and "mark the shutdown week Mon-Sun" should do the
    -- obvious thing instead of erroring.
    IF EXTRACT(DOW FROM v_cursor) NOT IN (0, 6) THEN

      -- Named up front so the admin gets the offending DATE. Falling through to
      -- the UNIQUE constraint would surface Postgres' raw index text instead.
      IF EXISTS (SELECT 1 FROM holidays WHERE holiday_date = v_cursor) THEN
        RAISE EXCEPTION '% is already marked as a holiday. Remove it first, or pick a range that does not include it.',
          v_cursor USING ERRCODE = 'PT409';
      END IF;

      -- One statement per row: this is the whole point of the function. The
      -- guardrail trigger fires here and sees every row inserted above it.
      INSERT INTO holidays (holiday_date, name, source, created_by)
      VALUES (v_cursor, btrim(p_name), 'manual', p_created_by)
      RETURNING * INTO v_row;

      RETURN NEXT v_row;
      v_count := v_count + 1;
    END IF;

    v_cursor := v_cursor + 1;
  END LOOP;

  IF v_count = 0 THEN
    RAISE EXCEPTION 'That range contains only weekends, which are already non-working days.'
      USING ERRCODE = 'PT422';
  END IF;

  RETURN;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION fn_create_holiday_range(DATE, DATE, TEXT, UUID) IS
  'Insert every weekday in [p_start, p_end] as one manual holiday, atomically. Loops row-by-row so the BEFORE-ROW guardrail trigger sees earlier rows of the same call (a multi-row INSERT would not). Weekends are skipped silently. Any guardrail rejection rolls the entire range back.';

REVOKE ALL   ON FUNCTION fn_create_holiday_range(DATE, DATE, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION fn_create_holiday_range(DATE, DATE, TEXT, UUID) TO service_role;


-- ============================================================================
-- SECTION 8: VIEWS (read surfaces)
-- ============================================================================

-- One denormalized read surface for every cross-project milestone view:
--   • the dashboard "Needs your attention" card (paused milestones)
--   • the /milestones cross-project list (filter + sort + paginate)
--   • the project Milestones timeline tab
--
-- WHY A VIEW: these surfaces all need milestone + task + project + vendor +
-- creator + "how long has this been stuck", which is 5 joins plus a lateral over
-- the event ledger. Doing that client-side would be an N+1 per row. PostgREST
-- can select/filter/order/range a view exactly like a table, so one object
-- serves all three surfaces and the frontend stays a plain Supabase read.
--
-- SECURITY: security_invoker = true means the CALLER's RLS applies (not the view
-- owner's). Without it a view silently bypasses RLS. Requires PG15+ (Supabase is).

-- ============================================================================

CREATE OR REPLACE VIEW v_milestone_overview
WITH (security_invoker = true) AS
SELECT
    m.id                    AS milestone_id,
    m.name                  AS milestone_name,
    m.status,
    m.cycle_number,
    m.sort_order,

    -- Dates: working plan, frozen commitment, and what actually happened.
    m.start_date,
    m.end_date,
    m.baseline_end_date,
    m.actual_start_date,
    m.actual_end_date,

    -- Drift: the end date moved from what the vendor originally committed to.
    (m.end_date IS DISTINCT FROM m.baseline_end_date)          AS end_date_moved,

    -- Late by the honest measure: against the BASELINE, never the rescheduled end.
    CASE
      WHEN m.actual_end_date IS NOT NULL
        THEN GREATEST(0, m.actual_end_date - m.baseline_end_date)
    END                                                        AS days_late,

    -- Live and past its committed finish, but not yet done.
    (m.status IN ('scheduled','in_progress','delayed','unresponsive')
       AND m.end_date < (NOW() AT TIME ZONE 'America/Chicago')::date)
                                                               AS is_overdue,

    -- HOW LONG HAS THIS BEEN STUCK ON A HUMAN.
    -- delayed/unresponsive PAUSE the check-in cycle: the system stops chasing the
    -- vendor and waits for a PM. A milestone paused three weeks ago that nobody
    -- touched is a fire; one paused yesterday is fine. This is the whole point of
    -- the attention card, so it is sorted on.
    p.paused_since,
    CASE
      WHEN m.status IN ('delayed','unresponsive') AND p.paused_since IS NOT NULL
        THEN (NOW() AT TIME ZONE 'America/Chicago')::date
             - (p.paused_since AT TIME ZONE 'America/Chicago')::date
    END                                                        AS days_paused,

    -- Context needed to render a row AND to build the detail link, which requires
    -- all three of project_id / task_id / milestone_id.
    t.id                    AS task_id,
    t.name                  AS task_name,
    pr.id                   AS project_id,
    pr.name                 AS project_name,

    c.id                    AS contract_id,
    v.id                    AS vendor_id,
    v.company_name          AS vendor_company_name,

    m.created_by,
    u.full_name             AS created_by_name,

    m.notes,
    m.created_at,
    m.updated_at

FROM milestones m
JOIN tasks     t  ON t.id  = m.task_id
JOIN projects  pr ON pr.id = t.project_id
JOIN contracts c  ON c.id  = m.contract_id
JOIN vendors   v  ON v.id  = c.vendor_id
LEFT JOIN users u ON u.id  = m.created_by

-- The most recent transition INTO a paused state. LATERAL keeps this one indexed
-- lookup per milestone instead of a scan.
LEFT JOIN LATERAL (
    SELECT e.created_at AS paused_since
      FROM milestone_events e
     WHERE e.milestone_id = m.id
       AND e.to_status IN ('delayed','unresponsive')
     ORDER BY e.created_at DESC
     LIMIT 1
) p ON TRUE

WHERE t.deleted_at  IS NULL
  AND pr.deleted_at IS NULL
  AND v.deleted_at  IS NULL;


COMMENT ON VIEW v_milestone_overview IS
  'Cross-project milestone read surface: milestone + task + project + vendor + creator, plus days_paused (how long a delayed/unresponsive milestone has been stalled awaiting a PM), is_overdue, and baseline drift. Serves the dashboard attention card, the /milestones list, and the project timeline tab. security_invoker = true so caller RLS applies.';


-- Read-only surface for signed-in staff. Vendors never touch it.
REVOKE ALL ON v_milestone_overview FROM PUBLIC, anon;
GRANT SELECT ON v_milestone_overview TO authenticated, service_role;


-- Per-vendor flat average rating and 0-100 performance_score (avg/5*100, so a
-- poorly-rated vendor floors at 20, not 0). Flat mean is deliberate: predictable
-- and human-reproducible. Vendors with no reviews are ABSENT -> the scorer uses
-- the neutral 75 fallback (a new vendor is not penalised for having no history).
-- security_invoker = true: caller RLS applies (a view without it bypasses RLS).
CREATE OR REPLACE VIEW v_vendor_performance
WITH (security_invoker = true) AS
SELECT
    vendor_id,
    COUNT(*)                                  AS review_count,
    ROUND(AVG(rating)::numeric, 2)            AS avg_rating,
    ROUND(AVG(rating)::numeric / 5 * 100, 2)  AS performance_score   -- 0-100
FROM vendor_performance_reviews
GROUP BY vendor_id;

COMMENT ON VIEW v_vendor_performance IS
  'Per-vendor flat average rating and 0-100 performance_score (avg_rating/5*100). Feeds the Phase 8 performance dimension. Vendors with no reviews are absent -> scorer uses the neutral 75 fallback. security_invoker = true.';

REVOKE ALL ON v_vendor_performance FROM PUBLIC, anon;
GRANT SELECT ON v_vendor_performance TO authenticated, service_role;


-- ────────────────────────────────────────────────────────────────────────────
-- v_vendor_email_log — attributes every outbound email to the vendor that got it
-- ────────────────────────────────────────────────────────────────────────────
--
-- WHY A VIEW: email_log has no vendor_id. It is polymorphic
-- (reference_type + reference_id), and five different flows each pin
-- reference_id to a different table. Resolving that in Python meant fetching
-- every invitation id for a vendor, running one unbounded email_log query per
-- reference_type with a giant IN (...), then deduping and SORTING IN MEMORY.
-- That shape cannot be paginated (you cannot take page 3 of a merged result
-- without materialising all of it) and it silently truncated at PostgREST's
-- 1000-row ceiling, so a busy vendor's log looked complete while quietly
-- dropping rows. Here the union, the attribution, and the ordering all happen
-- in Postgres, so the callers can range/count it like any other list.
--
-- WHY TOP-LEVEL UNION ALL, NOT A LATERAL OVER email_log: qualifiers push down
-- into UNION ALL branches. `WHERE vendor_id = X` therefore filters
-- bid_invitations on its indexed vendor_id and probes email_log through
-- idx_email_log_reference. A LATERAL would force a full email_log scan per
-- request, which is exactly the cost being removed.
--
-- NO DEDUPE NEEDED: a row carries exactly one (reference_type, reference_id)
-- pair, so it can satisfy exactly one branch.
--
-- recipient_type = 'vendor_contact' on every branch. Milestone emails go to
-- BOTH vendors (check-ins) and PMs (no-response alerts); only the former is
-- correspondence with the vendor.
--
-- bid_invitation_id / bid_package_id are NULL on the award and milestone
-- branches: neither hangs off an invitation. The bid-package surface filters on
-- bid_package_id, so it sees only the three invitation-linked types — the
-- package view is unchanged, and only the vendor view gains rows.
--
-- NOT COVERED: decline notifications (email_type 'decline_notification') pin
-- reference_id to the BID PACKAGE, not the invitation, so nothing but the
-- recipient address identifies the vendor. Fixing that means changing
-- decline_service to reference the invitation; until then they are absent
-- here rather than attributed by a fragile email match.

CREATE OR REPLACE VIEW v_vendor_email_log
WITH (security_invoker = true) AS

-- 1. Straight off the invitation: the initial invite and every reminder.
SELECT
    el.id, el.recipient_email, el.recipient_type, el.email_type, el.subject,
    el.status, el.sent_at, el.opened_at, el.clicked_at, el.error_message,
    el.retry_count, el.created_at, el.reference_type, el.reference_id,
    bi.vendor_id,
    bi.id             AS bid_invitation_id,
    bi.bid_package_id
  FROM bid_invitations bi
  JOIN email_log el
    ON el.reference_type = 'bid_invitations'
   AND el.reference_id   = bi.id
 WHERE el.recipient_type = 'vendor_contact'

UNION ALL

-- 2. PM revision requests → the invitation they were raised against.
SELECT
    el.id, el.recipient_email, el.recipient_type, el.email_type, el.subject,
    el.status, el.sent_at, el.opened_at, el.clicked_at, el.error_message,
    el.retry_count, el.created_at, el.reference_type, el.reference_id,
    bi.vendor_id, bi.id, bi.bid_package_id
  FROM bid_revision_requests rr
  JOIN bid_invitations bi ON bi.id = rr.bid_invitation_id
  JOIN email_log el
    ON el.reference_type = 'bid_revision_requests'
   AND el.reference_id   = rr.id
 WHERE el.recipient_type = 'vendor_contact'

UNION ALL

-- 3. Submission and revision receipts → the invitation they were filed under.
SELECT
    el.id, el.recipient_email, el.recipient_type, el.email_type, el.subject,
    el.status, el.sent_at, el.opened_at, el.clicked_at, el.error_message,
    el.retry_count, el.created_at, el.reference_type, el.reference_id,
    bi.vendor_id, bi.id, bi.bid_package_id
  FROM bid_submissions bs
  JOIN bid_invitations bi ON bi.id = bs.bid_invitation_id
  JOIN email_log el
    ON el.reference_type = 'bid_submissions'
   AND el.reference_id   = bs.id
 WHERE el.recipient_type = 'vendor_contact'

UNION ALL

-- 4. Award notifications. The award names the vendor directly.
SELECT
    el.id, el.recipient_email, el.recipient_type, el.email_type, el.subject,
    el.status, el.sent_at, el.opened_at, el.clicked_at, el.error_message,
    el.retry_count, el.created_at, el.reference_type, el.reference_id,
    a.vendor_id, NULL::uuid, NULL::uuid
  FROM awards a
  JOIN email_log el
    ON el.reference_type = 'awards'
   AND el.reference_id   = a.id
 WHERE el.recipient_type = 'vendor_contact'

UNION ALL

-- 5. Milestone check-ins → the vendor holding the contract.
SELECT
    el.id, el.recipient_email, el.recipient_type, el.email_type, el.subject,
    el.status, el.sent_at, el.opened_at, el.clicked_at, el.error_message,
    el.retry_count, el.created_at, el.reference_type, el.reference_id,
    c.vendor_id, NULL::uuid, NULL::uuid
  FROM milestones m
  JOIN contracts c ON c.id = m.contract_id
  JOIN email_log el
    ON el.reference_type = 'milestones'
   AND el.reference_id   = m.id
 WHERE el.recipient_type = 'vendor_contact';


COMMENT ON VIEW v_vendor_email_log IS
  'Every outbound email attributed to the vendor that received it, resolving email_log''s polymorphic reference across five flows: bid_invitations, bid_revision_requests, bid_submissions, awards, and milestones. Carries bid_invitation_id / bid_package_id for the three invitation-linked flows (NULL on award and milestone rows), so the same object serves the vendor Communication tab and the bid-package email log. Vendor-directed only (recipient_type = vendor_contact), so PM milestone alerts stay out. Order by created_at DESC, id DESC — the id tiebreaker keeps offset pagination stable when a bulk send gives many rows the same created_at. security_invoker = true so caller RLS applies.';

REVOKE ALL ON v_vendor_email_log FROM PUBLIC, anon;
GRANT SELECT ON v_vendor_email_log TO authenticated, service_role;


-- 1. Create task_templates table
CREATE TABLE IF NOT EXISTS public.task_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    phase VARCHAR(50) NOT NULL CHECK (phase IN ('due_diligence', 'development')),
    trade_id UUID NOT NULL REFERENCES public.trades(id) ON DELETE RESTRICT,
    bid_type VARCHAR(50) NOT NULL DEFAULT 'competitive' CHECK (bid_type IN ('competitive', 'internal', 'direct_assign')),
    budget_estimate NUMERIC(12, 2) NOT NULL DEFAULT 0.00 CHECK (budget_estimate >= 0),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ DEFAULT NULL
);

-- 2. Performance & query indexes
CREATE INDEX IF NOT EXISTS idx_task_templates_trade_id 
    ON public.task_templates(trade_id);

CREATE INDEX IF NOT EXISTS idx_task_templates_phase 
    ON public.task_templates(phase);

CREATE INDEX IF NOT EXISTS idx_task_templates_sort_order 
    ON public.task_templates(sort_order);

CREATE INDEX IF NOT EXISTS idx_task_templates_active 
    ON public.task_templates(is_active) 
    WHERE deleted_at IS NULL;

-- 3. Automatic updated_at trigger
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_task_templates_updated_at ON public.task_templates;
CREATE TRIGGER trg_task_templates_updated_at
    BEFORE UPDATE ON public.task_templates
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- 4. Enable Row Level Security (RLS)
ALTER TABLE public.task_templates ENABLE ROW LEVEL SECURITY;

-- Allow authenticated users to view active (non-deleted) templates
CREATE POLICY "Allow authenticated read task_templates"
    ON public.task_templates
    FOR SELECT
    TO authenticated
    USING (deleted_at IS NULL);

-- Allow authenticated users / admins full management (insert, update, delete)
CREATE POLICY "Allow authenticated manage task_templates"
    ON public.task_templates
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);
    


-- ############################################################################
-- ############################################################################
--
--  SECTION 9: FINANCIAL AUTOMATION — PHASE 1 FOUNDATION (v4.0, Nov 11 2026)
--
--  Source of truth for EXISTING databases: the idempotent migration
--    database/migrations/20261111_financial_phase1/001_financial_foundation.sql
--  This section is the same DDL (minus BEGIN/COMMIT and the RLS part, which
--  lives in rls_policies.sql) so a fresh install from this file matches.
--  Adds GROUPS 9–14 (19 tables). Every statement here is re-runnable.
--
-- ############################################################################
-- ############################################################################

CREATE SCHEMA IF NOT EXISTS private;   -- also created by rls_policies.sql; needed here first

-- ============================================================================
-- SECTION 9.A: HELPER FUNCTIONS (private schema — not exposed by the Data API)
-- ============================================================================

-- A.1  Is the current transaction an authorised financial writer?
CREATE OR REPLACE FUNCTION private.fin_write_authorized()
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  SELECT COALESCE(current_setting('bluonx.financial_write', TRUE), '') = 'on';
$$;

COMMENT ON FUNCTION private.fin_write_authorized() IS
  'TRUE while a financial stored procedure has set bluonx.financial_write = on for this transaction. Guard triggers use it to tell the authoritative writer apart from every other writer.';


-- ============================================================================
-- SECTION 9.B: EXTEND EXISTING TABLES (additive only)
-- ============================================================================

-- ── B.1 users ───────────────────────────────────────────────────────────────
-- users.role is deliberately NOT changed (stays admin | project_manager): the
-- current backend and frontend hard-code those two values. Financial roles
-- live in user_roles (Section C), which also allows several roles per person.

ALTER TABLE public.users ADD COLUMN IF NOT EXISTS is_employee        BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS reports_to         UUID;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS backup_approver_id UUID;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS approval_limit     DECIMAL(15,2);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_reports_to') THEN
    ALTER TABLE public.users ADD CONSTRAINT fk_users_reports_to
      FOREIGN KEY (reports_to) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_backup_approver') THEN
    ALTER TABLE public.users ADD CONSTRAINT fk_users_backup_approver
      FOREIGN KEY (backup_approver_id) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_reports_to_not_self') THEN
    ALTER TABLE public.users ADD CONSTRAINT chk_users_reports_to_not_self
      CHECK (reports_to IS NULL OR reports_to <> id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_backup_not_self') THEN
    ALTER TABLE public.users ADD CONSTRAINT chk_users_backup_not_self
      CHECK (backup_approver_id IS NULL OR backup_approver_id <> id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_approval_limit_nonneg') THEN
    ALTER TABLE public.users ADD CONSTRAINT chk_users_approval_limit_nonneg
      CHECK (approval_limit IS NULL OR approval_limit >= 0);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_users_reports_to         ON public.users (reports_to)         WHERE reports_to IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_backup_approver_id ON public.users (backup_approver_id) WHERE backup_approver_id IS NOT NULL;

COMMENT ON COLUMN public.users.is_employee        IS 'TRUE = internal employee. FALSE = external / temporary field manager with their own login: may confirm work is done, may NEVER authorise payment.';
COMMENT ON COLUMN public.users.reports_to         IS 'Manager one level above this person (fixed per person). Receives over-limit / external approvals for second approval.';
COMMENT ON COLUMN public.users.backup_approver_id IS 'Standing backup approver used when reports_to is unavailable. Temporary windows go in approval_delegations.';
COMMENT ON COLUMN public.users.approval_limit     IS 'Max amount this user may approve alone. NULL = financial_settings.default_field_approval_limit.';
COMMENT ON COLUMN public.users.role               IS 'Base application access tier for the Bid Management System (admin | project_manager). Unchanged by the financial module; financial roles are held in user_roles (a user may hold several).';


-- ── B.2 projects ────────────────────────────────────────────────────────────
-- projects.budget (admin-editable today) is left exactly as it is. The
-- financial total lives in approved_budget_total and is guarded.

ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS manager_id                    UUID;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS field_manager_id              UUID;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS contingency_percent           DECIMAL(5,2);
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS budget_status                 VARCHAR(20) NOT NULL DEFAULT 'none';
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS approved_budget_total         DECIMAL(15,2);
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS budget_baselined_at           TIMESTAMPTZ;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS budget_baselined_by           UUID;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS contingency_at_groundbreaking DECIMAL(15,2);
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS long_tail_reserve_amount      DECIMAL(15,2);
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS business_entity               VARCHAR(20);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_projects_manager') THEN
    ALTER TABLE public.projects ADD CONSTRAINT fk_projects_manager
      FOREIGN KEY (manager_id) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_projects_field_manager') THEN
    ALTER TABLE public.projects ADD CONSTRAINT fk_projects_field_manager
      FOREIGN KEY (field_manager_id) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_projects_budget_baselined_by') THEN
    ALTER TABLE public.projects ADD CONSTRAINT fk_projects_budget_baselined_by
      FOREIGN KEY (budget_baselined_by) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_projects_budget_status') THEN
    ALTER TABLE public.projects ADD CONSTRAINT chk_projects_budget_status
      CHECK (budget_status IN ('none', 'draft', 'baselined'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_projects_contingency_percent') THEN
    ALTER TABLE public.projects ADD CONSTRAINT chk_projects_contingency_percent
      CHECK (contingency_percent IS NULL OR contingency_percent BETWEEN 0 AND 100);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_projects_approved_total_nonneg') THEN
    ALTER TABLE public.projects ADD CONSTRAINT chk_projects_approved_total_nonneg
      CHECK (approved_budget_total IS NULL OR approved_budget_total >= 0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_projects_baselined_has_total') THEN
    ALTER TABLE public.projects ADD CONSTRAINT chk_projects_baselined_has_total
      CHECK (budget_status <> 'baselined' OR approved_budget_total IS NOT NULL);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_projects_long_tail_reserve_nonneg') THEN
    ALTER TABLE public.projects ADD CONSTRAINT chk_projects_long_tail_reserve_nonneg
      CHECK (long_tail_reserve_amount IS NULL OR long_tail_reserve_amount >= 0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_projects_business_entity') THEN
    ALTER TABLE public.projects ADD CONSTRAINT chk_projects_business_entity
      CHECK (business_entity IS NULL OR business_entity IN ('bluonx', 'capstone'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_projects_manager_id       ON public.projects (manager_id)       WHERE manager_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_projects_field_manager_id ON public.projects (field_manager_id) WHERE field_manager_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_projects_budget_status    ON public.projects (budget_status)    WHERE deleted_at IS NULL;

COMMENT ON COLUMN public.projects.manager_id                    IS 'Assigned manager (one level above the field manager). Receives guardrail alerts and second approvals.';
COMMENT ON COLUMN public.projects.field_manager_id              IS 'Assigned field manager. Confirms work and first-approves payments.';
COMMENT ON COLUMN public.projects.contingency_percent           IS 'Program contingency % for this project. NULL = financial_settings.default_contingency_percent (15). Longer deals may carry more.';
COMMENT ON COLUMN public.projects.budget_status                 IS 'none = no financial budget yet; draft = budget being built (lines freely editable); baselined = estimates frozen, flat-budget rule active. Only fn_baseline_project_budget() moves draft → baselined.';
COMMENT ON COLUMN public.projects.approved_budget_total         IS 'Approved financial budget total. Set at baseline; changes ONLY through an executive-approved contingency top-up (fn_approve_contingency_top_up). Independent of the legacy projects.budget field.';
COMMENT ON COLUMN public.projects.budget_baselined_at           IS 'When the budget was baselined (original estimates frozen).';
COMMENT ON COLUMN public.projects.budget_baselined_by           IS 'Admin who baselined the budget.';
COMMENT ON COLUMN public.projects.contingency_at_groundbreaking IS 'Contingency amount at groundbreaking — denominator of the guardrail "contingency left %". Set by the Phase 5 checkpoint.';
COMMENT ON COLUMN public.projects.long_tail_reserve_amount      IS 'Fixed dollar reserve kept in contingency for open escrows and property taxes (per project). Used by the long-tail reserve check.';
COMMENT ON COLUMN public.projects.business_entity               IS 'bluonx (land / horizontal) or capstone (vertical). Drives the separate owner-dashboard views. NULL = not yet classified.';


-- ── B.3 contracts ───────────────────────────────────────────────────────────
ALTER TABLE public.contracts ADD COLUMN IF NOT EXISTS payment_terms_days INTEGER;
ALTER TABLE public.contracts ADD COLUMN IF NOT EXISTS retainage_percent  DECIMAL(5,2);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_contracts_payment_terms_days') THEN
    ALTER TABLE public.contracts ADD CONSTRAINT chk_contracts_payment_terms_days
      CHECK (payment_terms_days IS NULL OR payment_terms_days BETWEEN 0 AND 365);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_contracts_retainage_percent') THEN
    ALTER TABLE public.contracts ADD CONSTRAINT chk_contracts_retainage_percent
      CHECK (retainage_percent IS NULL OR retainage_percent BETWEEN 0 AND 100);
  END IF;
END $$;

COMMENT ON COLUMN public.contracts.payment_terms_days IS 'Numeric payment terms in days used by cash flow. NULL = line / settings default (30). The legacy free-text payment_terms column is unchanged.';
COMMENT ON COLUMN public.contracts.retainage_percent  IS 'Retainage held back on progress payments, % of each payment. NULL = no retainage.';


-- ============================================================================
-- SECTION 9.C: NEW TABLES
-- ============================================================================

-- ========================================
-- GROUP 9: BUDGET STRUCTURE (4 tables)
-- ========================================

-- 9.1 budget_templates ─ the standard budget layout
CREATE TABLE IF NOT EXISTS public.budget_templates (
  id           UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  name         VARCHAR(255)  NOT NULL,
  description  TEXT,
  is_default   BOOLEAN       NOT NULL DEFAULT FALSE,
  is_active    BOOLEAN       NOT NULL DEFAULT TRUE,
  created_by   UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at   TIMESTAMPTZ,

  CONSTRAINT chk_budget_templates_name_not_blank CHECK (btrim(name) <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_budget_templates_one_default
  ON public.budget_templates (is_default)
  WHERE is_default = TRUE AND is_active = TRUE AND deleted_at IS NULL;

COMMENT ON TABLE  public.budget_templates            IS 'Standard budget layouts maintained by admins. Applied when a project budget is created; later template edits never change existing budgets.';
COMMENT ON COLUMN public.budget_templates.is_default IS 'The template applied to new budgets. At most one active, non-deleted default (partial unique index).';
COMMENT ON COLUMN public.budget_templates.deleted_at IS 'Soft delete. NULL = active record.';


-- 9.2 budget_template_lines ─ ordered rows of a template
CREATE TABLE IF NOT EXISTS public.budget_template_lines (
  id                          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  budget_template_id          UUID          NOT NULL REFERENCES public.budget_templates(id) ON DELETE CASCADE,
  line_type                   VARCHAR(20)   NOT NULL
                                            CHECK (line_type IN ('land', 'bid_activity', 'internal_tm', 'permit',
                                                                 'impact_fee', 'soft_cost', 'contingency', 'long_tail')),
  line_subtype                VARCHAR(30)
                                            CHECK (line_subtype IS NULL OR line_subtype IN (
                                                     'land_purchase', 'earnest_money', 'due_diligence', 'engineering',
                                                     'escrow_bond_premium', 'escrow_repairs', 'property_tax', 'other')),
  name                        VARCHAR(255)  NOT NULL CHECK (btrim(name) <> ''),
  section_name                VARCHAR(100),
  trade_id                    UUID          REFERENCES public.trades(id) ON DELETE RESTRICT,
  task_template_id            UUID,
  sort_order                  INTEGER       NOT NULL DEFAULT 0,
  default_amount              DECIMAL(15,2) CHECK (default_amount IS NULL OR default_amount >= 0),
  default_payment_terms_days  INTEGER       CHECK (default_payment_terms_days IS NULL OR default_payment_terms_days BETWEEN 0 AND 365),
  default_cash_bucket         VARCHAR(30)   CHECK (default_cash_bucket IS NULL OR default_cash_bucket IN ('land', 'vertical_construction', 'overhead')),
  is_active                   BOOLEAN       NOT NULL DEFAULT TRUE,
  created_at                  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at                  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- task_templates is a newer table; link to it only where it exists.
DO $$
BEGIN
  IF to_regclass('public.task_templates') IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_budget_template_lines_task_template') THEN
    ALTER TABLE public.budget_template_lines ADD CONSTRAINT fk_budget_template_lines_task_template
      FOREIGN KEY (task_template_id) REFERENCES public.task_templates(id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_budget_template_lines_template ON public.budget_template_lines (budget_template_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_budget_template_lines_trade    ON public.budget_template_lines (trade_id) WHERE trade_id IS NOT NULL;

COMMENT ON TABLE  public.budget_template_lines                  IS 'Ordered lines of a budget template, from land acquisition down to escrows and property taxes. Copied into budget_lines when a budget is created.';
COMMENT ON COLUMN public.budget_template_lines.section_name     IS 'Heading the line sits under in the budget view (e.g. Land, Soft costs, Site work, Long-tail).';
COMMENT ON COLUMN public.budget_template_lines.task_template_id IS 'Optional link to task_templates (FK added only when that table exists).';
COMMENT ON COLUMN public.budget_template_lines.sort_order       IS 'Top-to-bottom order in the standard layout.';


-- 9.3 budget_lines ─ THE core financial table
CREATE TABLE IF NOT EXISTS public.budget_lines (
  id                       UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id               UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  task_id                  UUID          REFERENCES public.tasks(id) ON DELETE RESTRICT,
  template_line_id         UUID          REFERENCES public.budget_template_lines(id) ON DELETE SET NULL,
  parent_line_id           UUID          REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  line_type                VARCHAR(20)   NOT NULL
                                         CHECK (line_type IN ('land', 'bid_activity', 'internal_tm', 'permit', 'impact_fee',
                                                              'soft_cost', 'contingency', 'variance', 'long_tail')),
  line_subtype             VARCHAR(30)
                                         CHECK (line_subtype IS NULL OR line_subtype IN (
                                                  'land_purchase', 'earnest_money', 'due_diligence', 'engineering',
                                                  'escrow_bond_premium', 'escrow_repairs', 'property_tax', 'other')),
  name                     VARCHAR(255)  NOT NULL CHECK (btrim(name) <> ''),
  description              TEXT,
  section_name             VARCHAR(100),
  sort_order               INTEGER       NOT NULL DEFAULT 0,
  original_estimate        DECIMAL(15,2) CHECK (original_estimate IS NULL OR original_estimate >= 0),
  budget_amount            DECIMAL(15,2) NOT NULL DEFAULT 0,
  committed_amount         DECIMAL(15,2) NOT NULL DEFAULT 0 CHECK (committed_amount >= 0),
  pre_award_budget_amount  DECIMAL(15,2) CHECK (pre_award_budget_amount IS NULL OR pre_award_budget_amount >= 0),
  award_id                 UUID          REFERENCES public.awards(id) ON DELETE RESTRICT,
  contract_id              UUID          REFERENCES public.contracts(id) ON DELETE RESTRICT,
  is_locked                BOOLEAN       NOT NULL DEFAULT FALSE,
  locked_at                TIMESTAMPTZ,
  locked_by                UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  lock_reason              TEXT,
  anticipated_start_date   DATE,
  anticipated_end_date     DATE,
  payment_terms_days       INTEGER       NOT NULL DEFAULT 30 CHECK (payment_terms_days BETWEEN 0 AND 365),
  cash_bucket              VARCHAR(30)   NOT NULL DEFAULT 'land'
                                         CHECK (cash_bucket IN ('land', 'vertical_construction', 'overhead')),
  approval_state           VARCHAR(20)   NOT NULL DEFAULT 'not_requested'
                                         CHECK (approval_state IN ('not_requested', 'pending', 'field_approved',
                                                                   'manager_approved', 'sent_to_finance', 'rejected')),
  is_payment_exempt        BOOLEAN       NOT NULL DEFAULT FALSE,
  created_by               UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  updated_by               UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at               TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at               TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at               TIMESTAMPTZ,

  -- Contingency is the only line that may go negative (that is what the
  -- urgent "negative contingency" alert detects).
  CONSTRAINT chk_budget_lines_amount_nonneg
    CHECK (line_type = 'contingency' OR budget_amount >= 0),
  CONSTRAINT chk_budget_lines_dates
    CHECK (anticipated_start_date IS NULL OR anticipated_end_date IS NULL
           OR anticipated_end_date >= anticipated_start_date),
  -- Only bid / internal activity lines are tied to a task.
  CONSTRAINT chk_budget_lines_task_type
    CHECK (task_id IS NULL OR line_type IN ('bid_activity', 'internal_tm')),
  -- A variance always hangs under its activity line.
  CONSTRAINT chk_budget_lines_variance_parent
    CHECK (line_type <> 'variance' OR parent_line_id IS NOT NULL),
  CONSTRAINT chk_budget_lines_parent_not_self
    CHECK (parent_line_id IS NULL OR parent_line_id <> id),
  -- Land and contingency never go through the payment workflow.
  CONSTRAINT chk_budget_lines_exempt_types
    CHECK (line_type NOT IN ('land', 'contingency') OR is_payment_exempt = TRUE),
  CONSTRAINT chk_budget_lines_lock_fields
    CHECK (is_locked = FALSE OR locked_at IS NOT NULL)
);

-- One live budget line per task (task_id nullable; soft-deleted lines free the task).
CREATE UNIQUE INDEX IF NOT EXISTS uq_budget_lines_task
  ON public.budget_lines (task_id)
  WHERE task_id IS NOT NULL AND deleted_at IS NULL;

-- Exactly one live contingency line per project.
CREATE UNIQUE INDEX IF NOT EXISTS uq_budget_lines_one_contingency_per_project
  ON public.budget_lines (project_id)
  WHERE line_type = 'contingency' AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_budget_lines_project_sort ON public.budget_lines (project_id, sort_order) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_budget_lines_project_type ON public.budget_lines (project_id, line_type) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_budget_lines_parent       ON public.budget_lines (parent_line_id) WHERE parent_line_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_budget_lines_award        ON public.budget_lines (award_id)       WHERE award_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_budget_lines_contract     ON public.budget_lines (contract_id)    WHERE contract_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_budget_lines_template_line ON public.budget_lines (template_line_id) WHERE template_line_id IS NOT NULL;

COMMENT ON TABLE  public.budget_lines                         IS 'Every line of a project budget. Bid / internal activity lines link 1:1 to an existing task; land, permit, impact fee, soft cost, contingency, variance and long-tail lines have no task. The contingency line''s budget_amount IS the live contingency balance. Once the project is baselined the SUM of live lines must equal projects.approved_budget_total (flat-budget rule).';
COMMENT ON COLUMN public.budget_lines.task_id                 IS 'Existing task this line represents (bid_activity ↔ competitive / direct_assign, internal_tm ↔ internal). Nullable; unique among non-deleted lines.';
COMMENT ON COLUMN public.budget_lines.parent_line_id          IS 'Variance → its activity line; also groups e.g. an engineering T&M portion under the engineering heading.';
COMMENT ON COLUMN public.budget_lines.line_type               IS 'land | bid_activity | internal_tm | permit | impact_fee | soft_cost | contingency | variance | long_tail.';
COMMENT ON COLUMN public.budget_lines.line_subtype             IS 'Finer classification: land_purchase, earnest_money, due_diligence, engineering, escrow_bond_premium, escrow_repairs, property_tax, other.';
COMMENT ON COLUMN public.budget_lines.original_estimate       IS 'Baseline estimate frozen when the budget is baselined (A21). Never changes afterwards. Feeds the budget accuracy report.';
COMMENT ON COLUMN public.budget_lines.budget_amount           IS 'Current budget for the line. After baseline it changes ONLY through financial procedures, always offset by contingency so the total stays flat.';
COMMENT ON COLUMN public.budget_lines.committed_amount        IS 'Amount committed by an accepted award (= award amount once fn_apply_bid_to_line runs).';
COMMENT ON COLUMN public.budget_lines.pre_award_budget_amount IS 'Budget amount just before the current award was applied. Used by fn_reverse_bid_on_line to restore the line if the award is declined / voided.';
COMMENT ON COLUMN public.budget_lines.award_id                IS 'Award currently applied to this line (set by fn_apply_bid_to_line, cleared by fn_reverse_bid_on_line).';
COMMENT ON COLUMN public.budget_lines.contract_id             IS 'Executed contract that locked this line (fn_lock_budget_line).';
COMMENT ON COLUMN public.budget_lines.is_locked               IS 'TRUE once the contract is executed. Locked amounts cannot be edited; later changes only via variance lines.';
COMMENT ON COLUMN public.budget_lines.anticipated_start_date  IS 'Planned start — cash-flow input.';
COMMENT ON COLUMN public.budget_lines.anticipated_end_date    IS 'Planned end — cash-flow input (cash recognised end + payment terms).';
COMMENT ON COLUMN public.budget_lines.payment_terms_days      IS 'Days between work completion / approval and cash out. Default 30.';
COMMENT ON COLUMN public.budget_lines.cash_bucket             IS 'Cash-out bucket: land (incl. development crews, escrows, taxes), vertical_construction, overhead.';
COMMENT ON COLUMN public.budget_lines.approval_state          IS 'Roll-up of the payment approval state for the line. Detail lives in payment_approvals.';
COMMENT ON COLUMN public.budget_lines.is_payment_exempt       IS 'TRUE for land (title company / bank) and contingency (never paid against).';
COMMENT ON COLUMN public.budget_lines.deleted_at              IS 'Soft delete (lines not needed are removed; the budget doubles as a checklist).';


-- 9.4 land_closings ─ phased takedowns under a land-purchase line
CREATE TABLE IF NOT EXISTS public.land_closings (
  id                    UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  budget_line_id        UUID          NOT NULL REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  closing_sequence      INTEGER       NOT NULL CHECK (closing_sequence >= 1),
  acres                 DECIMAL(12,4) CHECK (acres IS NULL OR acres >= 0),
  amount                DECIMAL(15,2) NOT NULL CHECK (amount >= 0),
  planned_closing_date  DATE          NOT NULL,
  actual_closing_date   DATE,
  status                VARCHAR(20)   NOT NULL DEFAULT 'planned'
                                      CHECK (status IN ('planned', 'closed', 'cancelled')),
  notes                 TEXT,
  created_by            UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_land_closings_sequence UNIQUE (budget_line_id, closing_sequence)
);

CREATE INDEX IF NOT EXISTS idx_land_closings_project ON public.land_closings (project_id);

COMMENT ON TABLE  public.land_closings                     IS 'Phased land takedowns (e.g. 40 of 100 acres now, 60 acres later). Each closing feeds cash flow on its own date.';
COMMENT ON COLUMN public.land_closings.budget_line_id      IS 'The land_purchase budget line this closing belongs to.';
COMMENT ON COLUMN public.land_closings.closing_sequence    IS '1 = first takedown, 2 = second … unique per land line.';
COMMENT ON COLUMN public.land_closings.planned_closing_date IS 'Planned closing date (cash-flow month).';


-- ========================================
-- GROUP 10: CONTINGENCY (3 tables)
-- ========================================

-- 10.1 contingency_buckets ─ every funding source, incl. top-up requests
CREATE TABLE IF NOT EXISTS public.contingency_buckets (
  id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id           UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  contingency_line_id  UUID          NOT NULL REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  bucket_kind          VARCHAR(20)   NOT NULL CHECK (bucket_kind IN ('initial', 'top_up')),
  requested_amount     DECIMAL(15,2) NOT NULL CHECK (requested_amount >= 0),
  approved_amount      DECIMAL(15,2) CHECK (approved_amount IS NULL OR approved_amount >= 0),
  status               VARCHAR(20)   NOT NULL DEFAULT 'pending'
                                     CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
  reason               TEXT          NOT NULL CHECK (btrim(reason) <> ''),
  requested_by         UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  requested_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  decided_by           UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  decided_at           TIMESTAMPTZ,
  decision_note        TEXT,
  created_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_contingency_buckets_topup_positive
    CHECK (bucket_kind = 'initial' OR requested_amount > 0),
  CONSTRAINT chk_contingency_buckets_approved_fields
    CHECK (status <> 'approved' OR (approved_amount IS NOT NULL AND decided_by IS NOT NULL AND decided_at IS NOT NULL)),
  CONSTRAINT chk_contingency_buckets_rejected_fields
    CHECK (status <> 'rejected' OR (decided_by IS NOT NULL AND decided_at IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_contingency_buckets_one_initial
  ON public.contingency_buckets (project_id) WHERE bucket_kind = 'initial';
CREATE INDEX IF NOT EXISTS idx_contingency_buckets_project ON public.contingency_buckets (project_id, status);

COMMENT ON TABLE  public.contingency_buckets                 IS 'Funding sources of a project''s contingency: the initial bucket (at baseline) and every top-up request with its executive decision. The balance itself lives on the single contingency budget line; each approved bucket also has a contingency_ledger row.';
COMMENT ON COLUMN public.contingency_buckets.bucket_kind     IS 'initial = funded at baseline; top_up = executive-approved increase (recorded separately for audit).';
COMMENT ON COLUMN public.contingency_buckets.status          IS 'pending → approved | rejected | cancelled. Approve / reject only via fn_approve_contingency_top_up (executive role).';
COMMENT ON COLUMN public.contingency_buckets.approved_amount IS 'Amount actually approved (may differ from requested).';


-- 10.2 contingency_ledger ─ APPEND-ONLY record of every contingency movement
CREATE TABLE IF NOT EXISTS public.contingency_ledger (
  id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  entry_no               BIGINT        GENERATED ALWAYS AS IDENTITY UNIQUE,
  project_id            UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  contingency_line_id    UUID          NOT NULL REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  contingency_bucket_id  UUID          REFERENCES public.contingency_buckets(id) ON DELETE RESTRICT,
  movement_type          VARCHAR(30)   NOT NULL
                                       CHECK (movement_type IN ('initial_funding', 'bid_overrun', 'bid_savings', 'bid_reversal',
                                                                'variance_created', 'variance_adjusted', 'variance_cancelled',
                                                                'top_up', 'invoice_overage')),
  amount                 DECIMAL(15,2) NOT NULL,
  balance_before         DECIMAL(15,2) NOT NULL,
  balance_after          DECIMAL(15,2) NOT NULL,
  source_budget_line_id  UUID          REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  variance_line_id       UUID,
  award_id               UUID          REFERENCES public.awards(id) ON DELETE RESTRICT,
  actor_user_id          UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  reason                 TEXT,
  created_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_contingency_ledger_balance  CHECK (balance_after = balance_before + amount),
  CONSTRAINT chk_contingency_ledger_nonzero  CHECK (amount <> 0 OR movement_type = 'initial_funding')
);

CREATE INDEX IF NOT EXISTS idx_contingency_ledger_project     ON public.contingency_ledger (project_id, entry_no DESC);
CREATE INDEX IF NOT EXISTS idx_contingency_ledger_source_line ON public.contingency_ledger (source_budget_line_id) WHERE source_budget_line_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contingency_ledger_variance    ON public.contingency_ledger (variance_line_id)      WHERE variance_line_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contingency_ledger_award       ON public.contingency_ledger (award_id)              WHERE award_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contingency_ledger_bucket      ON public.contingency_ledger (contingency_bucket_id) WHERE contingency_bucket_id IS NOT NULL;

COMMENT ON TABLE  public.contingency_ledger                IS 'Append-only audit ledger. One immutable row per contingency movement, always written by a financial stored procedure in the same transaction as the movement. UPDATE / DELETE / TRUNCATE blocked by trg_contingency_ledger_immutable (PT403).';
COMMENT ON COLUMN public.contingency_ledger.entry_no       IS 'Monotonic sequence number. Order the ledger by entry_no (several movements in one transaction share created_at).';
COMMENT ON COLUMN public.contingency_ledger.amount         IS 'Signed: + money INTO contingency (bid savings, adjustment down, top-up), − money OUT of contingency (bid overrun, new variance).';
COMMENT ON COLUMN public.contingency_ledger.balance_before IS 'Contingency line balance before this movement.';
COMMENT ON COLUMN public.contingency_ledger.balance_after  IS 'Contingency line balance after this movement (= before + amount, CHECK-enforced). Running balance for the ledger view.';
COMMENT ON COLUMN public.contingency_ledger.source_budget_line_id IS 'Budget line that caused the movement (bid line, variance line).';
COMMENT ON COLUMN public.contingency_ledger.actor_user_id  IS 'User on whose behalf the procedure ran (who).';


-- 10.3 variance_lines ─ field variance metadata (money is on its own budget line)
CREATE TABLE IF NOT EXISTS public.variance_lines (
  id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id             UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  budget_line_id         UUID          NOT NULL UNIQUE REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  parent_budget_line_id  UUID          NOT NULL REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  trade_id               UUID          REFERENCES public.trades(id) ON DELETE RESTRICT,
  vendor_id              UUID          REFERENCES public.vendors(id) ON DELETE RESTRICT,
  description            TEXT          NOT NULL CHECK (btrim(description) <> ''),
  estimated_amount       DECIMAL(15,2) NOT NULL CHECK (estimated_amount > 0),
  status                 VARCHAR(20)   NOT NULL DEFAULT 'pending_approval'
                                       CHECK (status IN ('draft', 'pending_approval', 'approved', 'rejected', 'cancelled')),
  created_by             UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  approved_by            UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  approved_at            TIMESTAMPTZ,
  rejected_by            UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  rejected_at            TIMESTAMPTZ,
  rejection_reason       TEXT,
  created_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at             TIMESTAMPTZ,

  -- The person who created a variance can never approve it.
  CONSTRAINT chk_variance_lines_not_self_approved CHECK (approved_by IS NULL OR approved_by <> created_by),
  CONSTRAINT chk_variance_lines_approved_fields   CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)),
  CONSTRAINT chk_variance_lines_parent_not_self   CHECK (parent_budget_line_id <> budget_line_id)
);

CREATE INDEX IF NOT EXISTS idx_variance_lines_project ON public.variance_lines (project_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_variance_lines_parent  ON public.variance_lines (parent_budget_line_id);
CREATE INDEX IF NOT EXISTS idx_variance_lines_trade   ON public.variance_lines (trade_id)  WHERE trade_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_variance_lines_vendor  ON public.variance_lines (vendor_id) WHERE vendor_id IS NOT NULL;

-- Ledger → variance FK (variance_lines created after contingency_ledger)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_contingency_ledger_variance') THEN
    ALTER TABLE public.contingency_ledger ADD CONSTRAINT fk_contingency_ledger_variance
      FOREIGN KEY (variance_line_id) REFERENCES public.variance_lines(id) ON DELETE RESTRICT;
  END IF;
END $$;

COMMENT ON TABLE  public.variance_lines                       IS 'Unforeseen field conditions (e.g. rock in the sanitary sewer). The amount lives on the variance''s own budget_lines row (line_type = variance), so totals, the flat-budget rule and cash flow treat it like any line. Created / adjusted only via fn_create_variance / fn_adjust_variance, which move contingency and write the ledger.';
COMMENT ON COLUMN public.variance_lines.budget_line_id        IS 'The variance''s own budget line (1:1). Its budget_amount is the current variance amount.';
COMMENT ON COLUMN public.variance_lines.parent_budget_line_id IS 'Activity line the variance sits under (e.g. sanitary sewer).';
COMMENT ON COLUMN public.variance_lines.estimated_amount      IS 'First estimate at creation (history). The current amount is on the variance budget line.';
COMMENT ON COLUMN public.variance_lines.status                IS 'draft | pending_approval | approved | rejected | cancelled. Approved and cancelled variances are frozen; a further change needs a new variance.';


-- ========================================
-- GROUP 11: PAYMENTS & FINANCE HAND-OFF (3 tables)
-- ========================================

-- 11.1 internal_invoices ─ incoming invoices for internal T&M lines
CREATE TABLE IF NOT EXISTS public.internal_invoices (
  id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id       UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  budget_line_id   UUID          REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  vendor_id        UUID          REFERENCES public.vendors(id) ON DELETE RESTRICT,
  payee_name       VARCHAR(255),
  invoice_number   VARCHAR(100),
  invoice_date     DATE,
  amount           DECIMAL(15,2) NOT NULL CHECK (amount >= 0),
  file_path        TEXT          NOT NULL,
  file_name        VARCHAR(255)  NOT NULL,
  file_size        BIGINT        CHECK (file_size IS NULL OR file_size >= 0),
  status           VARCHAR(20)   NOT NULL DEFAULT 'received'
                                 CHECK (status IN ('received', 'categorised', 'in_approval', 'approved', 'rejected', 'cancelled')),
  notes            TEXT,
  uploaded_by      UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at       TIMESTAMPTZ,

  CONSTRAINT chk_internal_invoices_payee CHECK (vendor_id IS NOT NULL OR payee_name IS NOT NULL),
  CONSTRAINT chk_internal_invoices_categorised CHECK (status IN ('received', 'cancelled') OR budget_line_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_internal_invoices_project ON public.internal_invoices (project_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_internal_invoices_line    ON public.internal_invoices (budget_line_id) WHERE budget_line_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_internal_invoices_vendor  ON public.internal_invoices (vendor_id)      WHERE vendor_id IS NOT NULL;

COMMENT ON TABLE  public.internal_invoices                IS 'Invoices received for internal T&M lines (e.g. attorney). Categorised against a budget line, then sent through payment approval. An invoice over its line allowance creates a variance (Phase 2).';
COMMENT ON COLUMN public.internal_invoices.file_path      IS 'Path in Supabase Storage (finance-documents private bucket).';
COMMENT ON COLUMN public.internal_invoices.budget_line_id IS 'Line the invoice is categorised to. NULL while status = received.';


-- 11.2 payment_approvals ─ one approval request per payment
CREATE TABLE IF NOT EXISTS public.payment_approvals (
  id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id             UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  budget_line_id         UUID          NOT NULL REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  internal_invoice_id    UUID          REFERENCES public.internal_invoices(id) ON DELETE RESTRICT,
  vendor_id              UUID          REFERENCES public.vendors(id) ON DELETE RESTRICT,
  amount                 DECIMAL(15,2) NOT NULL CHECK (amount > 0),
  payment_kind           VARCHAR(20)   NOT NULL DEFAULT 'full'
                                       CHECK (payment_kind IN ('full', 'progress', 'retainage_release')),
  progress_percent       DECIMAL(5,2)  CHECK (progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100),
  retainage_amount       DECIMAL(15,2) CHECK (retainage_amount IS NULL OR retainage_amount >= 0),
  status                 VARCHAR(20)   NOT NULL DEFAULT 'pending'
                                       CHECK (status IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive',
                                                         'approved', 'sent_to_finance', 'rejected', 'cancelled')),
  requested_by           UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  field_approved_by      UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  field_approved_at      TIMESTAMPTZ,
  routed_to_user_id      UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  manager_approved_by    UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  manager_approved_at    TIMESTAMPTZ,
  executive_approved_by  UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  executive_approved_at  TIMESTAMPTZ,
  rejected_by            UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  rejected_at            TIMESTAMPTZ,
  rejection_reason       TEXT,
  comments               TEXT,
  expected_payment_date  DATE,
  created_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  -- Two-person rule: the second approval is always a different person.
  CONSTRAINT chk_payment_approvals_two_person_manager
    CHECK (manager_approved_by IS NULL OR field_approved_by IS NULL OR manager_approved_by <> field_approved_by),
  CONSTRAINT chk_payment_approvals_two_person_executive
    CHECK (executive_approved_by IS NULL OR field_approved_by IS NULL OR executive_approved_by <> field_approved_by),
  CONSTRAINT chk_payment_approvals_progress
    CHECK (payment_kind <> 'progress' OR progress_percent IS NOT NULL),
  CONSTRAINT chk_payment_approvals_rejected_fields
    CHECK (status <> 'rejected' OR (rejected_by IS NOT NULL AND rejected_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_payment_approvals_project  ON public.payment_approvals (project_id, status);
CREATE INDEX IF NOT EXISTS idx_payment_approvals_line     ON public.payment_approvals (budget_line_id);
CREATE INDEX IF NOT EXISTS idx_payment_approvals_routed   ON public.payment_approvals (routed_to_user_id, status) WHERE routed_to_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payment_approvals_invoice  ON public.payment_approvals (internal_invoice_id) WHERE internal_invoice_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payment_approvals_vendor   ON public.payment_approvals (vendor_id) WHERE vendor_id IS NOT NULL;

COMMENT ON TABLE  public.payment_approvals                       IS 'Approve-for-payment requests on bid, variance and internal invoice lines (full, progress or retainage release). Flow: pending → field_approved → awaiting_manager / awaiting_executive → approved → sent_to_finance. Two-person rule CHECK-enforced.';
COMMENT ON COLUMN public.payment_approvals.routed_to_user_id     IS 'Who the second approval is waiting on: reports_to manager, or the backup / delegate when the manager is unavailable.';
COMMENT ON COLUMN public.payment_approvals.expected_payment_date IS 'Final approval date + payment terms. Written to cash flow.';
COMMENT ON COLUMN public.payment_approvals.retainage_amount      IS 'Amount held back from this payment under the contract''s retainage terms.';


-- 11.3 finance_handoffs ─ what was sent to finance (internal invoice / PO record)
CREATE TABLE IF NOT EXISTS public.finance_handoffs (
  id                    UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  payment_approval_id   UUID          NOT NULL UNIQUE REFERENCES public.payment_approvals(id) ON DELETE RESTRICT,
  project_id            UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  po_number             VARCHAR(50)   NOT NULL UNIQUE,
  vendor_id             UUID          REFERENCES public.vendors(id) ON DELETE RESTRICT,
  amount                DECIMAL(15,2) NOT NULL CHECK (amount > 0),
  payload               JSONB         NOT NULL DEFAULT '{}'::jsonb,
  document_path         TEXT,
  email_log_id          UUID          REFERENCES public.email_log(id) ON DELETE SET NULL,
  status                VARCHAR(20)   NOT NULL DEFAULT 'pending'
                                      CHECK (status IN ('pending', 'sent', 'delivered', 'failed')),
  sent_at               TIMESTAMPTZ,
  exported_at           TIMESTAMPTZ,
  created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finance_handoffs_project ON public.finance_handoffs (project_id, status);
CREATE INDEX IF NOT EXISTS idx_finance_handoffs_email   ON public.finance_handoffs (email_log_id) WHERE email_log_id IS NOT NULL;

COMMENT ON TABLE  public.finance_handoffs               IS 'Finance hand-off log: one row per finally-approved payment with its internal invoice / PO record. Finance pays outside the system; delivery is proven by email_log.';
COMMENT ON COLUMN public.finance_handoffs.payload       IS 'Snapshot sent to finance: trade, amount, project, activity, date, approvers, contract number.';
COMMENT ON COLUMN public.finance_handoffs.document_path IS 'Generated PO / internal invoice PDF in the finance-documents bucket.';
COMMENT ON COLUMN public.finance_handoffs.email_log_id  IS 'The finance email in email_log (delivery status = audit proof).';


-- ========================================
-- GROUP 12: LONG-TAIL ITEMS (2 tables)
-- ========================================

-- 12.1 escrows
CREATE TABLE IF NOT EXISTS public.escrows (
  id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  name              VARCHAR(255)  NOT NULL CHECK (btrim(name) <> ''),
  beneficiary       VARCHAR(20)   NOT NULL CHECK (beneficiary IN ('city', 'county', 'hoa', 'other')),
  covered_areas     TEXT[]        NOT NULL DEFAULT '{}',
  security_form     VARCHAR(10)   NOT NULL CHECK (security_form IN ('cash', 'bond')),
  holder_type       VARCHAR(30)   CHECK (holder_type IS NULL OR holder_type IN ('insurance_company', 'bank', 'other')),
  holder_name       VARCHAR(255),
  secured_amount    DECIMAL(15,2) NOT NULL CHECK (secured_amount >= 0),
  premium_amount    DECIMAL(15,2) CHECK (premium_amount IS NULL OR premium_amount >= 0),
  bond_number       VARCHAR(100),
  bond_expiry_date  DATE,
  status            VARCHAR(20)   NOT NULL DEFAULT 'planned'
                                  CHECK (status IN ('planned', 'posted', 'works_built', 'inspection', 'corrections',
                                                    'signed_off', 'released', 'cancelled')),
  posted_date       DATE,
  released_date     DATE,
  premium_line_id   UUID          REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  repair_line_id    UUID          REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  document_path     TEXT,
  notes             TEXT,
  created_by        UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at        TIMESTAMPTZ,

  CONSTRAINT chk_escrows_release_after_post CHECK (released_date IS NULL OR posted_date IS NULL OR released_date >= posted_date),
  CONSTRAINT chk_escrows_released_has_date  CHECK (status <> 'released' OR released_date IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_escrows_project ON public.escrows (project_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_escrows_bond_expiry ON public.escrows (bond_expiry_date) WHERE bond_expiry_date IS NOT NULL AND deleted_at IS NULL;

COMMENT ON TABLE  public.escrows                  IS 'Escrows posted for public / HOA works (roads to the city; landscaping, trails, common areas to the HOA). Each carries two cost lines: the bond / insurance premium and repairs to city standard. Lifecycle posted → works_built → inspection → corrections → signed_off → released.';
COMMENT ON COLUMN public.escrows.covered_areas    IS 'One escrow may cover several areas, e.g. {roads} or {landscaping, trails, benches}.';
COMMENT ON COLUMN public.escrows.security_form    IS 'cash = cash posted (cash out, back in on release); bond = insurance policy equal to the value of the works.';
COMMENT ON COLUMN public.escrows.secured_amount   IS 'Value of the works the escrow secures (e.g. $10k bond for $10k of roads).';
COMMENT ON COLUMN public.escrows.premium_line_id  IS 'Cost 1: budget line for the bond / insurance premium.';
COMMENT ON COLUMN public.escrows.repair_line_id   IS 'Cost 2: budget line for repairs to city standard found at the inspection walk.';
COMMENT ON COLUMN public.escrows.bond_expiry_date IS 'Bond expiry — drives renewal reminders while the escrow is open.';


-- 12.2 property_taxes
CREATE TABLE IF NOT EXISTS public.property_taxes (
  id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id             UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  budget_line_id         UUID          REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  tax_year               INTEGER       NOT NULL CHECK (tax_year BETWEEN 2000 AND 2200),
  jurisdiction           VARCHAR(150)  NOT NULL CHECK (btrim(jurisdiction) <> ''),
  parcel_reference       VARCHAR(100),
  installment_number     INTEGER       NOT NULL DEFAULT 1 CHECK (installment_number >= 1),
  due_date               DATE,
  estimate_basis         VARCHAR(20)   NOT NULL DEFAULT 'manual'
                                       CHECK (estimate_basis IN ('prior_year_actual', 'assessed_value', 'manual')),
  estimated_amount       DECIMAL(15,2) NOT NULL CHECK (estimated_amount >= 0),
  actual_amount          DECIMAL(15,2) CHECK (actual_amount IS NULL OR actual_amount >= 0),
  sold_portion_percent   DECIMAL(5,2)  CHECK (sold_portion_percent IS NULL OR sold_portion_percent BETWEEN 0 AND 100),
  status                 VARCHAR(20)   NOT NULL DEFAULT 'estimated'
                                       CHECK (status IN ('estimated', 'billed', 'in_approval', 'sent_to_finance', 'cancelled')),
  notes                  TEXT,
  created_by             UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_property_taxes_installment UNIQUE (project_id, tax_year, jurisdiction, installment_number)
);

CREATE INDEX IF NOT EXISTS idx_property_taxes_due ON public.property_taxes (due_date) WHERE status IN ('estimated', 'billed');

COMMENT ON TABLE  public.property_taxes                      IS 'Yearly property tax for each year the land is owned, per jurisdiction and instalment. Estimated internally; estimate vs actual tracked to catch increases; reduced as lots sell.';
COMMENT ON COLUMN public.property_taxes.estimate_basis       IS 'prior_year_actual | assessed_value | manual (entered by finance).';
COMMENT ON COLUMN public.property_taxes.sold_portion_percent IS 'Share of the land already sold — the tax line is reduced for it.';


-- ========================================
-- GROUP 13: CASH FLOW (3 tables)
-- ========================================

-- 13.1 accounting_periods ─ company-wide months
CREATE TABLE IF NOT EXISTS public.accounting_periods (
  id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  period_month  DATE          NOT NULL UNIQUE CHECK (EXTRACT(DAY FROM period_month) = 1),
  status        VARCHAR(10)   NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
  closed_by     UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  closed_at     TIMESTAMPTZ,
  notes         TEXT,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_accounting_periods_closed_fields CHECK (status <> 'closed' OR (closed_by IS NOT NULL AND closed_at IS NOT NULL))
);

COMMENT ON TABLE  public.accounting_periods              IS 'Company-wide accounting months. A closed month is never changed retroactively: cash_flow_entries in it are frozen. Closed only via fn_close_accounting_month (finance / executive); never reopened.';
COMMENT ON COLUMN public.accounting_periods.period_month IS 'First day of the month (e.g. 2027-01-01).';


-- 13.2 company_cash_items ─ overhead, deposits, closings (manual / CSV)
CREATE TABLE IF NOT EXISTS public.company_cash_items (
  id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  item_type        VARCHAR(30)   NOT NULL CHECK (item_type IN ('overhead', 'deposit', 'closing', 'vertical_construction', 'other')),
  direction        VARCHAR(3)    NOT NULL CHECK (direction IN ('out', 'in')),
  cash_bucket      VARCHAR(30)   NOT NULL CHECK (cash_bucket IN ('land', 'vertical_construction', 'overhead', 'deposits', 'closings')),
  business_entity  VARCHAR(20)   CHECK (business_entity IS NULL OR business_entity IN ('bluonx', 'capstone')),
  project_id       UUID          REFERENCES public.projects(id) ON DELETE RESTRICT,
  description      VARCHAR(255)  NOT NULL CHECK (btrim(description) <> ''),
  period_month     DATE          NOT NULL CHECK (EXTRACT(DAY FROM period_month) = 1),
  amount           DECIMAL(15,2) NOT NULL CHECK (amount >= 0),
  source           VARCHAR(20)   NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'csv_import')),
  created_by       UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_company_cash_items_month   ON public.company_cash_items (period_month, cash_bucket) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_company_cash_items_project ON public.company_cash_items (project_id) WHERE project_id IS NOT NULL;

COMMENT ON TABLE  public.company_cash_items           IS 'Company-level cash items not tied to a budget line: overhead (salaries, insurance), customer deposits, closings, vertical construction. Entered manually or by CSV import. Finance-restricted.';
COMMENT ON COLUMN public.company_cash_items.direction IS 'out = cash leaving the account; in = cash arriving (deposits, closings).';


-- 13.3 cash_flow_entries ─ monthly cash schedule
CREATE TABLE IF NOT EXISTS public.cash_flow_entries (
  id                    UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            UUID          REFERENCES public.projects(id) ON DELETE RESTRICT,
  budget_line_id        UUID          REFERENCES public.budget_lines(id) ON DELETE RESTRICT,
  land_closing_id       UUID          REFERENCES public.land_closings(id) ON DELETE RESTRICT,
  escrow_id             UUID          REFERENCES public.escrows(id) ON DELETE RESTRICT,
  payment_approval_id   UUID          REFERENCES public.payment_approvals(id) ON DELETE RESTRICT,
  company_cash_item_id  UUID          REFERENCES public.company_cash_items(id) ON DELETE RESTRICT,
  period_month          DATE          NOT NULL CHECK (EXTRACT(DAY FROM period_month) = 1),
  direction             VARCHAR(3)    NOT NULL CHECK (direction IN ('out', 'in')),
  cash_bucket           VARCHAR(30)   NOT NULL CHECK (cash_bucket IN ('land', 'vertical_construction', 'overhead', 'deposits', 'closings')),
  amount                DECIMAL(15,2) NOT NULL CHECK (amount >= 0),
  entry_kind            VARCHAR(10)   NOT NULL DEFAULT 'forecast' CHECK (entry_kind IN ('forecast', 'expected', 'actual')),
  source_note           TEXT,
  created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_cash_flow_entries_has_source CHECK (
    budget_line_id IS NOT NULL OR land_closing_id IS NOT NULL OR escrow_id IS NOT NULL
    OR payment_approval_id IS NOT NULL OR company_cash_item_id IS NOT NULL
  )
);

CREATE INDEX IF NOT EXISTS idx_cash_flow_entries_month   ON public.cash_flow_entries (period_month, cash_bucket);
CREATE INDEX IF NOT EXISTS idx_cash_flow_entries_project ON public.cash_flow_entries (project_id, period_month) WHERE project_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cash_flow_entries_line    ON public.cash_flow_entries (budget_line_id)       WHERE budget_line_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cash_flow_entries_closing ON public.cash_flow_entries (land_closing_id)      WHERE land_closing_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cash_flow_entries_escrow  ON public.cash_flow_entries (escrow_id)            WHERE escrow_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cash_flow_entries_payment ON public.cash_flow_entries (payment_approval_id)  WHERE payment_approval_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cash_flow_entries_company ON public.cash_flow_entries (company_cash_item_id) WHERE company_cash_item_id IS NOT NULL;

COMMENT ON TABLE  public.cash_flow_entries              IS 'Monthly cash schedule (macro, not day-level). Generated from line dates + payment terms, land closings, escrow postings / releases, approved payments and company items. Rows in a closed accounting month are frozen (trg_cash_flow_entries_closed_period).';
COMMENT ON COLUMN public.cash_flow_entries.period_month IS 'First day of the month the cash moves in.';
COMMENT ON COLUMN public.cash_flow_entries.entry_kind   IS 'forecast = from line dates; expected = from an approved payment''s expected date; actual = confirmed (optional).';


-- ========================================
-- GROUP 14: SETTINGS, ALERTS & ROLES (4 tables)
-- ========================================

-- 14.1 financial_settings ─ key / value (typed JSON)
CREATE TABLE IF NOT EXISTS public.financial_settings (
  setting_key  VARCHAR(100)  PRIMARY KEY CHECK (setting_key ~ '^[a-z][a-z0-9_]*$'),
  value        JSONB         NOT NULL,
  description  TEXT,
  updated_by   UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  public.financial_settings       IS 'Organisation-wide financial settings (contingency %, targets, limits, thresholds, notification recipients). Key / value so a new setting never needs a migration.';
COMMENT ON COLUMN public.financial_settings.value IS 'JSON value: number, string, array or object depending on the key (see description).';


-- 14.2 financial_alerts ─ guardrail alerts and their decisions
CREATE TABLE IF NOT EXISTS public.financial_alerts (
  id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id             UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  alert_type             VARCHAR(30)   NOT NULL
                                       CHECK (alert_type IN ('contingency_health', 'contingency_near_zero', 'contingency_negative',
                                                             'long_tail_reserve', 'bidding_checkpoint')),
  severity               VARCHAR(10)   NOT NULL CHECK (severity IN ('warning', 'urgent', 'critical')),
  status                 VARCHAR(20)   NOT NULL DEFAULT 'open'
                                       CHECK (status IN ('open', 'acknowledged', 'proceed_approved', 'on_hold', 'resolved', 'superseded')),
  contingency_left_pct   DECIMAL(7,2),
  work_left_pct          DECIMAL(7,2),
  contingency_remaining  DECIMAL(15,2),
  reserve_required       DECIMAL(15,2),
  message                TEXT,
  decision               VARCHAR(10)   CHECK (decision IS NULL OR decision IN ('proceed', 'hold')),
  decision_reason        TEXT,
  decided_by             UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  decided_at             TIMESTAMPTZ,
  resolved_at            TIMESTAMPTZ,
  created_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_financial_alerts_decision_fields
    CHECK (decision IS NULL OR (decided_by IS NOT NULL AND decided_at IS NOT NULL AND btrim(COALESCE(decision_reason, '')) <> ''))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_financial_alerts_one_open
  ON public.financial_alerts (project_id, alert_type) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_financial_alerts_project ON public.financial_alerts (project_id, created_at DESC);

COMMENT ON TABLE  public.financial_alerts                 IS 'Contingency guardrail alerts (health, near zero, negative, long-tail reserve, bidding checkpoint) with the snapshot that triggered them and the manager''s recorded OK-to-proceed / hold decision. One open alert per project and type.';
COMMENT ON COLUMN public.financial_alerts.decision        IS 'proceed = work continues (reason logged); hold = project placed on the existing on_hold status.';
COMMENT ON COLUMN public.financial_alerts.decision_reason IS 'Required whenever a decision is recorded.';


-- 14.3 user_roles ─ many roles per user
CREATE TABLE IF NOT EXISTS public.user_roles (
  id           UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  role         VARCHAR(20)   NOT NULL
                             CHECK (role IN ('admin', 'project_manager', 'field_manager', 'executive', 'finance')),
  granted_by   UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  granted_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  revoked_at   TIMESTAMPTZ,
  revoked_by   UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_roles_active
  ON public.user_roles (user_id, role) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON public.user_roles (role) WHERE revoked_at IS NULL;

COMMENT ON TABLE  public.user_roles            IS 'Roles held by each user. One person may hold several (e.g. executive + manager). Base role mirrors users.role (sync trigger); financial roles field_manager / executive / finance are granted here. Revoke = set revoked_at (never deleted, for audit).';
COMMENT ON COLUMN public.user_roles.role       IS 'admin | project_manager | field_manager | executive | finance.';
COMMENT ON COLUMN public.user_roles.revoked_at IS 'NULL = role active. Partial unique index allows re-granting after a revoke.';


-- 14.4 approval_delegations ─ temporary delegation while a manager is away
CREATE TABLE IF NOT EXISTS public.approval_delegations (
  id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  delegator_user_id  UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  delegate_user_id   UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  starts_at          TIMESTAMPTZ   NOT NULL,
  ends_at            TIMESTAMPTZ   NOT NULL,
  reason             TEXT,
  created_by         UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  revoked_at         TIMESTAMPTZ,
  created_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_approval_delegations_window  CHECK (ends_at > starts_at),
  CONSTRAINT chk_approval_delegations_not_self CHECK (delegator_user_id <> delegate_user_id)
);

CREATE INDEX IF NOT EXISTS idx_approval_delegations_delegator ON public.approval_delegations (delegator_user_id, starts_at, ends_at) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_approval_delegations_delegate  ON public.approval_delegations (delegate_user_id) WHERE revoked_at IS NULL;

COMMENT ON TABLE  public.approval_delegations          IS 'Temporary hand-over of a manager''s approvals to another user for a time window (holiday, sick leave). Overrides users.backup_approver_id while active.';
COMMENT ON COLUMN public.approval_delegations.ends_at  IS 'Exclusive end of the delegation window.';


-- ============================================================================
-- SECTION 9.D: TYPE VOCABULARIES (email_log, notifications)
-- ============================================================================

-- D.1 email_log.email_type — widen the CHECK to a SUPERSET.
--     The new list = planned values ∪ every value already present in the
--     table, so validation can never fail on production data. The old
--     constraint is found by definition (name differs between environments).
DO $$
DECLARE
  v_planned  TEXT[] := ARRAY[
    -- existing (Phase 1 bid system)
    'bid_invitation', 'bid_reminder', 'award_notification', 'decline_notification',
    'milestone_alert', 'general',
    -- financial
    'payment_approval_request', 'payment_approved', 'payment_rejected',
    'finance_handoff', 'finance_daily_summary',
    'contingency_alert', 'contingency_escalation', 'contingency_top_up',
    'long_tail_reserve_alert', 'bidding_checkpoint',
    'property_tax_reminder', 'bond_renewal_reminder', 'owner_weekly_summary'
  ];
  v_existing TEXT[];
  v_all      TEXT[];
  v_list     TEXT;
  r          RECORD;
BEGIN
  SELECT array_agg(DISTINCT email_type) INTO v_existing FROM public.email_log;
  SELECT array_agg(x ORDER BY x) INTO v_all
    FROM (SELECT DISTINCT unnest(v_planned || COALESCE(v_existing, '{}'::text[])) AS x) s;

  FOR r IN
    SELECT conname
      FROM pg_constraint
     WHERE conrelid = 'public.email_log'::regclass
       AND contype  = 'c'
       AND pg_get_constraintdef(oid) ILIKE '%email_type%'
  LOOP
    EXECUTE format('ALTER TABLE public.email_log DROP CONSTRAINT %I', r.conname);
  END LOOP;

  SELECT string_agg(quote_literal(x), ', ' ORDER BY x) INTO v_list FROM unnest(v_all) AS x;
  EXECUTE format(
    'ALTER TABLE public.email_log ADD CONSTRAINT chk_email_log_email_type CHECK (email_type IN (%s)) NOT VALID',
    v_list);
  EXECUTE 'ALTER TABLE public.email_log VALIDATE CONSTRAINT chk_email_log_email_type';
END $$;

COMMENT ON COLUMN public.email_log.email_type IS
  'Bid system: bid_invitation, bid_reminder, award_notification, decline_notification, milestone_alert, general. Financial (v4.0): payment_approval_request, payment_approved, payment_rejected, finance_handoff, finance_daily_summary, contingency_alert, contingency_escalation, contingency_top_up, long_tail_reserve_alert, bidding_checkpoint, property_tax_reminder, bond_renewal_reminder, owner_weekly_summary.';

-- D.2 notifications.notification_type — no CHECK exists and none is added
--     (an incomplete list would reject types written by existing jobs).
COMMENT ON COLUMN public.notifications.notification_type IS
  'Free-text type (VARCHAR 30, no CHECK by design). Bid system: milestone_completed, milestone_delayed, milestone_unresponsive, milestone_delivery_failed, insurance_*, scheduler_alert, post-deadline escalation. Financial (v4.0): contingency_health_alert, contingency_urgent_alert, long_tail_reserve_alert, bidding_checkpoint_alert, top_up_requested, top_up_decided, payment_approval_requested, payment_approved, payment_rejected, variance_pending_approval, property_tax_due, bond_renewal_due, month_closed.';


-- ============================================================================
-- SECTION 9.D2: ROLE HELPERS (need user_roles, so defined after the tables)
-- ============================================================================

-- A.2  Does a given user hold a given role? (procedure-side check)
--      Considers the user active, non-deleted, and the role un-revoked.
CREATE OR REPLACE FUNCTION private.user_has_role(p_user_id UUID, p_role TEXT)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT 1
      FROM public.user_roles ur
      JOIN public.users u ON u.id = ur.user_id
     WHERE ur.user_id   = p_user_id
       AND ur.role      = p_role
       AND ur.revoked_at IS NULL
       AND u.is_active  = TRUE
       AND u.deleted_at IS NULL
  );
$$;

COMMENT ON FUNCTION private.user_has_role(UUID, TEXT) IS
  'TRUE when the user is active and holds the role in user_roles (not revoked). Used inside financial procedures for defence-in-depth role checks (e.g. executive-only top-ups).';


-- A.3  Does the CALLER (auth.uid()) hold any of the roles? (RLS-side check)
--      Admins always pass.
CREATE OR REPLACE FUNCTION private.has_any_role(p_roles TEXT[])
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT EXISTS (
    SELECT 1
      FROM public.users u
     WHERE u.id = (SELECT auth.uid())
       AND u.is_active = TRUE
       AND u.deleted_at IS NULL
       AND (
             u.role = 'admin'
          OR EXISTS (
               SELECT 1 FROM public.user_roles ur
                WHERE ur.user_id = u.id
                  AND ur.revoked_at IS NULL
                  AND (ur.role = 'admin' OR ur.role = ANY (p_roles))
             )
       )
  );
$$;

COMMENT ON FUNCTION private.has_any_role(TEXT[]) IS
  'RLS helper: TRUE when the signed-in user is active and holds any of the given roles (admins always pass). SECURITY DEFINER so it can read users/user_roles without recursive RLS.';


-- ============================================================================
-- SECTION 9.E: TRIGGERS (guards, consistency, timestamps)
-- ============================================================================

-- ── E.1 updated_at on every new table (except the append-only ledger) ───────
DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'budget_templates', 'budget_template_lines', 'budget_lines', 'land_closings',
    'contingency_buckets', 'variance_lines', 'internal_invoices', 'payment_approvals',
    'finance_handoffs', 'escrows', 'property_taxes', 'accounting_periods',
    'company_cash_items', 'cash_flow_entries', 'financial_settings', 'financial_alerts',
    'user_roles', 'approval_delegations'
  ] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I', 'trg_' || t || '_updated_at', t);
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at()',
      'trg_' || t || '_updated_at', t);
  END LOOP;
END $$;


-- ── E.2 contingency_ledger immutability (same pattern as milestone_events) ──
CREATE OR REPLACE FUNCTION public.fn_block_contingency_ledger_mutation()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_LEVEL = 'STATEMENT' THEN
    RAISE EXCEPTION 'contingency_ledger is append-only (attempted %)', TG_OP
      USING ERRCODE = 'PT403';
  END IF;
  RAISE EXCEPTION 'contingency_ledger is append-only (attempted % on ledger row %)',
    TG_OP, OLD.id
    USING ERRCODE = 'PT403';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_contingency_ledger_immutable ON public.contingency_ledger;
CREATE TRIGGER trg_contingency_ledger_immutable
  BEFORE UPDATE OR DELETE ON public.contingency_ledger
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_contingency_ledger_mutation();

DROP TRIGGER IF EXISTS trg_contingency_ledger_no_truncate ON public.contingency_ledger;
CREATE TRIGGER trg_contingency_ledger_no_truncate
  BEFORE TRUNCATE ON public.contingency_ledger
  FOR EACH STATEMENT EXECUTE FUNCTION public.fn_block_contingency_ledger_mutation();


-- ── E.3 budget_lines guard ──────────────────────────────────────────────────
-- Consistency (always):
--   • project_id and line_type never change after insert
--   • task belongs to the same project, and line_type matches task.bid_type
--   • parent line belongs to the same project
-- Money (once the project is BASELINED, unless a financial procedure runs):
--   • budget_amount, committed_amount, award_id, original_estimate frozen
--   • a new line may only be inserted with budget_amount = 0
-- Locks (always, unless a financial procedure runs):
--   • a locked line's amounts / award cannot change and it cannot be unlocked
CREATE OR REPLACE FUNCTION public.fn_guard_budget_lines()
RETURNS TRIGGER AS $$
DECLARE
  v_auth        BOOLEAN := private.fin_write_authorized();
  v_baselined   BOOLEAN;
  v_task        RECORD;
  v_parent_proj UUID;
BEGIN
  -- Immutable identity columns
  IF TG_OP = 'UPDATE' THEN
    IF NEW.project_id IS DISTINCT FROM OLD.project_id THEN
      RAISE EXCEPTION 'A budget line cannot move to another project (line %)', OLD.id USING ERRCODE = 'PT422';
    END IF;
    IF NEW.line_type IS DISTINCT FROM OLD.line_type THEN
      RAISE EXCEPTION 'line_type cannot change after a line is created (line %: % → %). Remove the line and add a new one.',
        OLD.id, OLD.line_type, NEW.line_type USING ERRCODE = 'PT422';
    END IF;
  END IF;

  -- Task consistency
  IF NEW.task_id IS NOT NULL
     AND (TG_OP = 'INSERT' OR NEW.task_id IS DISTINCT FROM OLD.task_id) THEN
    SELECT project_id, bid_type, deleted_at INTO v_task FROM public.tasks WHERE id = NEW.task_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Task % not found', NEW.task_id USING ERRCODE = 'PT404';
    END IF;
    IF v_task.project_id <> NEW.project_id THEN
      RAISE EXCEPTION 'Task % belongs to project %, not %', NEW.task_id, v_task.project_id, NEW.project_id
        USING ERRCODE = 'PT422';
    END IF;
    IF (NEW.line_type = 'bid_activity' AND v_task.bid_type NOT IN ('competitive', 'direct_assign'))
       OR (NEW.line_type = 'internal_tm' AND v_task.bid_type <> 'internal') THEN
      RAISE EXCEPTION 'Line type % does not match task bid_type % (bid_activity ↔ competitive/direct_assign, internal_tm ↔ internal)',
        NEW.line_type, v_task.bid_type USING ERRCODE = 'PT422';
    END IF;
  END IF;

  -- Parent consistency
  IF NEW.parent_line_id IS NOT NULL
     AND (TG_OP = 'INSERT' OR NEW.parent_line_id IS DISTINCT FROM OLD.parent_line_id) THEN
    SELECT project_id INTO v_parent_proj FROM public.budget_lines WHERE id = NEW.parent_line_id;
    IF v_parent_proj IS DISTINCT FROM NEW.project_id THEN
      RAISE EXCEPTION 'Parent line % is not in project %', NEW.parent_line_id, NEW.project_id USING ERRCODE = 'PT422';
    END IF;
  END IF;

  -- Authoritative writer: everything below is the procedures' business.
  IF v_auth THEN
    RETURN NEW;
  END IF;

  -- Lock rules (always)
  IF TG_OP = 'UPDATE' AND OLD.is_locked THEN
    IF NEW.is_locked = FALSE
       OR NEW.budget_amount    IS DISTINCT FROM OLD.budget_amount
       OR NEW.committed_amount IS DISTINCT FROM OLD.committed_amount
       OR NEW.award_id         IS DISTINCT FROM OLD.award_id
       OR NEW.contract_id      IS DISTINCT FROM OLD.contract_id THEN
      RAISE EXCEPTION 'Budget line % is locked (contract executed). Locked amounts cannot be edited; use a variance line.',
        OLD.id USING ERRCODE = 'PT409';
    END IF;
  END IF;

  SELECT budget_status = 'baselined' INTO v_baselined FROM public.projects WHERE id = NEW.project_id;

  IF COALESCE(v_baselined, FALSE) THEN
    IF TG_OP = 'INSERT' THEN
      IF NEW.budget_amount <> 0 OR NEW.committed_amount <> 0 OR NEW.award_id IS NOT NULL THEN
        RAISE EXCEPTION 'Project budget is baselined: a new line must start at $0 and be funded through a financial procedure (total budget must stay flat).'
          USING ERRCODE = 'PT409';
      END IF;
    ELSE
      IF NEW.budget_amount     IS DISTINCT FROM OLD.budget_amount
         OR NEW.committed_amount  IS DISTINCT FROM OLD.committed_amount
         OR NEW.award_id          IS DISTINCT FROM OLD.award_id
         OR NEW.original_estimate IS DISTINCT FROM OLD.original_estimate THEN
        RAISE EXCEPTION 'Project budget is baselined: amounts on line % change only through financial procedures (bid, variance, top-up) so contingency and the ledger stay in step.',
          OLD.id USING ERRCODE = 'PT409';
      END IF;
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_budget_lines_guard ON public.budget_lines;
CREATE TRIGGER trg_budget_lines_guard
  BEFORE INSERT OR UPDATE ON public.budget_lines
  FOR EACH ROW EXECUTE FUNCTION public.fn_guard_budget_lines();


-- ── E.4 Flat-budget rule (deferred: checked once, at COMMIT) ────────────────
-- A bid overrun is two writes (+2,000 on the line, −2,000 on contingency);
-- checking at commit lets every procedure move money in balanced pairs while
-- any one-sided change — from anywhere — fails the whole transaction.
CREATE OR REPLACE FUNCTION public.fn_check_flat_budget_total()
RETURNS TRIGGER AS $$
DECLARE
  v_project_id UUID := COALESCE(NEW.project_id, OLD.project_id);
  v_status     TEXT;
  v_approved   NUMERIC;
  v_actual     NUMERIC;
BEGIN
  SELECT budget_status, approved_budget_total INTO v_status, v_approved
    FROM public.projects WHERE id = v_project_id;

  IF v_status IS DISTINCT FROM 'baselined' THEN
    RETURN NULL;
  END IF;

  SELECT COALESCE(SUM(budget_amount), 0) INTO v_actual
    FROM public.budget_lines
   WHERE project_id = v_project_id AND deleted_at IS NULL;

  IF v_actual <> v_approved THEN
    RAISE EXCEPTION 'Flat-budget rule violated for project %: lines total % but the approved budget is %. The total can only change through an executive-approved contingency top-up.',
      v_project_id, v_actual, v_approved
      USING ERRCODE = 'PT409';
  END IF;

  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_budget_lines_flat_total ON public.budget_lines;
CREATE CONSTRAINT TRIGGER trg_budget_lines_flat_total
  AFTER INSERT OR UPDATE OR DELETE ON public.budget_lines
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION public.fn_check_flat_budget_total();


-- ── E.5 projects: approved total / baseline only via procedures ─────────────
-- none ↔ draft is free (Phase 2 budget builder). Anything touching
-- 'baselined', the approved total or the baseline stamp needs the flag.
-- Fires only when these new columns are in the UPDATE, so the existing
-- project PATCH endpoint is unaffected.
CREATE OR REPLACE FUNCTION public.fn_guard_project_budget_total()
RETURNS TRIGGER AS $$
BEGIN
  IF private.fin_write_authorized() THEN
    RETURN NEW;
  END IF;

  IF NEW.approved_budget_total IS DISTINCT FROM OLD.approved_budget_total
     OR NEW.budget_baselined_at IS DISTINCT FROM OLD.budget_baselined_at
     OR NEW.budget_baselined_by IS DISTINCT FROM OLD.budget_baselined_by
     OR (NEW.budget_status IS DISTINCT FROM OLD.budget_status
         AND 'baselined' IN (NEW.budget_status, OLD.budget_status)) THEN
    RAISE EXCEPTION 'The approved budget of project % can only be set by baselining and changed by an executive-approved contingency top-up.',
      OLD.id USING ERRCODE = 'PT409';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_projects_guard_budget_total ON public.projects;
CREATE TRIGGER trg_projects_guard_budget_total
  BEFORE UPDATE OF approved_budget_total, budget_status, budget_baselined_at, budget_baselined_by
  ON public.projects
  FOR EACH ROW EXECUTE FUNCTION public.fn_guard_project_budget_total();


-- ── E.6 contingency_buckets: decisions only via the top-up procedure ────────
CREATE OR REPLACE FUNCTION public.fn_guard_contingency_buckets()
RETURNS TRIGGER AS $$
BEGIN
  IF private.fin_write_authorized() THEN
    RETURN NEW;
  END IF;

  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'pending' OR NEW.bucket_kind <> 'top_up' THEN
      RAISE EXCEPTION 'Only pending top-up requests may be inserted directly; initial buckets and decisions are written by financial procedures.'
        USING ERRCODE = 'PT409';
    END IF;
    RETURN NEW;
  END IF;

  IF OLD.status <> 'pending' THEN
    RAISE EXCEPTION 'Contingency bucket % is already % and cannot change.', OLD.id, OLD.status USING ERRCODE = 'PT409';
  END IF;
  IF NEW.status = 'approved' OR NEW.status = 'rejected'
     OR NEW.approved_amount IS DISTINCT FROM OLD.approved_amount
     OR NEW.decided_by      IS DISTINCT FROM OLD.decided_by THEN
    RAISE EXCEPTION 'Top-up decisions are recorded only by fn_approve_contingency_top_up (executive role).'
      USING ERRCODE = 'PT409';
  END IF;
  IF NEW.project_id IS DISTINCT FROM OLD.project_id
     OR NEW.contingency_line_id IS DISTINCT FROM OLD.contingency_line_id
     OR NEW.bucket_kind IS DISTINCT FROM OLD.bucket_kind THEN
    RAISE EXCEPTION 'Bucket identity columns cannot change.' USING ERRCODE = 'PT422';
  END IF;
  RETURN NEW;  -- pending → cancelled, or editing reason / requested amount while pending
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_contingency_buckets_guard ON public.contingency_buckets;
CREATE TRIGGER trg_contingency_buckets_guard
  BEFORE INSERT OR UPDATE ON public.contingency_buckets
  FOR EACH ROW EXECUTE FUNCTION public.fn_guard_contingency_buckets();


-- ── E.7 variance_lines guard ────────────────────────────────────────────────
-- Variances are created / adjusted / cancelled only by procedures (money moves
-- with them). Approved and cancelled variances are frozen. Approval itself is
-- a status change the Phase 4 service performs directly.
CREATE OR REPLACE FUNCTION public.fn_guard_variance_lines()
RETURNS TRIGGER AS $$
BEGIN
  IF private.fin_write_authorized() THEN
    RETURN NEW;
  END IF;

  IF TG_OP = 'INSERT' THEN
    RAISE EXCEPTION 'Variances are created only through fn_create_variance (it moves contingency and writes the ledger).'
      USING ERRCODE = 'PT409';
  END IF;

  IF OLD.status IN ('approved', 'cancelled') THEN
    RAISE EXCEPTION 'Variance % is % and frozen. Create a new variance instead.', OLD.id, OLD.status
      USING ERRCODE = 'PT409';
  END IF;

  IF NEW.status = 'cancelled' THEN
    RAISE EXCEPTION 'Cancel a variance through fn_adjust_variance(…, 0, …) so its amount returns to contingency.'
      USING ERRCODE = 'PT409';
  END IF;

  IF NEW.project_id IS DISTINCT FROM OLD.project_id
     OR NEW.budget_line_id IS DISTINCT FROM OLD.budget_line_id
     OR NEW.parent_budget_line_id IS DISTINCT FROM OLD.parent_budget_line_id
     OR NEW.estimated_amount IS DISTINCT FROM OLD.estimated_amount
     OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
    RAISE EXCEPTION 'Variance identity / history columns cannot change (variance %).', OLD.id USING ERRCODE = 'PT422';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_variance_lines_guard ON public.variance_lines;
CREATE TRIGGER trg_variance_lines_guard
  BEFORE INSERT OR UPDATE ON public.variance_lines
  FOR EACH ROW EXECUTE FUNCTION public.fn_guard_variance_lines();


-- ── E.8 accounting periods: close only via procedure, never reopen ─────────
CREATE OR REPLACE FUNCTION public.fn_guard_accounting_periods()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status = 'closed' THEN
      RAISE EXCEPTION 'Closed month % cannot be deleted.', OLD.period_month USING ERRCODE = 'PT409';
    END IF;
    RETURN OLD;
  END IF;

  IF TG_OP = 'UPDATE' AND OLD.status = 'closed' THEN
    IF NEW.status <> 'closed' OR NEW.period_month <> OLD.period_month
       OR NEW.closed_by IS DISTINCT FROM OLD.closed_by OR NEW.closed_at IS DISTINCT FROM OLD.closed_at THEN
      RAISE EXCEPTION 'Month % is closed and can never be reopened or changed.', OLD.period_month USING ERRCODE = 'PT409';
    END IF;
    RETURN NEW;
  END IF;

  IF NEW.status = 'closed' AND NOT private.fin_write_authorized() THEN
    RAISE EXCEPTION 'Months are closed only through fn_close_accounting_month (finance / executive).'
      USING ERRCODE = 'PT409';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_accounting_periods_guard ON public.accounting_periods;
CREATE TRIGGER trg_accounting_periods_guard
  BEFORE INSERT OR UPDATE OR DELETE ON public.accounting_periods
  FOR EACH ROW EXECUTE FUNCTION public.fn_guard_accounting_periods();


-- ── E.9 cash_flow_entries: closed months are frozen ─────────────────────────
CREATE OR REPLACE FUNCTION public.fn_guard_cash_flow_closed_period()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') AND EXISTS (
       SELECT 1 FROM public.accounting_periods
        WHERE period_month = OLD.period_month AND status = 'closed') THEN
    RAISE EXCEPTION 'Cash-flow month % is closed; its entries cannot be changed.', OLD.period_month
      USING ERRCODE = 'PT409';
  END IF;

  IF TG_OP IN ('INSERT', 'UPDATE') AND EXISTS (
       SELECT 1 FROM public.accounting_periods
        WHERE period_month = NEW.period_month AND status = 'closed') THEN
    RAISE EXCEPTION 'Cash-flow month % is closed; new entries cannot be added to it.', NEW.period_month
      USING ERRCODE = 'PT409';
  END IF;

  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cash_flow_entries_closed_period ON public.cash_flow_entries;
CREATE TRIGGER trg_cash_flow_entries_closed_period
  BEFORE INSERT OR UPDATE OR DELETE ON public.cash_flow_entries
  FOR EACH ROW EXECUTE FUNCTION public.fn_guard_cash_flow_closed_period();


-- ── E.10 users.role → user_roles mirror ─────────────────────────────────────
-- Keeps the base role in user_roles in step with the existing admin screen
-- (which flips users.role admin ↔ project_manager). Never touches users.
CREATE OR REPLACE FUNCTION public.fn_sync_user_base_role()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.role IS NOT DISTINCT FROM OLD.role THEN
    RETURN NEW;
  END IF;

  IF TG_OP = 'UPDATE' THEN
    UPDATE public.user_roles
       SET revoked_at = NOW()
     WHERE user_id = NEW.id
       AND role = OLD.role
       AND revoked_at IS NULL;
  END IF;

  INSERT INTO public.user_roles (user_id, role, granted_by)
  VALUES (NEW.id, NEW.role, NEW.invited_by)
  ON CONFLICT (user_id, role) WHERE revoked_at IS NULL DO NOTHING;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_users_sync_base_role ON public.users;
CREATE TRIGGER trg_users_sync_base_role
  AFTER INSERT OR UPDATE OF role ON public.users
  FOR EACH ROW EXECUTE FUNCTION public.fn_sync_user_base_role();


-- ── E.11 Backfill: every existing user's base role into user_roles ──────────
--     Writes only to the new table. Re-run safe.
INSERT INTO public.user_roles (user_id, role, granted_by)
SELECT u.id, u.role, u.invited_by
  FROM public.users u
 WHERE u.role IN ('admin', 'project_manager')
ON CONFLICT (user_id, role) WHERE revoked_at IS NULL DO NOTHING;


-- ── E.12 Supabase Auth → profile trigger (extended, backward compatible) ────
-- Behaviour with today's invite metadata {full_name, role} is identical to
-- v3.9 (plus the base-role row, written by trg_users_sync_base_role).
-- New optional metadata keys:
--   roles        JSON array of extra roles, e.g. ["executive","finance"]
--   is_employee  boolean (false = external / temporary field manager)
-- Invalid extra roles are ignored, and a failure in the financial part is
-- logged as a WARNING — it can never block a signup / invite.
CREATE OR REPLACE FUNCTION public.fn_handle_new_auth_user()
RETURNS TRIGGER AS $$
DECLARE
  v_meta JSONB := COALESCE(NEW.raw_user_meta_data, '{}'::jsonb);
BEGIN
  INSERT INTO public.users (id, email, full_name, role)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(v_meta ->> 'full_name', split_part(NEW.email, '@', 1)),
    COALESCE(v_meta ->> 'role', 'project_manager')
  );

  BEGIN
    IF jsonb_typeof(v_meta -> 'is_employee') = 'boolean' THEN
      UPDATE public.users
         SET is_employee = (v_meta ->> 'is_employee')::boolean
       WHERE id = NEW.id;
    END IF;

    IF jsonb_typeof(v_meta -> 'roles') = 'array' THEN
      INSERT INTO public.user_roles (user_id, role)
      SELECT NEW.id, r.role_name
        FROM jsonb_array_elements_text(v_meta -> 'roles') AS r(role_name)
       WHERE r.role_name IN ('admin', 'project_manager', 'field_manager', 'executive', 'finance')
      ON CONFLICT (user_id, role) WHERE revoked_at IS NULL DO NOTHING;
    END IF;
  EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'fn_handle_new_auth_user: financial role metadata ignored for user % (%)', NEW.id, SQLERRM;
  END;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';


-- ============================================================================
-- SECTION 9.F: FINANCIAL STORED PROCEDURES (callable via PostgREST /rpc)
-- ============================================================================
-- Each runs in ONE implicit transaction (supabase-py has no client
-- transactions). Python validates first; these are the atomic writes, with
-- defence-in-depth checks. Errors: PT403 / PT404 / PT409 / PT422.
-- PRIVILEGES: REVOKE from PUBLIC, anon, authenticated; GRANT to service_role.
-- ----------------------------------------------------------------------------

-- F.0  Internal: move contingency + write the ledger row (private, not exposed)
CREATE OR REPLACE FUNCTION private.fin_move_contingency(
  p_project_id      UUID,
  p_amount          NUMERIC,          -- signed: + into contingency, − out
  p_movement_type   TEXT,
  p_actor_user_id   UUID,
  p_reason          TEXT DEFAULT NULL,
  p_source_line_id  UUID DEFAULT NULL,
  p_variance_id     UUID DEFAULT NULL,
  p_award_id        UUID DEFAULT NULL,
  p_bucket_id       UUID DEFAULT NULL
)
RETURNS public.contingency_ledger
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_line   public.budget_lines;
  v_entry  public.contingency_ledger;
BEGIN
  IF p_actor_user_id IS NULL THEN
    RAISE EXCEPTION 'An actor is required for every contingency movement' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_line
    FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Project % has no contingency line', p_project_id USING ERRCODE = 'PT409';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  UPDATE public.budget_lines
     SET budget_amount = budget_amount + p_amount,
         updated_by    = p_actor_user_id
   WHERE id = v_line.id;

  INSERT INTO public.contingency_ledger (
    project_id, contingency_line_id, contingency_bucket_id, movement_type,
    amount, balance_before, balance_after,
    source_budget_line_id, variance_line_id, award_id, actor_user_id, reason
  ) VALUES (
    p_project_id, v_line.id, p_bucket_id, p_movement_type,
    p_amount, v_line.budget_amount, v_line.budget_amount + p_amount,
    p_source_line_id, p_variance_id, p_award_id, p_actor_user_id, p_reason
  )
  RETURNING * INTO v_entry;

  RETURN v_entry;
END;
$$;

COMMENT ON FUNCTION private.fin_move_contingency(UUID, NUMERIC, TEXT, UUID, TEXT, UUID, UUID, UUID, UUID) IS
  'Internal: row-locks the project contingency line, applies a signed movement and writes the matching contingency_ledger row. Called only by the public financial procedures (private schema = not exposed via the Data API).';


-- F.0b Internal: load + check a project for a money movement
CREATE OR REPLACE FUNCTION private.fin_lock_project(
  p_project_id       UUID,
  p_require_baseline BOOLEAN,
  p_block_on_hold    BOOLEAN
)
RETURNS public.projects
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
BEGIN
  SELECT * INTO v_project FROM public.projects WHERE id = p_project_id FOR UPDATE;
  IF NOT FOUND OR v_project.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Project % not found', p_project_id USING ERRCODE = 'PT404';
  END IF;
  IF p_require_baseline AND v_project.budget_status <> 'baselined' THEN
    RAISE EXCEPTION 'Project % budget is not baselined yet (status %)', p_project_id, v_project.budget_status
      USING ERRCODE = 'PT409';
  END IF;
  IF p_block_on_hold AND v_project.status = 'on_hold' THEN
    RAISE EXCEPTION 'Project % is on hold; financial changes are blocked until the hold is lifted', p_project_id
      USING ERRCODE = 'PT409';
  END IF;
  RETURN v_project;
END;
$$;


-- F.1  fn_baseline_project_budget — freeze estimates, set approved total
CREATE OR REPLACE FUNCTION public.fn_baseline_project_budget(
  p_project_id UUID,
  p_actor      UUID
)
RETURNS SETOF public.projects
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project  public.projects;
  v_cont     public.budget_lines;
  v_total    NUMERIC;
  v_bucket   public.contingency_buckets;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);

  IF v_project.budget_status = 'baselined' THEN
    RAISE EXCEPTION 'Project % budget is already baselined', p_project_id USING ERRCODE = 'PT409';
  END IF;
  IF v_project.budget_status <> 'draft' THEN
    RAISE EXCEPTION 'Project % has no draft budget to baseline', p_project_id USING ERRCODE = 'PT409';
  END IF;

  SELECT * INTO v_cont
    FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Project % needs a contingency line before it can be baselined', p_project_id
      USING ERRCODE = 'PT409';
  END IF;
  IF v_cont.budget_amount < 0 THEN
    RAISE EXCEPTION 'Contingency cannot start negative (%)', v_cont.budget_amount USING ERRCODE = 'PT422';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  -- A21: freeze the original estimate of every live line (caller may preset it).
  UPDATE public.budget_lines
     SET original_estimate = COALESCE(original_estimate, budget_amount),
         updated_by        = p_actor
   WHERE project_id = p_project_id
     AND deleted_at IS NULL
     AND line_type <> 'contingency';

  UPDATE public.budget_lines
     SET original_estimate = budget_amount
   WHERE id = v_cont.id;

  SELECT COALESCE(SUM(budget_amount), 0) INTO v_total
    FROM public.budget_lines
   WHERE project_id = p_project_id AND deleted_at IS NULL;

  INSERT INTO public.contingency_buckets (
    project_id, contingency_line_id, bucket_kind, requested_amount, approved_amount,
    status, reason, requested_by, decided_by, decided_at
  ) VALUES (
    p_project_id, v_cont.id, 'initial', v_cont.budget_amount, v_cont.budget_amount,
    'approved', 'Initial contingency at budget baseline', p_actor, p_actor, NOW()
  )
  RETURNING * INTO v_bucket;

  INSERT INTO public.contingency_ledger (
    project_id, contingency_line_id, contingency_bucket_id, movement_type,
    amount, balance_before, balance_after, actor_user_id, reason
  ) VALUES (
    p_project_id, v_cont.id, v_bucket.id, 'initial_funding',
    v_cont.budget_amount, 0, v_cont.budget_amount, p_actor, 'Initial contingency at budget baseline'
  );

  UPDATE public.projects
     SET budget_status         = 'baselined',
         approved_budget_total = v_total,
         budget_baselined_at   = NOW(),
         budget_baselined_by   = p_actor
   WHERE id = p_project_id
   RETURNING * INTO v_project;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_project;
END;
$$;

COMMENT ON FUNCTION public.fn_baseline_project_budget(UUID, UUID) IS
  'Draft → baselined: freezes every line''s original_estimate (A21), sets projects.approved_budget_total = SUM(live lines), records the initial contingency bucket and the initial_funding ledger row. From then on the flat-budget rule applies.';


-- F.2  fn_apply_bid_to_line — award amount → line, difference ↔ contingency
CREATE OR REPLACE FUNCTION public.fn_apply_bid_to_line(
  p_budget_line_id UUID,
  p_award_id       UUID,
  p_amount         NUMERIC,
  p_actor          UUID
)
RETURNS SETOF public.budget_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_line     public.budget_lines;
  v_award    public.awards;
  v_project  public.projects;
  v_delta    NUMERIC;
  v_result   public.budget_lines;
BEGIN
  IF p_amount IS NULL OR p_amount < 0 THEN
    RAISE EXCEPTION 'Bid amount must be zero or more (got %)', p_amount USING ERRCODE = 'PT422';
  END IF;
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_budget_line_id;
  IF NOT FOUND OR v_line.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Budget line % not found', p_budget_line_id USING ERRCODE = 'PT404';
  END IF;

  -- Lock order everywhere: project → lines (avoids deadlocks).
  v_project := private.fin_lock_project(v_line.project_id, FALSE, TRUE);
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_budget_line_id FOR UPDATE;

  IF v_line.line_type <> 'bid_activity' THEN
    RAISE EXCEPTION 'Bids apply only to bid_activity lines (line % is %)', v_line.id, v_line.line_type
      USING ERRCODE = 'PT422';
  END IF;
  IF v_line.is_locked THEN
    RAISE EXCEPTION 'Budget line % is locked (contract executed)', v_line.id USING ERRCODE = 'PT409';
  END IF;

  SELECT * INTO v_award FROM public.awards WHERE id = p_award_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Award % not found', p_award_id USING ERRCODE = 'PT404';
  END IF;
  IF v_award.task_id IS DISTINCT FROM v_line.task_id THEN
    RAISE EXCEPTION 'Award % is for task %, not this line''s task %', p_award_id, v_award.task_id, v_line.task_id
      USING ERRCODE = 'PT422';
  END IF;
  IF v_award.status IN ('declined_by_vendor', 'cancelled') THEN
    RAISE EXCEPTION 'Award % is % and cannot be applied', p_award_id, v_award.status USING ERRCODE = 'PT409';
  END IF;
  IF v_line.award_id IS NOT NULL AND v_line.award_id <> p_award_id THEN
    RAISE EXCEPTION 'Line % already carries award %; reverse it first', v_line.id, v_line.award_id
      USING ERRCODE = 'PT409';
  END IF;

  -- Idempotent retry: same award, same amount → nothing to do.
  IF v_line.award_id = p_award_id AND v_line.budget_amount = p_amount AND v_line.committed_amount = p_amount THEN
    RETURN NEXT v_line;
    RETURN;
  END IF;

  v_delta := p_amount - v_line.budget_amount;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  UPDATE public.budget_lines
     SET pre_award_budget_amount = CASE WHEN award_id IS NULL THEN budget_amount ELSE pre_award_budget_amount END,
         budget_amount           = p_amount,
         committed_amount        = p_amount,
         award_id                = p_award_id,
         updated_by              = p_actor
   WHERE id = v_line.id
   RETURNING * INTO v_result;

  -- Draft budgets have no ledger yet: the line simply takes the bid.
  IF v_project.budget_status = 'baselined' AND v_delta <> 0 THEN
    PERFORM private.fin_move_contingency(
      v_line.project_id, -v_delta,
      CASE WHEN v_delta > 0 THEN 'bid_overrun' ELSE 'bid_savings' END,
      p_actor,
      format('Bid applied to "%s": %s → %s', v_line.name, v_line.budget_amount, p_amount),
      v_line.id, NULL, p_award_id, NULL);
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_result;
END;
$$;

COMMENT ON FUNCTION public.fn_apply_bid_to_line(UUID, UUID, NUMERIC, UUID) IS
  'A2/A3: sets the bid line''s budget and committed amount to the award amount; the difference moves out of (overrun) or into (savings) contingency with a ledger row. Idempotent for the same award + amount. Blocked on locked lines and on-hold projects.';


-- F.3  fn_reverse_bid_on_line — award declined / voided / cancelled
CREATE OR REPLACE FUNCTION public.fn_reverse_bid_on_line(
  p_budget_line_id UUID,
  p_award_id       UUID,
  p_actor          UUID,
  p_reason         TEXT DEFAULT NULL
)
RETURNS SETOF public.budget_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_line     public.budget_lines;
  v_project  public.projects;
  v_restore  NUMERIC;
  v_delta    NUMERIC;
  v_result   public.budget_lines;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_budget_line_id;
  IF NOT FOUND OR v_line.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Budget line % not found', p_budget_line_id USING ERRCODE = 'PT404';
  END IF;

  -- Reversals are allowed even when the project is on hold (a decline happens regardless).
  v_project := private.fin_lock_project(v_line.project_id, FALSE, FALSE);
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_budget_line_id FOR UPDATE;

  IF v_line.award_id IS DISTINCT FROM p_award_id THEN
    RAISE EXCEPTION 'Award % is not applied to line % — nothing to reverse', p_award_id, p_budget_line_id
      USING ERRCODE = 'PT409';
  END IF;

  v_restore := COALESCE(v_line.pre_award_budget_amount, v_line.budget_amount);
  v_delta   := v_restore - v_line.budget_amount;   -- change on the line

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  UPDATE public.budget_lines
     SET budget_amount           = v_restore,
         committed_amount        = 0,
         award_id                = NULL,
         contract_id             = NULL,
         pre_award_budget_amount = NULL,
         is_locked               = FALSE,
         locked_at               = NULL,
         locked_by               = NULL,
         lock_reason             = NULL,
         updated_by              = p_actor
   WHERE id = v_line.id
   RETURNING * INTO v_result;

  IF v_project.budget_status = 'baselined' AND v_delta <> 0 THEN
    PERFORM private.fin_move_contingency(
      v_line.project_id, -v_delta, 'bid_reversal', p_actor,
      COALESCE(p_reason, format('Award reversed on "%s": %s → %s', v_line.name, v_line.budget_amount, v_restore)),
      v_line.id, NULL, p_award_id, NULL);
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_result;
END;
$$;

COMMENT ON FUNCTION public.fn_reverse_bid_on_line(UUID, UUID, UUID, TEXT) IS
  'Undoes fn_apply_bid_to_line when the vendor declines or the award / envelope is cancelled or voided: restores the pre-award amount, clears committed / award / lock, and moves the difference back with a bid_reversal ledger row.';


-- F.4  fn_lock_budget_line — contract executed
CREATE OR REPLACE FUNCTION public.fn_lock_budget_line(
  p_budget_line_id UUID,
  p_contract_id    UUID,
  p_actor          UUID
)
RETURNS SETOF public.budget_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_line      public.budget_lines;
  v_contract  public.contracts;
  v_start     DATE;
  v_end       DATE;
  v_result    public.budget_lines;
BEGIN
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_budget_line_id FOR UPDATE;
  IF NOT FOUND OR v_line.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Budget line % not found', p_budget_line_id USING ERRCODE = 'PT404';
  END IF;

  SELECT * INTO v_contract FROM public.contracts WHERE id = p_contract_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Contract % not found', p_contract_id USING ERRCODE = 'PT404';
  END IF;
  IF v_contract.task_id IS DISTINCT FROM v_line.task_id THEN
    RAISE EXCEPTION 'Contract % is for task %, not this line''s task %', p_contract_id, v_contract.task_id, v_line.task_id
      USING ERRCODE = 'PT422';
  END IF;
  IF v_line.award_id IS NOT NULL AND v_line.award_id <> v_contract.award_id THEN
    RAISE EXCEPTION 'Line % carries award %, but contract % belongs to award %',
      v_line.id, v_line.award_id, p_contract_id, v_contract.award_id USING ERRCODE = 'PT409';
  END IF;

  IF v_line.is_locked AND v_line.contract_id = p_contract_id THEN
    RETURN NEXT v_line;   -- idempotent (webhook retries)
    RETURN;
  END IF;

  v_start := COALESCE(v_line.anticipated_start_date, v_contract.start_date);
  v_end   := COALESCE(v_line.anticipated_end_date,   v_contract.end_date);
  IF v_start IS NOT NULL AND v_end IS NOT NULL AND v_end < v_start THEN
    v_start := v_line.anticipated_start_date;
    v_end   := v_line.anticipated_end_date;
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  UPDATE public.budget_lines
     SET is_locked              = TRUE,
         locked_at              = NOW(),
         locked_by              = p_actor,
         lock_reason            = 'Contract executed',
         contract_id            = p_contract_id,
         anticipated_start_date = v_start,
         anticipated_end_date   = v_end,
         updated_by             = p_actor
   WHERE id = v_line.id
   RETURNING * INTO v_result;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_result;
END;
$$;

COMMENT ON FUNCTION public.fn_lock_budget_line(UUID, UUID, UUID) IS
  'Locks a bid line when its contract is executed (DocuSign completed) and defaults the line dates from the contract start / end when they are empty. Idempotent.';


-- F.5  fn_create_variance — variance line + contingency deduction (A5)
CREATE OR REPLACE FUNCTION public.fn_create_variance(
  p_parent_line_id UUID,
  p_description    TEXT,
  p_amount         NUMERIC,
  p_actor          UUID,
  p_trade_id       UUID DEFAULT NULL,
  p_vendor_id      UUID DEFAULT NULL,
  p_start_date     DATE DEFAULT NULL,
  p_end_date       DATE DEFAULT NULL
)
RETURNS SETOF public.variance_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_parent    public.budget_lines;
  v_line      public.budget_lines;
  v_variance  public.variance_lines;
BEGIN
  IF p_amount IS NULL OR p_amount <= 0 THEN
    RAISE EXCEPTION 'Variance amount must be greater than zero (got %)', p_amount USING ERRCODE = 'PT422';
  END IF;
  IF btrim(COALESCE(p_description, '')) = '' THEN
    RAISE EXCEPTION 'A variance needs a description' USING ERRCODE = 'PT422';
  END IF;
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_parent FROM public.budget_lines WHERE id = p_parent_line_id;
  IF NOT FOUND OR v_parent.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Budget line % not found', p_parent_line_id USING ERRCODE = 'PT404';
  END IF;
  IF v_parent.line_type IN ('contingency', 'variance', 'land') THEN
    RAISE EXCEPTION 'A variance cannot be created under a % line', v_parent.line_type USING ERRCODE = 'PT422';
  END IF;

  PERFORM private.fin_lock_project(v_parent.project_id, TRUE, TRUE);

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  INSERT INTO public.budget_lines (
    project_id, parent_line_id, line_type, name, description, section_name, sort_order,
    budget_amount, anticipated_start_date, anticipated_end_date,
    payment_terms_days, cash_bucket, created_by, updated_by
  ) VALUES (
    v_parent.project_id, v_parent.id, 'variance',
    left('Variance: ' || btrim(p_description), 255), p_description,
    v_parent.section_name, v_parent.sort_order,
    p_amount,
    COALESCE(p_start_date, v_parent.anticipated_start_date),
    COALESCE(p_end_date,   v_parent.anticipated_end_date),
    v_parent.payment_terms_days, v_parent.cash_bucket, p_actor, p_actor
  )
  RETURNING * INTO v_line;

  INSERT INTO public.variance_lines (
    project_id, budget_line_id, parent_budget_line_id, trade_id, vendor_id,
    description, estimated_amount, status, created_by
  ) VALUES (
    v_parent.project_id, v_line.id, v_parent.id, p_trade_id, p_vendor_id,
    btrim(p_description), p_amount, 'pending_approval', p_actor
  )
  RETURNING * INTO v_variance;

  PERFORM private.fin_move_contingency(
    v_parent.project_id, -p_amount, 'variance_created', p_actor,
    format('Variance under "%s": %s', v_parent.name, btrim(p_description)),
    v_line.id, v_variance.id, NULL, NULL);

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_variance;
END;
$$;

COMMENT ON FUNCTION public.fn_create_variance(UUID, TEXT, NUMERIC, UUID, UUID, UUID, DATE, DATE) IS
  'A5: creates a variance (own budget line of type variance + variance_lines row, status pending_approval) under an activity line and deducts the same amount from contingency with a ledger row. Total budget stays flat.';


-- F.6  fn_adjust_variance — edit before approval, or cancel (A6)
CREATE OR REPLACE FUNCTION public.fn_adjust_variance(
  p_variance_id UUID,
  p_new_amount  NUMERIC,
  p_actor       UUID,
  p_reason      TEXT DEFAULT NULL
)
RETURNS SETOF public.variance_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_variance  public.variance_lines;
  v_line      public.budget_lines;
  v_delta     NUMERIC;
BEGIN
  IF p_new_amount IS NULL OR p_new_amount < 0 THEN
    RAISE EXCEPTION 'New variance amount must be zero (cancel) or more (got %)', p_new_amount USING ERRCODE = 'PT422';
  END IF;
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id;
  IF NOT FOUND OR v_variance.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Variance % not found', p_variance_id USING ERRCODE = 'PT404';
  END IF;

  -- Adjustments may be needed on a held project to free contingency, so no hold block.
  PERFORM private.fin_lock_project(v_variance.project_id, TRUE, FALSE);
  SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id FOR UPDATE;
  SELECT * INTO v_line     FROM public.budget_lines   WHERE id = v_variance.budget_line_id FOR UPDATE;

  IF v_variance.status NOT IN ('draft', 'pending_approval', 'rejected') THEN
    RAISE EXCEPTION 'Variance % is % and can no longer be changed; create a new variance', p_variance_id, v_variance.status
      USING ERRCODE = 'PT409';
  END IF;

  v_delta := p_new_amount - v_line.budget_amount;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  IF p_new_amount = 0 THEN
    -- Cancel: return the full amount, retire the line.
    UPDATE public.budget_lines
       SET budget_amount = 0, deleted_at = NOW(), updated_by = p_actor
     WHERE id = v_line.id;

    UPDATE public.variance_lines
       SET status = 'cancelled'
     WHERE id = p_variance_id
     RETURNING * INTO v_variance;

    IF v_delta <> 0 THEN
      PERFORM private.fin_move_contingency(
        v_variance.project_id, -v_delta, 'variance_cancelled', p_actor,
        COALESCE(p_reason, 'Variance cancelled'), v_line.id, p_variance_id, NULL, NULL);
    END IF;
  ELSIF v_delta <> 0 THEN
    UPDATE public.budget_lines
       SET budget_amount = p_new_amount, updated_by = p_actor
     WHERE id = v_line.id;

    PERFORM private.fin_move_contingency(
      v_variance.project_id, -v_delta, 'variance_adjusted', p_actor,
      COALESCE(p_reason, format('Variance adjusted %s → %s', v_line.budget_amount, p_new_amount)),
      v_line.id, p_variance_id, NULL, NULL);

    SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id;
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_variance;
END;
$$;

COMMENT ON FUNCTION public.fn_adjust_variance(UUID, NUMERIC, UUID, TEXT) IS
  'A6: changes a not-yet-approved variance amount; the difference flows back to (or out of) contingency with a ledger row (e.g. $5,000 estimate → $3,000 actual returns $2,000). p_new_amount = 0 cancels the variance and returns everything.';


-- F.7  fn_request_contingency_top_up — convenience writer for a request
CREATE OR REPLACE FUNCTION public.fn_request_contingency_top_up(
  p_project_id UUID,
  p_amount     NUMERIC,
  p_reason     TEXT,
  p_actor      UUID
)
RETURNS SETOF public.contingency_buckets
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_cont    public.budget_lines;
  v_bucket  public.contingency_buckets;
BEGIN
  IF p_amount IS NULL OR p_amount <= 0 THEN
    RAISE EXCEPTION 'Top-up amount must be greater than zero' USING ERRCODE = 'PT422';
  END IF;
  IF btrim(COALESCE(p_reason, '')) = '' THEN
    RAISE EXCEPTION 'A top-up request needs a reason' USING ERRCODE = 'PT422';
  END IF;
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  PERFORM private.fin_lock_project(p_project_id, TRUE, FALSE);

  SELECT * INTO v_cont FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL;

  INSERT INTO public.contingency_buckets (
    project_id, contingency_line_id, bucket_kind, requested_amount, status, reason, requested_by
  ) VALUES (
    p_project_id, v_cont.id, 'top_up', p_amount, 'pending', btrim(p_reason), p_actor
  )
  RETURNING * INTO v_bucket;

  RETURN NEXT v_bucket;
END;
$$;

COMMENT ON FUNCTION public.fn_request_contingency_top_up(UUID, NUMERIC, TEXT, UUID) IS
  'Records a pending contingency top-up request (amount + reason). Approval is executive-only via fn_approve_contingency_top_up.';


-- F.8  fn_approve_contingency_top_up — executive decision (A13)
CREATE OR REPLACE FUNCTION public.fn_approve_contingency_top_up(
  p_bucket_id        UUID,
  p_approver         UUID,
  p_approve          BOOLEAN,
  p_approved_amount  NUMERIC DEFAULT NULL,
  p_note             TEXT DEFAULT NULL
)
RETURNS SETOF public.contingency_buckets
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_bucket  public.contingency_buckets;
  v_amount  NUMERIC;
BEGIN
  IF p_approver IS NULL OR p_approve IS NULL THEN
    RAISE EXCEPTION 'p_approver and p_approve are required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_bucket FROM public.contingency_buckets WHERE id = p_bucket_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Contingency bucket % not found', p_bucket_id USING ERRCODE = 'PT404';
  END IF;

  IF NOT private.user_has_role(p_approver, 'executive') THEN
    RAISE EXCEPTION 'Only an executive can approve or reject a contingency top-up' USING ERRCODE = 'PT403';
  END IF;

  -- Lock order: project → bucket → lines.
  PERFORM private.fin_lock_project(v_bucket.project_id, TRUE, FALSE);
  SELECT * INTO v_bucket FROM public.contingency_buckets WHERE id = p_bucket_id FOR UPDATE;

  IF v_bucket.bucket_kind <> 'top_up' THEN
    RAISE EXCEPTION 'Bucket % is not a top-up request', p_bucket_id USING ERRCODE = 'PT422';
  END IF;
  IF v_bucket.status <> 'pending' THEN
    RAISE EXCEPTION 'Top-up request % is already %', p_bucket_id, v_bucket.status USING ERRCODE = 'PT409';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  IF NOT p_approve THEN
    UPDATE public.contingency_buckets
       SET status = 'rejected', decided_by = p_approver, decided_at = NOW(), decision_note = p_note
     WHERE id = p_bucket_id
     RETURNING * INTO v_bucket;
  ELSE
    v_amount := COALESCE(p_approved_amount, v_bucket.requested_amount);
    IF v_amount <= 0 THEN
      RAISE EXCEPTION 'Approved amount must be greater than zero' USING ERRCODE = 'PT422';
    END IF;

    -- The ONLY path (besides baseline) that changes the approved total.
    UPDATE public.projects
       SET approved_budget_total = approved_budget_total + v_amount
     WHERE id = v_bucket.project_id;

    PERFORM private.fin_move_contingency(
      v_bucket.project_id, v_amount, 'top_up', p_approver,
      COALESCE(p_note, v_bucket.reason), NULL, NULL, NULL, p_bucket_id);

    UPDATE public.contingency_buckets
       SET status = 'approved', approved_amount = v_amount,
           decided_by = p_approver, decided_at = NOW(), decision_note = p_note
     WHERE id = p_bucket_id
     RETURNING * INTO v_bucket;
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_bucket;
END;
$$;

COMMENT ON FUNCTION public.fn_approve_contingency_top_up(UUID, UUID, BOOLEAN, NUMERIC, TEXT) IS
  'A13: executive-only (PT403 otherwise). Approve: contingency line + amount, projects.approved_budget_total + amount (the only way the total grows after baseline), top_up ledger row tied to the bucket. Reject: decision recorded, no money moves.';


-- F.9  fn_close_accounting_month — finance / executive close
CREATE OR REPLACE FUNCTION public.fn_close_accounting_month(
  p_month DATE,
  p_actor UUID,
  p_notes TEXT DEFAULT NULL
)
RETURNS SETOF public.accounting_periods
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_period  public.accounting_periods;
  v_current DATE := date_trunc('month', (NOW() AT TIME ZONE 'America/Chicago'))::date;
BEGIN
  IF p_month IS NULL OR EXTRACT(DAY FROM p_month) <> 1 THEN
    RAISE EXCEPTION 'p_month must be the first day of a month (got %)', p_month USING ERRCODE = 'PT422';
  END IF;
  IF p_month > v_current THEN
    RAISE EXCEPTION 'Cannot close a future month (%)', p_month USING ERRCODE = 'PT422';
  END IF;
  IF p_actor IS NULL
     OR NOT (private.user_has_role(p_actor, 'finance') OR private.user_has_role(p_actor, 'executive')) THEN
    RAISE EXCEPTION 'Only finance or an executive can close a month' USING ERRCODE = 'PT403';
  END IF;

  SELECT * INTO v_period FROM public.accounting_periods WHERE period_month = p_month FOR UPDATE;
  IF FOUND AND v_period.status = 'closed' THEN
    RAISE EXCEPTION 'Month % is already closed', p_month USING ERRCODE = 'PT409';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  INSERT INTO public.accounting_periods (period_month, status, closed_by, closed_at, notes)
  VALUES (p_month, 'closed', p_actor, NOW(), p_notes)
  ON CONFLICT (period_month) DO UPDATE
     SET status = 'closed', closed_by = EXCLUDED.closed_by, closed_at = EXCLUDED.closed_at,
         notes = COALESCE(EXCLUDED.notes, public.accounting_periods.notes)
  RETURNING * INTO v_period;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_period;
END;
$$;

COMMENT ON FUNCTION public.fn_close_accounting_month(DATE, UUID, TEXT) IS
  'Closes a company-wide accounting month (finance or executive role, PT403 otherwise). From then on cash_flow_entries in that month are frozen and the month can never be reopened.';


-- F.10 Privileges: write RPCs for service_role only; internals not exposed.
DO $$
DECLARE
  f TEXT;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'public.fn_baseline_project_budget(uuid, uuid)',
    'public.fn_apply_bid_to_line(uuid, uuid, numeric, uuid)',
    'public.fn_reverse_bid_on_line(uuid, uuid, uuid, text)',
    'public.fn_lock_budget_line(uuid, uuid, uuid)',
    'public.fn_create_variance(uuid, text, numeric, uuid, uuid, uuid, date, date)',
    'public.fn_adjust_variance(uuid, numeric, uuid, text)',
    'public.fn_request_contingency_top_up(uuid, numeric, text, uuid)',
    'public.fn_approve_contingency_top_up(uuid, uuid, boolean, numeric, text)',
    'public.fn_close_accounting_month(date, uuid, text)',
    'private.fin_move_contingency(uuid, numeric, text, uuid, text, uuid, uuid, uuid, uuid)',
    'private.fin_lock_project(uuid, boolean, boolean)'
  ] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role', f);
  END LOOP;
END $$;

-- Trigger functions are not callable as RPCs, but keep them closed anyway.
REVOKE ALL ON FUNCTION public.fn_block_contingency_ledger_mutation() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_guard_budget_lines()               FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_check_flat_budget_total()          FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_guard_project_budget_total()       FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_guard_contingency_buckets()        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_guard_variance_lines()             FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_guard_accounting_periods()         FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_guard_cash_flow_closed_period()    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_sync_user_base_role()              FROM PUBLIC, anon, authenticated;

-- Private helpers: service_role (procedures) and authenticated (RLS) need them.
GRANT USAGE ON SCHEMA private TO service_role, authenticated;
REVOKE ALL ON FUNCTION private.fin_write_authorized()           FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.user_has_role(UUID, TEXT)        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.has_any_role(TEXT[])             FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.fin_write_authorized()        TO service_role, authenticated;
GRANT EXECUTE ON FUNCTION private.user_has_role(UUID, TEXT)     TO service_role;
GRANT EXECUTE ON FUNCTION private.has_any_role(TEXT[])          TO authenticated, service_role;


-- ============================================================================
-- SECTION 9.H: DEFAULT FINANCIAL SETTINGS (never overwrites existing values)
-- ============================================================================

INSERT INTO public.financial_settings (setting_key, value, description) VALUES
  ('default_contingency_percent',       '15'::jsonb,   'Program contingency % applied to the contingency base (total budget − land − contingency). Per-project override: projects.contingency_percent.'),
  ('contingency_min_percent',           '15'::jsonb,   'Lower bound of the program contingency range agreed at discovery.'),
  ('contingency_max_percent',           '20'::jsonb,   'Upper bound of the program contingency range agreed at discovery.'),
  ('bidding_target_contingency_percent','10'::jsonb,   'Target contingency left after bidding (checkpoint A4). Far below → executive escalation.'),
  ('bidding_escalation_percent',        '5'::jsonb,    'Contingency % after bidding at or below which the checkpoint escalates to executives. Open question — confirm with client.'),
  ('default_payment_terms_days',        '30'::jsonb,   'Default payment terms (days) for budget lines and contracts.'),
  ('default_field_approval_limit',      '5000'::jsonb, 'Amount a field manager may approve alone when users.approval_limit is NULL.'),
  ('executive_approval_threshold',      'null'::jsonb, 'Payments above this amount also need an executive approval. NULL = not configured yet (open question).'),
  ('contingency_near_zero_percent',     '5'::jsonb,    'Contingency left % at or below which the urgent near-zero alert fires. Open question — confirm with client.'),
  ('alert_recipients',                  '{"warning": [], "urgent": [], "critical": []}'::jsonb, 'User ids (or emails) per alert severity, in addition to the project manager / field manager.'),
  ('land_team_emails',                  '[]'::jsonb,   'Land team addresses copied on payment approvals.'),
  ('finance_emails',                    '[]'::jsonb,   'Finance addresses receiving hand-offs and the daily summary.'),
  ('sales_emails',                      '[]'::jsonb,   'Sales addresses notified of approved contingency top-ups.'),
  ('po_number_format',                  '"PO-{YYYY}-{SEQ:05}"'::jsonb, 'Format for internal invoice / PO numbers. Open question — confirm with client.'),
  ('environment',                       '"unset"'::jsonb, 'Set to "development" on non-production databases. The dev seed script refuses to run unless it is "development".')
ON CONFLICT (setting_key) DO NOTHING;


-- ============================================================================
-- SECTION 9.I: SCHEMA VERSION MARKER
-- ============================================================================
-- Always updated (not DO NOTHING) so it reflects the last migration applied.

INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.0.0 (20261111_financial_phase1)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;



-- ############################################################################
--
--  SECTION 10: FINANCIAL AUTOMATION — PHASE 2 BUDGET STRUCTURE (v4.1, Nov 18 2026)
--
--  Source of truth for EXISTING databases: the idempotent migration
--    database/migrations/20261118_financial_phase2/001_budget_structure.sql
--  Same DDL minus BEGIN/COMMIT. Requires Section 9. Re-runnable.
--
-- ############################################################################

-- ============================================================================
-- SECTION 10.A: DEFAULT STANDARD TEMPLATE
-- ============================================================================
-- Activity rows (bid_activity / internal_tm) are ORDERING SLOTS: activity lines
-- only ever exist as tasks; a slot decides where a matching task sits and under
-- which heading. Admins replace this layout in Settings → Budget Template.

DO $$
DECLARE
  v_tmpl UUID;
BEGIN
  IF EXISTS (SELECT 1 FROM public.budget_templates
              WHERE is_default AND is_active AND deleted_at IS NULL) THEN
    RETURN;
  END IF;

  INSERT INTO public.budget_templates (name, description, is_default)
  VALUES ('Standard development budget',
          'Starting layout from land acquisition down to escrows and property taxes. Edit in Settings → Budget Template.',
          TRUE)
  RETURNING id INTO v_tmpl;

  INSERT INTO public.budget_template_lines
    (budget_template_id, line_type, line_subtype, name, section_name, sort_order, default_cash_bucket)
  VALUES
    (v_tmpl, 'land',         'land_purchase',       'Land purchase',                   'Land',        10, 'land'),
    (v_tmpl, 'land',         'earnest_money',       'Earnest money',                   'Land',        20, 'land'),
    (v_tmpl, 'land',         'due_diligence',       'Due diligence',                   'Land',        30, 'land'),
    (v_tmpl, 'soft_cost',    'engineering',         'Engineering',                     'Soft costs',  40, 'land'),
    (v_tmpl, 'permit',       NULL,                  'Permits',                         'Soft costs',  50, 'land'),
    (v_tmpl, 'impact_fee',   NULL,                  'Impact fees',                     'Soft costs',  60, 'land'),
    (v_tmpl, 'soft_cost',    'other',               'Other soft costs',                'Soft costs',  70, 'land'),
    (v_tmpl, 'bid_activity', NULL,                  'Clearing',                        'Site work',   80, 'land'),
    (v_tmpl, 'bid_activity', NULL,                  'Grading',                         'Site work',   90, 'land'),
    (v_tmpl, 'bid_activity', NULL,                  'Sanitary sewer',                  'Utilities',  100, 'land'),
    (v_tmpl, 'bid_activity', NULL,                  'Water + storm',                   'Utilities',  110, 'land'),
    (v_tmpl, 'bid_activity', NULL,                  'Paving',                          'Roads',      120, 'land'),
    (v_tmpl, 'internal_tm',  NULL,                  'Attorney',                        'Internal',   130, 'land'),
    (v_tmpl, 'contingency',  NULL,                  'Contingency',                     'Contingency',140, 'land'),
    (v_tmpl, 'long_tail',    'escrow_bond_premium', 'Escrow bond / insurance premium', 'Long-tail',  150, 'land'),
    (v_tmpl, 'long_tail',    'escrow_repairs',      'Escrow repairs to city standard', 'Long-tail',  160, 'land'),
    (v_tmpl, 'long_tail',    'property_tax',        'Property tax',                    'Long-tail',  170, 'land');
END $$;


-- ============================================================================
-- SECTION 10.B: INTERNAL HELPERS
-- ============================================================================

-- B.1 Map a task bid_type to its budget line type.
CREATE OR REPLACE FUNCTION private.fin_line_type_for_bid_type(p_bid_type TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
SET search_path = ''
AS $$
  SELECT CASE WHEN p_bid_type = 'internal' THEN 'internal_tm' ELSE 'bid_activity' END;
$$;

-- B.2 Invoiced total on a line. SECURITY DEFINER so the totals views are the
--     same for every viewer even though internal_invoices rows are
--     finance-restricted (only the SUM leaves this function).
CREATE OR REPLACE FUNCTION private.fin_line_invoiced(p_line_id UUID)
RETURNS NUMERIC
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT COALESCE(SUM(amount), 0)
    FROM public.internal_invoices
   WHERE budget_line_id = p_line_id
     AND deleted_at IS NULL
     AND status NOT IN ('received', 'rejected', 'cancelled');
$$;

COMMENT ON FUNCTION private.fin_line_invoiced(UUID) IS
  'Sum of categorised (non-rejected, non-cancelled) internal invoices on a budget line. SECURITY DEFINER: exposes only the total, so budget totals are identical for every role.';

-- B.3 Is a line free of money and commitments? (removal / type change rules)
CREATE OR REPLACE FUNCTION private.fin_line_is_empty(p_line_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT l.budget_amount = 0
     AND l.committed_amount = 0
     AND l.award_id IS NULL
     AND NOT EXISTS (SELECT 1 FROM public.internal_invoices i
                      WHERE i.budget_line_id = l.id AND i.deleted_at IS NULL
                        AND i.status NOT IN ('rejected', 'cancelled'))
     AND NOT EXISTS (SELECT 1 FROM public.payment_approvals pa
                      WHERE pa.budget_line_id = l.id AND pa.status NOT IN ('rejected', 'cancelled'))
     AND NOT EXISTS (SELECT 1 FROM public.budget_lines c
                      WHERE c.parent_line_id = l.id AND c.deleted_at IS NULL)
    FROM public.budget_lines l
   WHERE l.id = p_line_id;
$$;

-- B.4 Next sort position for a new activity line (after the last line of the
--     same type, else before contingency, else at the end).
CREATE OR REPLACE FUNCTION private.fin_next_activity_position(p_project_id UUID, p_line_type TEXT)
RETURNS TABLE (sort_order INTEGER, section_name VARCHAR)
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  WITH same AS (
    SELECT l.sort_order, l.section_name FROM public.budget_lines l
     WHERE l.project_id = p_project_id AND l.deleted_at IS NULL AND l.line_type = p_line_type
     ORDER BY l.sort_order DESC LIMIT 1
  ), cont AS (
    SELECT l.sort_order FROM public.budget_lines l
     WHERE l.project_id = p_project_id AND l.deleted_at IS NULL AND l.line_type = 'contingency'
  ), mx AS (
    SELECT COALESCE(MAX(l.sort_order), 0) AS m FROM public.budget_lines l
     WHERE l.project_id = p_project_id AND l.deleted_at IS NULL
  )
  SELECT COALESCE((SELECT s.sort_order + 1 FROM same s),
                  (SELECT c.sort_order - 1 FROM cont c),
                  (SELECT m + 10 FROM mx)),
         COALESCE((SELECT s.section_name FROM same s),
                  CASE WHEN p_line_type = 'internal_tm' THEN 'Internal' ELSE 'Site work' END)::VARCHAR;
$$;


-- ============================================================================
-- SECTION 10.C: PROCEDURES
-- ============================================================================

-- C.1 fn_create_project_budget ─ template + every task → draft budget
CREATE OR REPLACE FUNCTION public.fn_create_project_budget(
  p_project_id          UUID,
  p_actor               UUID,
  p_template_id         UUID DEFAULT NULL,
  p_contingency_percent NUMERIC DEFAULT NULL
)
RETURNS SETOF public.budget_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project   public.projects;
  v_template  UUID;
  v_pct       NUMERIC;
  v_rank      INTEGER := 0;
  v_tl        RECORD;
  v_task      RECORD;
  v_slot      RECORD;
  v_base      NUMERIC;
  v_cont_id   UUID;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;
  IF p_contingency_percent IS NOT NULL AND (p_contingency_percent < 0 OR p_contingency_percent > 100) THEN
    RAISE EXCEPTION 'Contingency %% must be between 0 and 100 (got %)', p_contingency_percent USING ERRCODE = 'PT422';
  END IF;

  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.budget_status <> 'none' THEN
    RAISE EXCEPTION 'Project % already has a budget (%)', p_project_id, v_project.budget_status USING ERRCODE = 'PT409';
  END IF;

  v_template := COALESCE(p_template_id, (
    SELECT id FROM public.budget_templates
     WHERE is_default AND is_active AND deleted_at IS NULL LIMIT 1));
  IF v_template IS NULL OR NOT EXISTS (
       SELECT 1 FROM public.budget_templates WHERE id = v_template AND is_active AND deleted_at IS NULL) THEN
    RAISE EXCEPTION 'No active budget template found. Set one up in Settings → Budget Template.' USING ERRCODE = 'PT409';
  END IF;

  v_pct := COALESCE(p_contingency_percent, v_project.contingency_percent,
                    (SELECT (value #>> '{}')::numeric FROM public.financial_settings
                      WHERE setting_key = 'default_contingency_percent'),
                    15);

  UPDATE public.projects
     SET budget_status = 'draft', contingency_percent = v_pct
   WHERE id = p_project_id;

  -- Slots ranked 1..n in template order; line sort_order = rank * 1000 (+ task order).
  CREATE TEMP TABLE IF NOT EXISTS _fin_slots (
    rnk INTEGER, line_type TEXT, name TEXT, section_name TEXT, trade_id UUID, template_line_id UUID
  ) ON COMMIT DROP;
  TRUNCATE _fin_slots;

  FOR v_tl IN
    SELECT * FROM public.budget_template_lines
     WHERE budget_template_id = v_template AND is_active
     ORDER BY sort_order, created_at
  LOOP
    v_rank := v_rank + 1;
    IF v_tl.line_type IN ('bid_activity', 'internal_tm') THEN
      INSERT INTO _fin_slots VALUES (v_rank, v_tl.line_type, lower(btrim(v_tl.name)),
                                     v_tl.section_name, v_tl.trade_id, v_tl.id);
    ELSE
      INSERT INTO public.budget_lines (
        project_id, template_line_id, line_type, line_subtype, name, section_name, sort_order,
        budget_amount, payment_terms_days, cash_bucket, is_payment_exempt, created_by, updated_by
      ) VALUES (
        p_project_id, v_tl.id, v_tl.line_type, v_tl.line_subtype, v_tl.name, v_tl.section_name, v_rank * 1000,
        CASE WHEN v_tl.line_type = 'contingency' THEN 0 ELSE COALESCE(v_tl.default_amount, 0) END,
        COALESCE(v_tl.default_payment_terms_days,
                 (SELECT (value #>> '{}')::int FROM public.financial_settings WHERE setting_key = 'default_payment_terms_days'),
                 30),
        COALESCE(v_tl.default_cash_bucket, 'land'),
        v_tl.line_type IN ('land', 'contingency'),
        p_actor, p_actor
      );
    END IF;
  END LOOP;

  -- Every live task becomes a line, at its matching slot (name, then trade).
  FOR v_task IN
    SELECT * FROM public.tasks
     WHERE project_id = p_project_id AND deleted_at IS NULL
     ORDER BY sort_order, created_at
  LOOP
    SELECT * INTO v_slot FROM _fin_slots s
     WHERE s.line_type = private.fin_line_type_for_bid_type(v_task.bid_type)
       AND s.name = lower(btrim(v_task.name))
     ORDER BY s.rnk LIMIT 1;
    IF NOT FOUND THEN
      SELECT * INTO v_slot FROM _fin_slots s
       WHERE s.line_type = private.fin_line_type_for_bid_type(v_task.bid_type)
         AND s.trade_id = v_task.trade_id
       ORDER BY s.rnk LIMIT 1;
    END IF;
    IF NOT FOUND THEN  -- no slot: after the last slot of that type, else at the end
      SELECT * INTO v_slot FROM _fin_slots s
       WHERE s.line_type = private.fin_line_type_for_bid_type(v_task.bid_type)
       ORDER BY s.rnk DESC LIMIT 1;
      IF NOT FOUND THEN
        v_slot := NULL;
      END IF;
    END IF;

    INSERT INTO public.budget_lines (
      project_id, task_id, template_line_id, line_type, name, description, section_name, sort_order,
      budget_amount, payment_terms_days, cash_bucket, created_by, updated_by
    ) VALUES (
      p_project_id, v_task.id, v_slot.template_line_id,
      private.fin_line_type_for_bid_type(v_task.bid_type),
      v_task.name, v_task.description,
      COALESCE(v_slot.section_name, CASE WHEN v_task.bid_type = 'internal' THEN 'Internal' ELSE 'Site work' END),
      COALESCE(v_slot.rnk, v_rank + 1) * 1000 + LEAST(GREATEST(v_task.sort_order, 0), 999),
      COALESCE(v_task.budget_estimate, 0),
      COALESCE((SELECT (value #>> '{}')::int FROM public.financial_settings WHERE setting_key = 'default_payment_terms_days'), 30),
      'land', p_actor, p_actor
    );
  END LOOP;

  -- Contingency: a line always exists; amount = pct × base (base excludes land and contingency).
  SELECT id INTO v_cont_id FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL;
  IF v_cont_id IS NULL THEN
    INSERT INTO public.budget_lines (project_id, line_type, name, section_name, sort_order,
                                     budget_amount, is_payment_exempt, created_by, updated_by)
    VALUES (p_project_id, 'contingency', 'Contingency', 'Contingency', (v_rank + 2) * 1000, 0, TRUE, p_actor, p_actor)
    RETURNING id INTO v_cont_id;
  END IF;

  SELECT COALESCE(SUM(budget_amount), 0) INTO v_base FROM public.budget_lines
   WHERE project_id = p_project_id AND deleted_at IS NULL AND line_type NOT IN ('land', 'contingency');

  UPDATE public.budget_lines
     SET budget_amount = round(v_base * v_pct / 100, 2)
   WHERE id = v_cont_id;

  RETURN QUERY
    SELECT * FROM public.budget_lines
     WHERE project_id = p_project_id AND deleted_at IS NULL
     ORDER BY sort_order;
END;
$$;

COMMENT ON FUNCTION public.fn_create_project_budget(UUID, UUID, UUID, NUMERIC) IS
  'Creates a DRAFT budget: one line per non-activity template row, one line per live task placed at its matching template slot (name, then trade), and the contingency line at pct × base (base excludes land and contingency). none → draft. PT409 if a budget exists.';


-- C.2 fn_reorder_budget_lines
CREATE OR REPLACE FUNCTION public.fn_reorder_budget_lines(
  p_project_id UUID,
  p_line_ids   UUID[],
  p_actor      UUID
)
RETURNS SETOF public.budget_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_live   INTEGER;
  v_given  INTEGER;
BEGIN
  PERFORM private.fin_lock_project(p_project_id, FALSE, FALSE);

  SELECT count(*) INTO v_live FROM public.budget_lines
   WHERE project_id = p_project_id AND deleted_at IS NULL;
  SELECT count(DISTINCT x) INTO v_given FROM unnest(p_line_ids) x
   WHERE x IN (SELECT id FROM public.budget_lines WHERE project_id = p_project_id AND deleted_at IS NULL);

  IF v_given <> v_live OR cardinality(p_line_ids) <> v_live THEN
    RAISE EXCEPTION 'Reorder must list every live line of the project exactly once (% given, % live)',
      cardinality(p_line_ids), v_live USING ERRCODE = 'PT422';
  END IF;

  UPDATE public.budget_lines l
     SET sort_order = o.ord * 10, updated_by = p_actor
    FROM unnest(p_line_ids) WITH ORDINALITY AS o(id, ord)
   WHERE l.id = o.id AND l.sort_order IS DISTINCT FROM o.ord * 10;

  RETURN QUERY SELECT * FROM public.budget_lines
                WHERE project_id = p_project_id AND deleted_at IS NULL ORDER BY sort_order;
END;
$$;

COMMENT ON FUNCTION public.fn_reorder_budget_lines(UUID, UUID[], UUID) IS
  'Rewrites sort_order for every live line of a project in the given order (10, 20, 30 …). Must list each live line exactly once.';


-- C.3 fn_remove_budget_line ─ checklist removal
CREATE OR REPLACE FUNCTION public.fn_remove_budget_line(
  p_line_id UUID,
  p_actor   UUID
)
RETURNS SETOF public.budget_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_line    public.budget_lines;
  v_project public.projects;
  v_result  public.budget_lines;
BEGIN
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_line_id;
  IF NOT FOUND OR v_line.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Budget line % not found', p_line_id USING ERRCODE = 'PT404';
  END IF;

  v_project := private.fin_lock_project(v_line.project_id, FALSE, FALSE);
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_line_id FOR UPDATE;

  IF v_line.line_type = 'contingency' THEN
    RAISE EXCEPTION 'The contingency line cannot be removed' USING ERRCODE = 'PT409';
  END IF;
  IF v_line.line_type = 'variance' THEN
    RAISE EXCEPTION 'Variances are cancelled, not removed' USING ERRCODE = 'PT422';
  END IF;
  IF v_line.task_id IS NOT NULL AND EXISTS (
       SELECT 1 FROM public.tasks WHERE id = v_line.task_id AND deleted_at IS NULL) THEN
    RAISE EXCEPTION 'This line belongs to task "%". Delete the task (Tasks tab) and its budget line goes with it.', v_line.name
      USING ERRCODE = 'PT409';
  END IF;
  IF EXISTS (SELECT 1 FROM public.land_closings WHERE budget_line_id = p_line_id AND status <> 'cancelled') THEN
    RAISE EXCEPTION 'Cancel this line''s land closings first' USING ERRCODE = 'PT409';
  END IF;
  IF EXISTS (SELECT 1 FROM public.escrows
              WHERE (premium_line_id = p_line_id OR repair_line_id = p_line_id)
                AND deleted_at IS NULL AND status <> 'cancelled') THEN
    RAISE EXCEPTION 'This line is an open escrow cost' USING ERRCODE = 'PT409';
  END IF;

  IF v_project.budget_status = 'baselined' THEN
    IF NOT private.fin_line_is_empty(p_line_id) THEN
      RAISE EXCEPTION 'Budget is baselined: only a $0 line with no award, invoices, approvals or variances can be removed (line "%" holds %).',
        v_line.name, v_line.budget_amount USING ERRCODE = 'PT409';
    END IF;
  ELSE
    IF EXISTS (SELECT 1 FROM public.internal_invoices WHERE budget_line_id = p_line_id
                 AND deleted_at IS NULL AND status NOT IN ('rejected', 'cancelled'))
       OR EXISTS (SELECT 1 FROM public.payment_approvals WHERE budget_line_id = p_line_id
                    AND status NOT IN ('rejected', 'cancelled')) THEN
      RAISE EXCEPTION 'Line "%" has invoices or payment approvals', v_line.name USING ERRCODE = 'PT409';
    END IF;
  END IF;

  UPDATE public.budget_lines
     SET deleted_at = NOW(), updated_by = p_actor
   WHERE id = p_line_id
   RETURNING * INTO v_result;

  RETURN NEXT v_result;
END;
$$;

COMMENT ON FUNCTION public.fn_remove_budget_line(UUID, UUID) IS
  'Soft-deletes a non-task line (the budget doubles as a checklist). Never the contingency line; task lines go with their task; after baseline only $0 lines with no award / invoices / approvals / variances.';


-- C.4 fn_apply_budget_import ─ draft budgets only
-- p_rows: JSON array of {line_id?, name, line_type?, line_subtype?, section_name?,
--          budget_amount?, anticipated_start_date?, anticipated_end_date?,
--          payment_terms_days?, cash_bucket?}
CREATE OR REPLACE FUNCTION public.fn_apply_budget_import(
  p_project_id UUID,
  p_rows       JSONB,
  p_actor      UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project  public.projects;
  v_row      JSONB;
  v_line     public.budget_lines;
  v_updated  INTEGER := 0;
  v_added    INTEGER := 0;
  v_sort     INTEGER;
  v_type     TEXT;
BEGIN
  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.budget_status <> 'draft' THEN
    RAISE EXCEPTION 'Import is only possible while the budget is a draft (status %)', v_project.budget_status
      USING ERRCODE = 'PT409';
  END IF;
  IF jsonb_typeof(p_rows) <> 'array' THEN
    RAISE EXCEPTION 'p_rows must be a JSON array' USING ERRCODE = 'PT422';
  END IF;

  SELECT COALESCE(MAX(sort_order), 0) INTO v_sort FROM public.budget_lines
   WHERE project_id = p_project_id AND deleted_at IS NULL AND line_type <> 'contingency';

  FOR v_row IN SELECT * FROM jsonb_array_elements(p_rows) LOOP
    IF v_row ? 'line_id' AND v_row ->> 'line_id' IS NOT NULL THEN
      SELECT * INTO v_line FROM public.budget_lines
       WHERE id = (v_row ->> 'line_id')::uuid AND project_id = p_project_id AND deleted_at IS NULL
       FOR UPDATE;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'Import row refers to unknown line %', v_row ->> 'line_id' USING ERRCODE = 'PT404';
      END IF;

      UPDATE public.budget_lines SET
        budget_amount          = COALESCE((v_row ->> 'budget_amount')::numeric, budget_amount),
        anticipated_start_date = COALESCE((v_row ->> 'anticipated_start_date')::date, anticipated_start_date),
        anticipated_end_date   = COALESCE((v_row ->> 'anticipated_end_date')::date, anticipated_end_date),
        payment_terms_days     = COALESCE((v_row ->> 'payment_terms_days')::int, payment_terms_days),
        cash_bucket            = COALESCE(v_row ->> 'cash_bucket', cash_bucket),
        section_name           = COALESCE(v_row ->> 'section_name', section_name),
        updated_by             = p_actor
       WHERE id = v_line.id;
      v_updated := v_updated + 1;
    ELSE
      v_type := COALESCE(v_row ->> 'line_type', 'soft_cost');
      IF v_type IN ('bid_activity', 'contingency', 'variance') THEN
        RAISE EXCEPTION 'Import cannot add a % line ("%"); bid activities come from tasks', v_type, v_row ->> 'name'
          USING ERRCODE = 'PT422';
      END IF;
      -- Place the new line after the last line of its heading, else just
      -- before contingency, else at the end.
      SELECT COALESCE(
               (SELECT MAX(sort_order) + 1 FROM public.budget_lines
                 WHERE project_id = p_project_id AND deleted_at IS NULL
                   AND section_name = NULLIF(v_row ->> 'section_name', '')),
               (SELECT MIN(sort_order) - 1 FROM public.budget_lines
                 WHERE project_id = p_project_id AND deleted_at IS NULL AND line_type = 'contingency'),
               v_sort + 1)
        INTO v_sort;
      INSERT INTO public.budget_lines (
        project_id, line_type, line_subtype, name, section_name, sort_order, budget_amount,
        anticipated_start_date, anticipated_end_date, payment_terms_days, cash_bucket,
        is_payment_exempt, created_by, updated_by
      ) VALUES (
        p_project_id, v_type, NULLIF(v_row ->> 'line_subtype', ''), btrim(v_row ->> 'name'),
        NULLIF(v_row ->> 'section_name', ''), v_sort,
        COALESCE((v_row ->> 'budget_amount')::numeric, 0),
        (v_row ->> 'anticipated_start_date')::date, (v_row ->> 'anticipated_end_date')::date,
        COALESCE((v_row ->> 'payment_terms_days')::int, 30),
        COALESCE(v_row ->> 'cash_bucket', 'land'),
        v_type = 'land', p_actor, p_actor
      );
      v_added := v_added + 1;
    END IF;
  END LOOP;

  RETURN jsonb_build_object('updated', v_updated, 'added', v_added);
END;
$$;

COMMENT ON FUNCTION public.fn_apply_budget_import(UUID, JSONB, UUID) IS
  'Applies confirmed CSV / Excel import rows to a DRAFT budget in one transaction: rows with line_id update amount / dates / terms / bucket / section; rows without add non-activity lines.';


-- C.5 fn_categorise_internal_invoice ─ invoice → line, overage → variance
CREATE OR REPLACE FUNCTION public.fn_categorise_internal_invoice(
  p_invoice_id UUID,
  p_line_id    UUID,
  p_actor      UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_inv        public.internal_invoices;
  v_line       public.budget_lines;
  v_project    public.projects;
  v_other      NUMERIC;
  v_allowance  NUMERIC;
  v_overage    NUMERIC := 0;
  v_in_amount  NUMERIC;
  v_var_line   public.budget_lines;
  v_variance   public.variance_lines;
  v_approvals  JSONB := '[]'::jsonb;
  v_pa_id      UUID;
  v_label      TEXT;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_inv FROM public.internal_invoices WHERE id = p_invoice_id;
  IF NOT FOUND OR v_inv.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Invoice % not found', p_invoice_id USING ERRCODE = 'PT404';
  END IF;

  v_project := private.fin_lock_project(v_inv.project_id, FALSE, TRUE);
  SELECT * INTO v_inv FROM public.internal_invoices WHERE id = p_invoice_id FOR UPDATE;

  IF v_inv.status NOT IN ('received', 'categorised') THEN
    RAISE EXCEPTION 'Invoice is already % and cannot be re-categorised', v_inv.status USING ERRCODE = 'PT409';
  END IF;
  IF v_inv.amount <= 0 THEN
    RAISE EXCEPTION 'Invoice amount must be greater than zero' USING ERRCODE = 'PT422';
  END IF;
  IF v_project.budget_status = 'none' THEN
    RAISE EXCEPTION 'The project has no budget yet' USING ERRCODE = 'PT409';
  END IF;

  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_line_id FOR UPDATE;
  IF NOT FOUND OR v_line.deleted_at IS NOT NULL OR v_line.project_id <> v_inv.project_id THEN
    RAISE EXCEPTION 'Budget line % not found on this project', p_line_id USING ERRCODE = 'PT404';
  END IF;
  IF v_line.line_type <> 'internal_tm' THEN
    RAISE EXCEPTION 'Invoices are categorised to internal T&M lines only (line "%" is %)', v_line.name, v_line.line_type
      USING ERRCODE = 'PT422';
  END IF;

  SELECT COALESCE(SUM(amount), 0) INTO v_other FROM public.internal_invoices
   WHERE budget_line_id = p_line_id AND id <> p_invoice_id AND deleted_at IS NULL
     AND status NOT IN ('received', 'rejected', 'cancelled');

  v_allowance := GREATEST(v_line.budget_amount - v_other, 0);
  v_overage   := GREATEST(v_inv.amount - v_allowance, 0);
  v_in_amount := v_inv.amount - v_overage;
  v_label     := COALESCE(NULLIF(btrim(v_inv.invoice_number), ''), v_inv.payee_name, 'invoice');

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  -- Overage on a baselined budget → variance funded from contingency.
  IF v_overage > 0 AND v_project.budget_status = 'baselined' THEN
    INSERT INTO public.budget_lines (
      project_id, parent_line_id, line_type, name, description, section_name, sort_order,
      budget_amount, anticipated_start_date, anticipated_end_date,
      payment_terms_days, cash_bucket, approval_state, created_by, updated_by
    ) VALUES (
      v_line.project_id, v_line.id, 'variance',
      left('Variance: invoice overage ' || v_label, 255),
      format('Invoice %s exceeds the remaining allowance of %s on "%s" by %s', v_label, v_allowance, v_line.name, v_overage),
      v_line.section_name, v_line.sort_order, v_overage,
      v_line.anticipated_start_date, v_line.anticipated_end_date,
      v_line.payment_terms_days, v_line.cash_bucket, 'pending', p_actor, p_actor
    ) RETURNING * INTO v_var_line;

    INSERT INTO public.variance_lines (
      project_id, budget_line_id, parent_budget_line_id, vendor_id,
      description, estimated_amount, status, created_by
    ) VALUES (
      v_line.project_id, v_var_line.id, v_line.id, v_inv.vendor_id,
      format('Invoice overage — %s', v_label), v_overage, 'pending_approval', p_actor
    ) RETURNING * INTO v_variance;

    PERFORM private.fin_move_contingency(
      v_line.project_id, -v_overage, 'invoice_overage', p_actor,
      format('Invoice %s over the "%s" allowance by %s', v_label, v_line.name, v_overage),
      v_var_line.id, v_variance.id, NULL, NULL);
  ELSE
    v_in_amount := v_inv.amount;   -- draft: whole invoice on the line; overage reported
  END IF;

  IF v_in_amount > 0 THEN
    INSERT INTO public.payment_approvals (project_id, budget_line_id, internal_invoice_id, vendor_id,
                                          amount, payment_kind, status, requested_by)
    VALUES (v_line.project_id, v_line.id, p_invoice_id, v_inv.vendor_id, v_in_amount, 'full', 'pending', p_actor)
    RETURNING id INTO v_pa_id;
    v_approvals := v_approvals || jsonb_build_object('id', v_pa_id, 'budget_line_id', v_line.id, 'amount', v_in_amount);
  END IF;

  IF v_var_line.id IS NOT NULL THEN
    INSERT INTO public.payment_approvals (project_id, budget_line_id, internal_invoice_id, vendor_id,
                                          amount, payment_kind, status, requested_by)
    VALUES (v_line.project_id, v_var_line.id, p_invoice_id, v_inv.vendor_id, v_overage, 'full', 'pending', p_actor)
    RETURNING id INTO v_pa_id;
    v_approvals := v_approvals || jsonb_build_object('id', v_pa_id, 'budget_line_id', v_var_line.id, 'amount', v_overage);
  END IF;

  UPDATE public.budget_lines SET approval_state = 'pending', updated_by = p_actor
   WHERE id = v_line.id AND approval_state IN ('not_requested', 'rejected');

  UPDATE public.internal_invoices
     SET budget_line_id = p_line_id, status = 'in_approval'
   WHERE id = p_invoice_id
   RETURNING * INTO v_inv;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN jsonb_build_object(
    'invoice_id',        v_inv.id,
    'budget_line_id',    p_line_id,
    'status',            v_inv.status,
    'allowance',         v_allowance,
    'overage',           v_overage,
    'variance_id',       v_variance.id,
    'variance_line_id',  v_var_line.id,
    'budget_status',     v_project.budget_status,
    'payment_approvals', v_approvals
  );
END;
$$;

COMMENT ON FUNCTION public.fn_categorise_internal_invoice(UUID, UUID, UUID) IS
  'Categorises an internal invoice to an internal T&M line and starts payment approval (pending requests). Allowance = line budget − other categorised invoices. On a baselined budget the overage becomes a variance line funded from contingency (ledger invoice_overage) with its own approval request; on a draft budget the overage is only reported.';


-- ============================================================================
-- SECTION 10.D: TASK → BUDGET LINE SYNC (no double entry)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.fn_sync_task_budget_line()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_status   TEXT;
  v_line     public.budget_lines;
  v_pos      RECORD;
  v_type     TEXT;
  v_amount   NUMERIC;
BEGIN
  SELECT budget_status INTO v_status FROM public.projects WHERE id = NEW.project_id;
  IF v_status IS NULL OR v_status = 'none' THEN
    RETURN NEW;   -- no budget on this project: nothing to sync
  END IF;

  SELECT * INTO v_line FROM public.budget_lines
   WHERE task_id = NEW.id AND deleted_at IS NULL;

  v_type := private.fin_line_type_for_bid_type(NEW.bid_type);

  -- ── Task soft-deleted → its line goes too (money rules apply) ────────────
  IF TG_OP = 'UPDATE' AND NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
    IF v_line.id IS NOT NULL THEN
      IF v_status = 'baselined' AND NOT private.fin_line_is_empty(v_line.id) THEN
        RAISE EXCEPTION 'Task "%" cannot be deleted: its budget line holds % (or has an award, invoices or variances). Settle the line first.',
          NEW.name, v_line.budget_amount USING ERRCODE = 'PT409';
      END IF;
      UPDATE public.budget_lines SET deleted_at = NOW() WHERE id = v_line.id;
    END IF;
    RETURN NEW;
  END IF;

  IF NEW.deleted_at IS NOT NULL THEN
    RETURN NEW;
  END IF;

  -- ── New / restored task → new line ──────────────────────────────────────
  IF v_line.id IS NULL THEN
    SELECT * INTO v_pos FROM private.fin_next_activity_position(NEW.project_id, v_type);
    INSERT INTO public.budget_lines (
      project_id, task_id, line_type, name, description, section_name, sort_order,
      budget_amount, payment_terms_days, cash_bucket, created_by, updated_by
    ) VALUES (
      NEW.project_id, NEW.id, v_type, NEW.name, NEW.description, v_pos.section_name, v_pos.sort_order,
      CASE WHEN v_status = 'draft' THEN COALESCE(NEW.budget_estimate, 0) ELSE 0 END,
      COALESCE((SELECT (value #>> '{}')::int FROM public.financial_settings WHERE setting_key = 'default_payment_terms_days'), 30),
      'land', NEW.created_by, NEW.created_by
    );
    RETURN NEW;
  END IF;

  IF TG_OP <> 'UPDATE' THEN
    RETURN NEW;
  END IF;

  -- ── bid_type change → replace the line with the right type ──────────────
  IF NEW.bid_type IS DISTINCT FROM OLD.bid_type AND v_line.line_type <> v_type THEN
    IF v_status = 'baselined' AND NOT private.fin_line_is_empty(v_line.id) THEN
      RAISE EXCEPTION 'Task "%" type cannot change: its budget line holds money or commitments.', NEW.name
        USING ERRCODE = 'PT409';
    END IF;
    v_amount := CASE WHEN v_status = 'draft' THEN v_line.budget_amount ELSE 0 END;
    UPDATE public.budget_lines SET deleted_at = NOW() WHERE id = v_line.id;
    INSERT INTO public.budget_lines (
      project_id, task_id, template_line_id, line_type, name, description, section_name, sort_order,
      budget_amount, anticipated_start_date, anticipated_end_date, payment_terms_days, cash_bucket,
      created_by, updated_by
    ) VALUES (
      NEW.project_id, NEW.id, v_line.template_line_id, v_type, NEW.name, v_line.description,
      v_line.section_name, v_line.sort_order, v_amount,
      v_line.anticipated_start_date, v_line.anticipated_end_date, v_line.payment_terms_days, v_line.cash_bucket,
      v_line.created_by, NEW.created_by
    );
    RETURN NEW;
  END IF;

  -- ── Name follows the task ────────────────────────────────────────────────
  IF NEW.name IS DISTINCT FROM OLD.name THEN
    UPDATE public.budget_lines SET name = NEW.name WHERE id = v_line.id;
  END IF;

  -- ── Estimate follows the task while draft and untouched ─────────────────
  IF NEW.budget_estimate IS DISTINCT FROM OLD.budget_estimate
     AND v_status = 'draft'
     AND v_line.award_id IS NULL
     AND v_line.budget_amount = COALESCE(OLD.budget_estimate, 0) THEN
    UPDATE public.budget_lines SET budget_amount = COALESCE(NEW.budget_estimate, 0) WHERE id = v_line.id;
  END IF;

  RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.fn_sync_task_budget_line() IS
  'Keeps budget lines in step with tasks for projects that have a budget: new / restored task → line (draft: estimate, baselined: $0); rename → line name; estimate change → line amount while draft and untouched; bid_type change → line replaced with the right type; soft delete → line removed (PT409 if it carries money after baseline). No-op for projects without a budget.';

DROP TRIGGER IF EXISTS trg_tasks_sync_budget_line ON public.tasks;
CREATE TRIGGER trg_tasks_sync_budget_line
  AFTER INSERT OR UPDATE OF name, budget_estimate, bid_type, deleted_at ON public.tasks
  FOR EACH ROW EXECUTE FUNCTION public.fn_sync_task_budget_line();


-- ============================================================================
-- SECTION 10.E: READ VIEWS (exact NUMERIC totals; security_invoker)
-- ============================================================================

CREATE OR REPLACE VIEW public.v_budget_lines
WITH (security_invoker = true) AS
SELECT
  bl.id,
  bl.project_id,
  bl.task_id,
  bl.template_line_id,
  bl.parent_line_id,
  bl.line_type,
  bl.line_subtype,
  bl.name,
  bl.description,
  bl.section_name,
  bl.sort_order,
  bl.original_estimate,
  bl.budget_amount,
  bl.committed_amount,
  bl.award_id,
  bl.contract_id,
  bl.is_locked,
  bl.locked_at,
  bl.lock_reason,
  bl.anticipated_start_date,
  bl.anticipated_end_date,
  bl.payment_terms_days,
  bl.cash_bucket,
  bl.approval_state,
  bl.is_payment_exempt,
  bl.created_at,
  bl.updated_at,
  t.name                     AS task_name,
  t.status                   AS task_status,
  t.bid_type                 AS task_bid_type,
  tr.name                    AS trade_name,
  a.status                   AS award_status,
  a.award_amount,
  v.id                       AS vendor_id,
  v.company_name             AS vendor_name,
  c.contract_number,
  c.status                   AS contract_status,
  vl.id                      AS variance_id,
  vl.status                  AS variance_status,
  COALESCE(var.total, 0)     AS variance_total,
  COALESCE(var.cnt, 0)       AS variance_count,
  private.fin_line_invoiced(bl.id) AS invoiced,
  CASE bl.line_type
    WHEN 'internal_tm' THEN private.fin_line_invoiced(bl.id)
    WHEN 'variance'    THEN CASE WHEN vl.status = 'approved' THEN bl.budget_amount ELSE 0 END
    ELSE bl.committed_amount
  END                        AS committed,
  COALESCE(pay.spent, 0)     AS spent,
  COALESCE(pay.pending, 0)   AS pending_approval,
  bl.budget_amount - COALESCE(pay.spent, 0)                                  AS remaining,
  CASE WHEN bl.original_estimate IS NOT NULL
       THEN bl.budget_amount - bl.original_estimate END                     AS bid_vs_estimate,
  (bl.anticipated_start_date IS NOT NULL AND bl.anticipated_end_date IS NOT NULL) AS has_dates,
  COALESCE(cl.total, 0)      AS closings_total,
  COALESCE(cl.cnt, 0)        AS closings_count
FROM public.budget_lines bl
LEFT JOIN public.tasks           t  ON t.id  = bl.task_id
LEFT JOIN public.trades          tr ON tr.id = t.trade_id
LEFT JOIN public.awards          a  ON a.id  = bl.award_id
LEFT JOIN public.vendors         v  ON v.id  = a.vendor_id
LEFT JOIN public.contracts       c  ON c.id  = bl.contract_id
LEFT JOIN public.variance_lines  vl ON vl.budget_line_id = bl.id
LEFT JOIN LATERAL (
  SELECT SUM(ch.budget_amount) AS total, count(*) AS cnt
    FROM public.budget_lines ch
   WHERE ch.parent_line_id = bl.id AND ch.line_type = 'variance' AND ch.deleted_at IS NULL
) var ON TRUE
LEFT JOIN LATERAL (
  SELECT SUM(pa.amount) FILTER (WHERE pa.status IN ('approved', 'sent_to_finance'))           AS spent,
         SUM(pa.amount) FILTER (WHERE pa.status IN ('pending', 'field_approved',
                                                    'awaiting_manager', 'awaiting_executive')) AS pending
    FROM public.payment_approvals pa
   WHERE pa.budget_line_id = bl.id
) pay ON TRUE
LEFT JOIN LATERAL (
  SELECT SUM(lc.amount) AS total, count(*) AS cnt
    FROM public.land_closings lc
   WHERE lc.budget_line_id = bl.id AND lc.status <> 'cancelled'
) cl ON TRUE
WHERE bl.deleted_at IS NULL;

COMMENT ON VIEW public.v_budget_lines IS
  'Budget tab read surface: one row per live budget line with task / trade / award / vendor / contract context and NUMERIC totals — variance_total, invoiced, committed (bid: award; internal T&M: categorised invoices; variance: amount once approved), spent (approved + sent-to-finance payments), pending_approval, remaining (= budget − spent), bid_vs_estimate, closings. security_invoker = true.';

REVOKE ALL ON public.v_budget_lines FROM PUBLIC, anon;
GRANT SELECT ON public.v_budget_lines TO authenticated, service_role;


CREATE OR REPLACE VIEW public.v_project_budget_summary
WITH (security_invoker = true) AS
SELECT
  p.id                                    AS project_id,
  p.name                                  AS project_name,
  p.budget_status,
  p.approved_budget_total,
  p.contingency_percent,
  p.budget_baselined_at,
  COALESCE(SUM(l.budget_amount), 0)                                                     AS total_budget,
  COALESCE(SUM(l.committed) FILTER (WHERE l.line_type <> 'contingency'), 0)             AS committed,
  COALESCE(SUM(l.spent), 0)                                                             AS spent,
  COALESCE(SUM(l.budget_amount), 0) - COALESCE(SUM(l.spent), 0)                         AS remaining,
  COALESCE(SUM(l.pending_approval), 0)                                                  AS pending_approval,
  COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_type = 'contingency'), 0)          AS contingency_now,
  (SELECT cb.approved_amount FROM public.contingency_buckets cb
    WHERE cb.project_id = p.id AND cb.bucket_kind = 'initial')                          AS contingency_at_baseline,
  COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_type = 'land'), 0)                 AS land_total,
  COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_type NOT IN ('land', 'contingency')), 0) AS contingency_base,
  count(l.id)                                                                           AS line_count,
  count(l.id) FILTER (WHERE NOT l.has_dates AND l.line_type NOT IN ('contingency', 'land')) AS lines_missing_dates,
  (SELECT count(*) FROM public.tasks t
    WHERE t.project_id = p.id AND t.deleted_at IS NULL
      AND NOT EXISTS (SELECT 1 FROM public.budget_lines b
                       WHERE b.task_id = t.id AND b.deleted_at IS NULL))                AS tasks_without_line,
  CASE WHEN p.budget_status = 'baselined'
       THEN COALESCE(SUM(l.budget_amount), 0) = p.approved_budget_total
       ELSE TRUE END                                                                    AS flat_ok
FROM public.projects p
LEFT JOIN public.v_budget_lines l ON l.project_id = p.id
WHERE p.deleted_at IS NULL
GROUP BY p.id;

COMMENT ON VIEW public.v_project_budget_summary IS
  'Per-project budget summary cards: total, committed, spent, remaining, pending approval, contingency now / at baseline, land total, contingency base, missing dates, tasks without a line, flat-budget check. security_invoker = true.';

REVOKE ALL ON public.v_project_budget_summary FROM PUBLIC, anon;
GRANT SELECT ON public.v_project_budget_summary TO authenticated, service_role;


-- ============================================================================
-- SECTION 10.F: PRIVILEGES
-- ============================================================================

DO $$
DECLARE
  f TEXT;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'public.fn_create_project_budget(uuid, uuid, uuid, numeric)',
    'public.fn_reorder_budget_lines(uuid, uuid[], uuid)',
    'public.fn_remove_budget_line(uuid, uuid)',
    'public.fn_apply_budget_import(uuid, jsonb, uuid)',
    'public.fn_categorise_internal_invoice(uuid, uuid, uuid)',
    'private.fin_next_activity_position(uuid, text)',
    'private.fin_line_is_empty(uuid)'
  ] LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role', f);
  END LOOP;
END $$;

REVOKE ALL ON FUNCTION public.fn_sync_task_budget_line()            FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_line_type_for_bid_type(TEXT)     FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.fin_line_invoiced(UUID)              FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.fin_line_type_for_bid_type(TEXT)  TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.fin_line_invoiced(UUID)           TO authenticated, service_role;


-- ============================================================================
-- SECTION 10.G: STORAGE BUCKET finance-documents (private, no client policies)
-- ============================================================================
-- Files are reachable only through FastAPI (service_role) and 1-hour signed
-- URLs. No storage.objects policy is created for authenticated on purpose.

DO $$
BEGIN
  IF to_regclass('storage.buckets') IS NOT NULL THEN
    EXECUTE $q$
      INSERT INTO storage.buckets (id, name, public, file_size_limit)
      VALUES ('finance-documents', 'finance-documents', FALSE, 26214400)
      ON CONFLICT (id) DO NOTHING
    $q$;
  END IF;
END $$;


-- ============================================================================
-- SECTION 10.H: VERSION MARKER
-- ============================================================================

INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.1.0 (20261118_financial_phase2)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;



-- ############################################################################
--
--  SECTION 11: FINANCIAL AUTOMATION — PHASE 2 PATCH: BUDGET ENVELOPE (v4.2)
--
--  Source of truth for EXISTING databases: the idempotent migration
--    database/migrations/20261119_financial_phase2_budget_envelope/001_budget_envelope.sql
--  Same DDL minus BEGIN/COMMIT. Requires Sections 9 and 10.
--  Replaces fn_create_project_budget and the two budget views from Section 10.
--
-- ############################################################################

-- ============================================================================
-- SECTION 11.A: 'unallocated' line subtype
-- ============================================================================
-- The budget_lines.line_subtype CHECK is widened (superset). The old
-- constraint is found by definition; its name is not guessed.
DO $$
DECLARE
  r RECORD;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint
              WHERE conname = 'chk_budget_lines_line_subtype'
                AND pg_get_constraintdef(oid) ILIKE '%unallocated%') THEN
    RETURN;
  END IF;
  FOR r IN
    SELECT conname FROM pg_constraint
     WHERE conrelid = 'public.budget_lines'::regclass AND contype = 'c'
       AND pg_get_constraintdef(oid) ILIKE '%line_subtype%'
  LOOP
    EXECUTE format('ALTER TABLE public.budget_lines DROP CONSTRAINT %I', r.conname);
  END LOOP;
  ALTER TABLE public.budget_lines ADD CONSTRAINT chk_budget_lines_line_subtype
    CHECK (line_subtype IS NULL OR line_subtype IN (
      'land_purchase', 'earnest_money', 'due_diligence', 'engineering',
      'escrow_bond_premium', 'escrow_repairs', 'property_tax', 'other', 'unallocated'));
END $$;

COMMENT ON COLUMN public.budget_lines.line_subtype IS
  'Finer classification: land_purchase, earnest_money, due_diligence, engineering, escrow_bond_premium, escrow_repairs, property_tax, other, unallocated (the balancing line that keeps a draft budget at the project''s Budget value).';

CREATE UNIQUE INDEX IF NOT EXISTS uq_budget_lines_one_unallocated_per_project
  ON public.budget_lines (project_id)
  WHERE line_subtype = 'unallocated' AND deleted_at IS NULL;


-- ============================================================================
-- SECTION 11.B: fn_create_project_budget (same signature, new rules)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_create_project_budget(
  p_project_id          UUID,
  p_actor               UUID,
  p_template_id         UUID DEFAULT NULL,
  p_contingency_percent NUMERIC DEFAULT NULL
)
RETURNS SETOF public.budget_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project   public.projects;
  v_template  UUID;
  v_pct       NUMERIC;
  v_rank      INTEGER := 0;
  v_tl        RECORD;
  v_task      RECORD;
  v_slot      RECORD;
  v_line      RECORD;
  v_award     RECORD;
  v_contract  RECORD;
  v_cont_id   UUID;
  v_cont_sort INTEGER;
  v_total     NUMERIC;
  v_land      NUMERIC;
  v_base      NUMERIC;
  v_cont      NUMERIC;
  v_others    NUMERIC;
  v_terms     INTEGER;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;
  IF p_contingency_percent IS NOT NULL AND (p_contingency_percent < 0 OR p_contingency_percent > 100) THEN
    RAISE EXCEPTION 'Contingency %% must be between 0 and 100 (got %)', p_contingency_percent USING ERRCODE = 'PT422';
  END IF;

  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.budget_status <> 'none' THEN
    RAISE EXCEPTION 'Project % already has a budget (%)', p_project_id, v_project.budget_status USING ERRCODE = 'PT409';
  END IF;

  v_template := COALESCE(p_template_id, (
    SELECT id FROM public.budget_templates
     WHERE is_default AND is_active AND deleted_at IS NULL LIMIT 1));
  IF v_template IS NULL OR NOT EXISTS (
       SELECT 1 FROM public.budget_templates WHERE id = v_template AND is_active AND deleted_at IS NULL) THEN
    RAISE EXCEPTION 'No active budget template found. Set one up in Settings → Budget Template.' USING ERRCODE = 'PT409';
  END IF;

  v_pct := COALESCE(p_contingency_percent, v_project.contingency_percent,
                    (SELECT (value #>> '{}')::numeric FROM public.financial_settings
                      WHERE setting_key = 'default_contingency_percent'),
                    15);
  v_terms := COALESCE((SELECT (value #>> '{}')::int FROM public.financial_settings
                        WHERE setting_key = 'default_payment_terms_days'), 30);
  -- The project's own Budget value is the total when it is set.
  v_total := CASE WHEN v_project.budget IS NOT NULL AND v_project.budget > 0 THEN v_project.budget END;

  UPDATE public.projects SET budget_status = 'draft', contingency_percent = v_pct WHERE id = p_project_id;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  CREATE TEMP TABLE IF NOT EXISTS _fin_slots (
    rnk INTEGER, line_type TEXT, name TEXT, section_name TEXT, trade_id UUID, template_line_id UUID
  ) ON COMMIT DROP;
  TRUNCATE _fin_slots;

  -- 1. Template rows: non-activity rows become lines, activity rows are slots.
  FOR v_tl IN
    SELECT * FROM public.budget_template_lines
     WHERE budget_template_id = v_template AND is_active
     ORDER BY sort_order, created_at
  LOOP
    v_rank := v_rank + 1;
    IF v_tl.line_type IN ('bid_activity', 'internal_tm') THEN
      INSERT INTO _fin_slots VALUES (v_rank, v_tl.line_type, lower(btrim(v_tl.name)),
                                     v_tl.section_name, v_tl.trade_id, v_tl.id);
    ELSE
      INSERT INTO public.budget_lines (
        project_id, template_line_id, line_type, line_subtype, name, section_name, sort_order,
        budget_amount, payment_terms_days, cash_bucket, is_payment_exempt, created_by, updated_by
      ) VALUES (
        p_project_id, v_tl.id, v_tl.line_type, v_tl.line_subtype, v_tl.name, v_tl.section_name, v_rank * 1000,
        CASE WHEN v_tl.line_type = 'contingency' THEN 0 ELSE COALESCE(v_tl.default_amount, 0) END,
        COALESCE(v_tl.default_payment_terms_days, v_terms),
        COALESCE(v_tl.default_cash_bucket, 'land'),
        v_tl.line_type IN ('land', 'contingency'),
        p_actor, p_actor
      );
    END IF;
  END LOOP;

  -- 2. Every live task becomes a line at its matching slot (name, then trade).
  FOR v_task IN
    SELECT * FROM public.tasks
     WHERE project_id = p_project_id AND deleted_at IS NULL
     ORDER BY sort_order, created_at
  LOOP
    SELECT * INTO v_slot FROM _fin_slots s
     WHERE s.line_type = private.fin_line_type_for_bid_type(v_task.bid_type)
       AND s.name = lower(btrim(v_task.name))
     ORDER BY s.rnk LIMIT 1;
    IF NOT FOUND THEN
      SELECT * INTO v_slot FROM _fin_slots s
       WHERE s.line_type = private.fin_line_type_for_bid_type(v_task.bid_type)
         AND s.trade_id = v_task.trade_id
       ORDER BY s.rnk LIMIT 1;
    END IF;
    IF NOT FOUND THEN
      SELECT * INTO v_slot FROM _fin_slots s
       WHERE s.line_type = private.fin_line_type_for_bid_type(v_task.bid_type)
       ORDER BY s.rnk DESC LIMIT 1;
      IF NOT FOUND THEN
        v_slot := NULL;
      END IF;
    END IF;

    INSERT INTO public.budget_lines (
      project_id, task_id, template_line_id, line_type, name, description, section_name, sort_order,
      budget_amount, payment_terms_days, cash_bucket, created_by, updated_by
    ) VALUES (
      p_project_id, v_task.id, v_slot.template_line_id,
      private.fin_line_type_for_bid_type(v_task.bid_type),
      v_task.name, v_task.description,
      COALESCE(v_slot.section_name, CASE WHEN v_task.bid_type = 'internal' THEN 'Internal' ELSE 'Site work' END),
      COALESCE(v_slot.rnk, v_rank + 1) * 1000 + LEAST(GREATEST(v_task.sort_order, 0), 999),
      COALESCE(v_task.budget_estimate, 0), v_terms, 'land', p_actor, p_actor
    );
  END LOOP;

  -- 3. Tasks already awarded come in at the award amount (committed); an
  --    executed contract locks the line and supplies its dates.
  FOR v_line IN
    SELECT * FROM public.budget_lines
     WHERE project_id = p_project_id AND deleted_at IS NULL
       AND line_type = 'bid_activity' AND task_id IS NOT NULL
  LOOP
    SELECT * INTO v_award FROM public.awards
     WHERE task_id = v_line.task_id AND status IN ('pending_acceptance', 'accepted')
     ORDER BY awarded_at DESC LIMIT 1;
    CONTINUE WHEN NOT FOUND;

    SELECT * INTO v_contract FROM public.contracts
     WHERE award_id = v_award.id AND status IN ('executed', 'active', 'completed')
     ORDER BY created_at DESC LIMIT 1;

    UPDATE public.budget_lines
       SET pre_award_budget_amount = budget_amount,
           budget_amount           = v_award.award_amount,
           committed_amount        = v_award.award_amount,
           award_id                = v_award.id,
           is_locked               = (v_contract.id IS NOT NULL),
           locked_at               = CASE WHEN v_contract.id IS NOT NULL THEN NOW() END,
           locked_by               = CASE WHEN v_contract.id IS NOT NULL THEN p_actor END,
           lock_reason             = CASE WHEN v_contract.id IS NOT NULL THEN 'Contract executed' END,
           contract_id             = v_contract.id,
           anticipated_start_date  = CASE WHEN v_contract.id IS NOT NULL
                                            AND (v_contract.end_date IS NULL OR v_contract.start_date IS NULL
                                                 OR v_contract.end_date >= v_contract.start_date)
                                          THEN COALESCE(v_contract.start_date, anticipated_start_date)
                                          ELSE anticipated_start_date END,
           anticipated_end_date    = CASE WHEN v_contract.id IS NOT NULL
                                            AND (v_contract.end_date IS NULL OR v_contract.start_date IS NULL
                                                 OR v_contract.end_date >= v_contract.start_date)
                                          THEN COALESCE(v_contract.end_date, anticipated_end_date)
                                          ELSE anticipated_end_date END
     WHERE id = v_line.id;
  END LOOP;

  -- 4. Contingency line (always exists).
  SELECT id, sort_order INTO v_cont_id, v_cont_sort FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL;
  IF v_cont_id IS NULL THEN
    v_cont_sort := (v_rank + 2) * 1000;
    INSERT INTO public.budget_lines (project_id, line_type, name, section_name, sort_order,
                                     budget_amount, is_payment_exempt, created_by, updated_by)
    VALUES (p_project_id, 'contingency', 'Contingency', 'Contingency', v_cont_sort, 0, TRUE, p_actor, p_actor)
    RETURNING id INTO v_cont_id;
  END IF;

  SELECT COALESCE(SUM(budget_amount) FILTER (WHERE line_type = 'land'), 0),
         COALESCE(SUM(budget_amount) FILTER (WHERE line_type NOT IN ('land', 'contingency')), 0)
    INTO v_land, v_others
    FROM public.budget_lines
   WHERE project_id = p_project_id AND deleted_at IS NULL;

  IF v_total IS NOT NULL THEN
    -- base = total − land − contingency and contingency = pct × base
    v_cont := round(GREATEST(v_total - v_land, 0) * v_pct / (100 + v_pct), 2);
  ELSE
    v_base := v_others;
    v_cont := round(v_base * v_pct / 100, 2);
  END IF;

  UPDATE public.budget_lines SET budget_amount = v_cont WHERE id = v_cont_id;

  -- 5. Balancing line so the lines add up to the project's Budget value.
  IF v_total IS NOT NULL AND v_total - v_land - v_cont - v_others > 0 THEN
    INSERT INTO public.budget_lines (
      project_id, line_type, line_subtype, name, description, section_name, sort_order,
      budget_amount, payment_terms_days, cash_bucket, created_by, updated_by
    ) VALUES (
      p_project_id, 'soft_cost', 'unallocated', 'Unallocated budget',
      'Part of the project budget not yet assigned to a line. While the budget is a draft it grows or shrinks automatically as other lines change.',
      'Unallocated', v_cont_sort - 1,
      v_total - v_land - v_cont - v_others, v_terms, 'land', p_actor, p_actor
    );
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN QUERY
    SELECT * FROM public.budget_lines
     WHERE project_id = p_project_id AND deleted_at IS NULL
     ORDER BY sort_order;
END;
$$;

COMMENT ON FUNCTION public.fn_create_project_budget(UUID, UUID, UUID, NUMERIC) IS
  'Creates a DRAFT budget. Total = the project''s Budget value when set (else the sum of the lines). Template rows + every live task (at its template slot); awarded tasks come in at their award amount as committed, executed contracts locked; contingency = (total − land) × pct / (100 + pct) when the total is fixed, else pct × base; an Unallocated line balances the lines to the total. none → draft. PT409 if a budget exists.';

REVOKE ALL ON FUNCTION public.fn_create_project_budget(uuid, uuid, uuid, numeric) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_create_project_budget(uuid, uuid, uuid, numeric) TO service_role;


-- ============================================================================
-- SECTION 11.C: Draft budgets stay at the project budget (Unallocated absorbs)
-- ============================================================================
-- Any change to another line's effective amount in a DRAFT budget (edit,
-- import, new / deleted task, award, removed line) is offset on the Unallocated
-- line, floored at $0 (beyond that the budget simply exceeds the project
-- budget and the summary shows it). Baselined budgets: no-op (there the
-- flat-budget rule and contingency do this job).
CREATE OR REPLACE FUNCTION public.fn_budget_absorb_unallocated()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_status    TEXT;
  v_unalloc   public.budget_lines;
  v_old       NUMERIC := 0;
  v_new       NUMERIC := 0;
  v_delta     NUMERIC;
BEGIN
  IF NEW.line_subtype = 'unallocated' THEN
    RETURN NULL;
  END IF;

  SELECT budget_status INTO v_status FROM public.projects WHERE id = NEW.project_id;
  IF v_status IS DISTINCT FROM 'draft' THEN
    RETURN NULL;
  END IF;

  SELECT * INTO v_unalloc FROM public.budget_lines
   WHERE project_id = NEW.project_id AND line_subtype = 'unallocated' AND deleted_at IS NULL
   FOR UPDATE;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  IF TG_OP = 'UPDATE' AND OLD.deleted_at IS NULL THEN
    v_old := OLD.budget_amount;
  END IF;
  IF NEW.deleted_at IS NULL THEN
    v_new := NEW.budget_amount;
  END IF;
  v_delta := v_new - v_old;
  IF v_delta = 0 THEN
    RETURN NULL;
  END IF;

  UPDATE public.budget_lines
     SET budget_amount = GREATEST(v_unalloc.budget_amount - v_delta, 0)
   WHERE id = v_unalloc.id;

  RETURN NULL;
END;
$$;

COMMENT ON FUNCTION public.fn_budget_absorb_unallocated() IS
  'Draft budgets only: offsets every change to another line on the Unallocated line (floored at 0) so the budget stays at the project''s Budget value.';

DROP TRIGGER IF EXISTS trg_budget_lines_absorb_unallocated ON public.budget_lines;
CREATE TRIGGER trg_budget_lines_absorb_unallocated
  AFTER INSERT OR UPDATE OF budget_amount, deleted_at ON public.budget_lines
  FOR EACH ROW EXECUTE FUNCTION public.fn_budget_absorb_unallocated();

REVOKE ALL ON FUNCTION public.fn_budget_absorb_unallocated() FROM PUBLIC, anon, authenticated;


-- ============================================================================
-- SECTION 11.D: fn_reset_draft_budget — start a draft budget over
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_reset_draft_budget(
  p_project_id UUID,
  p_actor      UUID
)
RETURNS SETOF public.projects
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
BEGIN
  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.budget_status <> 'draft' THEN
    RAISE EXCEPTION 'Only a draft budget can be reset (this one is %)', v_project.budget_status USING ERRCODE = 'PT409';
  END IF;
  IF EXISTS (SELECT 1 FROM public.internal_invoices i
               JOIN public.budget_lines l ON l.id = i.budget_line_id
              WHERE l.project_id = p_project_id AND i.deleted_at IS NULL
                AND i.status NOT IN ('rejected', 'cancelled'))
     OR EXISTS (SELECT 1 FROM public.payment_approvals
                 WHERE project_id = p_project_id AND status NOT IN ('rejected', 'cancelled'))
     OR EXISTS (SELECT 1 FROM public.land_closings
                 WHERE project_id = p_project_id AND status <> 'cancelled') THEN
    RAISE EXCEPTION 'This draft budget has invoices, payment approvals or land closings; cancel them before resetting.'
      USING ERRCODE = 'PT409';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  -- Status first, so the Unallocated trigger stops reacting.
  UPDATE public.projects SET budget_status = 'none' WHERE id = p_project_id RETURNING * INTO v_project;
  UPDATE public.budget_lines SET deleted_at = NOW(), updated_by = p_actor
   WHERE project_id = p_project_id AND deleted_at IS NULL;
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_project;
END;
$$;

COMMENT ON FUNCTION public.fn_reset_draft_budget(UUID, UUID) IS
  'Draft budgets only: retires every line (soft delete, kept for history) and returns the project to "no budget" so it can be created again from the template, the project budget and the current awards. Refused when invoices, approvals or land closings exist.';

REVOKE ALL ON FUNCTION public.fn_reset_draft_budget(uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_reset_draft_budget(uuid, uuid) TO service_role;


-- ============================================================================
-- SECTION 11.E: Views — remaining = budget − committed; project figures
-- ============================================================================
-- Column lists are unchanged (new columns only at the end), so CREATE OR
-- REPLACE works on databases that already have the Phase 2 views.
CREATE OR REPLACE VIEW public.v_budget_lines
WITH (security_invoker = true) AS
SELECT
  bl.id,
  bl.project_id,
  bl.task_id,
  bl.template_line_id,
  bl.parent_line_id,
  bl.line_type,
  bl.line_subtype,
  bl.name,
  bl.description,
  bl.section_name,
  bl.sort_order,
  bl.original_estimate,
  bl.budget_amount,
  bl.committed_amount,
  bl.award_id,
  bl.contract_id,
  bl.is_locked,
  bl.locked_at,
  bl.lock_reason,
  bl.anticipated_start_date,
  bl.anticipated_end_date,
  bl.payment_terms_days,
  bl.cash_bucket,
  bl.approval_state,
  bl.is_payment_exempt,
  bl.created_at,
  bl.updated_at,
  t.name                     AS task_name,
  t.status                   AS task_status,
  t.bid_type                 AS task_bid_type,
  tr.name                    AS trade_name,
  a.status                   AS award_status,
  a.award_amount,
  v.id                       AS vendor_id,
  v.company_name             AS vendor_name,
  c.contract_number,
  c.status                   AS contract_status,
  vl.id                      AS variance_id,
  vl.status                  AS variance_status,
  COALESCE(var.total, 0)     AS variance_total,
  COALESCE(var.cnt, 0)       AS variance_count,
  private.fin_line_invoiced(bl.id) AS invoiced,
  cm.committed               AS committed,
  COALESCE(pay.spent, 0)     AS spent,
  COALESCE(pay.pending, 0)   AS pending_approval,
  -- Not yet committed. Contingency is a reserve, not something to commit
  -- against, so it has no "remaining" of its own (NULL).
  CASE WHEN bl.line_type = 'contingency' THEN NULL
       ELSE bl.budget_amount - cm.committed END                              AS remaining,
  CASE WHEN bl.original_estimate IS NOT NULL
       THEN bl.budget_amount - bl.original_estimate END                     AS bid_vs_estimate,
  (bl.anticipated_start_date IS NOT NULL AND bl.anticipated_end_date IS NOT NULL) AS has_dates,
  COALESCE(cl.total, 0)      AS closings_total,
  COALESCE(cl.cnt, 0)        AS closings_count
FROM public.budget_lines bl
LEFT JOIN public.tasks           t  ON t.id  = bl.task_id
LEFT JOIN public.trades          tr ON tr.id = t.trade_id
LEFT JOIN public.awards          a  ON a.id  = bl.award_id
LEFT JOIN public.vendors         v  ON v.id  = a.vendor_id
LEFT JOIN public.contracts       c  ON c.id  = bl.contract_id
LEFT JOIN public.variance_lines  vl ON vl.budget_line_id = bl.id
LEFT JOIN LATERAL (
  SELECT CASE bl.line_type
           WHEN 'internal_tm' THEN private.fin_line_invoiced(bl.id)
           WHEN 'variance'    THEN CASE WHEN vl.status = 'approved' THEN bl.budget_amount ELSE 0 END
           WHEN 'contingency' THEN 0
           ELSE bl.committed_amount
         END AS committed
) cm ON TRUE
LEFT JOIN LATERAL (
  SELECT SUM(ch.budget_amount) AS total, count(*) AS cnt
    FROM public.budget_lines ch
   WHERE ch.parent_line_id = bl.id AND ch.line_type = 'variance' AND ch.deleted_at IS NULL
) var ON TRUE
LEFT JOIN LATERAL (
  SELECT SUM(pa.amount) FILTER (WHERE pa.status IN ('approved', 'sent_to_finance'))           AS spent,
         SUM(pa.amount) FILTER (WHERE pa.status IN ('pending', 'field_approved',
                                                    'awaiting_manager', 'awaiting_executive')) AS pending
    FROM public.payment_approvals pa
   WHERE pa.budget_line_id = bl.id
) pay ON TRUE
LEFT JOIN LATERAL (
  SELECT SUM(lc.amount) AS total, count(*) AS cnt
    FROM public.land_closings lc
   WHERE lc.budget_line_id = bl.id AND lc.status <> 'cancelled'
) cl ON TRUE
WHERE bl.deleted_at IS NULL;

COMMENT ON VIEW public.v_budget_lines IS
  'Budget tab read surface: one row per live line with task / trade / award / vendor / contract context and NUMERIC totals — committed (bid: award; internal T&M: categorised invoices; variance: amount once approved; contingency: 0), spent, pending_approval, remaining (= budget − committed; NULL for contingency), bid_vs_estimate, closings. security_invoker = true.';


CREATE OR REPLACE VIEW public.v_project_budget_summary
WITH (security_invoker = true) AS
SELECT
  p.id                                    AS project_id,
  p.name                                  AS project_name,
  p.budget_status,
  p.approved_budget_total,
  p.contingency_percent,
  p.budget_baselined_at,
  COALESCE(SUM(l.budget_amount), 0)                                                     AS total_budget,
  COALESCE(SUM(l.committed), 0)                                                         AS committed,
  COALESCE(SUM(l.spent), 0)                                                             AS spent,
  -- Remaining = total budget − contingency − committed
  COALESCE(SUM(l.budget_amount), 0)
    - COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_type = 'contingency'), 0)
    - COALESCE(SUM(l.committed), 0)                                                     AS remaining,
  COALESCE(SUM(l.pending_approval), 0)                                                  AS pending_approval,
  COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_type = 'contingency'), 0)          AS contingency_now,
  (SELECT cb.approved_amount FROM public.contingency_buckets cb
    WHERE cb.project_id = p.id AND cb.bucket_kind = 'initial')                          AS contingency_at_baseline,
  COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_type = 'land'), 0)                 AS land_total,
  COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_type NOT IN ('land', 'contingency')), 0) AS contingency_base,
  count(l.id)                                                                           AS line_count,
  count(l.id) FILTER (WHERE NOT l.has_dates AND l.line_type NOT IN ('contingency', 'land')
                        AND COALESCE(l.line_subtype, '') <> 'unallocated')             AS lines_missing_dates,
  (SELECT count(*) FROM public.tasks t
    WHERE t.project_id = p.id AND t.deleted_at IS NULL
      AND NOT EXISTS (SELECT 1 FROM public.budget_lines b
                       WHERE b.task_id = t.id AND b.deleted_at IS NULL))                AS tasks_without_line,
  CASE WHEN p.budget_status = 'baselined'
       THEN COALESCE(SUM(l.budget_amount), 0) = p.approved_budget_total
       ELSE TRUE END                                                                    AS flat_ok,
  -- v4.2 additions (end of the column list)
  p.budget                                                                              AS project_budget,
  COALESCE(SUM(l.budget_amount) FILTER (WHERE l.line_subtype = 'unallocated'), 0)       AS unallocated,
  CASE WHEN p.budget IS NOT NULL
       THEN COALESCE(SUM(l.budget_amount), 0) - p.budget END                            AS over_project_budget
FROM public.projects p
LEFT JOIN public.v_budget_lines l ON l.project_id = p.id
WHERE p.deleted_at IS NULL
GROUP BY p.id;

COMMENT ON VIEW public.v_project_budget_summary IS
  'Per-project budget summary: total budget, committed, spent, remaining (= total − contingency − committed), pending approval, contingency now / at baseline, land, contingency base, missing dates, tasks without a line, flat-budget check, the project''s own Budget value, the Unallocated amount and how far the lines are over / under the project budget. security_invoker = true.';

REVOKE ALL ON public.v_budget_lines, public.v_project_budget_summary FROM PUBLIC, anon;
GRANT SELECT ON public.v_budget_lines, public.v_project_budget_summary TO authenticated, service_role;


-- ============================================================================
-- SECTION 11.F: VERSION MARKER
-- ============================================================================
INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.2.0 (20261119_financial_phase2_budget_envelope)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;



-- ############################################################################
--
--  SECTION 12: PROJECT NOTES, SUBTRADES, SAFE TRADE DELETE (v4.3)
--
--  Source of truth for EXISTING databases: the idempotent migration
--    database/migrations/20261117_notes_states_subtrades/001_notes_and_subtrades.sql
--  Same DDL minus BEGIN/COMMIT and the RLS part (in rls_policies.sql).
--  Replaces UNIQUE(trades.name) from Section 1
--  with uq_trades_top_level_name + uq_trades_subtrade_name.
--
-- ############################################################################

-- ============================================================================
-- SECTION 12.A: project_notes
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.project_notes (
  id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  title         VARCHAR(255)  NOT NULL CHECK (btrim(title) <> ''),
  content_html  TEXT          NOT NULL DEFAULT '',
  content_text  TEXT          NOT NULL DEFAULT '',
  created_by    UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  updated_by    UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at    TIMESTAMPTZ,

  -- Document-sized notes are fine; this only stops a runaway paste (~2 MB).
  CONSTRAINT chk_project_notes_size CHECK (length(content_html) <= 2000000)
);

CREATE INDEX IF NOT EXISTS idx_project_notes_project
  ON public.project_notes (project_id, updated_at DESC) WHERE deleted_at IS NULL;

COMMENT ON TABLE  public.project_notes              IS 'Free-form rich-text notes on a project (meeting notes, site observations, decisions). Written through FastAPI; any active user reads. Soft-deleted.';
COMMENT ON COLUMN public.project_notes.content_html IS 'Rich text as HTML produced by the editor (bold, italic, headings, lists, links …). Rendered back through the same editor schema, never injected as raw HTML.';
COMMENT ON COLUMN public.project_notes.content_text IS 'Plain-text copy of the note for previews and search.';
COMMENT ON COLUMN public.project_notes.deleted_at   IS 'Soft delete. NULL = visible.';

DROP TRIGGER IF EXISTS trg_project_notes_updated_at ON public.project_notes;
CREATE TRIGGER trg_project_notes_updated_at
  BEFORE UPDATE ON public.project_notes FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

-- RLS, grants and the read policy for project_notes live in rls_policies.sql
-- (section "PROJECT NOTES (v4.3)"), like every other table.


-- ============================================================================
-- SECTION 12.B: Subtrades
-- ============================================================================

ALTER TABLE public.trades ADD COLUMN IF NOT EXISTS parent_trade_id UUID;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_trades_parent') THEN
    ALTER TABLE public.trades ADD CONSTRAINT fk_trades_parent
      FOREIGN KEY (parent_trade_id) REFERENCES public.trades(id) ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_trades_parent_not_self') THEN
    ALTER TABLE public.trades ADD CONSTRAINT chk_trades_parent_not_self
      CHECK (parent_trade_id IS NULL OR parent_trade_id <> id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_trades_parent ON public.trades (parent_trade_id) WHERE parent_trade_id IS NOT NULL;

COMMENT ON COLUMN public.trades.parent_trade_id IS
  'NULL = top-level trade. Set = subtrade of that trade (one level only). A subtrade inherits its parent''s phase. A trade that has subtrades must be assigned through one of them.';

-- Names: unique among top-level trades, and within each parent.
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT conname FROM pg_constraint
     WHERE conrelid = 'public.trades'::regclass AND contype = 'u'
       AND pg_get_constraintdef(oid) = 'UNIQUE (name)'
  LOOP
    EXECUTE format('ALTER TABLE public.trades DROP CONSTRAINT %I', r.conname);
  END LOOP;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_trades_top_level_name
  ON public.trades (name) WHERE parent_trade_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_trades_subtrade_name
  ON public.trades (parent_trade_id, name) WHERE parent_trade_id IS NOT NULL;


-- B.1 One level only; a subtrade takes its parent's phase.
CREATE OR REPLACE FUNCTION public.fn_trades_hierarchy()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_parent public.trades;
BEGIN
  IF NEW.parent_trade_id IS NULL THEN
    RETURN NEW;
  END IF;

  SELECT * INTO v_parent FROM public.trades WHERE id = NEW.parent_trade_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Parent trade % not found', NEW.parent_trade_id USING ERRCODE = 'PT404';
  END IF;
  IF v_parent.parent_trade_id IS NOT NULL THEN
    RAISE EXCEPTION 'Subtrades cannot have their own subtrades ("%" is already a subtrade).', v_parent.name
      USING ERRCODE = 'PT422';
  END IF;
  IF TG_OP = 'UPDATE' AND EXISTS (SELECT 1 FROM public.trades WHERE parent_trade_id = NEW.id) THEN
    RAISE EXCEPTION 'Trade "%" has subtrades, so it cannot become a subtrade itself.', NEW.name
      USING ERRCODE = 'PT422';
  END IF;

  NEW.phase := v_parent.phase;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_trades_hierarchy ON public.trades;
CREATE TRIGGER trg_trades_hierarchy
  BEFORE INSERT OR UPDATE OF parent_trade_id, phase ON public.trades
  FOR EACH ROW EXECUTE FUNCTION public.fn_trades_hierarchy();

-- B.2 Parent phase change flows down to its subtrades.
CREATE OR REPLACE FUNCTION public.fn_trades_cascade_phase()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  IF NEW.parent_trade_id IS NULL AND NEW.phase IS DISTINCT FROM OLD.phase THEN
    UPDATE public.trades SET phase = NEW.phase WHERE parent_trade_id = NEW.id AND phase <> NEW.phase;
  END IF;
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_trades_cascade_phase ON public.trades;
CREATE TRIGGER trg_trades_cascade_phase
  AFTER UPDATE OF phase ON public.trades
  FOR EACH ROW EXECUTE FUNCTION public.fn_trades_cascade_phase();


-- B.3 A trade with subtrades must be assigned through a subtrade.
--     Fires only when trade_id is set or changed, so existing rows that point
--     at a trade which later gets subtrades are never blocked.
CREATE OR REPLACE FUNCTION public.fn_enforce_leaf_trade()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_name TEXT;
BEGIN
  IF NEW.trade_id IS NULL THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.trade_id IS NOT DISTINCT FROM OLD.trade_id THEN
    RETURN NEW;
  END IF;
  IF EXISTS (SELECT 1 FROM public.trades WHERE parent_trade_id = NEW.trade_id AND is_active) THEN
    SELECT name INTO v_name FROM public.trades WHERE id = NEW.trade_id;
    RAISE EXCEPTION 'Trade "%" has subtrades — choose one of its subtrades.', v_name
      USING ERRCODE = 'PT422';
  END IF;
  RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.fn_enforce_leaf_trade() IS
  'Blocks assigning a trade that has active subtrades (one of the subtrades must be chosen). Attached to tasks, vendor_trades, task_templates and bid_templates; only fires when trade_id is set or changed.';

DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['tasks', 'vendor_trades', 'task_templates', 'bid_templates'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I', 'trg_' || t || '_leaf_trade', t);
      EXECUTE format(
        'CREATE TRIGGER %I BEFORE INSERT OR UPDATE OF trade_id ON public.%I FOR EACH ROW EXECUTE FUNCTION public.fn_enforce_leaf_trade()',
        'trg_' || t || '_leaf_trade', t);
    END IF;
  END LOOP;
END $$;


-- ============================================================================
-- SECTION 12.C: Trade usage + safe delete
-- ============================================================================

-- C.1 How many live records use a trade; C.2 delete or retire it (20261120 fix).
CREATE OR REPLACE FUNCTION public.fn_trade_usage(p_trade_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SET search_path = ''
AS $$
DECLARE
  v_tasks          BIGINT := 0;
  v_vendors        BIGINT := 0;
  v_task_templates BIGINT := 0;
  v_bid_templates  BIGINT := 0;
  v_budget_lines   BIGINT := 0;
  v_variances      BIGINT := 0;
  v_subtrades      BIGINT := 0;
BEGIN
  SELECT count(*) INTO v_tasks
    FROM public.tasks t
    JOIN public.projects p ON p.id = t.project_id
   WHERE t.trade_id = p_trade_id
     AND t.deleted_at IS NULL
     AND p.deleted_at IS NULL;

  SELECT count(*) INTO v_vendors
    FROM public.vendor_trades vt
    JOIN public.vendors v ON v.id = vt.vendor_id
   WHERE vt.trade_id = p_trade_id
     AND v.deleted_at IS NULL;

  SELECT count(*) INTO v_task_templates
    FROM public.task_templates
   WHERE trade_id = p_trade_id
     AND deleted_at IS NULL;

  SELECT count(*) INTO v_bid_templates
    FROM public.bid_templates
   WHERE trade_id = p_trade_id;

  -- Financial module tables: counted only when they exist.
  IF to_regclass('public.budget_template_lines') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.budget_template_lines WHERE trade_id = $1'
      INTO v_budget_lines USING p_trade_id;
  END IF;
  IF to_regclass('public.variance_lines') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.variance_lines WHERE trade_id = $1'
      INTO v_variances USING p_trade_id;
  END IF;

  SELECT count(*) INTO v_subtrades
    FROM public.trades
   WHERE parent_trade_id = p_trade_id
     AND is_active;

  RETURN jsonb_build_object(
    'tasks',                 v_tasks,
    'vendors',               v_vendors,
    'task_templates',        v_task_templates,
    'bid_templates',         v_bid_templates,
    'budget_template_lines', v_budget_lines,
    'variances',             v_variances,
    'subtrades',             v_subtrades,
    'total', v_tasks + v_vendors + v_task_templates + v_bid_templates
             + v_budget_lines + v_variances + v_subtrades
  );
END;
$$;

COMMENT ON FUNCTION public.fn_trade_usage(UUID) IS
  'Counts the live records that use a trade: tasks (not deleted, in a project that is not deleted), vendors (not deleted), task templates (not deleted), bid / budget templates, variances, and its active subtrades. Removed records are not counted. total = 0 means it can be edited or deleted.';


CREATE OR REPLACE FUNCTION public.fn_delete_trade(p_trade_id UUID)
RETURNS SETOF public.trades
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_trade public.trades;
  v_usage JSONB;
  v_parts TEXT;
  v_tag   TEXT;
BEGIN
  SELECT * INTO v_trade FROM public.trades WHERE id = p_trade_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Trade % not found', p_trade_id USING ERRCODE = 'PT404';
  END IF;

  v_usage := public.fn_trade_usage(p_trade_id);
  IF (v_usage ->> 'total')::bigint > 0 THEN
    SELECT string_agg(value || ' ' || replace(key, '_', ' '), ', ' ORDER BY key) INTO v_parts
      FROM jsonb_each_text(v_usage)
     WHERE key <> 'total' AND value::bigint > 0;
    RAISE EXCEPTION '"%" cannot be deleted because it is in use (%).', v_trade.name, v_parts
      USING ERRCODE = 'PT409';
  END IF;

  BEGIN
    DELETE FROM public.trades WHERE id = p_trade_id;
  EXCEPTION WHEN foreign_key_violation THEN
    -- Only removed records (deleted tasks / vendors / templates, retired
    -- subtrades) still reference it. Retire it: hidden everywhere, name freed.
    v_tag := ' [removed ' || left(p_trade_id::text, 8) || ']';
    UPDATE public.trades
       SET is_active = false,
           name      = left(name, 100 - length(v_tag)) || v_tag
     WHERE id = p_trade_id
     RETURNING * INTO v_trade;
  END;

  RETURN NEXT v_trade;
END;
$$;

COMMENT ON FUNCTION public.fn_delete_trade(UUID) IS
  'Deletes a trade or subtrade, row-locked, only when fn_trade_usage reports no live use (PT409 with the usage otherwise). Hard-deletes it when nothing references it; when only removed records still do, retires it instead (is_active = false, name suffixed " [removed xxxxxxxx]" so the name can be reused).';

REVOKE ALL ON FUNCTION public.fn_trade_usage(uuid)  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_delete_trade(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_trade_usage(uuid)  TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_delete_trade(uuid) TO service_role;
REVOKE ALL ON FUNCTION public.fn_trades_hierarchy()     FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_trades_cascade_phase() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_enforce_leaf_trade()   FROM PUBLIC, anon, authenticated;

-- ============================================================================
--  SECTION 13: FINANCIAL AUTOMATION — PHASE 3 CONTINGENCY ENGINE (v4.4, Nov 21 2026)
--  Same content as migrations/20261121_financial_phase3_contingency/001.
-- ============================================================================

-- ============================================================================
-- SECTION 13.A: projects — bidding checkpoint columns
-- ============================================================================
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS bidding_completed_at          TIMESTAMPTZ;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS bidding_completed_by          UUID;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS bidding_contingency_left_pct  DECIMAL(9,2);
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS bidding_completion_note       TEXT;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_projects_bidding_completed_by') THEN
    ALTER TABLE public.projects ADD CONSTRAINT fk_projects_bidding_completed_by
      FOREIGN KEY (bidding_completed_by) REFERENCES public.users(id) ON DELETE SET NULL;
  END IF;
END $$;

COMMENT ON COLUMN public.projects.bidding_completed_at         IS 'When the project manager marked bidding complete (checkpoint). NULL = bidding still open. Set only by fn_complete_bidding.';
COMMENT ON COLUMN public.projects.bidding_completed_by         IS 'Who marked bidding complete.';
COMMENT ON COLUMN public.projects.bidding_contingency_left_pct IS 'Contingency left as % of the contingency base at the moment bidding was marked complete.';
COMMENT ON COLUMN public.projects.bidding_completion_note      IS 'Optional note entered when bidding was marked complete.';


-- ============================================================================
-- SECTION 13.B: 3.1 CONTINGENCY CALCULATION
-- ============================================================================

-- B.1 Snapshot: contingency, base, % left and the checkpoint targets.
CREATE OR REPLACE FUNCTION private.fin_contingency_snapshot(p_project_id UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  WITH l AS (
    SELECT COALESCE(SUM(budget_amount) FILTER (WHERE line_type = 'contingency'), 0)                AS cont,
           COALESCE(SUM(budget_amount) FILTER (WHERE line_type NOT IN ('land', 'contingency')), 0) AS base,
           COALESCE(SUM(budget_amount) FILTER (WHERE line_type = 'land'), 0)                       AS land,
           COALESCE(SUM(budget_amount), 0)                                                         AS total
      FROM public.budget_lines
     WHERE project_id = p_project_id AND deleted_at IS NULL
  ),
  s AS (
    SELECT COALESCE((SELECT (value #>> '{}')::numeric FROM public.financial_settings
                      WHERE setting_key = 'bidding_target_contingency_percent'), 10) AS target,
           COALESCE((SELECT (value #>> '{}')::numeric FROM public.financial_settings
                      WHERE setting_key = 'bidding_escalation_percent'), 5)          AS esc
  )
  SELECT jsonb_build_object(
           'contingency',        l.cont,
           'base',               l.base,
           'land',               l.land,
           'total',              l.total,
           'left_percent',       CASE WHEN l.base > 0 THEN round(l.cont * 100 / l.base, 2) END,
           'target_percent',     s.target,
           'escalation_percent', s.esc)
    FROM l, s;
$$;

COMMENT ON FUNCTION private.fin_contingency_snapshot(UUID) IS
  'Contingency now, contingency base (total − land − contingency), % left (contingency ÷ base) and the bidding target / escalation % from financial_settings.';


-- B.2 Recalculate a DRAFT budget's contingency from its base.
CREATE OR REPLACE FUNCTION private.fin_recalc_draft_contingency(p_project_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
  v_line    public.budget_lines;
  v_pct     NUMERIC;
  v_total   NUMERIC;
  v_land    NUMERIC;
  v_others  NUMERIC;
  v_new     NUMERIC;
BEGIN
  SELECT * INTO v_project FROM public.projects WHERE id = p_project_id;
  IF NOT FOUND OR v_project.budget_status <> 'draft' OR v_project.bidding_completed_at IS NOT NULL THEN
    RETURN;
  END IF;

  SELECT * INTO v_line FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL
   FOR UPDATE;
  IF NOT FOUND THEN
    RETURN;
  END IF;

  v_pct := COALESCE(v_project.contingency_percent,
                    (SELECT (value #>> '{}')::numeric FROM public.financial_settings
                      WHERE setting_key = 'default_contingency_percent'),
                    15);
  v_total := CASE WHEN v_project.budget IS NOT NULL AND v_project.budget > 0 THEN v_project.budget END;

  SELECT COALESCE(SUM(budget_amount) FILTER (WHERE line_type = 'land'), 0),
         COALESCE(SUM(budget_amount) FILTER (WHERE line_type NOT IN ('land', 'contingency')), 0)
    INTO v_land, v_others
    FROM public.budget_lines
   WHERE project_id = p_project_id AND deleted_at IS NULL;

  IF v_total IS NOT NULL THEN
    -- base = total − land − contingency, contingency = pct × base
    v_new := round(GREATEST(v_total - v_land, 0) * v_pct / (100 + v_pct), 2);
  ELSE
    v_new := round(v_others * v_pct / 100, 2);
  END IF;

  IF v_new IS DISTINCT FROM v_line.budget_amount THEN
    -- The Unallocated trigger offsets this change, so the total stays put.
    UPDATE public.budget_lines SET budget_amount = v_new WHERE id = v_line.id;
  END IF;
END;
$$;

COMMENT ON FUNCTION private.fin_recalc_draft_contingency(UUID) IS
  'Draft budgets before bidding only: sets the contingency line to pct of the contingency base. Fixed total (project Budget set): (total − land) × pct / (100 + pct). Otherwise pct × (all lines − land − contingency). No-op for baselined budgets.';


-- B.3 Line trigger: a base change on a draft budget recalculates contingency.
CREATE OR REPLACE FUNCTION public.fn_budget_lines_recalc_contingency()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_status TEXT;
  v_budget NUMERIC;
BEGIN
  IF NEW.line_type = 'contingency' OR COALESCE(NEW.line_subtype, '') = 'unallocated' THEN
    RETURN NULL;
  END IF;

  SELECT budget_status, budget INTO v_status, v_budget FROM public.projects WHERE id = NEW.project_id;
  IF v_status IS DISTINCT FROM 'draft' THEN
    RETURN NULL;
  END IF;

  -- With a fixed total only land moves the base (other lines trade with
  -- Unallocated); without one, every line is part of the base.
  IF v_budget IS NOT NULL AND v_budget > 0 AND NEW.line_type <> 'land' THEN
    RETURN NULL;
  END IF;

  PERFORM private.fin_recalc_draft_contingency(NEW.project_id);
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_budget_lines_recalc_contingency ON public.budget_lines;
CREATE TRIGGER trg_budget_lines_recalc_contingency
  AFTER INSERT OR UPDATE OF budget_amount, deleted_at ON public.budget_lines
  FOR EACH ROW EXECUTE FUNCTION public.fn_budget_lines_recalc_contingency();

COMMENT ON FUNCTION public.fn_budget_lines_recalc_contingency() IS
  'Draft budgets: after a base line changes, recalculates contingency (fin_recalc_draft_contingency). Fires after trg_budget_lines_absorb_unallocated (alphabetical), so Unallocated absorbs both changes.';


-- B.4 Project trigger: Budget value or contingency % changed on a draft.
CREATE OR REPLACE FUNCTION public.fn_projects_recalc_draft_contingency()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_unalloc public.budget_lines;
BEGIN
  IF NEW.budget_status IS DISTINCT FROM 'draft' OR NEW.bidding_completed_at IS NOT NULL THEN
    RETURN NULL;
  END IF;

  -- A new project Budget value moves the total: Unallocated takes the change
  -- first, then contingency is recalculated from the new total.
  IF NEW.budget IS DISTINCT FROM OLD.budget
     AND COALESCE(OLD.budget, 0) > 0 AND COALESCE(NEW.budget, 0) > 0 THEN
    SELECT * INTO v_unalloc FROM public.budget_lines
     WHERE project_id = NEW.id AND line_subtype = 'unallocated' AND deleted_at IS NULL
     FOR UPDATE;
    IF FOUND THEN
      UPDATE public.budget_lines
         SET budget_amount = GREATEST(v_unalloc.budget_amount + (NEW.budget - OLD.budget), 0)
       WHERE id = v_unalloc.id;
    END IF;
  END IF;

  PERFORM private.fin_recalc_draft_contingency(NEW.id);
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_projects_recalc_draft_contingency ON public.projects;
CREATE TRIGGER trg_projects_recalc_draft_contingency
  AFTER UPDATE OF budget, contingency_percent ON public.projects
  FOR EACH ROW EXECUTE FUNCTION public.fn_projects_recalc_draft_contingency();

COMMENT ON FUNCTION public.fn_projects_recalc_draft_contingency() IS
  'Draft budgets: when the project Budget value or contingency % changes, Unallocated takes the change in total and contingency is recalculated.';


-- B.5 Admin: set the project contingency %.
CREATE OR REPLACE FUNCTION public.fn_set_project_contingency_percent(
  p_project_id UUID,
  p_percent    NUMERIC,
  p_actor      UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;
  IF p_percent IS NOT NULL AND (p_percent < 0 OR p_percent > 100) THEN
    RAISE EXCEPTION 'Contingency %% must be between 0 and 100 (got %)', p_percent USING ERRCODE = 'PT422';
  END IF;

  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.budget_status = 'baselined' THEN
    RAISE EXCEPTION 'The contingency %% is fixed once the budget is baselined. Raise contingency with an executive-approved top-up instead.'
      USING ERRCODE = 'PT409';
  END IF;

  UPDATE public.projects SET contingency_percent = p_percent WHERE id = p_project_id;

  RETURN private.fin_contingency_snapshot(p_project_id)
         || jsonb_build_object('contingency_percent', p_percent);
END;
$$;

COMMENT ON FUNCTION public.fn_set_project_contingency_percent(UUID, NUMERIC, UUID) IS
  'Sets projects.contingency_percent (NULL = the default from financial_settings) before a budget exists or while it is a draft; a draft budget''s contingency is recalculated at once. PT409 after baseline (use a top-up).';


-- ============================================================================
-- SECTION 13.C: 3.3 CONTINGENCY LEDGER VIEW
-- ============================================================================
CREATE OR REPLACE VIEW public.v_contingency_ledger
WITH (security_invoker = true) AS
SELECT
  cl.id,
  cl.entry_no,
  cl.project_id,
  cl.contingency_line_id,
  cl.contingency_bucket_id,
  cb.bucket_kind,
  cl.movement_type,
  cl.amount,
  CASE WHEN cl.amount > 0 THEN 'in' WHEN cl.amount < 0 THEN 'out' ELSE 'none' END AS direction,
  cl.balance_before,
  cl.balance_after,
  cl.source_budget_line_id,
  sl.name       AS source_line_name,
  sl.line_type  AS source_line_type,
  cl.variance_line_id,
  cl.award_id,
  cl.actor_user_id,
  u.full_name   AS actor_name,
  u.email       AS actor_email,
  cl.reason,
  cl.created_at
FROM public.contingency_ledger cl
LEFT JOIN public.contingency_buckets cb ON cb.id = cl.contingency_bucket_id
LEFT JOIN public.budget_lines        sl ON sl.id = cl.source_budget_line_id
LEFT JOIN public.users               u  ON u.id  = cl.actor_user_id;

COMMENT ON VIEW public.v_contingency_ledger IS
  'Contingency ledger read surface: every movement with its source line, direction (in / out), user, bucket kind and running balance (balance_after). Order by entry_no. security_invoker = true.';

GRANT SELECT ON public.v_contingency_ledger TO authenticated, service_role;


-- ============================================================================
-- SECTION 13.D: 3.4 BIDDING-COMPLETE CHECKPOINT
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_complete_bidding(
  p_project_id UUID,
  p_actor      UUID,
  p_note       TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project  public.projects;
  v_snap     JSONB;
  v_left     NUMERIC;
  v_target   NUMERIC;
  v_esc      NUMERIC;
  v_outcome  TEXT;
  v_severity TEXT;
  v_alert    UUID;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.budget_status <> 'baselined' THEN
    RAISE EXCEPTION 'Baseline the budget before marking bidding complete, so bid differences are measured against contingency.'
      USING ERRCODE = 'PT409';
  END IF;
  IF v_project.bidding_completed_at IS NOT NULL THEN
    RAISE EXCEPTION 'Bidding is already marked complete for this project.' USING ERRCODE = 'PT409';
  END IF;

  v_snap   := private.fin_contingency_snapshot(p_project_id);
  v_left   := (v_snap ->> 'left_percent')::numeric;
  v_target := (v_snap ->> 'target_percent')::numeric;
  v_esc    := (v_snap ->> 'escalation_percent')::numeric;

  v_outcome := CASE
                 WHEN v_left IS NULL     THEN 'no_base'
                 WHEN v_left <= v_esc    THEN 'escalated'
                 WHEN v_left <  v_target THEN 'below_target'
                 ELSE 'on_target'
               END;

  -- One open checkpoint alert per project: an older one is superseded.
  UPDATE public.financial_alerts
     SET status = 'superseded', updated_at = NOW()
   WHERE project_id = p_project_id AND alert_type = 'bidding_checkpoint' AND status = 'open';

  IF v_outcome IN ('escalated', 'below_target') THEN
    v_severity := CASE WHEN v_outcome = 'escalated' THEN 'critical' ELSE 'warning' END;
    INSERT INTO public.financial_alerts (
      project_id, alert_type, severity, contingency_left_pct, contingency_remaining, message
    ) VALUES (
      p_project_id, 'bidding_checkpoint', v_severity, v_left, (v_snap ->> 'contingency')::numeric,
      format('Bidding complete with %s%% contingency left (target %s%%, escalation at %s%%).', v_left, v_target, v_esc)
    )
    RETURNING id INTO v_alert;
  END IF;

  -- Above target: recorded only. Contingency is never released early.
  UPDATE public.projects
     SET bidding_completed_at         = NOW(),
         bidding_completed_by         = p_actor,
         bidding_contingency_left_pct = v_left,
         bidding_completion_note      = NULLIF(btrim(COALESCE(p_note, '')), '')
   WHERE id = p_project_id;

  RETURN v_snap || jsonb_build_object('outcome', v_outcome, 'severity', v_severity, 'alert_id', v_alert);
END;
$$;

COMMENT ON FUNCTION public.fn_complete_bidding(UUID, UUID, TEXT) IS
  'Bidding-complete checkpoint (baselined budgets): records who / when and the contingency left % of the base. Below target → warning alert; at or below the escalation % (or negative) → critical alert for executive escalation; at or above target → recorded only, nothing released. Returns the snapshot and the outcome.';


CREATE OR REPLACE FUNCTION public.fn_reopen_bidding(
  p_project_id UUID,
  p_actor      UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;
  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.bidding_completed_at IS NULL THEN
    RAISE EXCEPTION 'Bidding is not marked complete for this project.' USING ERRCODE = 'PT409';
  END IF;

  UPDATE public.financial_alerts
     SET status = 'resolved', resolved_at = NOW(), updated_at = NOW()
   WHERE project_id = p_project_id AND alert_type = 'bidding_checkpoint' AND status = 'open';

  UPDATE public.projects
     SET bidding_completed_at = NULL, bidding_completed_by = NULL,
         bidding_contingency_left_pct = NULL, bidding_completion_note = NULL
   WHERE id = p_project_id;

  RETURN private.fin_contingency_snapshot(p_project_id);
END;
$$;

COMMENT ON FUNCTION public.fn_reopen_bidding(UUID, UUID) IS
  'Admin undo of the bidding-complete checkpoint: clears the completion and resolves its open alert.';


-- ============================================================================
-- SECTION 13.E: 3.5 TOP-UP APPROVAL also raises the project Budget value
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_approve_contingency_top_up(
  p_bucket_id        UUID,
  p_approver         UUID,
  p_approve          BOOLEAN,
  p_approved_amount  NUMERIC DEFAULT NULL,
  p_note             TEXT DEFAULT NULL
)
RETURNS SETOF public.contingency_buckets
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_bucket  public.contingency_buckets;
  v_amount  NUMERIC;
BEGIN
  IF p_approver IS NULL OR p_approve IS NULL THEN
    RAISE EXCEPTION 'p_approver and p_approve are required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_bucket FROM public.contingency_buckets WHERE id = p_bucket_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Contingency bucket % not found', p_bucket_id USING ERRCODE = 'PT404';
  END IF;

  IF NOT private.user_has_role(p_approver, 'executive') THEN
    RAISE EXCEPTION 'Only an executive can approve or reject a contingency top-up' USING ERRCODE = 'PT403';
  END IF;

  -- Lock order: project → bucket → lines.
  PERFORM private.fin_lock_project(v_bucket.project_id, TRUE, FALSE);
  SELECT * INTO v_bucket FROM public.contingency_buckets WHERE id = p_bucket_id FOR UPDATE;

  IF v_bucket.bucket_kind <> 'top_up' THEN
    RAISE EXCEPTION 'Bucket % is not a top-up request', p_bucket_id USING ERRCODE = 'PT422';
  END IF;
  IF v_bucket.status <> 'pending' THEN
    RAISE EXCEPTION 'Top-up request % is already %', p_bucket_id, v_bucket.status USING ERRCODE = 'PT409';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  IF NOT p_approve THEN
    UPDATE public.contingency_buckets
       SET status = 'rejected', decided_by = p_approver, decided_at = NOW(), decision_note = p_note
     WHERE id = p_bucket_id
     RETURNING * INTO v_bucket;
  ELSE
    v_amount := COALESCE(p_approved_amount, v_bucket.requested_amount);
    IF v_amount <= 0 THEN
      RAISE EXCEPTION 'Approved amount must be greater than zero' USING ERRCODE = 'PT422';
    END IF;

    -- The ONLY path (besides baseline) that changes the approved total. The
    -- project's Budget value follows, so both show the same total.
    UPDATE public.projects
       SET approved_budget_total = approved_budget_total + v_amount,
           budget                = CASE WHEN budget IS NOT NULL THEN budget + v_amount ELSE budget END
     WHERE id = v_bucket.project_id;

    PERFORM private.fin_move_contingency(
      v_bucket.project_id, v_amount, 'top_up', p_approver,
      COALESCE(p_note, v_bucket.reason), NULL, NULL, NULL, p_bucket_id);

    UPDATE public.contingency_buckets
       SET status = 'approved', approved_amount = v_amount,
           decided_by = p_approver, decided_at = NOW(), decision_note = p_note
     WHERE id = p_bucket_id
     RETURNING * INTO v_bucket;
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_bucket;
END;
$$;

COMMENT ON FUNCTION public.fn_approve_contingency_top_up(UUID, UUID, BOOLEAN, NUMERIC, TEXT) IS
  'A13: executive-only (PT403 otherwise). Approve: contingency line + amount, projects.approved_budget_total + amount (the only way the total grows after baseline) and the project Budget value + amount, top_up ledger row tied to the bucket. Reject: decision recorded, no money moves.';


-- ============================================================================
-- SECTION 13.F: PRIVILEGES
-- ============================================================================
-- The private helpers run inside triggers as the CALLING role, so the roles
-- that write budgets need EXECUTE (the private schema is not exposed by the API).
REVOKE ALL ON FUNCTION private.fin_contingency_snapshot(uuid)                  FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.fin_recalc_draft_contingency(uuid)              FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.fin_contingency_snapshot(uuid)               TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.fin_recalc_draft_contingency(uuid)           TO authenticated, service_role;
REVOKE ALL ON FUNCTION public.fn_budget_lines_recalc_contingency()             FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_projects_recalc_draft_contingency()           FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_set_project_contingency_percent(uuid, numeric, uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_complete_bidding(uuid, uuid, text)            FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_reopen_bidding(uuid, uuid)                    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_approve_contingency_top_up(uuid, uuid, boolean, numeric, text) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.fn_set_project_contingency_percent(uuid, numeric, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_complete_bidding(uuid, uuid, text)            TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_reopen_bidding(uuid, uuid)                    TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_approve_contingency_top_up(uuid, uuid, boolean, numeric, text) TO service_role;


-- ============================================================================
-- SECTION 13.G: VERSION MARKER
-- ============================================================================
INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.4.0 (20261121_financial_phase3_contingency)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;


-- ############################################################################
--
--  SECTION 14: PHASE 4 VARIANCE LINE MANAGEMENT (v4.5)
--
--  Source of truth for EXISTING databases: the idempotent migration
--    database/migrations/20261125_financial_phase4_variances/001_variance_management.sql
--  Same DDL minus BEGIN/COMMIT and the RLS part (in rls_policies.sql).
--  Replaces four Phase 1 functions from Section 9 (CREATE OR REPLACE).
--
-- ############################################################################

-- ============================================================================
-- SECTION A: variance_events (append-only history)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.variance_events (
  id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  event_no       BIGINT        GENERATED ALWAYS AS IDENTITY UNIQUE,
  variance_id    UUID          NOT NULL REFERENCES public.variance_lines(id) ON DELETE RESTRICT,
  project_id     UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  event_type     VARCHAR(30)   NOT NULL
                               CHECK (event_type IN ('created', 'amount_changed', 'details_changed', 'resubmitted',
                                                     'routed_to_manager', 'approved', 'rejected', 'cancelled')),
  amount_before  DECIMAL(15,2),
  amount_after   DECIMAL(15,2),
  actor_user_id  UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  note           TEXT,
  created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_variance_events_variance ON public.variance_events (variance_id, event_no);
CREATE INDEX IF NOT EXISTS idx_variance_events_project  ON public.variance_events (project_id);

COMMENT ON TABLE public.variance_events IS
  'Append-only history of a variance: estimate, edits, approvals, rejection, cancellation. Order by event_no.';

CREATE OR REPLACE FUNCTION public.fn_block_variance_event_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  RAISE EXCEPTION 'Variance history is append-only and cannot be changed.' USING ERRCODE = 'PT403';
END;
$$;

DROP TRIGGER IF EXISTS trg_variance_events_immutable ON public.variance_events;
CREATE TRIGGER trg_variance_events_immutable
  BEFORE UPDATE OR DELETE ON public.variance_events
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_variance_event_mutation();

DROP TRIGGER IF EXISTS trg_variance_events_no_truncate ON public.variance_events;
CREATE TRIGGER trg_variance_events_no_truncate
  BEFORE TRUNCATE ON public.variance_events
  FOR EACH STATEMENT EXECUTE FUNCTION public.fn_block_variance_event_mutation();

-- Every variance starts its history, whichever procedure created it
-- (fn_create_variance or an invoice overage).
CREATE OR REPLACE FUNCTION public.fn_variance_created_event()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_after, actor_user_id, note)
  VALUES (NEW.id, NEW.project_id, 'created', NEW.estimated_amount, NEW.created_by, NEW.description);
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_variance_lines_created_event ON public.variance_lines;
CREATE TRIGGER trg_variance_lines_created_event
  AFTER INSERT ON public.variance_lines
  FOR EACH ROW EXECUTE FUNCTION public.fn_variance_created_event();

INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_after, actor_user_id, note, created_at)
SELECT v.id, v.project_id, 'created', v.estimated_amount, v.created_by, v.description, v.created_at
  FROM public.variance_lines v
 WHERE NOT EXISTS (SELECT 1 FROM public.variance_events e WHERE e.variance_id = v.id AND e.event_type = 'created');


-- ============================================================================
-- SECTION B: GUARDRAIL RECALCULATION (after every contingency movement)
-- ============================================================================
-- left % = contingency now ÷ contingency funded (initial + approved top-ups).
CREATE OR REPLACE FUNCTION private.fin_recalc_guardrails(p_project_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_cont    NUMERIC;
  v_funded  NUMERIC;
  v_left    NUMERIC;
  v_near    NUMERIC;
  v_type    TEXT;
  v_active  BOOLEAN;
  v_msg     TEXT;
BEGIN
  SELECT budget_amount INTO v_cont FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL;
  IF v_cont IS NULL THEN
    RETURN;
  END IF;

  SELECT COALESCE(SUM(approved_amount), 0) INTO v_funded
    FROM public.contingency_buckets WHERE project_id = p_project_id AND status = 'approved';
  v_near := COALESCE((SELECT (value #>> '{}')::numeric FROM public.financial_settings
                       WHERE setting_key = 'contingency_near_zero_percent'), 5);
  -- Clamped to the DECIMAL(7,2) alert column.
  v_left := CASE WHEN v_funded > 0
                 THEN GREATEST(LEAST(round(v_cont * 100 / v_funded, 2), 99999.99), -99999.99) END;

  FOREACH v_type IN ARRAY ARRAY['contingency_near_zero', 'contingency_negative'] LOOP
    IF v_type = 'contingency_negative' THEN
      v_active := v_cont < 0;
      v_msg    := format('Contingency is negative: %s.', v_cont);
    ELSE
      v_active := v_cont >= 0 AND v_left IS NOT NULL AND v_left <= v_near;
      v_msg    := format('Contingency is nearly used up: %s left (%s%% of the funded contingency, alert at %s%%).',
                         v_cont, v_left, v_near);
    END IF;

    IF v_active THEN
      UPDATE public.financial_alerts
         SET contingency_left_pct = v_left, contingency_remaining = v_cont, message = v_msg
       WHERE project_id = p_project_id AND alert_type = v_type
         AND status IN ('open', 'acknowledged', 'proceed_approved', 'on_hold');
      IF NOT FOUND THEN
        INSERT INTO public.financial_alerts (project_id, alert_type, severity, contingency_left_pct, contingency_remaining, message)
        VALUES (p_project_id, v_type,
                CASE WHEN v_type = 'contingency_negative' THEN 'critical' ELSE 'urgent' END,
                v_left, v_cont, v_msg);
      END IF;
    ELSE
      UPDATE public.financial_alerts SET status = 'resolved', resolved_at = NOW()
       WHERE project_id = p_project_id AND alert_type = v_type
         AND status IN ('open', 'acknowledged', 'proceed_approved', 'on_hold');
    END IF;
  END LOOP;
END;
$$;

COMMENT ON FUNCTION private.fin_recalc_guardrails(UUID) IS
  'Opens / refreshes / resolves the near-zero and negative contingency alerts of a project.';

CREATE OR REPLACE FUNCTION public.fn_ledger_recalc_guardrails()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  PERFORM private.fin_recalc_guardrails(NEW.project_id);
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_contingency_ledger_guardrails ON public.contingency_ledger;
CREATE TRIGGER trg_contingency_ledger_guardrails
  AFTER INSERT ON public.contingency_ledger
  FOR EACH ROW EXECUTE FUNCTION public.fn_ledger_recalc_guardrails();


-- ============================================================================
-- SECTION C: 4.5 LOCK RULES (Phase 1 functions; locked / frozen = PT422)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_guard_budget_lines()
RETURNS TRIGGER AS $$
DECLARE
  v_auth        BOOLEAN := private.fin_write_authorized();
  v_baselined   BOOLEAN;
  v_task        RECORD;
  v_parent_proj UUID;
BEGIN
  -- Immutable identity columns
  IF TG_OP = 'UPDATE' THEN
    IF NEW.project_id IS DISTINCT FROM OLD.project_id THEN
      RAISE EXCEPTION 'A budget line cannot move to another project (line %)', OLD.id USING ERRCODE = 'PT422';
    END IF;
    IF NEW.line_type IS DISTINCT FROM OLD.line_type THEN
      RAISE EXCEPTION 'line_type cannot change after a line is created (line %: % → %). Remove the line and add a new one.',
        OLD.id, OLD.line_type, NEW.line_type USING ERRCODE = 'PT422';
    END IF;
  END IF;

  -- Task consistency
  IF NEW.task_id IS NOT NULL
     AND (TG_OP = 'INSERT' OR NEW.task_id IS DISTINCT FROM OLD.task_id) THEN
    SELECT project_id, bid_type, deleted_at INTO v_task FROM public.tasks WHERE id = NEW.task_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Task % not found', NEW.task_id USING ERRCODE = 'PT404';
    END IF;
    IF v_task.project_id <> NEW.project_id THEN
      RAISE EXCEPTION 'Task % belongs to project %, not %', NEW.task_id, v_task.project_id, NEW.project_id
        USING ERRCODE = 'PT422';
    END IF;
    IF (NEW.line_type = 'bid_activity' AND v_task.bid_type NOT IN ('competitive', 'direct_assign'))
       OR (NEW.line_type = 'internal_tm' AND v_task.bid_type <> 'internal') THEN
      RAISE EXCEPTION 'Line type % does not match task bid_type % (bid_activity ↔ competitive/direct_assign, internal_tm ↔ internal)',
        NEW.line_type, v_task.bid_type USING ERRCODE = 'PT422';
    END IF;
  END IF;

  -- Parent consistency
  IF NEW.parent_line_id IS NOT NULL
     AND (TG_OP = 'INSERT' OR NEW.parent_line_id IS DISTINCT FROM OLD.parent_line_id) THEN
    SELECT project_id INTO v_parent_proj FROM public.budget_lines WHERE id = NEW.parent_line_id;
    IF v_parent_proj IS DISTINCT FROM NEW.project_id THEN
      RAISE EXCEPTION 'Parent line % is not in project %', NEW.parent_line_id, NEW.project_id USING ERRCODE = 'PT422';
    END IF;
  END IF;

  -- Authoritative writer: everything below is the procedures' business.
  IF v_auth THEN
    RETURN NEW;
  END IF;

  -- Lock rules (always)
  IF TG_OP = 'UPDATE' AND OLD.is_locked THEN
    IF NEW.is_locked = FALSE
       OR NEW.budget_amount    IS DISTINCT FROM OLD.budget_amount
       OR NEW.committed_amount IS DISTINCT FROM OLD.committed_amount
       OR NEW.award_id         IS DISTINCT FROM OLD.award_id
       OR NEW.contract_id      IS DISTINCT FROM OLD.contract_id THEN
      RAISE EXCEPTION 'Budget line % is locked (contract executed). Locked amounts cannot be edited; use a variance line.',
        OLD.id USING ERRCODE = 'PT422';
    END IF;
  END IF;

  SELECT budget_status = 'baselined' INTO v_baselined FROM public.projects WHERE id = NEW.project_id;

  IF COALESCE(v_baselined, FALSE) THEN
    IF TG_OP = 'INSERT' THEN
      IF NEW.budget_amount <> 0 OR NEW.committed_amount <> 0 OR NEW.award_id IS NOT NULL THEN
        RAISE EXCEPTION 'Project budget is baselined: a new line must start at $0 and be funded through a financial procedure (total budget must stay flat).'
          USING ERRCODE = 'PT409';
      END IF;
    ELSE
      IF NEW.budget_amount     IS DISTINCT FROM OLD.budget_amount
         OR NEW.committed_amount  IS DISTINCT FROM OLD.committed_amount
         OR NEW.award_id          IS DISTINCT FROM OLD.award_id
         OR NEW.original_estimate IS DISTINCT FROM OLD.original_estimate THEN
        RAISE EXCEPTION 'Project budget is baselined: amounts on line % change only through financial procedures (bid, variance, top-up) so contingency and the ledger stay in step.',
          OLD.id USING ERRCODE = 'PT409';
      END IF;
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION public.fn_guard_variance_lines()
RETURNS TRIGGER AS $$
BEGIN
  IF private.fin_write_authorized() THEN
    RETURN NEW;
  END IF;

  IF TG_OP = 'INSERT' THEN
    RAISE EXCEPTION 'Variances are created only through fn_create_variance (it moves contingency and writes the ledger).'
      USING ERRCODE = 'PT409';
  END IF;

  IF OLD.status IN ('approved', 'cancelled') THEN
    RAISE EXCEPTION 'Variance % is % and frozen. Create a new variance instead.', OLD.id, OLD.status
      USING ERRCODE = 'PT422';
  END IF;

  IF NEW.status = 'cancelled' THEN
    RAISE EXCEPTION 'Cancel a variance through fn_adjust_variance(…, 0, …) so its amount returns to contingency.'
      USING ERRCODE = 'PT409';
  END IF;

  IF NEW.project_id IS DISTINCT FROM OLD.project_id
     OR NEW.budget_line_id IS DISTINCT FROM OLD.budget_line_id
     OR NEW.parent_budget_line_id IS DISTINCT FROM OLD.parent_budget_line_id
     OR NEW.estimated_amount IS DISTINCT FROM OLD.estimated_amount
     OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
    RAISE EXCEPTION 'Variance identity / history columns cannot change (variance %).', OLD.id USING ERRCODE = 'PT422';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION public.fn_apply_bid_to_line(
  p_budget_line_id UUID,
  p_award_id       UUID,
  p_amount         NUMERIC,
  p_actor          UUID
)
RETURNS SETOF public.budget_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_line     public.budget_lines;
  v_award    public.awards;
  v_project  public.projects;
  v_delta    NUMERIC;
  v_result   public.budget_lines;
BEGIN
  IF p_amount IS NULL OR p_amount < 0 THEN
    RAISE EXCEPTION 'Bid amount must be zero or more (got %)', p_amount USING ERRCODE = 'PT422';
  END IF;
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_budget_line_id;
  IF NOT FOUND OR v_line.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Budget line % not found', p_budget_line_id USING ERRCODE = 'PT404';
  END IF;

  -- Lock order everywhere: project → lines (avoids deadlocks).
  v_project := private.fin_lock_project(v_line.project_id, FALSE, TRUE);
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_budget_line_id FOR UPDATE;

  IF v_line.line_type <> 'bid_activity' THEN
    RAISE EXCEPTION 'Bids apply only to bid_activity lines (line % is %)', v_line.id, v_line.line_type
      USING ERRCODE = 'PT422';
  END IF;
  IF v_line.is_locked THEN
    RAISE EXCEPTION 'Budget line % is locked (contract executed). Locked bid amounts cannot be edited; use a variance.', v_line.id USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_award FROM public.awards WHERE id = p_award_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Award % not found', p_award_id USING ERRCODE = 'PT404';
  END IF;
  IF v_award.task_id IS DISTINCT FROM v_line.task_id THEN
    RAISE EXCEPTION 'Award % is for task %, not this line''s task %', p_award_id, v_award.task_id, v_line.task_id
      USING ERRCODE = 'PT422';
  END IF;
  IF v_award.status IN ('declined_by_vendor', 'cancelled') THEN
    RAISE EXCEPTION 'Award % is % and cannot be applied', p_award_id, v_award.status USING ERRCODE = 'PT409';
  END IF;
  IF v_line.award_id IS NOT NULL AND v_line.award_id <> p_award_id THEN
    RAISE EXCEPTION 'Line % already carries award %; reverse it first', v_line.id, v_line.award_id
      USING ERRCODE = 'PT409';
  END IF;

  -- Idempotent retry: same award, same amount → nothing to do.
  IF v_line.award_id = p_award_id AND v_line.budget_amount = p_amount AND v_line.committed_amount = p_amount THEN
    RETURN NEXT v_line;
    RETURN;
  END IF;

  v_delta := p_amount - v_line.budget_amount;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  UPDATE public.budget_lines
     SET pre_award_budget_amount = CASE WHEN award_id IS NULL THEN budget_amount ELSE pre_award_budget_amount END,
         budget_amount           = p_amount,
         committed_amount        = p_amount,
         award_id                = p_award_id,
         updated_by              = p_actor
   WHERE id = v_line.id
   RETURNING * INTO v_result;

  -- Draft budgets have no ledger yet: the line simply takes the bid.
  IF v_project.budget_status = 'baselined' AND v_delta <> 0 THEN
    PERFORM private.fin_move_contingency(
      v_line.project_id, -v_delta,
      CASE WHEN v_delta > 0 THEN 'bid_overrun' ELSE 'bid_savings' END,
      p_actor,
      format('Bid applied to "%s": %s → %s', v_line.name, v_line.budget_amount, p_amount),
      v_line.id, NULL, p_award_id, NULL);
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_result;
END;
$$;


-- ============================================================================
-- SECTION D: 4.2 EDIT / CANCEL
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_adjust_variance(
  p_variance_id UUID,
  p_new_amount  NUMERIC,
  p_actor       UUID,
  p_reason      TEXT DEFAULT NULL
)
RETURNS SETOF public.variance_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_variance  public.variance_lines;
  v_line      public.budget_lines;
  v_delta     NUMERIC;
BEGIN
  IF p_new_amount IS NULL OR p_new_amount < 0 THEN
    RAISE EXCEPTION 'New variance amount must be zero (cancel) or more (got %)', p_new_amount USING ERRCODE = 'PT422';
  END IF;
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;

  SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id;
  IF NOT FOUND OR v_variance.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Variance % not found', p_variance_id USING ERRCODE = 'PT404';
  END IF;

  -- Adjustments may be needed on a held project to free contingency, so no hold block.
  PERFORM private.fin_lock_project(v_variance.project_id, TRUE, FALSE);
  SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id FOR UPDATE;
  SELECT * INTO v_line     FROM public.budget_lines   WHERE id = v_variance.budget_line_id FOR UPDATE;

  IF v_variance.status NOT IN ('draft', 'pending_approval', 'rejected') THEN
    RAISE EXCEPTION 'This variance is % and can no longer be changed. Create a new variance instead.', v_variance.status
      USING ERRCODE = 'PT422';
  END IF;

  v_delta := p_new_amount - v_line.budget_amount;

  -- An invoice overage is the invoice's own amount: it cannot drift from it.
  IF v_delta <> 0 AND EXISTS (SELECT 1 FROM public.payment_approvals
                               WHERE budget_line_id = v_line.id AND internal_invoice_id IS NOT NULL) THEN
    RAISE EXCEPTION 'This variance comes from an invoice, so its amount cannot be changed or cancelled here.'
      USING ERRCODE = 'PT422';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  -- A changed amount restarts the approval: earlier sign-offs were for the old one.
  IF v_delta <> 0 THEN
    UPDATE public.payment_approvals SET status = 'cancelled'
     WHERE budget_line_id = v_line.id AND status IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive');
    UPDATE public.budget_lines SET approval_state = 'not_requested'
     WHERE id = v_line.id AND approval_state <> 'not_requested';
  END IF;

  IF p_new_amount = 0 THEN
    -- Cancel: return the full amount, retire the line.
    UPDATE public.budget_lines
       SET budget_amount = 0, deleted_at = NOW(), updated_by = p_actor
     WHERE id = v_line.id;

    UPDATE public.variance_lines SET status = 'cancelled'
     WHERE id = p_variance_id RETURNING * INTO v_variance;

    IF v_delta <> 0 THEN
      PERFORM private.fin_move_contingency(
        v_variance.project_id, -v_delta, 'variance_cancelled', p_actor,
        COALESCE(p_reason, 'Variance cancelled'), v_line.id, p_variance_id, NULL, NULL);
    END IF;
    INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_before, amount_after, actor_user_id, note)
    VALUES (p_variance_id, v_variance.project_id, 'cancelled', v_line.budget_amount, 0, p_actor, p_reason);
  ELSIF v_delta <> 0 THEN
    UPDATE public.budget_lines
       SET budget_amount = p_new_amount, updated_by = p_actor
     WHERE id = v_line.id;

    PERFORM private.fin_move_contingency(
      v_variance.project_id, -v_delta, 'variance_adjusted', p_actor,
      COALESCE(p_reason, format('Variance adjusted %s → %s', v_line.budget_amount, p_new_amount)),
      v_line.id, p_variance_id, NULL, NULL);
    INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_before, amount_after, actor_user_id, note)
    VALUES (p_variance_id, v_variance.project_id, 'amount_changed', v_line.budget_amount, p_new_amount, p_actor, p_reason);

    SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id;
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN NEXT v_variance;
END;
$$;

COMMENT ON FUNCTION public.fn_adjust_variance(UUID, NUMERIC, UUID, TEXT) IS
  'Changes a not-yet-approved variance amount; the difference flows back to (or out of) contingency with a ledger row and a history event, and any approval in progress restarts. 0 cancels. Approved / cancelled = PT422.';


-- Amount and details together, in one transaction. A rejected variance goes
-- back to pending approval when it is edited.
CREATE OR REPLACE FUNCTION public.fn_edit_variance(
  p_variance_id UUID,
  p_amount      NUMERIC,
  p_description TEXT,
  p_trade_id    UUID,
  p_vendor_id   UUID,
  p_actor       UUID,
  p_reason      TEXT DEFAULT NULL
)
RETURNS SETOF public.variance_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_old  public.variance_lines;
  v_new  public.variance_lines;
BEGIN
  IF p_amount IS NULL OR p_amount <= 0 THEN
    RAISE EXCEPTION 'Variance amount must be greater than zero. To drop the variance, cancel it.' USING ERRCODE = 'PT422';
  END IF;
  IF btrim(COALESCE(p_description, '')) = '' THEN
    RAISE EXCEPTION 'A variance needs a description' USING ERRCODE = 'PT422';
  END IF;

  -- Locks, checks the status, moves the money.
  PERFORM * FROM public.fn_adjust_variance(p_variance_id, p_amount, p_actor, p_reason);
  SELECT * INTO v_old FROM public.variance_lines WHERE id = p_variance_id;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  UPDATE public.variance_lines
     SET description      = btrim(p_description),
         trade_id         = p_trade_id,
         vendor_id        = p_vendor_id,
         status           = 'pending_approval',
         rejected_by      = NULL,
         rejected_at      = NULL,
         rejection_reason = NULL
   WHERE id = p_variance_id
   RETURNING * INTO v_new;

  IF v_old.description IS DISTINCT FROM v_new.description
     OR v_old.trade_id IS DISTINCT FROM v_new.trade_id
     OR v_old.vendor_id IS DISTINCT FROM v_new.vendor_id THEN
    UPDATE public.budget_lines
       SET name = left('Variance: ' || v_new.description, 255), description = v_new.description, updated_by = p_actor
     WHERE id = v_new.budget_line_id;
    -- A first sign-off was for the old details: start the approval again.
    -- (A pending invoice request has no sign-off yet, so it stays.)
    UPDATE public.payment_approvals SET status = 'cancelled'
     WHERE budget_line_id = v_new.budget_line_id AND status IN ('field_approved', 'awaiting_manager', 'awaiting_executive');
    UPDATE public.payment_approvals SET vendor_id = v_new.vendor_id
     WHERE budget_line_id = v_new.budget_line_id AND status = 'pending' AND internal_invoice_id IS NULL;
    INSERT INTO public.variance_events (variance_id, project_id, event_type, actor_user_id, note)
    VALUES (p_variance_id, v_new.project_id, 'details_changed', p_actor, p_reason);
  END IF;

  UPDATE public.budget_lines SET approval_state = 'not_requested', updated_by = p_actor
   WHERE id = v_new.budget_line_id AND approval_state <> 'not_requested'
     AND NOT EXISTS (SELECT 1 FROM public.payment_approvals pa
                      WHERE pa.budget_line_id = v_new.budget_line_id
                        AND pa.status IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive'));

  IF v_old.status = 'rejected' THEN
    INSERT INTO public.variance_events (variance_id, project_id, event_type, actor_user_id, note)
    VALUES (p_variance_id, v_new.project_id, 'resubmitted', p_actor, p_reason);
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_new;
END;
$$;

COMMENT ON FUNCTION public.fn_edit_variance(UUID, NUMERIC, TEXT, UUID, UUID, UUID, TEXT) IS
  'Edits a not-yet-approved variance (amount, description, trade, vendor) in one transaction; a rejected one returns to pending approval.';


-- ============================================================================
-- SECTION E: 4.3 APPROVE FOR PAYMENT / REJECT
-- ============================================================================
-- Who gets the second approval: the person's manager, else the project's
-- manager. Each is replaced by an active delegate or, when unavailable, by the
-- standing backup. NULL = nobody specific: any manager may approve.
CREATE OR REPLACE FUNCTION private.fin_route_manager(p_from_user UUID, p_project_id UUID, p_exclude UUID[])
RETURNS UUID
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_manager   UUID;
  v_candidate UUID;
BEGIN
  FOREACH v_manager IN ARRAY ARRAY[
    (SELECT reports_to FROM public.users WHERE id = p_from_user),
    (SELECT manager_id FROM public.projects WHERE id = p_project_id)
  ] LOOP
    CONTINUE WHEN v_manager IS NULL;
    FOREACH v_candidate IN ARRAY ARRAY[
      (SELECT delegate_user_id FROM public.approval_delegations
        WHERE delegator_user_id = v_manager AND revoked_at IS NULL
          AND NOW() >= starts_at AND NOW() < ends_at
        ORDER BY created_at DESC LIMIT 1),
      v_manager,
      (SELECT backup_approver_id FROM public.users WHERE id = v_manager)
    ] LOOP
      IF v_candidate IS NOT NULL AND NOT (v_candidate = ANY (p_exclude))
         AND EXISTS (SELECT 1 FROM public.users
                      WHERE id = v_candidate AND is_active AND deleted_at IS NULL) THEN
        RETURN v_candidate;
      END IF;
    END LOOP;
  END LOOP;
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_approve_variance(
  p_variance_id UUID,
  p_actor       UUID,
  p_note        TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_variance  public.variance_lines;
  v_line      public.budget_lines;
  v_pa        public.payment_approvals;
  v_manager   BOOLEAN;
  v_field     BOOLEAN;
  v_limit     NUMERIC;
  v_second    BOOLEAN;
  v_routed    UUID;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;
  SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id;
  IF NOT FOUND OR v_variance.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Variance % not found', p_variance_id USING ERRCODE = 'PT404';
  END IF;

  PERFORM private.fin_lock_project(v_variance.project_id, TRUE, TRUE);
  SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id FOR UPDATE;
  SELECT * INTO v_line     FROM public.budget_lines   WHERE id = v_variance.budget_line_id FOR UPDATE;

  IF v_variance.status <> 'pending_approval' THEN
    RAISE EXCEPTION 'This variance is % and cannot be approved.', replace(v_variance.status, '_', ' ') USING ERRCODE = 'PT422';
  END IF;
  IF p_actor = v_variance.created_by THEN
    RAISE EXCEPTION 'You created this variance, so a different person must approve it.' USING ERRCODE = 'PT403';
  END IF;

  v_manager := private.user_has_role(p_actor, 'project_manager') OR private.user_has_role(p_actor, 'executive')
               OR private.user_has_role(p_actor, 'admin');
  v_field   := private.user_has_role(p_actor, 'field_manager');

  SELECT * INTO v_pa FROM public.payment_approvals
   WHERE budget_line_id = v_line.id
     AND status IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive')
   ORDER BY created_at DESC LIMIT 1 FOR UPDATE;
  v_second := COALESCE(v_pa.status = 'awaiting_manager', FALSE);

  IF v_second THEN
    IF p_actor = v_pa.field_approved_by THEN
      RAISE EXCEPTION 'You gave the first approval, so a manager must give the second one.' USING ERRCODE = 'PT403';
    END IF;
    IF NOT v_manager AND p_actor IS DISTINCT FROM v_pa.routed_to_user_id THEN
      RAISE EXCEPTION 'This amount is above the field manager limit and needs a manager''s approval.' USING ERRCODE = 'PT403';
    END IF;
  ELSIF NOT (v_manager OR v_field) THEN
    RAISE EXCEPTION 'Only a field manager, project manager, executive or admin can approve a variance.' USING ERRCODE = 'PT403';
  END IF;

  -- Personal limit first; a field manager without one gets the default.
  SELECT approval_limit INTO v_limit FROM public.users WHERE id = p_actor;
  IF v_limit IS NULL AND NOT v_manager THEN
    v_limit := COALESCE((SELECT (value #>> '{}')::numeric FROM public.financial_settings
                          WHERE setting_key = 'default_field_approval_limit'), 5000);
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  IF v_pa.id IS NULL THEN
    INSERT INTO public.payment_approvals (
      project_id, budget_line_id, internal_invoice_id, vendor_id, amount, payment_kind, status, requested_by
    ) VALUES (
      v_variance.project_id, v_line.id,
      (SELECT internal_invoice_id FROM public.payment_approvals
        WHERE budget_line_id = v_line.id AND internal_invoice_id IS NOT NULL ORDER BY created_at DESC LIMIT 1),
      v_variance.vendor_id, v_line.budget_amount, 'full', 'pending', v_variance.created_by
    ) RETURNING * INTO v_pa;
  END IF;

  IF NOT v_second AND v_limit IS NOT NULL AND v_line.budget_amount > v_limit THEN
    v_routed := private.fin_route_manager(p_actor, v_variance.project_id, ARRAY[p_actor, v_variance.created_by]);
    UPDATE public.payment_approvals
       SET status = 'awaiting_manager', field_approved_by = p_actor, field_approved_at = NOW(),
           routed_to_user_id = v_routed, comments = COALESCE(p_note, comments)
     WHERE id = v_pa.id RETURNING * INTO v_pa;
    UPDATE public.budget_lines SET approval_state = 'field_approved', updated_by = p_actor WHERE id = v_line.id;
    INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_after, actor_user_id, note)
    VALUES (p_variance_id, v_variance.project_id, 'routed_to_manager', v_line.budget_amount, p_actor, p_note);
  ELSE
    UPDATE public.payment_approvals
       SET status                = 'approved',
           vendor_id             = COALESCE(vendor_id, v_variance.vendor_id),
           field_approved_by     = CASE WHEN v_second OR v_manager THEN field_approved_by ELSE p_actor END,
           field_approved_at     = CASE WHEN v_second OR v_manager THEN field_approved_at ELSE NOW() END,
           manager_approved_by   = CASE WHEN v_second OR v_manager THEN p_actor ELSE manager_approved_by END,
           manager_approved_at   = CASE WHEN v_second OR v_manager THEN NOW() ELSE manager_approved_at END,
           expected_payment_date = CURRENT_DATE + v_line.payment_terms_days,
           comments              = COALESCE(p_note, comments)
     WHERE id = v_pa.id RETURNING * INTO v_pa;
    UPDATE public.variance_lines
       SET status = 'approved', approved_by = p_actor, approved_at = NOW()
     WHERE id = p_variance_id RETURNING * INTO v_variance;
    UPDATE public.budget_lines
       SET approval_state = CASE WHEN v_second OR v_manager THEN 'manager_approved' ELSE 'field_approved' END,
           updated_by = p_actor
     WHERE id = v_line.id;
    INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_after, actor_user_id, note)
    VALUES (p_variance_id, v_variance.project_id, 'approved', v_line.budget_amount, p_actor, p_note);
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN jsonb_build_object(
    'variance_id', p_variance_id, 'status', v_variance.status, 'payment_status', v_pa.status,
    'payment_approval_id', v_pa.id, 'routed_to_user_id', v_pa.routed_to_user_id, 'limit', v_limit);
END;
$$;

COMMENT ON FUNCTION public.fn_approve_variance(UUID, UUID, TEXT) IS
  'Approve for payment, independent of the parent bid line. The creator can never approve. Above the approver''s limit the first approval is recorded and the request is routed to a manager (a different person). Final approval freezes the variance.';


CREATE OR REPLACE FUNCTION public.fn_reject_variance(
  p_variance_id UUID,
  p_actor       UUID,
  p_reason      TEXT
)
RETURNS SETOF public.variance_lines
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_variance public.variance_lines;
  v_line     public.budget_lines;
BEGIN
  IF p_actor IS NULL THEN
    RAISE EXCEPTION 'p_actor is required' USING ERRCODE = 'PT422';
  END IF;
  IF btrim(COALESCE(p_reason, '')) = '' THEN
    RAISE EXCEPTION 'A rejection needs a reason' USING ERRCODE = 'PT422';
  END IF;
  SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id;
  IF NOT FOUND OR v_variance.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Variance % not found', p_variance_id USING ERRCODE = 'PT404';
  END IF;

  PERFORM private.fin_lock_project(v_variance.project_id, TRUE, FALSE);
  SELECT * INTO v_variance FROM public.variance_lines WHERE id = p_variance_id FOR UPDATE;
  SELECT * INTO v_line     FROM public.budget_lines   WHERE id = v_variance.budget_line_id FOR UPDATE;

  IF v_variance.status <> 'pending_approval' THEN
    RAISE EXCEPTION 'This variance is % and cannot be rejected.', replace(v_variance.status, '_', ' ') USING ERRCODE = 'PT422';
  END IF;
  IF p_actor = v_variance.created_by THEN
    RAISE EXCEPTION 'You created this variance: edit or cancel it instead of rejecting it.' USING ERRCODE = 'PT403';
  END IF;
  IF NOT (private.user_has_role(p_actor, 'field_manager') OR private.user_has_role(p_actor, 'project_manager')
          OR private.user_has_role(p_actor, 'executive') OR private.user_has_role(p_actor, 'admin')
          OR EXISTS (SELECT 1 FROM public.payment_approvals
                      WHERE budget_line_id = v_line.id AND status = 'awaiting_manager' AND routed_to_user_id = p_actor)) THEN
    RAISE EXCEPTION 'Only a field manager, project manager, executive or admin can reject a variance.' USING ERRCODE = 'PT403';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  UPDATE public.payment_approvals
     SET status = 'rejected', rejected_by = p_actor, rejected_at = NOW(), rejection_reason = btrim(p_reason)
   WHERE budget_line_id = v_line.id AND status IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive');
  UPDATE public.budget_lines SET approval_state = 'rejected', updated_by = p_actor WHERE id = v_line.id;
  UPDATE public.variance_lines
     SET status = 'rejected', rejected_by = p_actor, rejected_at = NOW(), rejection_reason = btrim(p_reason)
   WHERE id = p_variance_id RETURNING * INTO v_variance;
  INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_after, actor_user_id, note)
  VALUES (p_variance_id, v_variance.project_id, 'rejected', v_line.budget_amount, p_actor, btrim(p_reason));

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_variance;
END;
$$;

COMMENT ON FUNCTION public.fn_reject_variance(UUID, UUID, TEXT) IS
  'Sends a variance back with a reason. The amount stays reserved until the variance is edited (back to pending approval) or cancelled (returned to contingency).';


-- ============================================================================
-- SECTION F: 4.4 READ SURFACE
-- ============================================================================
CREATE OR REPLACE VIEW public.v_variances
WITH (security_invoker = true) AS
SELECT
  v.id, v.project_id, p.name AS project_name, v.budget_line_id, v.parent_budget_line_id,
  pl.name AS parent_line_name, pl.line_type AS parent_line_type, pl.budget_amount AS parent_budget_amount,
  pl.is_locked AS parent_is_locked, pl.approval_state AS parent_approval_state,
  v.trade_id, t.name AS trade_name, v.vendor_id, vd.company_name AS vendor_name,
  v.description, v.estimated_amount, bl.budget_amount AS amount, v.status,
  bl.payment_terms_days,
  v.created_by, cu.full_name AS created_by_name, v.created_at, v.updated_at,
  v.approved_by, au.full_name AS approved_by_name, v.approved_at,
  v.rejected_by, ru.full_name AS rejected_by_name, v.rejected_at, v.rejection_reason,
  pa.id AS payment_approval_id,
  -- A resubmitted variance has no request yet: its old rejection is history.
  CASE WHEN pa.status = 'rejected' AND v.status = 'pending_approval' THEN 'not_requested'
       ELSE COALESCE(pa.status, 'not_requested') END AS payment_status,
  pa.field_approved_by, fu.full_name AS field_approved_by_name,
  pa.routed_to_user_id, mu.full_name AS routed_to_name,
  pa.expected_payment_date,
  inv.id AS internal_invoice_id
FROM public.variance_lines v
JOIN public.projects          p  ON p.id  = v.project_id AND p.deleted_at IS NULL
JOIN public.budget_lines      bl ON bl.id = v.budget_line_id
JOIN public.budget_lines      pl ON pl.id = v.parent_budget_line_id
LEFT JOIN public.trades       t  ON t.id  = v.trade_id
LEFT JOIN public.vendors      vd ON vd.id = v.vendor_id
LEFT JOIN public.users        cu ON cu.id = v.created_by
LEFT JOIN public.users        au ON au.id = v.approved_by
LEFT JOIN public.users        ru ON ru.id = v.rejected_by
LEFT JOIN LATERAL (
  SELECT * FROM public.payment_approvals x
   WHERE x.budget_line_id = v.budget_line_id AND x.status <> 'cancelled'
   ORDER BY x.created_at DESC LIMIT 1
) pa ON TRUE
LEFT JOIN LATERAL (
  SELECT x.internal_invoice_id AS id FROM public.payment_approvals x
   WHERE x.budget_line_id = v.budget_line_id AND x.internal_invoice_id IS NOT NULL LIMIT 1
) inv ON TRUE
LEFT JOIN public.users        fu ON fu.id = pa.field_approved_by
LEFT JOIN public.users        mu ON mu.id = pa.routed_to_user_id
WHERE v.deleted_at IS NULL;

COMMENT ON VIEW public.v_variances IS
  'Variances with project, parent line, trade, vendor, people, current amount and own payment status. security_invoker = true.';


-- ============================================================================
-- SECTION G: PRIVILEGES
-- ============================================================================
REVOKE ALL ON public.v_variances FROM PUBLIC, anon;
GRANT SELECT ON public.v_variances TO authenticated, service_role;

-- Run inside triggers / procedures as the calling role.
REVOKE ALL ON FUNCTION private.fin_recalc_guardrails(uuid)             FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_route_manager(uuid, uuid, uuid[])   FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.fin_recalc_guardrails(uuid)           TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_route_manager(uuid, uuid, uuid[]) TO service_role;

REVOKE ALL ON FUNCTION public.fn_block_variance_event_mutation()       FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_variance_created_event()              FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_ledger_recalc_guardrails()            FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_adjust_variance(uuid, numeric, uuid, text)                        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_edit_variance(uuid, numeric, text, uuid, uuid, uuid, text)        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_approve_variance(uuid, uuid, text)                                FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_reject_variance(uuid, uuid, text)                                 FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_adjust_variance(uuid, numeric, uuid, text)                     TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_edit_variance(uuid, numeric, text, uuid, uuid, uuid, text)     TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_approve_variance(uuid, uuid, text)                             TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_reject_variance(uuid, uuid, text)                              TO service_role;


-- ============================================================================
-- SECTION H: VERSION MARKER
-- ============================================================================
INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.5.0 (20261125_financial_phase4_variances)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;


-- ############################################################################
--
--  SECTION 15: PHASE 5 CONTINGENCY HEALTH GUARDRAIL & ALERTS (v4.6)
--
--  Source of truth for EXISTING databases: the idempotent migration
--    database/migrations/20261126_financial_phase5_health/001_contingency_health.sql
--  Same DDL minus BEGIN/COMMIT. Retires the Section 14 guardrail trigger.
--
-- ############################################################################

-- ============================================================================
-- SECTION A: COLUMNS
-- ============================================================================
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS groundbreaking_at            TIMESTAMPTZ;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS groundbreaking_by            UUID REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS status_before_hold           VARCHAR(20);
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS long_tail_reserve_updated_at TIMESTAMPTZ;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS long_tail_reserve_updated_by UUID REFERENCES public.users(id) ON DELETE SET NULL;

COMMENT ON COLUMN public.projects.contingency_at_groundbreaking IS 'Contingency when groundbreaking was recorded: denominator of contingency left %. NULL = not recorded yet; the initial contingency at baseline is used.';
COMMENT ON COLUMN public.projects.groundbreaking_at             IS 'When groundbreaking was recorded (fn_record_groundbreaking).';
COMMENT ON COLUMN public.projects.status_before_hold            IS 'Status to return to when a financial hold is lifted.';

ALTER TABLE public.financial_alerts ADD COLUMN IF NOT EXISTS discussed_with     UUID REFERENCES public.users(id) ON DELETE RESTRICT;
ALTER TABLE public.financial_alerts ADD COLUMN IF NOT EXISTS conversation_notes TEXT;
ALTER TABLE public.financial_alerts ADD COLUMN IF NOT EXISTS hold_lifted_by     UUID REFERENCES public.users(id) ON DELETE RESTRICT;
ALTER TABLE public.financial_alerts ADD COLUMN IF NOT EXISTS hold_lifted_at     TIMESTAMPTZ;
ALTER TABLE public.financial_alerts ADD COLUMN IF NOT EXISTS hold_lift_reason   TEXT;
ALTER TABLE public.financial_alerts ADD COLUMN IF NOT EXISTS notified_at        TIMESTAMPTZ;
ALTER TABLE public.financial_alerts ADD COLUMN IF NOT EXISTS escalated_at       TIMESTAMPTZ;

COMMENT ON COLUMN public.financial_alerts.discussed_with     IS 'Field manager the deciding manager spoke with.';
COMMENT ON COLUMN public.financial_alerts.conversation_notes IS 'What the field manager and the manager discussed.';
COMMENT ON COLUMN public.financial_alerts.notified_at        IS 'When the alert was sent (in-app + email). NULL = not sent yet; the daily sweep sends it.';
COMMENT ON COLUMN public.financial_alerts.escalated_at       IS 'When the executives were told.';


-- ============================================================================
-- SECTION B: 5.2 ONE ENGINE (retire the Phase 4 SQL guardrails)
-- ============================================================================
DROP TRIGGER IF EXISTS trg_contingency_ledger_guardrails ON public.contingency_ledger;
DROP FUNCTION IF EXISTS public.fn_ledger_recalc_guardrails();
DROP FUNCTION IF EXISTS private.fin_recalc_guardrails(uuid);

-- Same function as Phase 1, but the hold message names the project.
CREATE OR REPLACE FUNCTION private.fin_lock_project(
  p_project_id       UUID,
  p_require_baseline BOOLEAN,
  p_block_on_hold    BOOLEAN
)
RETURNS public.projects
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
BEGIN
  SELECT * INTO v_project FROM public.projects WHERE id = p_project_id FOR UPDATE;
  IF NOT FOUND OR v_project.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Project % not found', p_project_id USING ERRCODE = 'PT404';
  END IF;
  IF p_require_baseline AND v_project.budget_status <> 'baselined' THEN
    RAISE EXCEPTION 'Project % budget is not baselined yet (status %)', p_project_id, v_project.budget_status
      USING ERRCODE = 'PT409';
  END IF;
  IF p_block_on_hold AND v_project.status = 'on_hold' THEN
    RAISE EXCEPTION 'Project "%" is on hold; financial changes are blocked until the hold is lifted.', v_project.name
      USING ERRCODE = 'PT409';
  END IF;
  RETURN v_project;
END;
$$;


-- ============================================================================
-- SECTION C: 5.1 INPUTS FOR THE CALCULATION
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_project_health_inputs(p_project_id UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  SELECT jsonb_build_object(
    'project_id',            p.id,
    'project_name',          p.name,
    'status',                p.status,
    'budget_status',         p.budget_status,
    'archived',              p.archived_at IS NOT NULL,
    'manager_id',            p.manager_id,
    'field_manager_id',      p.field_manager_id,
    'groundbreaking_at',     p.groundbreaking_at,
    'reserve',               p.long_tail_reserve_amount,
    'contingency',           (SELECT b.budget_amount FROM public.budget_lines b
                               WHERE b.project_id = p.id AND b.line_type = 'contingency' AND b.deleted_at IS NULL),
    'contingency_base',      COALESCE(p.contingency_at_groundbreaking,
                               (SELECT cb.approved_amount FROM public.contingency_buckets cb
                                 WHERE cb.project_id = p.id AND cb.bucket_kind = 'initial')),
    'total_budget',          (SELECT COALESCE(SUM(b.budget_amount), 0) FROM public.budget_lines b
                               WHERE b.project_id = p.id AND b.deleted_at IS NULL),
    'lines',                 (SELECT COALESCE(jsonb_agg(jsonb_build_object(
                                'committed',   b.committed_amount,
                                'approved',    COALESCE(pay.approved, 0),
                                'sent',        COALESCE(pay.sent, 0),
                                'land_closed', COALESCE(lc.closed, 0))), '[]'::jsonb)
                               FROM public.budget_lines b
                               LEFT JOIN LATERAL (
                                 SELECT SUM(x.amount) FILTER (WHERE x.status = 'approved')        AS approved,
                                        SUM(x.amount) FILTER (WHERE x.status = 'sent_to_finance') AS sent
                                   FROM public.payment_approvals x WHERE x.budget_line_id = b.id
                               ) pay ON TRUE
                               LEFT JOIN LATERAL (
                                 SELECT SUM(y.amount) AS closed FROM public.land_closings y
                                  WHERE y.budget_line_id = b.id AND y.status = 'closed'
                               ) lc ON TRUE
                              WHERE b.project_id = p.id AND b.deleted_at IS NULL AND b.line_type <> 'contingency'),
    'milestones_total',      ms.total,
    'milestones_completed',  ms.done,
    'near_zero_percent',     COALESCE((SELECT (value #>> '{}')::numeric FROM public.financial_settings
                                        WHERE setting_key = 'contingency_near_zero_percent'), 5)
  )
  FROM public.projects p
  CROSS JOIN LATERAL (
    SELECT count(*) AS total, count(*) FILTER (WHERE m.status = 'completed') AS done
      FROM public.milestones m
      JOIN public.tasks t ON t.id = m.task_id
     WHERE t.project_id = p.id AND t.deleted_at IS NULL AND m.status <> 'cancelled'
  ) ms
  WHERE p.id = p_project_id AND p.deleted_at IS NULL;
$$;

COMMENT ON FUNCTION public.fn_project_health_inputs(UUID) IS
  'Every number the health calculation (app/services/financial_health.py) needs, read in one statement.';

CREATE OR REPLACE FUNCTION public.fn_record_groundbreaking(p_project_id UUID, p_actor UUID)
RETURNS SETOF public.projects
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
  v_cont    NUMERIC;
BEGIN
  IF NOT (private.user_has_role(p_actor, 'project_manager') OR private.user_has_role(p_actor, 'executive')
          OR private.user_has_role(p_actor, 'admin')) THEN
    RAISE EXCEPTION 'Only a project manager, executive or admin can record groundbreaking.' USING ERRCODE = 'PT403';
  END IF;
  v_project := private.fin_lock_project(p_project_id, TRUE, FALSE);
  IF v_project.groundbreaking_at IS NOT NULL THEN
    RAISE EXCEPTION 'Groundbreaking is already recorded for this project.' USING ERRCODE = 'PT409';
  END IF;
  SELECT budget_amount INTO v_cont FROM public.budget_lines
   WHERE project_id = p_project_id AND line_type = 'contingency' AND deleted_at IS NULL;
  IF COALESCE(v_cont, 0) <= 0 THEN
    RAISE EXCEPTION 'Groundbreaking needs contingency above $0, because later checks are measured against it.'
      USING ERRCODE = 'PT422';
  END IF;
  UPDATE public.projects
     SET contingency_at_groundbreaking = v_cont, groundbreaking_at = NOW(), groundbreaking_by = p_actor
   WHERE id = p_project_id RETURNING * INTO v_project;
  RETURN NEXT v_project;
END;
$$;


-- ============================================================================
-- SECTION D: 5.2 / 5.3 ALERT SYNC
-- ============================================================================
-- p_checks: [{type, active, severity, left_pct, work_left_pct, remaining, reserve, message}]
--   no live alert       → open one
--   open                → refresh its numbers
--   OK to proceed given → stays quiet until contingency drops below the amount
--                         it was decided at, then a new decision is needed
--   on hold             → untouched until the hold is lifted
--   no longer active    → resolved
CREATE OR REPLACE FUNCTION public.fn_sync_financial_alerts(p_project_id UUID, p_checks JSONB)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  c         JSONB;
  v_alert   public.financial_alerts;
  v_type    TEXT;
  v_remain  NUMERIC;
  v_new     UUID;
  v_found   BOOLEAN;
  v_opened  JSONB := '[]'::jsonb;
BEGIN
  PERFORM private.fin_lock_project(p_project_id, FALSE, FALSE);

  FOR c IN SELECT value FROM jsonb_array_elements(p_checks) LOOP
    v_type   := c ->> 'type';
    v_remain := (c ->> 'remaining')::numeric;

    IF NOT (c ->> 'active')::boolean THEN
      UPDATE public.financial_alerts SET status = 'resolved', resolved_at = NOW()
       WHERE project_id = p_project_id AND alert_type = v_type
         AND status IN ('open', 'acknowledged', 'proceed_approved');
      CONTINUE;
    END IF;

    SELECT * INTO v_alert FROM public.financial_alerts
     WHERE project_id = p_project_id AND alert_type = v_type
       AND status IN ('open', 'acknowledged', 'proceed_approved', 'on_hold')
     ORDER BY created_at DESC LIMIT 1;
    v_found := FOUND;

    IF v_found AND v_alert.status IN ('open', 'acknowledged') THEN
      UPDATE public.financial_alerts
         SET severity = c ->> 'severity', contingency_left_pct = (c ->> 'left_pct')::numeric,
             work_left_pct = (c ->> 'work_left_pct')::numeric, contingency_remaining = v_remain,
             reserve_required = (c ->> 'reserve')::numeric, message = c ->> 'message'
       WHERE id = v_alert.id;
      CONTINUE;
    END IF;
    IF v_found AND (v_alert.status = 'on_hold'
                    OR v_remain >= COALESCE(v_alert.contingency_remaining, v_remain)) THEN
      CONTINUE;
    END IF;
    IF v_found THEN
      UPDATE public.financial_alerts SET status = 'superseded' WHERE id = v_alert.id;
    END IF;

    INSERT INTO public.financial_alerts (
      project_id, alert_type, severity, contingency_left_pct, work_left_pct,
      contingency_remaining, reserve_required, message
    ) VALUES (
      p_project_id, v_type, c ->> 'severity', (c ->> 'left_pct')::numeric, (c ->> 'work_left_pct')::numeric,
      v_remain, (c ->> 'reserve')::numeric, c ->> 'message'
    ) RETURNING id INTO v_new;
    v_opened := v_opened || to_jsonb(v_new);
  END LOOP;

  RETURN v_opened;
END;
$$;

COMMENT ON FUNCTION public.fn_sync_financial_alerts(UUID, JSONB) IS
  'Brings a project''s guardrail alerts in line with the calculated checks. Returns the ids of newly opened alerts.';


-- ============================================================================
-- SECTION E: 5.4 DECISION AND HOLD
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_decide_financial_alert(
  p_alert_id       UUID,
  p_actor          UUID,
  p_decision       TEXT,
  p_reason         TEXT,
  p_discussed_with UUID,
  p_notes          TEXT
)
RETURNS SETOF public.financial_alerts
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_alert   public.financial_alerts;
  v_project public.projects;
BEGIN
  IF p_decision IS NULL OR p_decision NOT IN ('proceed', 'hold') THEN
    RAISE EXCEPTION 'The decision must be proceed or hold.' USING ERRCODE = 'PT422';
  END IF;
  IF btrim(COALESCE(p_reason, '')) = '' THEN
    RAISE EXCEPTION 'A decision needs a reason.' USING ERRCODE = 'PT422';
  END IF;
  IF btrim(COALESCE(p_notes, '')) = '' THEN
    RAISE EXCEPTION 'Record what was discussed with the field manager.' USING ERRCODE = 'PT422';
  END IF;
  IF NOT (private.user_has_role(p_actor, 'project_manager') OR private.user_has_role(p_actor, 'executive')
          OR private.user_has_role(p_actor, 'admin')) THEN
    RAISE EXCEPTION 'Only a project manager, executive or admin can decide this alert.' USING ERRCODE = 'PT403';
  END IF;

  SELECT * INTO v_alert FROM public.financial_alerts WHERE id = p_alert_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Alert not found' USING ERRCODE = 'PT404';
  END IF;
  IF v_alert.alert_type = 'bidding_checkpoint' THEN
    RAISE EXCEPTION 'The bidding checkpoint has no proceed / hold decision.' USING ERRCODE = 'PT422';
  END IF;

  v_project := private.fin_lock_project(v_alert.project_id, FALSE, FALSE);
  SELECT * INTO v_alert FROM public.financial_alerts WHERE id = p_alert_id FOR UPDATE;
  IF v_alert.status NOT IN ('open', 'acknowledged') THEN
    RAISE EXCEPTION 'This alert is already decided or resolved.' USING ERRCODE = 'PT409';
  END IF;
  IF v_project.archived_at IS NOT NULL OR v_project.status IN ('completed', 'cancelled') THEN
    RAISE EXCEPTION 'This project is closed or archived.' USING ERRCODE = 'PT409';
  END IF;

  -- The conversation is between two people, one of them a field manager.
  IF p_discussed_with IS NULL OR p_discussed_with = p_actor
     OR NOT EXISTS (SELECT 1 FROM public.users WHERE id = p_discussed_with AND is_active AND deleted_at IS NULL) THEN
    RAISE EXCEPTION 'Choose the field manager you spoke with (someone other than yourself).' USING ERRCODE = 'PT422';
  END IF;
  IF p_discussed_with IS DISTINCT FROM v_project.field_manager_id
     AND NOT private.user_has_role(p_discussed_with, 'field_manager') THEN
    RAISE EXCEPTION 'The person you spoke with must be a field manager.' USING ERRCODE = 'PT422';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  -- One conversation settles every open guardrail alert of the project.
  UPDATE public.financial_alerts
     SET status             = CASE WHEN p_decision = 'proceed' THEN 'proceed_approved' ELSE 'on_hold' END,
         decision           = p_decision,
         decision_reason    = btrim(p_reason),
         decided_by         = p_actor,
         decided_at         = NOW(),
         discussed_with     = p_discussed_with,
         conversation_notes = btrim(p_notes)
   WHERE project_id = v_project.id AND status IN ('open', 'acknowledged')
     AND alert_type <> 'bidding_checkpoint';

  IF p_decision = 'hold' AND v_project.status <> 'on_hold' THEN
    UPDATE public.projects SET status_before_hold = status, status = 'on_hold' WHERE id = v_project.id;
  END IF;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN QUERY SELECT * FROM public.financial_alerts WHERE id = p_alert_id;
END;
$$;

COMMENT ON FUNCTION public.fn_decide_financial_alert(UUID, UUID, TEXT, TEXT, UUID, TEXT) IS
  'Manager''s OK-to-proceed or hold, with the reason and the field manager conversation. Hold moves the project to on_hold.';

CREATE OR REPLACE FUNCTION public.fn_lift_financial_hold(p_project_id UUID, p_actor UUID, p_reason TEXT)
RETURNS SETOF public.projects
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_project public.projects;
BEGIN
  IF btrim(COALESCE(p_reason, '')) = '' THEN
    RAISE EXCEPTION 'Lifting the hold needs a reason.' USING ERRCODE = 'PT422';
  END IF;
  IF NOT (private.user_has_role(p_actor, 'project_manager') OR private.user_has_role(p_actor, 'executive')
          OR private.user_has_role(p_actor, 'admin')) THEN
    RAISE EXCEPTION 'Only a project manager, executive or admin can lift the hold.' USING ERRCODE = 'PT403';
  END IF;

  v_project := private.fin_lock_project(p_project_id, FALSE, FALSE);
  IF v_project.archived_at IS NOT NULL THEN
    RAISE EXCEPTION 'This project is archived. Unarchive it first.' USING ERRCODE = 'PT409';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.financial_alerts WHERE project_id = p_project_id AND status = 'on_hold') THEN
    RAISE EXCEPTION 'This project has no financial hold.' USING ERRCODE = 'PT409';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  -- Lifting is an OK to proceed at today's contingency: a further drop alerts again.
  UPDATE public.financial_alerts
     SET status = 'proceed_approved', hold_lifted_by = p_actor, hold_lifted_at = NOW(),
         hold_lift_reason = btrim(p_reason),
         contingency_remaining = COALESCE((SELECT budget_amount FROM public.budget_lines
                                            WHERE project_id = p_project_id AND line_type = 'contingency'
                                              AND deleted_at IS NULL), contingency_remaining)
   WHERE project_id = p_project_id AND status = 'on_hold';
  UPDATE public.projects
     SET status = CASE WHEN status = 'on_hold' THEN COALESCE(status_before_hold, 'active') ELSE status END,
         status_before_hold = NULL
   WHERE id = p_project_id RETURNING * INTO v_project;

  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_project;
END;
$$;

-- Project guard: a financial hold is lifted only through the procedure, and the
-- long-tail reserve is released only at project close.
CREATE OR REPLACE FUNCTION public.fn_guard_project_health()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  IF NOT private.fin_write_authorized()
     AND NEW.status IS DISTINCT FROM OLD.status AND OLD.status = 'on_hold'
     AND EXISTS (SELECT 1 FROM public.financial_alerts WHERE project_id = OLD.id AND status = 'on_hold') THEN
    RAISE EXCEPTION 'This project is on a financial hold. Lift the hold from its financial alert, with a reason.'
      USING ERRCODE = 'PT409';
  END IF;
  IF COALESCE(NEW.long_tail_reserve_amount, 0) < COALESCE(OLD.long_tail_reserve_amount, 0)
     AND OLD.groundbreaking_at IS NOT NULL AND NEW.status <> 'completed' THEN
    RAISE EXCEPTION 'The long-tail reserve can only be released when the project is completed.' USING ERRCODE = 'PT409';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_projects_guard_health ON public.projects;
CREATE TRIGGER trg_projects_guard_health
  BEFORE UPDATE OF status, long_tail_reserve_amount ON public.projects
  FOR EACH ROW EXECUTE FUNCTION public.fn_guard_project_health();

-- On hold = no new bid packages, awards, approvals or payments. Two functions,
-- because bid packages / awards reach the project through their task.
CREATE OR REPLACE FUNCTION public.fn_block_on_hold_task()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_status TEXT;
BEGIN
  -- FOR SHARE: waits for a hold that is being placed right now.
  SELECT p.status INTO v_status FROM public.projects p
   WHERE p.id = (SELECT t.project_id FROM public.tasks t WHERE t.id = NEW.task_id) FOR SHARE;
  IF v_status = 'on_hold' THEN
    RAISE EXCEPTION 'This project is on hold. New bid packages, awards, approvals and payments are blocked until the hold is lifted.'
      USING ERRCODE = 'PT409';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_block_on_hold_payment()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_status TEXT;
BEGIN
  SELECT p.status INTO v_status FROM public.projects p WHERE p.id = NEW.project_id FOR SHARE;
  IF v_status = 'on_hold' THEN
    RAISE EXCEPTION 'This project is on hold. New bid packages, awards, approvals and payments are blocked until the hold is lifted.'
      USING ERRCODE = 'PT409';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_bid_packages_block_on_hold ON public.bid_packages;
CREATE TRIGGER trg_bid_packages_block_on_hold BEFORE INSERT ON public.bid_packages
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_on_hold_task();
DROP TRIGGER IF EXISTS trg_awards_block_on_hold ON public.awards;
CREATE TRIGGER trg_awards_block_on_hold BEFORE INSERT ON public.awards
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_on_hold_task();
DROP TRIGGER IF EXISTS trg_payment_approvals_block_on_hold_ins ON public.payment_approvals;
CREATE TRIGGER trg_payment_approvals_block_on_hold_ins BEFORE INSERT ON public.payment_approvals
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_on_hold_payment();
-- Rejecting and cancelling stay possible on a held project.
DROP TRIGGER IF EXISTS trg_payment_approvals_block_on_hold_upd ON public.payment_approvals;
CREATE TRIGGER trg_payment_approvals_block_on_hold_upd BEFORE UPDATE OF status ON public.payment_approvals
  FOR EACH ROW
  WHEN (NEW.status IS DISTINCT FROM OLD.status AND NEW.status NOT IN ('pending', 'rejected', 'cancelled'))
  EXECUTE FUNCTION public.fn_block_on_hold_payment();
DROP TRIGGER IF EXISTS trg_finance_handoffs_block_on_hold ON public.finance_handoffs;
CREATE TRIGGER trg_finance_handoffs_block_on_hold BEFORE INSERT ON public.finance_handoffs
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_on_hold_payment();


-- ============================================================================
-- SECTION F: READ SURFACE
-- ============================================================================
CREATE OR REPLACE VIEW public.v_financial_alerts
WITH (security_invoker = true) AS
SELECT a.id, a.project_id, p.name AS project_name, p.status AS project_status,
       p.manager_id, p.field_manager_id, p.archived_at AS project_archived_at,
       a.alert_type, a.severity, a.status, a.contingency_left_pct, a.work_left_pct,
       a.contingency_remaining, a.reserve_required, a.message,
       a.decision, a.decision_reason, a.decided_by, du.full_name AS decided_by_name, a.decided_at,
       a.discussed_with, wu.full_name AS discussed_with_name, a.conversation_notes,
       a.hold_lifted_by, lu.full_name AS hold_lifted_by_name, a.hold_lifted_at, a.hold_lift_reason,
       a.notified_at, a.escalated_at, a.resolved_at, a.created_at, a.updated_at
  FROM public.financial_alerts a
  JOIN public.projects p ON p.id = a.project_id AND p.deleted_at IS NULL
  LEFT JOIN public.users du ON du.id = a.decided_by
  LEFT JOIN public.users wu ON wu.id = a.discussed_with
  LEFT JOIN public.users lu ON lu.id = a.hold_lifted_by;

COMMENT ON VIEW public.v_financial_alerts IS
  'Financial alerts with project and people names. security_invoker = true.';


-- ============================================================================
-- SECTION G: PRIVILEGES
-- ============================================================================
REVOKE ALL ON public.v_financial_alerts FROM PUBLIC, anon;
GRANT SELECT ON public.v_financial_alerts TO authenticated, service_role;

REVOKE ALL ON FUNCTION public.fn_project_health_inputs(uuid)                                   FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_record_groundbreaking(uuid, uuid)                             FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_sync_financial_alerts(uuid, jsonb)                            FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_decide_financial_alert(uuid, uuid, text, text, uuid, text)    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_lift_financial_hold(uuid, uuid, text)                         FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_guard_project_health()                                        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_block_on_hold_task()                                          FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_block_on_hold_payment()                                       FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_project_health_inputs(uuid)                                TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_record_groundbreaking(uuid, uuid)                          TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_sync_financial_alerts(uuid, jsonb)                         TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_decide_financial_alert(uuid, uuid, text, text, uuid, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_lift_financial_hold(uuid, uuid, text)                      TO service_role;


-- ============================================================================
-- SECTION H: SETTINGS AND VERSION MARKER
-- ============================================================================
INSERT INTO public.financial_settings (setting_key, value, description) VALUES
  ('contingency_near_zero_percent', '5'::jsonb, 'Contingency left % at or below which the urgent near-zero alert fires.'),
  ('alert_escalation_days', '2'::jsonb, 'Days an alert may stay undecided before the executives are emailed.'),
  ('alert_recipients', '{"warning": [], "urgent": [], "critical": []}'::jsonb, 'Emails per alert severity, besides the project''s manager and field manager.')
ON CONFLICT (setting_key) DO NOTHING;

INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.6.0 (20261126_financial_phase5_health)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;


-- ############################################################################
--
--  SECTION 16: PHASE 6 PAYMENT APPROVAL WORKFLOW & FINANCE HAND-OFF (v4.7)
--
--  Source of truth for EXISTING databases: the idempotent migration
--    database/migrations/20261127_financial_phase6_payments/001_payment_approvals.sql
--  Same DDL minus BEGIN/COMMIT and the RLS part (in rls_policies.sql).
--
-- ############################################################################

-- ============================================================================
-- SECTION A: COLUMNS
-- ============================================================================
ALTER TABLE public.payment_approvals ADD COLUMN IF NOT EXISTS gross_amount          DECIMAL(15,2);
ALTER TABLE public.payment_approvals ADD COLUMN IF NOT EXISTS work_confirmed_by     UUID REFERENCES public.users(id) ON DELETE RESTRICT;
ALTER TABLE public.payment_approvals ADD COLUMN IF NOT EXISTS work_confirmed_at     TIMESTAMPTZ;
ALTER TABLE public.payment_approvals ADD COLUMN IF NOT EXISTS confirmed_by_external BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.payment_approvals ADD COLUMN IF NOT EXISTS executive_required    BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.payment_approvals ADD COLUMN IF NOT EXISTS resubmitted_from      UUID REFERENCES public.payment_approvals(id) ON DELETE RESTRICT;
ALTER TABLE public.payment_approvals ADD COLUMN IF NOT EXISTS approved_at           TIMESTAMPTZ;

COMMENT ON COLUMN public.payment_approvals.amount                IS 'Net amount to pay = gross_amount − retainage_amount (a retainage release pays the retainage held).';
COMMENT ON COLUMN public.payment_approvals.gross_amount          IS 'Value of the work being paid (full: what is left on the line; progress: % of the line). NULL on Phase 2 invoice requests = amount.';
COMMENT ON COLUMN public.payment_approvals.work_confirmed_by     IS 'Field manager who confirmed the work is complete (may be external).';
COMMENT ON COLUMN public.payment_approvals.confirmed_by_external IS 'TRUE when the work was confirmed by an external / temporary field manager: a second, internal approval is always needed.';
COMMENT ON COLUMN public.payment_approvals.executive_required    IS 'Above financial_settings.executive_approval_threshold: an executive approval is also needed.';

ALTER TABLE public.finance_handoffs ADD COLUMN IF NOT EXISTS handoff_error TEXT;
COMMENT ON COLUMN public.finance_handoffs.handoff_error IS 'Why the last hand-off email failed. The daily summary job retries failed hand-offs.';


-- ============================================================================
-- SECTION B: HISTORY (append-only)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.payment_approval_events (
  id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  event_no             BIGINT        GENERATED ALWAYS AS IDENTITY UNIQUE,
  payment_approval_id  UUID          NOT NULL REFERENCES public.payment_approvals(id) ON DELETE RESTRICT,
  project_id           UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  event_type           VARCHAR(30)   NOT NULL
                                     CHECK (event_type IN ('requested', 'work_confirmed', 'field_approved', 'routed_to_manager',
                                                           'manager_approved', 'routed_to_executive', 'executive_approved',
                                                           'approved', 'rejected', 'resubmitted', 'cancelled',
                                                           'sent_to_finance', 'handoff_failed')),
  status_after         VARCHAR(20)   NOT NULL,
  actor_user_id        UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  routed_to_user_id    UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  note                 TEXT,
  created_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payment_approval_events_pa ON public.payment_approval_events (payment_approval_id, event_no);

COMMENT ON TABLE public.payment_approval_events IS
  'Append-only audit trail of every payment approval: request, work confirmation, each approval, routing, rejection, hand-off to finance.';

CREATE OR REPLACE FUNCTION public.fn_block_payment_event_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  RAISE EXCEPTION 'Payment approval history is append-only and cannot be changed.' USING ERRCODE = 'PT403';
END;
$$;

DROP TRIGGER IF EXISTS trg_payment_approval_events_immutable ON public.payment_approval_events;
CREATE TRIGGER trg_payment_approval_events_immutable
  BEFORE UPDATE OR DELETE ON public.payment_approval_events
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_payment_event_mutation();
DROP TRIGGER IF EXISTS trg_payment_approval_events_no_truncate ON public.payment_approval_events;
CREATE TRIGGER trg_payment_approval_events_no_truncate
  BEFORE TRUNCATE ON public.payment_approval_events
  FOR EACH STATEMENT EXECUTE FUNCTION public.fn_block_payment_event_mutation();

-- RLS for this table: rls_policies.sql (PAYMENT HISTORY RLS).


-- ============================================================================
-- SECTION C: HELPERS
-- ============================================================================
-- Amount a user may approve alone. NULL = no limit (a manager without a
-- personal limit). A field manager without one gets the default.
CREATE OR REPLACE FUNCTION private.fin_effective_limit(p_user UUID)
RETURNS NUMERIC
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT CASE
           WHEN u.approval_limit IS NOT NULL THEN u.approval_limit
           WHEN private.user_has_role(p_user, 'project_manager') OR private.user_has_role(p_user, 'executive')
                OR private.user_has_role(p_user, 'admin') THEN NULL
           ELSE COALESCE((SELECT (value #>> '{}')::numeric FROM public.financial_settings
                           WHERE setting_key = 'default_field_approval_limit'), 5000)
         END
    FROM public.users u WHERE u.id = p_user;
$$;

-- The contract behind a line: retainage %, payment terms, number.
CREATE OR REPLACE FUNCTION private.fin_line_contract(p_line_id UUID)
RETURNS public.contracts
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  SELECT c.* FROM public.budget_lines b
    JOIN public.contracts c ON c.id = b.contract_id
                            OR (b.contract_id IS NULL AND c.award_id = b.award_id AND c.status <> 'terminated')
   WHERE b.id = p_line_id
   ORDER BY (c.id = b.contract_id) DESC, c.created_at DESC
   LIMIT 1;
$$;

-- Line roll-up of its latest live payment request.
CREATE OR REPLACE FUNCTION private.fin_rollup_line_approval(p_line_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_status TEXT;
BEGIN
  SELECT status INTO v_status FROM public.payment_approvals
   WHERE budget_line_id = p_line_id AND status <> 'cancelled'
   ORDER BY created_at DESC LIMIT 1;
  UPDATE public.budget_lines
     SET approval_state = CASE
           WHEN v_status IS NULL THEN 'not_requested'
           WHEN v_status = 'pending' THEN 'pending'
           WHEN v_status IN ('field_approved', 'awaiting_manager', 'awaiting_executive') THEN 'field_approved'
           WHEN v_status = 'approved' THEN 'manager_approved'
           WHEN v_status = 'sent_to_finance' THEN 'sent_to_finance'
           ELSE 'rejected' END
   WHERE id = p_line_id;
END;
$$;

CREATE OR REPLACE FUNCTION private.fin_payment_event(
  p_pa public.payment_approvals, p_type TEXT, p_actor UUID, p_note TEXT, p_routed UUID DEFAULT NULL
)
RETURNS VOID
LANGUAGE sql
SET search_path = ''
AS $$
  INSERT INTO public.payment_approval_events (payment_approval_id, project_id, event_type, status_after,
                                              actor_user_id, routed_to_user_id, note)
  VALUES (p_pa.id, p_pa.project_id, p_type, p_pa.status, p_actor, p_routed, NULLIF(btrim(COALESCE(p_note, '')), ''));
$$;

CREATE OR REPLACE FUNCTION private.fin_is_approver(p_user UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  SELECT private.user_has_role(p_user, 'field_manager') OR private.user_has_role(p_user, 'project_manager')
      OR private.user_has_role(p_user, 'executive') OR private.user_has_role(p_user, 'admin');
$$;

-- PO number from the configured formats: {CONTRACT} {YYYY} {MM} {SEQ:n}.
CREATE OR REPLACE FUNCTION private.fin_next_po_number(p_contract TEXT)
RETURNS TEXT
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_fmt    TEXT;
  v_width  INT;
  v_prefix TEXT;
  v_suffix TEXT;
  v_seq    INT;
  v_po     TEXT;
BEGIN
  IF p_contract IS NOT NULL THEN
    v_fmt := COALESCE((SELECT value #>> '{}' FROM public.financial_settings WHERE setting_key = 'po_number_format_contract'),
                      '{CONTRACT}-{SEQ:03}');
  ELSE
    v_fmt := COALESCE((SELECT value #>> '{}' FROM public.financial_settings WHERE setting_key = 'po_number_format'),
                      'PO-{YYYY}-{SEQ:05}');
  END IF;
  IF v_fmt !~ '\{SEQ(:\d+)?\}' THEN
    v_fmt := v_fmt || '-{SEQ:03}';
  END IF;
  v_fmt := replace(replace(replace(v_fmt, '{CONTRACT}', COALESCE(p_contract, '')),
                           '{YYYY}', to_char(CURRENT_DATE, 'YYYY')), '{MM}', to_char(CURRENT_DATE, 'MM'));
  v_width  := COALESCE((regexp_match(v_fmt, '\{SEQ:(\d+)\}'))[1]::int, 1);
  v_prefix := split_part(regexp_replace(v_fmt, '\{SEQ(:\d+)?\}', '#SEQ#'), '#SEQ#', 1);
  v_suffix := split_part(regexp_replace(v_fmt, '\{SEQ(:\d+)?\}', '#SEQ#'), '#SEQ#', 2);

  PERFORM pg_advisory_xact_lock(hashtext('bluonx.po_number'));
  SELECT count(*) + 1 INTO v_seq FROM public.finance_handoffs
   WHERE left(po_number, length(v_prefix)) = v_prefix;
  LOOP
    v_po := left(v_prefix || lpad(v_seq::text, v_width, '0') || v_suffix, 50);
    EXIT WHEN NOT EXISTS (SELECT 1 FROM public.finance_handoffs WHERE po_number = v_po);
    v_seq := v_seq + 1;
  END LOOP;
  RETURN v_po;
END;
$$;


-- ============================================================================
-- SECTION D: 6.1 REQUEST
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_request_payment(
  p_line_id  UUID,
  p_actor    UUID,
  p_kind     TEXT,
  p_percent  NUMERIC,
  p_note     TEXT
)
RETURNS SETOF public.payment_approvals
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_line      public.budget_lines;
  v_contract  public.contracts;
  v_variance  public.variance_lines;
  v_total     NUMERIC;
  v_used      NUMERIC;
  v_gross     NUMERIC;
  v_ret       NUMERIC := 0;
  v_amount    NUMERIC;
  v_vendor    UUID;
  v_pa        public.payment_approvals;
BEGIN
  IF p_kind IS NULL OR p_kind NOT IN ('full', 'progress', 'retainage_release') THEN
    RAISE EXCEPTION 'Choose a full payment, a progress payment or a retainage release.' USING ERRCODE = 'PT422';
  END IF;
  IF NOT private.fin_is_approver(p_actor) THEN
    RAISE EXCEPTION 'Only a field manager, project manager, executive or admin can request a payment.' USING ERRCODE = 'PT403';
  END IF;

  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_line_id;
  IF NOT FOUND OR v_line.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Budget line % not found', p_line_id USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_line.project_id, FALSE, TRUE);
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_line_id FOR UPDATE;

  IF v_line.line_type = 'bid_activity' THEN
    IF v_line.award_id IS NULL OR v_line.committed_amount <= 0 THEN
      RAISE EXCEPTION 'This line has no award yet, so there is nothing to pay.' USING ERRCODE = 'PT422';
    END IF;
    v_total    := v_line.committed_amount;
    v_contract := private.fin_line_contract(p_line_id);
    v_ret      := COALESCE(v_contract.retainage_percent, 0);
    SELECT vendor_id INTO v_vendor FROM public.awards WHERE id = v_line.award_id;
  ELSIF v_line.line_type = 'variance' THEN
    SELECT * INTO v_variance FROM public.variance_lines WHERE budget_line_id = p_line_id;
    IF v_variance.status IS DISTINCT FROM 'pending_approval' THEN
      RAISE EXCEPTION 'Only a variance waiting for approval can be sent for payment.' USING ERRCODE = 'PT422';
    END IF;
    IF p_kind <> 'full' THEN
      RAISE EXCEPTION 'A variance is paid in full.' USING ERRCODE = 'PT422';
    END IF;
    v_total  := v_line.budget_amount;
    v_vendor := v_variance.vendor_id;
  ELSE
    RAISE EXCEPTION 'Payments on % lines start from their invoices (Invoices tab).', replace(v_line.line_type, '_', ' ')
      USING ERRCODE = 'PT422';
  END IF;

  IF EXISTS (SELECT 1 FROM public.payment_approvals WHERE budget_line_id = p_line_id
              AND status IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive')) THEN
    RAISE EXCEPTION 'This line already has a payment waiting for approval.' USING ERRCODE = 'PT409';
  END IF;

  SELECT COALESCE(SUM(COALESCE(gross_amount, amount)), 0) INTO v_used FROM public.payment_approvals
   WHERE budget_line_id = p_line_id AND status NOT IN ('rejected', 'cancelled') AND payment_kind <> 'retainage_release';

  IF p_kind = 'retainage_release' THEN
    IF v_used < v_total THEN
      RAISE EXCEPTION 'Retainage is released once the whole line has been approved for payment.' USING ERRCODE = 'PT422';
    END IF;
    SELECT COALESCE(SUM(retainage_amount) FILTER (WHERE payment_kind <> 'retainage_release'), 0)
           - COALESCE(SUM(amount) FILTER (WHERE payment_kind = 'retainage_release'), 0)
      INTO v_amount FROM public.payment_approvals
     WHERE budget_line_id = p_line_id AND status NOT IN ('rejected', 'cancelled');
    IF v_amount <= 0 THEN
      RAISE EXCEPTION 'No retainage is held on this line.' USING ERRCODE = 'PT422';
    END IF;
    v_gross := v_amount;
    v_ret   := NULL;
  ELSE
    IF p_kind = 'full' THEN
      v_gross := v_total - v_used;
    ELSE
      IF p_percent IS NULL OR p_percent <= 0 OR p_percent > 100 THEN
        RAISE EXCEPTION 'Enter a progress %% above 0 and up to 100.' USING ERRCODE = 'PT422';
      END IF;
      v_gross := round(v_total * p_percent / 100, 2);
    END IF;
    IF v_gross <= 0 THEN
      RAISE EXCEPTION 'This line is already fully approved for payment.' USING ERRCODE = 'PT422';
    END IF;
    IF v_gross > v_total - v_used THEN
      RAISE EXCEPTION 'That is more than is left to pay on this line (%).', v_total - v_used USING ERRCODE = 'PT422';
    END IF;
    v_ret    := round(v_gross * v_ret / 100, 2);
    v_amount := v_gross - v_ret;
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  INSERT INTO public.payment_approvals (
    project_id, budget_line_id, vendor_id, amount, gross_amount, payment_kind, progress_percent,
    retainage_amount, status, requested_by, comments
  ) VALUES (
    v_line.project_id, p_line_id, v_vendor, v_amount, v_gross, p_kind,
    CASE WHEN p_kind = 'progress' THEN p_percent END, NULLIF(v_ret, 0), 'pending', p_actor,
    NULLIF(btrim(COALESCE(p_note, '')), '')
  ) RETURNING * INTO v_pa;
  PERFORM private.fin_payment_event(v_pa, 'requested', p_actor, p_note);
  PERFORM private.fin_rollup_line_approval(p_line_id);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_pa;
END;
$$;

COMMENT ON FUNCTION public.fn_request_payment(UUID, UUID, TEXT, NUMERIC, TEXT) IS
  'Starts a payment on a bid or variance line: full (what is left), progress (% of the line) or retainage release (after the line is fully paid). Retainage follows the contract.';


-- ============================================================================
-- SECTION E: 6.2 / 6.3 APPROVAL STEP
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_payment_approval_step(
  p_id               UUID,
  p_actor            UUID,
  p_expected_status  TEXT,
  p_step             TEXT,
  p_next_status      TEXT,
  p_routed_to        UUID,
  p_note             TEXT,
  p_work_confirmed   BOOLEAN
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_pa        public.payment_approvals;
  v_project   UUID;
  v_actor     public.users;
  v_line      public.budget_lines;
  v_variance  public.variance_lines;
  v_contract  public.contracts;
  v_gross     NUMERIC;
  v_limit     NUMERIC;
  v_threshold NUMERIC;
  v_terms     INT;
  v_handoff   UUID;
  v_po        TEXT;
  v_names     JSONB;
BEGIN
  SELECT project_id INTO v_project FROM public.payment_approvals WHERE id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Payment approval not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_project, FALSE, FALSE);
  SELECT * INTO v_pa FROM public.payment_approvals WHERE id = p_id FOR UPDATE;
  IF v_pa.status IS DISTINCT FROM p_expected_status THEN
    RAISE EXCEPTION 'This payment changed a moment ago (now %). Reload and try again.', replace(v_pa.status, '_', ' ')
      USING ERRCODE = 'PT409';
  END IF;

  SELECT * INTO v_actor FROM public.users WHERE id = p_actor AND is_active AND deleted_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Your account is not active.' USING ERRCODE = 'PT403';
  END IF;
  SELECT * INTO v_line FROM public.budget_lines WHERE id = v_pa.budget_line_id FOR UPDATE;
  SELECT * INTO v_variance FROM public.variance_lines WHERE budget_line_id = v_line.id;
  IF v_variance.created_by = p_actor THEN
    RAISE EXCEPTION 'You created this variance, so a different person must approve it.' USING ERRCODE = 'PT403';
  END IF;

  v_gross     := COALESCE(v_pa.gross_amount, v_pa.amount);
  v_threshold := (SELECT (value #>> '{}')::numeric FROM public.financial_settings
                   WHERE setting_key = 'executive_approval_threshold' AND jsonb_typeof(value) = 'number');

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  IF p_step = 'field' THEN
    IF v_pa.status <> 'pending' OR p_next_status NOT IN ('awaiting_manager', 'awaiting_executive', 'approved') THEN
      RAISE EXCEPTION 'Work confirmation is the first step.' USING ERRCODE = 'PT409';
    END IF;
    IF NOT COALESCE(p_work_confirmed, FALSE) THEN
      RAISE EXCEPTION 'Confirm the work is complete before approving.' USING ERRCODE = 'PT422';
    END IF;
    IF NOT private.fin_is_approver(p_actor) THEN
      RAISE EXCEPTION 'Only a field manager, project manager, executive or admin can confirm work.' USING ERRCODE = 'PT403';
    END IF;
    IF NOT v_actor.is_employee AND p_next_status <> 'awaiting_manager' THEN
      RAISE EXCEPTION 'External field managers can confirm work but never authorise payment.' USING ERRCODE = 'PT403';
    END IF;
    UPDATE public.payment_approvals
       SET work_confirmed_by = p_actor, work_confirmed_at = NOW(),
           field_approved_by = p_actor, field_approved_at = NOW(),
           confirmed_by_external = NOT v_actor.is_employee
     WHERE id = p_id RETURNING * INTO v_pa;
    PERFORM private.fin_payment_event(v_pa, 'work_confirmed', p_actor, p_note);
  ELSIF p_step = 'manager' THEN
    IF v_pa.status <> 'awaiting_manager' OR p_next_status NOT IN ('awaiting_executive', 'approved') THEN
      RAISE EXCEPTION 'This payment is not waiting for a manager.' USING ERRCODE = 'PT409';
    END IF;
    IF NOT v_actor.is_employee THEN
      RAISE EXCEPTION 'Only internal employees can authorise payment.' USING ERRCODE = 'PT403';
    END IF;
    IF p_actor IN (v_pa.field_approved_by, v_pa.work_confirmed_by) THEN
      RAISE EXCEPTION 'You gave the first approval, so a different person must give the second.' USING ERRCODE = 'PT403';
    END IF;
    IF NOT (private.user_has_role(p_actor, 'project_manager') OR private.user_has_role(p_actor, 'executive')
            OR private.user_has_role(p_actor, 'admin') OR p_actor = v_pa.routed_to_user_id) THEN
      RAISE EXCEPTION 'Only a manager can give the second approval.' USING ERRCODE = 'PT403';
    END IF;
    IF v_actor.approval_limit IS NOT NULL AND v_gross > v_actor.approval_limit THEN
      RAISE EXCEPTION 'This amount is above your approval limit of %.', v_actor.approval_limit USING ERRCODE = 'PT403';
    END IF;
    UPDATE public.payment_approvals SET manager_approved_by = p_actor, manager_approved_at = NOW()
     WHERE id = p_id RETURNING * INTO v_pa;
    PERFORM private.fin_payment_event(v_pa, 'manager_approved', p_actor, p_note);
  ELSIF p_step = 'executive' THEN
    IF v_pa.status <> 'awaiting_executive' OR p_next_status <> 'approved' THEN
      RAISE EXCEPTION 'This payment is not waiting for an executive.' USING ERRCODE = 'PT409';
    END IF;
    IF NOT v_actor.is_employee OR NOT private.user_has_role(p_actor, 'executive') THEN
      RAISE EXCEPTION 'Only an internal executive can give the executive approval.' USING ERRCODE = 'PT403';
    END IF;
    IF p_actor IN (v_pa.field_approved_by, v_pa.work_confirmed_by, v_pa.manager_approved_by) THEN
      RAISE EXCEPTION 'You already approved this payment, so a different executive must approve it.' USING ERRCODE = 'PT403';
    END IF;
    UPDATE public.payment_approvals SET executive_approved_by = p_actor, executive_approved_at = NOW()
     WHERE id = p_id RETURNING * INTO v_pa;
    PERFORM private.fin_payment_event(v_pa, 'executive_approved', p_actor, p_note);
  ELSE
    RAISE EXCEPTION 'Unknown approval step %', p_step USING ERRCODE = 'PT422';
  END IF;

  -- The rules that must hold whatever the caller decided.
  IF p_next_status IN ('awaiting_executive', 'approved') THEN
    v_limit := private.fin_effective_limit(v_pa.field_approved_by);
    IF (v_pa.confirmed_by_external OR (v_limit IS NOT NULL AND v_gross > v_limit)) AND v_pa.manager_approved_by IS NULL THEN
      RAISE EXCEPTION 'This payment needs a second approval by a manager.' USING ERRCODE = 'PT422';
    END IF;
  END IF;
  IF p_next_status = 'approved' AND v_threshold IS NOT NULL AND v_gross > v_threshold
     AND v_pa.executive_approved_by IS NULL THEN
    RAISE EXCEPTION 'This payment is above the executive threshold and needs an executive approval.' USING ERRCODE = 'PT422';
  END IF;

  UPDATE public.payment_approvals
     SET status = p_next_status,
         routed_to_user_id = CASE WHEN p_next_status IN ('awaiting_manager', 'awaiting_executive') THEN p_routed_to END,
         executive_required = v_threshold IS NOT NULL AND v_gross > v_threshold,
         comments = COALESCE(NULLIF(btrim(COALESCE(p_note, '')), ''), comments)
   WHERE id = p_id RETURNING * INTO v_pa;

  IF p_next_status = 'awaiting_manager' THEN
    PERFORM private.fin_payment_event(v_pa, 'routed_to_manager', p_actor, NULL, p_routed_to);
  ELSIF p_next_status = 'awaiting_executive' THEN
    PERFORM private.fin_payment_event(v_pa, 'routed_to_executive', p_actor, NULL, p_routed_to);
  ELSE
    -- 6.4 / 6.5: final approval.
    v_contract := private.fin_line_contract(v_line.id);
    v_terms := COALESCE(v_contract.payment_terms_days, v_line.payment_terms_days);
    UPDATE public.payment_approvals
       SET approved_at = NOW(), expected_payment_date = CURRENT_DATE + v_terms
     WHERE id = p_id RETURNING * INTO v_pa;

    INSERT INTO public.cash_flow_entries (project_id, budget_line_id, payment_approval_id, period_month,
                                          direction, cash_bucket, amount, entry_kind, source_note)
    VALUES (v_pa.project_id, v_line.id, v_pa.id, date_trunc('month', v_pa.expected_payment_date)::date,
            'out', v_line.cash_bucket, v_pa.amount, 'expected', 'Approved payment, expected ' || v_pa.expected_payment_date);

    IF v_variance.id IS NOT NULL AND v_variance.status = 'pending_approval' THEN
      UPDATE public.variance_lines SET status = 'approved', approved_by = p_actor, approved_at = NOW()
       WHERE id = v_variance.id;
      INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_after, actor_user_id, note)
      VALUES (v_variance.id, v_variance.project_id, 'approved', v_line.budget_amount, p_actor, p_note);
    END IF;
    IF v_pa.internal_invoice_id IS NOT NULL AND NOT EXISTS (
         SELECT 1 FROM public.payment_approvals
          WHERE internal_invoice_id = v_pa.internal_invoice_id
            AND status NOT IN ('approved', 'sent_to_finance', 'cancelled')) THEN
      UPDATE public.internal_invoices SET status = 'approved' WHERE id = v_pa.internal_invoice_id;
    END IF;

    SELECT jsonb_object_agg(k, u.full_name) INTO v_names
      FROM (VALUES ('work_confirmed_by', v_pa.work_confirmed_by), ('field_approved_by', v_pa.field_approved_by),
                   ('manager_approved_by', v_pa.manager_approved_by),
                   ('executive_approved_by', v_pa.executive_approved_by)) AS a(k, id)
      JOIN public.users u ON u.id = a.id;

    v_po := private.fin_next_po_number(v_contract.contract_number);
    INSERT INTO public.finance_handoffs (payment_approval_id, project_id, po_number, vendor_id, amount, payload, status)
    SELECT v_pa.id, v_pa.project_id, v_po, v_pa.vendor_id, v_pa.amount,
           jsonb_build_object(
             'po_number', v_po,
             'project', p.name,
             'line', v_line.name,
             'line_type', v_line.line_type,
             'trade', COALESCE(tr.name, vt.name),
             'vendor', COALESCE(vd.company_name, inv.payee_name),
             'invoice_number', inv.invoice_number,
             'contract_number', v_contract.contract_number,
             'payment_kind', v_pa.payment_kind,
             'progress_percent', v_pa.progress_percent,
             'gross_amount', COALESCE(v_pa.gross_amount, v_pa.amount),
             'retainage_amount', COALESCE(v_pa.retainage_amount, 0),
             'amount', v_pa.amount,
             'approved_on', CURRENT_DATE,
             'expected_payment_date', v_pa.expected_payment_date,
             'payment_terms_days', v_terms,
             'approvers', COALESCE(v_names, '{}'::jsonb)),
           'pending'
      FROM public.projects p
      LEFT JOIN public.tasks t ON t.id = COALESCE(v_line.task_id, (SELECT task_id FROM public.budget_lines WHERE id = v_line.parent_line_id))
      LEFT JOIN public.trades tr ON tr.id = t.trade_id
      LEFT JOIN public.trades vt ON vt.id = v_variance.trade_id
      LEFT JOIN public.vendors vd ON vd.id = v_pa.vendor_id
      LEFT JOIN public.internal_invoices inv ON inv.id = v_pa.internal_invoice_id
     WHERE p.id = v_pa.project_id
    RETURNING id INTO v_handoff;

    PERFORM private.fin_payment_event(v_pa, 'approved', p_actor, 'PO ' || v_po);
  END IF;

  PERFORM private.fin_rollup_line_approval(v_line.id);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN jsonb_build_object('id', v_pa.id, 'status', v_pa.status, 'routed_to_user_id', v_pa.routed_to_user_id,
                            'handoff_id', v_handoff, 'po_number', v_po);
END;
$$;

COMMENT ON FUNCTION public.fn_payment_approval_step(UUID, UUID, TEXT, TEXT, TEXT, UUID, TEXT, BOOLEAN) IS
  'Records one approval step decided by app/services/payment_rules.py and re-checks the hard rules. Final approval writes the expected cash-flow entry, approves the variance / invoice and creates the finance hand-off with its PO number.';


-- ============================================================================
-- SECTION F: REJECT / RESUBMIT / CANCEL
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_reject_payment(p_id UUID, p_actor UUID, p_reason TEXT)
RETURNS SETOF public.payment_approvals
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_pa       public.payment_approvals;
  v_project  UUID;
  v_variance public.variance_lines;
BEGIN
  IF btrim(COALESCE(p_reason, '')) = '' THEN
    RAISE EXCEPTION 'A rejection needs a reason.' USING ERRCODE = 'PT422';
  END IF;
  SELECT project_id INTO v_project FROM public.payment_approvals WHERE id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Payment approval not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_project, FALSE, FALSE);
  SELECT * INTO v_pa FROM public.payment_approvals WHERE id = p_id FOR UPDATE;
  IF v_pa.status NOT IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive') THEN
    RAISE EXCEPTION 'This payment is % and cannot be rejected.', replace(v_pa.status, '_', ' ') USING ERRCODE = 'PT409';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.users WHERE id = p_actor AND is_active AND is_employee AND deleted_at IS NULL) THEN
    RAISE EXCEPTION 'Only internal employees can reject a payment.' USING ERRCODE = 'PT403';
  END IF;
  IF NOT (private.fin_is_approver(p_actor) OR p_actor = v_pa.routed_to_user_id) THEN
    RAISE EXCEPTION 'Only a field manager, project manager, executive or admin can reject a payment.' USING ERRCODE = 'PT403';
  END IF;
  SELECT * INTO v_variance FROM public.variance_lines WHERE budget_line_id = v_pa.budget_line_id;
  IF v_variance.created_by = p_actor THEN
    RAISE EXCEPTION 'You created this variance: edit or cancel it instead of rejecting it.' USING ERRCODE = 'PT403';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  UPDATE public.payment_approvals
     SET status = 'rejected', rejected_by = p_actor, rejected_at = NOW(), rejection_reason = btrim(p_reason),
         routed_to_user_id = NULL
   WHERE id = p_id RETURNING * INTO v_pa;
  IF v_variance.id IS NOT NULL AND v_variance.status = 'pending_approval' THEN
    UPDATE public.variance_lines
       SET status = 'rejected', rejected_by = p_actor, rejected_at = NOW(), rejection_reason = btrim(p_reason)
     WHERE id = v_variance.id;
    INSERT INTO public.variance_events (variance_id, project_id, event_type, actor_user_id, note)
    VALUES (v_variance.id, v_variance.project_id, 'rejected', p_actor, btrim(p_reason));
  END IF;
  IF v_pa.internal_invoice_id IS NOT NULL THEN
    UPDATE public.internal_invoices SET status = 'rejected' WHERE id = v_pa.internal_invoice_id;
  END IF;
  PERFORM private.fin_payment_event(v_pa, 'rejected', p_actor, p_reason);
  PERFORM private.fin_rollup_line_approval(v_pa.budget_line_id);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_pa;
END;
$$;

-- A rejected payment goes back to the field manager, who fixes it and sends a
-- copy (same amounts) for approval again. Variances resubmit by being edited.
CREATE OR REPLACE FUNCTION public.fn_resubmit_payment(p_id UUID, p_actor UUID, p_note TEXT)
RETURNS SETOF public.payment_approvals
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_old public.payment_approvals;
  v_new public.payment_approvals;
BEGIN
  SELECT * INTO v_old FROM public.payment_approvals WHERE id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Payment approval not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_old.project_id, FALSE, TRUE);
  SELECT * INTO v_old FROM public.payment_approvals WHERE id = p_id FOR UPDATE;
  IF v_old.status <> 'rejected' THEN
    RAISE EXCEPTION 'Only a rejected payment can be resubmitted.' USING ERRCODE = 'PT409';
  END IF;
  IF NOT private.fin_is_approver(p_actor) THEN
    RAISE EXCEPTION 'Only a field manager, project manager, executive or admin can resubmit a payment.' USING ERRCODE = 'PT403';
  END IF;
  IF EXISTS (SELECT 1 FROM public.variance_lines WHERE budget_line_id = v_old.budget_line_id) THEN
    RAISE EXCEPTION 'Edit the variance to resubmit it.' USING ERRCODE = 'PT422';
  END IF;
  IF EXISTS (SELECT 1 FROM public.payment_approvals WHERE budget_line_id = v_old.budget_line_id
              AND status IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive')) THEN
    RAISE EXCEPTION 'This line already has a payment waiting for approval.' USING ERRCODE = 'PT409';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  INSERT INTO public.payment_approvals (
    project_id, budget_line_id, internal_invoice_id, vendor_id, amount, gross_amount, payment_kind,
    progress_percent, retainage_amount, status, requested_by, comments, resubmitted_from
  ) VALUES (
    v_old.project_id, v_old.budget_line_id, v_old.internal_invoice_id, v_old.vendor_id, v_old.amount,
    v_old.gross_amount, v_old.payment_kind, v_old.progress_percent, v_old.retainage_amount, 'pending', p_actor,
    COALESCE(NULLIF(btrim(COALESCE(p_note, '')), ''), v_old.comments), v_old.id
  ) RETURNING * INTO v_new;
  IF v_new.internal_invoice_id IS NOT NULL THEN
    UPDATE public.internal_invoices SET status = 'in_approval' WHERE id = v_new.internal_invoice_id;
  END IF;
  PERFORM private.fin_payment_event(v_new, 'resubmitted', p_actor, p_note);
  PERFORM private.fin_rollup_line_approval(v_new.budget_line_id);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_new;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_cancel_payment(p_id UUID, p_actor UUID, p_note TEXT)
RETURNS SETOF public.payment_approvals
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_pa public.payment_approvals;
BEGIN
  SELECT * INTO v_pa FROM public.payment_approvals WHERE id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Payment approval not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_pa.project_id, FALSE, FALSE);
  SELECT * INTO v_pa FROM public.payment_approvals WHERE id = p_id FOR UPDATE;
  IF v_pa.status NOT IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive', 'rejected') THEN
    RAISE EXCEPTION 'This payment is % and cannot be withdrawn.', replace(v_pa.status, '_', ' ') USING ERRCODE = 'PT409';
  END IF;
  IF v_pa.internal_invoice_id IS NOT NULL
     OR EXISTS (SELECT 1 FROM public.variance_lines WHERE budget_line_id = v_pa.budget_line_id) THEN
    RAISE EXCEPTION 'Invoice and variance payments are withdrawn by cancelling the invoice or the variance.' USING ERRCODE = 'PT422';
  END IF;
  IF p_actor <> v_pa.requested_by AND NOT (private.user_has_role(p_actor, 'project_manager')
                                           OR private.user_has_role(p_actor, 'admin')) THEN
    RAISE EXCEPTION 'Only the person who asked for the payment, a project manager or an admin can withdraw it.' USING ERRCODE = 'PT403';
  END IF;
  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  UPDATE public.payment_approvals SET status = 'cancelled', routed_to_user_id = NULL
   WHERE id = p_id RETURNING * INTO v_pa;
  PERFORM private.fin_payment_event(v_pa, 'cancelled', p_actor, p_note);
  PERFORM private.fin_rollup_line_approval(v_pa.budget_line_id);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_pa;
END;
$$;


-- ============================================================================
-- SECTION G: 6.6 HAND-OFF DELIVERED
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_mark_finance_handoff(
  p_handoff_id   UUID,
  p_sent         BOOLEAN,
  p_email_log_id UUID,
  p_document     TEXT,
  p_error        TEXT
)
RETURNS SETOF public.finance_handoffs
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_h  public.finance_handoffs;
  v_pa public.payment_approvals;
BEGIN
  SELECT * INTO v_h FROM public.finance_handoffs WHERE id = p_handoff_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Hand-off not found' USING ERRCODE = 'PT404';
  END IF;
  UPDATE public.finance_handoffs
     SET document_path = COALESCE(p_document, document_path),
         email_log_id  = COALESCE(p_email_log_id, email_log_id),
         status        = CASE WHEN p_sent THEN 'sent' WHEN status = 'sent' THEN status ELSE 'failed' END,
         sent_at       = CASE WHEN p_sent THEN COALESCE(sent_at, NOW()) ELSE sent_at END,
         handoff_error = CASE WHEN p_sent THEN NULL ELSE p_error END
   WHERE id = p_handoff_id RETURNING * INTO v_h;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  UPDATE public.payment_approvals SET status = 'sent_to_finance'
   WHERE id = v_h.payment_approval_id AND status = 'approved' AND p_sent
   RETURNING * INTO v_pa;
  IF v_pa.id IS NOT NULL THEN
    PERFORM private.fin_payment_event(v_pa, 'sent_to_finance', NULL, 'PO ' || v_h.po_number);
    PERFORM private.fin_rollup_line_approval(v_pa.budget_line_id);
  ELSIF NOT p_sent THEN
    SELECT * INTO v_pa FROM public.payment_approvals WHERE id = v_h.payment_approval_id;
    PERFORM private.fin_payment_event(v_pa, 'handoff_failed', NULL, p_error);
  END IF;
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_h;
END;
$$;


-- ============================================================================
-- SECTION H: READ SURFACE
-- ============================================================================
CREATE OR REPLACE VIEW public.v_payment_approvals
WITH (security_invoker = true) AS
SELECT pa.id, pa.project_id, p.name AS project_name, p.status AS project_status,
       pa.budget_line_id, bl.name AS line_name, bl.line_type, bl.committed_amount AS line_committed,
       bl.budget_amount AS line_budget, bl.payment_terms_days,
       COALESCE(tr.name, vt.name) AS trade_name,
       pa.vendor_id, COALESCE(vd.company_name, inv.payee_name) AS vendor_name,
       pa.internal_invoice_id, inv.invoice_number,
       vl.id AS variance_id, vl.created_by AS variance_created_by,
       c.contract_number, c.retainage_percent,
       pa.amount, COALESCE(pa.gross_amount, pa.amount) AS gross_amount, COALESCE(pa.retainage_amount, 0) AS retainage_amount,
       pa.payment_kind, pa.progress_percent, pa.status, pa.comments,
       pa.requested_by, ru.full_name AS requested_by_name, pa.created_at,
       pa.work_confirmed_by, wu.full_name AS work_confirmed_by_name, pa.work_confirmed_at, pa.confirmed_by_external,
       pa.field_approved_by, fu.full_name AS field_approved_by_name, pa.field_approved_at,
       pa.routed_to_user_id, tu.full_name AS routed_to_name,
       pa.manager_approved_by, mu.full_name AS manager_approved_by_name, pa.manager_approved_at,
       pa.executive_required, pa.executive_approved_by, eu.full_name AS executive_approved_by_name, pa.executive_approved_at,
       pa.rejected_by, xu.full_name AS rejected_by_name, pa.rejected_at, pa.rejection_reason,
       pa.approved_at, pa.expected_payment_date, pa.resubmitted_from,
       fh.id AS handoff_id, fh.po_number, fh.status AS handoff_status, fh.sent_at AS handoff_sent_at,
       el.status AS handoff_delivery_status, pa.updated_at
  FROM public.payment_approvals pa
  JOIN public.projects p ON p.id = pa.project_id AND p.deleted_at IS NULL
  JOIN public.budget_lines bl ON bl.id = pa.budget_line_id
  LEFT JOIN public.variance_lines vl ON vl.budget_line_id = bl.id
  LEFT JOIN public.tasks t ON t.id = COALESCE(bl.task_id, (SELECT b2.task_id FROM public.budget_lines b2 WHERE b2.id = bl.parent_line_id))
  LEFT JOIN public.trades tr ON tr.id = t.trade_id
  LEFT JOIN public.trades vt ON vt.id = vl.trade_id
  LEFT JOIN public.vendors vd ON vd.id = pa.vendor_id
  LEFT JOIN public.internal_invoices inv ON inv.id = pa.internal_invoice_id
  LEFT JOIN LATERAL (SELECT * FROM private.fin_line_contract(bl.id)) c ON TRUE
  LEFT JOIN public.users ru ON ru.id = pa.requested_by
  LEFT JOIN public.users wu ON wu.id = pa.work_confirmed_by
  LEFT JOIN public.users fu ON fu.id = pa.field_approved_by
  LEFT JOIN public.users tu ON tu.id = pa.routed_to_user_id
  LEFT JOIN public.users mu ON mu.id = pa.manager_approved_by
  LEFT JOIN public.users eu ON eu.id = pa.executive_approved_by
  LEFT JOIN public.users xu ON xu.id = pa.rejected_by
  LEFT JOIN public.finance_handoffs fh ON fh.payment_approval_id = pa.id
  LEFT JOIN public.email_log el ON el.id = fh.email_log_id;

COMMENT ON VIEW public.v_payment_approvals IS
  'Payment approvals with project, line, trade, vendor, contract, every approver and the finance hand-off. security_invoker = true.';

CREATE OR REPLACE VIEW public.v_finance_handoffs
WITH (security_invoker = true) AS
SELECT fh.id, fh.payment_approval_id, fh.project_id, p.name AS project_name, fh.po_number, fh.vendor_id,
       fh.amount, fh.payload, fh.document_path, fh.status, fh.sent_at, fh.exported_at, fh.handoff_error,
       fh.email_log_id, el.recipient_email AS delivered_to, el.status AS delivery_status, el.sent_at AS email_sent_at,
       fh.created_at
  FROM public.finance_handoffs fh
  JOIN public.projects p ON p.id = fh.project_id AND p.deleted_at IS NULL
  LEFT JOIN public.email_log el ON el.id = fh.email_log_id;

COMMENT ON VIEW public.v_finance_handoffs IS
  'Finance hand-off log with the email_log delivery status of each PO. security_invoker = true.';


-- ============================================================================
-- SECTION I: PRIVILEGES
-- ============================================================================
REVOKE ALL ON public.v_payment_approvals, public.v_finance_handoffs FROM PUBLIC, anon;
GRANT SELECT ON public.v_payment_approvals TO authenticated, service_role;
GRANT SELECT ON public.v_finance_handoffs TO service_role;

REVOKE ALL ON FUNCTION private.fin_effective_limit(uuid)          FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.fin_line_contract(uuid)            FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.fin_is_approver(uuid)              FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.fin_effective_limit(uuid)       TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.fin_line_contract(uuid)         TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.fin_is_approver(uuid)           TO authenticated, service_role;
REVOKE ALL ON FUNCTION private.fin_rollup_line_approval(uuid)     FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_next_po_number(text)           FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_payment_event(public.payment_approvals, text, uuid, text, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.fin_rollup_line_approval(uuid)  TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_next_po_number(text)        TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_payment_event(public.payment_approvals, text, uuid, text, uuid) TO service_role;

REVOKE ALL ON FUNCTION public.fn_block_payment_event_mutation() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_request_payment(uuid, uuid, text, numeric, text)                          FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_payment_approval_step(uuid, uuid, text, text, text, uuid, text, boolean)  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_reject_payment(uuid, uuid, text)                                          FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_resubmit_payment(uuid, uuid, text)                                        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_cancel_payment(uuid, uuid, text)                                          FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_mark_finance_handoff(uuid, boolean, uuid, text, text)                     FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_request_payment(uuid, uuid, text, numeric, text)                       TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_payment_approval_step(uuid, uuid, text, text, text, uuid, text, boolean) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_reject_payment(uuid, uuid, text)                                       TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_resubmit_payment(uuid, uuid, text)                                     TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_cancel_payment(uuid, uuid, text)                                       TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_mark_finance_handoff(uuid, boolean, uuid, text, text)                  TO service_role;


-- ============================================================================
-- SECTION J: SETTINGS AND VERSION MARKER
-- ============================================================================
INSERT INTO public.financial_settings (setting_key, value, description) VALUES
  ('po_number_format_contract', '"{CONTRACT}-{SEQ:03}"'::jsonb, 'PO number when the line has a contract: the contract number is the default reference. Tokens {CONTRACT} {YYYY} {MM} {SEQ:n}.'),
  ('quickbooks_expense_account', '"Job Expenses"'::jsonb, 'Expense account written on every line of the QuickBooks bill import.')
ON CONFLICT (setting_key) DO NOTHING;

INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.7.0 (20261127_financial_phase6_payments)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;


-- ############################################################################
--
--  SECTION 17: PHASE 7 LONG-TAIL ITEMS: ESCROWS & PROPERTY TAXES (v4.8)
--
--  Source of truth for EXISTING databases: the idempotent migration
--    database/migrations/20261128_financial_phase7_long_tail/001_long_tail.sql
--  Same DDL minus BEGIN/COMMIT and the RLS part (in rls_policies.sql).
--
-- ############################################################################

-- ============================================================================
-- SECTION A: TABLES AND COLUMNS
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.jurisdictions (
  id                       UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  name                     VARCHAR(150)  NOT NULL CHECK (btrim(name) <> ''),
  kind                     VARCHAR(10)   NOT NULL DEFAULT 'city' CHECK (kind IN ('city', 'county', 'hoa', 'other')),
  state                    VARCHAR(50),
  repair_estimate_percent  DECIMAL(5,2)  CHECK (repair_estimate_percent IS NULL OR repair_estimate_percent BETWEEN 0 AND 100),
  tax_installments         JSONB         NOT NULL DEFAULT '[{"month": 12, "day": 31}]'::jsonb,
  reminder_days_before     INTEGER       NOT NULL DEFAULT 30 CHECK (reminder_days_before BETWEEN 1 AND 180),
  notes                    TEXT,
  created_by               UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at               TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at               TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at               TIMESTAMPTZ,
  CONSTRAINT chk_jurisdictions_installments CHECK (jsonb_typeof(tax_installments) = 'array' AND jsonb_array_length(tax_installments) BETWEEN 1 AND 12)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_jurisdictions_name ON public.jurisdictions (lower(name), kind, COALESCE(state, '')) WHERE deleted_at IS NULL;

COMMENT ON TABLE public.jurisdictions IS
  'Cities / counties / HOAs. Standards vary, so each holds its own repair estimate % (escrow repairs to city standard), property tax instalment dates [{month, day}] and reminder lead time.';

DROP TRIGGER IF EXISTS trg_jurisdictions_updated_at ON public.jurisdictions;
CREATE TRIGGER trg_jurisdictions_updated_at BEFORE UPDATE ON public.jurisdictions
  FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS jurisdiction_id        UUID REFERENCES public.jurisdictions(id) ON DELETE RESTRICT;
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS repair_estimate        DECIMAL(15,2) NOT NULL DEFAULT 0 CHECK (repair_estimate >= 0);
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS premium_frequency      VARCHAR(10) NOT NULL DEFAULT 'one_time' CHECK (premium_frequency IN ('one_time', 'yearly'));
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS premium_total          DECIMAL(15,2) NOT NULL DEFAULT 0 CHECK (premium_total >= 0);
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS works_built_date       DATE;
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS inspection_date        DATE;
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS inspection_notes       TEXT;
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS signoff_date           DATE;
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS signoff_by             VARCHAR(255);
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS expected_release_date  DATE;
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS bond_reminder_sent_for DATE;
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS document_name          VARCHAR(255);

COMMENT ON COLUMN public.escrows.repair_estimate        IS 'Internal estimate of repairs to city standard. The repairs line = the higher of this and the defect list.';
COMMENT ON COLUMN public.escrows.premium_total          IS 'All bond / insurance premiums so far (first + renewals) = the premium line.';
COMMENT ON COLUMN public.escrows.bond_reminder_sent_for IS 'Bond expiry date the last renewal reminder was sent for.';

CREATE TABLE IF NOT EXISTS public.escrow_defects (
  id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  escrow_id     UUID          NOT NULL REFERENCES public.escrows(id) ON DELETE RESTRICT,
  description   TEXT          NOT NULL CHECK (btrim(description) <> ''),
  location      VARCHAR(255),
  repair_cost   DECIMAL(15,2) NOT NULL DEFAULT 0 CHECK (repair_cost >= 0),
  status        VARCHAR(10)   NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'repaired', 'waived')),
  repaired_at   DATE,
  recorded_by   UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_escrow_defects_escrow ON public.escrow_defects (escrow_id);
COMMENT ON TABLE public.escrow_defects IS 'Defect list from the inspection walk, with the repair cost of each item.';
DROP TRIGGER IF EXISTS trg_escrow_defects_updated_at ON public.escrow_defects;
CREATE TRIGGER trg_escrow_defects_updated_at BEFORE UPDATE ON public.escrow_defects
  FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

CREATE TABLE IF NOT EXISTS public.escrow_events (
  id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  event_no       BIGINT        GENERATED ALWAYS AS IDENTITY UNIQUE,
  escrow_id      UUID          NOT NULL REFERENCES public.escrows(id) ON DELETE RESTRICT,
  project_id     UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  event_type     VARCHAR(30)   NOT NULL,
  status_after   VARCHAR(20)   NOT NULL,
  actor_user_id  UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  note           TEXT,
  created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_escrow_events_escrow ON public.escrow_events (escrow_id, event_no);
COMMENT ON TABLE public.escrow_events IS 'Append-only history of an escrow: created, each status, defects, renewals, cost changes.';

CREATE OR REPLACE FUNCTION public.fn_block_escrow_event_mutation()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  RAISE EXCEPTION 'Escrow history is append-only and cannot be changed.' USING ERRCODE = 'PT403';
END;
$$;
DROP TRIGGER IF EXISTS trg_escrow_events_immutable ON public.escrow_events;
CREATE TRIGGER trg_escrow_events_immutable BEFORE UPDATE OR DELETE ON public.escrow_events
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_escrow_event_mutation();

ALTER TABLE public.property_taxes ADD COLUMN IF NOT EXISTS jurisdiction_id    UUID REFERENCES public.jurisdictions(id) ON DELETE RESTRICT;
ALTER TABLE public.property_taxes ADD COLUMN IF NOT EXISTS assessed_value     DECIMAL(15,2) CHECK (assessed_value IS NULL OR assessed_value >= 0);
ALTER TABLE public.property_taxes ADD COLUMN IF NOT EXISTS tax_rate_percent   DECIMAL(7,4) CHECK (tax_rate_percent IS NULL OR tax_rate_percent BETWEEN 0 AND 100);
ALTER TABLE public.property_taxes ADD COLUMN IF NOT EXISTS reminded_days      INTEGER;
ALTER TABLE public.property_taxes ADD COLUMN IF NOT EXISTS paid_at            DATE;
COMMENT ON COLUMN public.property_taxes.reminded_days IS 'Days before the due date the last reminder went out (dedupe for the reminder job).';
COMMENT ON COLUMN public.property_taxes.status        IS 'estimated | billed | in_approval | sent_to_finance (paid) | cancelled.';

-- RLS for the new tables: rls_policies.sql (LONG-TAIL RLS).


-- ============================================================================
-- SECTION B: LEDGER MOVEMENT TYPE
-- ============================================================================
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT conname FROM pg_constraint
            WHERE conrelid = 'public.contingency_ledger'::regclass AND contype = 'c'
              AND pg_get_constraintdef(oid) ILIKE '%movement_type%' LOOP
    EXECUTE format('ALTER TABLE public.contingency_ledger DROP CONSTRAINT %I', r.conname);
  END LOOP;
  ALTER TABLE public.contingency_ledger ADD CONSTRAINT chk_contingency_ledger_movement_type
    CHECK (movement_type IN ('initial_funding', 'bid_overrun', 'bid_savings', 'bid_reversal',
                             'variance_created', 'variance_adjusted', 'variance_cancelled',
                             'top_up', 'invoice_overage', 'long_tail'));
END $$;


-- ============================================================================
-- SECTION C: HELPERS
-- ============================================================================
CREATE OR REPLACE FUNCTION private.fin_can(p_user UUID, p_roles TEXT[])
RETURNS BOOLEAN LANGUAGE sql STABLE SET search_path = '' AS $$
  SELECT private.user_has_role(p_user, 'admin')
      OR EXISTS (SELECT 1 FROM unnest(p_roles) r WHERE private.user_has_role(p_user, r));
$$;

-- New long-tail line at the bottom of the budget, at $0.
CREATE OR REPLACE FUNCTION private.fin_new_long_tail_line(p_project UUID, p_subtype TEXT, p_name TEXT, p_actor UUID)
RETURNS UUID LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE v_id UUID;
BEGIN
  INSERT INTO public.budget_lines (project_id, line_type, line_subtype, name, section_name, sort_order,
                                   budget_amount, cash_bucket, created_by, updated_by)
  VALUES (p_project, 'long_tail', p_subtype, left(p_name, 255), 'Long-tail',
          COALESCE((SELECT max(sort_order) FROM public.budget_lines WHERE project_id = p_project AND deleted_at IS NULL), 0) + 10,
          0, 'land', p_actor, p_actor)
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;

-- Set a long-tail line's amount, keeping the total flat: an increase comes
-- first from the template's placeholder line of the same kind (not linked to
-- any escrow / tax), then from contingency (baselined, ledger row); a decrease
-- goes back to contingency. Draft budgets: the Unallocated line absorbs it.
CREATE OR REPLACE FUNCTION private.fin_set_long_tail_amount(p_line_id UUID, p_amount NUMERIC, p_actor UUID, p_reason TEXT)
RETURNS VOID LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_line    public.budget_lines;
  v_status  TEXT;
  v_holder  public.budget_lines;
  v_delta   NUMERIC;
  v_take    NUMERIC := 0;
BEGIN
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_line_id FOR UPDATE;
  v_delta := round(GREATEST(COALESCE(p_amount, 0), 0), 2) - v_line.budget_amount;
  IF v_delta = 0 THEN
    RETURN;
  END IF;
  SELECT budget_status INTO v_status FROM public.projects WHERE id = v_line.project_id;
  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  IF v_delta > 0 THEN
    SELECT * INTO v_holder FROM public.budget_lines b
     WHERE b.project_id = v_line.project_id AND b.line_type = 'long_tail' AND b.line_subtype = v_line.line_subtype
       AND b.id <> p_line_id AND b.deleted_at IS NULL AND b.budget_amount > 0
       AND NOT EXISTS (SELECT 1 FROM public.escrows e WHERE b.id IN (e.premium_line_id, e.repair_line_id))
       AND NOT EXISTS (SELECT 1 FROM public.property_taxes t WHERE t.budget_line_id = b.id)
     ORDER BY b.sort_order LIMIT 1 FOR UPDATE;
    IF FOUND THEN
      v_take := LEAST(v_delta, v_holder.budget_amount);
      UPDATE public.budget_lines SET budget_amount = budget_amount - v_take, updated_by = p_actor WHERE id = v_holder.id;
    END IF;
  END IF;

  UPDATE public.budget_lines SET budget_amount = budget_amount + v_delta, updated_by = p_actor WHERE id = p_line_id;
  IF v_status = 'baselined' AND v_delta - v_take <> 0 THEN
    PERFORM private.fin_move_contingency(v_line.project_id, -(v_delta - v_take), 'long_tail', p_actor,
                                         COALESCE(p_reason, v_line.name), p_line_id, NULL, NULL, NULL);
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION private.fin_escrow_event(p_escrow public.escrows, p_type TEXT, p_actor UUID, p_note TEXT)
RETURNS VOID LANGUAGE sql SET search_path = '' AS $$
  INSERT INTO public.escrow_events (escrow_id, project_id, event_type, status_after, actor_user_id, note)
  VALUES (p_escrow.id, p_escrow.project_id, p_type, p_escrow.status, p_actor, NULLIF(btrim(COALESCE(p_note, '')), ''));
$$;

-- Cash flow for the project's escrows and taxes (forecast rows, open months only).
CREATE OR REPLACE FUNCTION private.fin_refresh_long_tail_cash(p_project UUID)
RETURNS VOID LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  DELETE FROM public.cash_flow_entries c
   WHERE c.project_id = p_project AND c.entry_kind = 'forecast'
     AND (c.escrow_id IS NOT NULL
          OR c.budget_line_id IN (SELECT budget_line_id FROM public.property_taxes WHERE project_id = p_project))
     AND NOT EXISTS (SELECT 1 FROM public.accounting_periods a WHERE a.period_month = c.period_month AND a.status = 'closed');

  INSERT INTO public.cash_flow_entries (project_id, budget_line_id, escrow_id, period_month, direction, cash_bucket,
                                        amount, entry_kind, source_note)
  SELECT p_project, x.line_id, x.escrow_id, date_trunc('month', x.d)::date, x.dir, 'land', x.amount, 'forecast', x.note
    FROM (
      -- posted cash goes out, and comes back in on release
      SELECT NULL::uuid AS line_id, e.id AS escrow_id, e.posted_date AS d, 'out' AS dir, e.secured_amount AS amount,
             'Escrow cash posted: ' || e.name AS note
        FROM public.escrows e
       WHERE e.project_id = p_project AND e.deleted_at IS NULL AND e.security_form = 'cash'
         AND e.status NOT IN ('planned', 'cancelled') AND e.posted_date IS NOT NULL
      UNION ALL
      SELECT NULL, e.id, COALESCE(e.released_date, e.expected_release_date), 'in', e.secured_amount,
             'Escrow cash returned: ' || e.name
        FROM public.escrows e
       WHERE e.project_id = p_project AND e.deleted_at IS NULL AND e.security_form = 'cash'
         AND e.status NOT IN ('planned', 'cancelled') AND e.posted_date IS NOT NULL
         AND COALESCE(e.released_date, e.expected_release_date) IS NOT NULL
      UNION ALL
      SELECT e.premium_line_id, e.id, COALESCE(e.posted_date, CURRENT_DATE), 'out', b.budget_amount,
             'Escrow premium: ' || e.name
        FROM public.escrows e JOIN public.budget_lines b ON b.id = e.premium_line_id
       WHERE e.project_id = p_project AND e.deleted_at IS NULL AND e.status <> 'cancelled' AND b.budget_amount > 0
      UNION ALL
      SELECT e.repair_line_id, e.id,
             COALESCE(e.signoff_date, e.inspection_date, e.expected_release_date, e.posted_date, CURRENT_DATE), 'out',
             b.budget_amount, 'Escrow repairs: ' || e.name
        FROM public.escrows e JOIN public.budget_lines b ON b.id = e.repair_line_id
       WHERE e.project_id = p_project AND e.deleted_at IS NULL AND e.status <> 'cancelled' AND b.budget_amount > 0
      UNION ALL
      SELECT t.budget_line_id, NULL, COALESCE(t.paid_at, t.due_date, make_date(t.tax_year, 12, 31)), 'out',
             COALESCE(t.actual_amount, round(t.estimated_amount * (100 - COALESCE(t.sold_portion_percent, 0)) / 100, 2)),
             format('Property tax %s %s #%s', t.tax_year, t.jurisdiction, t.installment_number)
        FROM public.property_taxes t
       WHERE t.project_id = p_project AND t.status <> 'cancelled' AND t.budget_line_id IS NOT NULL
    ) x
   WHERE x.amount > 0 AND x.d IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM public.accounting_periods a
                      WHERE a.period_month = date_trunc('month', x.d)::date AND a.status = 'closed');
END;
$$;

-- Escrow lines = premiums so far, and the higher of the repair estimate and the defect list.
CREATE OR REPLACE FUNCTION private.fin_sync_escrow(p_escrow_id UUID, p_actor UUID)
RETURNS VOID LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_e       public.escrows;
  v_defects NUMERIC;
BEGIN
  SELECT * INTO v_e FROM public.escrows WHERE id = p_escrow_id;
  SELECT COALESCE(SUM(repair_cost), 0) INTO v_defects FROM public.escrow_defects
   WHERE escrow_id = p_escrow_id AND status <> 'waived';
  IF v_e.status = 'cancelled' THEN
    PERFORM private.fin_set_long_tail_amount(v_e.premium_line_id, 0, p_actor, 'Escrow cancelled: ' || v_e.name);
    PERFORM private.fin_set_long_tail_amount(v_e.repair_line_id, 0, p_actor, 'Escrow cancelled: ' || v_e.name);
  ELSE
    PERFORM private.fin_set_long_tail_amount(v_e.premium_line_id, v_e.premium_total, p_actor, 'Escrow premium: ' || v_e.name);
    PERFORM private.fin_set_long_tail_amount(v_e.repair_line_id, GREATEST(v_e.repair_estimate, v_defects), p_actor,
                                             'Escrow repairs: ' || v_e.name);
  END IF;
  PERFORM private.fin_refresh_long_tail_cash(v_e.project_id);
END;
$$;


-- ============================================================================
-- SECTION D: 7.1 / 7.2 ESCROWS
-- ============================================================================
-- p_data: name, beneficiary, covered_areas[], security_form, holder_type,
-- holder_name, secured_amount, premium_amount, premium_frequency, bond_number,
-- bond_expiry_date, jurisdiction_id, repair_estimate (NULL = jurisdiction %),
-- expected_release_date, notes.
CREATE OR REPLACE FUNCTION public.fn_save_escrow(p_project UUID, p_escrow_id UUID, p_actor UUID, p_data JSONB)
RETURNS SETOF public.escrows
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_project public.projects;
  v_e       public.escrows;
  v_old     public.escrows;
  v_pct     NUMERIC;
  v_repair  NUMERIC;
  v_secured NUMERIC := (p_data ->> 'secured_amount')::numeric;
  v_premium NUMERIC := COALESCE((p_data ->> 'premium_amount')::numeric, 0);
  v_areas   TEXT[]  := ARRAY(SELECT btrim(x) FROM jsonb_array_elements_text(COALESCE(p_data -> 'covered_areas', '[]'::jsonb)) x
                              WHERE btrim(x) <> '');
BEGIN
  IF NOT private.fin_can(p_actor, ARRAY['project_manager']) THEN
    RAISE EXCEPTION 'Only a project manager or admin can set up escrows.' USING ERRCODE = 'PT403';
  END IF;
  v_project := private.fin_lock_project(p_project, FALSE, FALSE);
  IF v_project.budget_status = 'none' THEN
    RAISE EXCEPTION 'Create the budget first: each escrow adds two budget lines.' USING ERRCODE = 'PT409';
  END IF;
  IF btrim(COALESCE(p_data ->> 'name', '')) = '' OR v_secured IS NULL OR v_secured < 0 THEN
    RAISE EXCEPTION 'An escrow needs a name and the value of the works it secures.' USING ERRCODE = 'PT422';
  END IF;
  IF array_length(v_areas, 1) IS NULL THEN
    RAISE EXCEPTION 'List at least one area the escrow covers (e.g. roads).' USING ERRCODE = 'PT422';
  END IF;
  IF p_data ->> 'security_form' = 'bond' AND btrim(COALESCE(p_data ->> 'holder_name', '')) = '' THEN
    RAISE EXCEPTION 'A bond needs its holder (insurance company, bank or other).' USING ERRCODE = 'PT422';
  END IF;
  IF v_premium < 0 THEN
    RAISE EXCEPTION 'The premium cannot be negative.' USING ERRCODE = 'PT422';
  END IF;

  v_repair := (p_data ->> 'repair_estimate')::numeric;
  IF v_repair IS NULL THEN
    SELECT repair_estimate_percent INTO v_pct FROM public.jurisdictions WHERE id = (p_data ->> 'jurisdiction_id')::uuid;
    v_repair := round(v_secured * COALESCE(v_pct, 0) / 100, 2);
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  IF p_escrow_id IS NULL THEN
    INSERT INTO public.escrows (
      project_id, name, beneficiary, covered_areas, security_form, holder_type, holder_name, secured_amount,
      premium_amount, premium_total, premium_frequency, bond_number, bond_expiry_date, jurisdiction_id,
      repair_estimate, expected_release_date, notes, status, created_by,
      premium_line_id, repair_line_id
    ) VALUES (
      p_project, btrim(p_data ->> 'name'), p_data ->> 'beneficiary', v_areas, p_data ->> 'security_form',
      NULLIF(p_data ->> 'holder_type', ''), NULLIF(btrim(COALESCE(p_data ->> 'holder_name', '')), ''), v_secured,
      v_premium, v_premium, COALESCE(p_data ->> 'premium_frequency', 'one_time'), NULLIF(p_data ->> 'bond_number', ''),
      (p_data ->> 'bond_expiry_date')::date, (p_data ->> 'jurisdiction_id')::uuid, v_repair,
      (p_data ->> 'expected_release_date')::date, NULLIF(p_data ->> 'notes', ''), 'planned', p_actor,
      private.fin_new_long_tail_line(p_project, 'escrow_bond_premium', 'Escrow premium: ' || btrim(p_data ->> 'name'), p_actor),
      private.fin_new_long_tail_line(p_project, 'escrow_repairs', 'Escrow repairs: ' || btrim(p_data ->> 'name'), p_actor)
    ) RETURNING * INTO v_e;
    PERFORM private.fin_escrow_event(v_e, 'created', p_actor, array_to_string(v_areas, ', '));
  ELSE
    SELECT * INTO v_old FROM public.escrows WHERE id = p_escrow_id AND project_id = p_project AND deleted_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Escrow not found' USING ERRCODE = 'PT404';
    END IF;
    IF v_old.status IN ('released', 'cancelled') THEN
      RAISE EXCEPTION 'This escrow is % and can no longer be changed.', v_old.status USING ERRCODE = 'PT409';
    END IF;
    UPDATE public.escrows SET
      name = btrim(p_data ->> 'name'), beneficiary = p_data ->> 'beneficiary', covered_areas = v_areas,
      security_form = p_data ->> 'security_form', holder_type = NULLIF(p_data ->> 'holder_type', ''),
      holder_name = NULLIF(btrim(COALESCE(p_data ->> 'holder_name', '')), ''), secured_amount = v_secured,
      premium_total = premium_total - premium_amount + v_premium, premium_amount = v_premium,
      premium_frequency = COALESCE(p_data ->> 'premium_frequency', premium_frequency),
      bond_number = NULLIF(p_data ->> 'bond_number', ''), bond_expiry_date = (p_data ->> 'bond_expiry_date')::date,
      jurisdiction_id = (p_data ->> 'jurisdiction_id')::uuid, repair_estimate = v_repair,
      expected_release_date = (p_data ->> 'expected_release_date')::date, notes = NULLIF(p_data ->> 'notes', ''),
      bond_reminder_sent_for = CASE WHEN (p_data ->> 'bond_expiry_date')::date IS DISTINCT FROM bond_expiry_date
                                    THEN NULL ELSE bond_reminder_sent_for END
     WHERE id = p_escrow_id RETURNING * INTO v_e;
    UPDATE public.budget_lines SET name = left('Escrow premium: ' || v_e.name, 255) WHERE id = v_e.premium_line_id;
    UPDATE public.budget_lines SET name = left('Escrow repairs: ' || v_e.name, 255) WHERE id = v_e.repair_line_id;
    PERFORM private.fin_escrow_event(v_e, 'updated', p_actor, NULL);
  END IF;

  PERFORM private.fin_sync_escrow(v_e.id, p_actor);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN QUERY SELECT * FROM public.escrows WHERE id = v_e.id;
END;
$$;

COMMENT ON FUNCTION public.fn_save_escrow(UUID, UUID, UUID, JSONB) IS
  'Creates (p_escrow_id NULL) or edits an escrow. A new escrow gets its two cost lines at the bottom of the budget: premium and repairs to city standard (estimate, or the jurisdiction % of the secured value).';

-- 7.3 lifecycle. One step forward at a time; corrections only with open defects.
CREATE OR REPLACE FUNCTION public.fn_escrow_transition(
  p_escrow_id UUID, p_actor UUID, p_to TEXT, p_date DATE, p_note TEXT, p_signoff_by TEXT
)
RETURNS SETOF public.escrows
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_e     public.escrows;
  v_open  INT;
  v_ok    BOOLEAN;
  v_date  DATE := COALESCE(p_date, CURRENT_DATE);
BEGIN
  SELECT * INTO v_e FROM public.escrows WHERE id = p_escrow_id AND deleted_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Escrow not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_e.project_id, FALSE, FALSE);
  SELECT * INTO v_e FROM public.escrows WHERE id = p_escrow_id FOR UPDATE;

  IF p_to IN ('posted', 'released', 'cancelled') THEN
    IF NOT private.fin_can(p_actor, ARRAY['project_manager']) THEN
      RAISE EXCEPTION 'Only a project manager or admin can post, release or cancel an escrow.' USING ERRCODE = 'PT403';
    END IF;
  ELSIF NOT private.fin_can(p_actor, ARRAY['field_manager', 'project_manager']) THEN
    RAISE EXCEPTION 'Only a field manager, project manager or admin can record the escrow works.' USING ERRCODE = 'PT403';
  END IF;

  SELECT count(*) INTO v_open FROM public.escrow_defects WHERE escrow_id = p_escrow_id AND status = 'open';
  v_ok := CASE p_to
    WHEN 'posted'      THEN v_e.status = 'planned'
    WHEN 'works_built' THEN v_e.status = 'posted'
    WHEN 'inspection'  THEN v_e.status IN ('works_built', 'corrections')
    WHEN 'corrections' THEN v_e.status = 'inspection' AND v_open > 0
    WHEN 'signed_off'  THEN v_e.status IN ('inspection', 'corrections')
    WHEN 'released'    THEN v_e.status = 'signed_off'
    WHEN 'cancelled'   THEN v_e.status IN ('planned', 'posted')
    ELSE FALSE END;
  IF NOT v_ok THEN
    RAISE EXCEPTION 'An escrow that is % cannot move to %.', replace(v_e.status, '_', ' '), replace(p_to, '_', ' ')
      USING ERRCODE = 'PT409';
  END IF;
  IF p_to = 'signed_off' AND v_open > 0 THEN
    RAISE EXCEPTION 'Repair or waive the % open defect(s) before the government sign-off.', v_open USING ERRCODE = 'PT409';
  END IF;
  IF p_to = 'signed_off' AND btrim(COALESCE(p_signoff_by, '')) = '' THEN
    RAISE EXCEPTION 'Record who signed off for the government.' USING ERRCODE = 'PT422';
  END IF;
  IF p_to = 'posted' AND v_e.security_form = 'bond' AND v_e.bond_expiry_date IS NULL THEN
    RAISE EXCEPTION 'Enter the bond expiry date before posting.' USING ERRCODE = 'PT422';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  UPDATE public.escrows SET
    status           = p_to,
    posted_date      = CASE WHEN p_to = 'posted' THEN v_date ELSE posted_date END,
    works_built_date = CASE WHEN p_to = 'works_built' THEN v_date ELSE works_built_date END,
    inspection_date  = CASE WHEN p_to = 'inspection' THEN v_date ELSE inspection_date END,
    inspection_notes = CASE WHEN p_to = 'inspection' THEN NULLIF(btrim(COALESCE(p_note, '')), '') ELSE inspection_notes END,
    signoff_date     = CASE WHEN p_to = 'signed_off' THEN v_date ELSE signoff_date END,
    signoff_by       = CASE WHEN p_to = 'signed_off' THEN btrim(p_signoff_by) ELSE signoff_by END,
    released_date    = CASE WHEN p_to = 'released' THEN GREATEST(v_date, COALESCE(posted_date, v_date)) ELSE released_date END
   WHERE id = p_escrow_id RETURNING * INTO v_e;
  PERFORM private.fin_escrow_event(v_e, p_to, p_actor, COALESCE(p_note, p_signoff_by));
  PERFORM private.fin_sync_escrow(p_escrow_id, p_actor);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_e;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_save_escrow_defect(
  p_escrow_id UUID, p_defect_id UUID, p_actor UUID, p_description TEXT, p_location TEXT, p_cost NUMERIC, p_status TEXT
)
RETURNS SETOF public.escrow_defects
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_e  public.escrows;
  v_d  public.escrow_defects;
BEGIN
  IF NOT private.fin_can(p_actor, ARRAY['field_manager', 'project_manager']) THEN
    RAISE EXCEPTION 'Only a field manager, project manager or admin can record defects.' USING ERRCODE = 'PT403';
  END IF;
  SELECT * INTO v_e FROM public.escrows WHERE id = p_escrow_id AND deleted_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Escrow not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_e.project_id, FALSE, FALSE);
  IF v_e.status NOT IN ('inspection', 'corrections') THEN
    RAISE EXCEPTION 'Defects are recorded at the inspection walk and during corrections.' USING ERRCODE = 'PT409';
  END IF;
  IF btrim(COALESCE(p_description, '')) = '' OR COALESCE(p_cost, 0) < 0 THEN
    RAISE EXCEPTION 'A defect needs a description and a repair cost of $0 or more.' USING ERRCODE = 'PT422';
  END IF;

  IF p_defect_id IS NULL THEN
    INSERT INTO public.escrow_defects (escrow_id, description, location, repair_cost, status, recorded_by)
    VALUES (p_escrow_id, btrim(p_description), NULLIF(btrim(COALESCE(p_location, '')), ''), COALESCE(p_cost, 0),
            COALESCE(p_status, 'open'), p_actor)
    RETURNING * INTO v_d;
  ELSE
    UPDATE public.escrow_defects
       SET description = btrim(p_description), location = NULLIF(btrim(COALESCE(p_location, '')), ''),
           repair_cost = COALESCE(p_cost, 0), status = COALESCE(p_status, status),
           repaired_at = CASE WHEN p_status = 'repaired' THEN COALESCE(repaired_at, CURRENT_DATE)
                              WHEN p_status = 'open' THEN NULL ELSE repaired_at END
     WHERE id = p_defect_id AND escrow_id = p_escrow_id RETURNING * INTO v_d;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Defect not found' USING ERRCODE = 'PT404';
    END IF;
  END IF;
  PERFORM private.fin_escrow_event(v_e, 'defect_' || v_d.status, p_actor, format('%s (%s)', v_d.description, v_d.repair_cost));
  PERFORM private.fin_sync_escrow(p_escrow_id, p_actor);
  RETURN NEXT v_d;
END;
$$;

-- Yearly bond renewal: the new premium is added to the premium line.
CREATE OR REPLACE FUNCTION public.fn_renew_escrow_bond(p_escrow_id UUID, p_actor UUID, p_new_expiry DATE, p_premium NUMERIC)
RETURNS SETOF public.escrows
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE v_e public.escrows;
BEGIN
  IF NOT private.fin_can(p_actor, ARRAY['project_manager', 'finance']) THEN
    RAISE EXCEPTION 'Only a project manager, finance or admin can record a bond renewal.' USING ERRCODE = 'PT403';
  END IF;
  SELECT * INTO v_e FROM public.escrows WHERE id = p_escrow_id AND deleted_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Escrow not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_e.project_id, FALSE, FALSE);
  SELECT * INTO v_e FROM public.escrows WHERE id = p_escrow_id FOR UPDATE;
  IF v_e.security_form <> 'bond' OR v_e.status IN ('released', 'cancelled') THEN
    RAISE EXCEPTION 'Only an open bond can be renewed.' USING ERRCODE = 'PT409';
  END IF;
  IF p_new_expiry IS NULL OR p_new_expiry <= COALESCE(v_e.bond_expiry_date, CURRENT_DATE) OR COALESCE(p_premium, -1) < 0 THEN
    RAISE EXCEPTION 'Enter a new expiry date after the current one and the renewal premium.' USING ERRCODE = 'PT422';
  END IF;
  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  UPDATE public.escrows SET bond_expiry_date = p_new_expiry, premium_total = premium_total + p_premium,
                            bond_reminder_sent_for = NULL
   WHERE id = p_escrow_id RETURNING * INTO v_e;
  PERFORM private.fin_escrow_event(v_e, 'bond_renewed', p_actor, format('Until %s, premium %s', p_new_expiry, p_premium));
  PERFORM private.fin_sync_escrow(p_escrow_id, p_actor);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_e;
END;
$$;


-- ============================================================================
-- SECTION E: 7.4 PROPERTY TAXES
-- ============================================================================
CREATE OR REPLACE FUNCTION private.fin_sync_tax_line(p_line_id UUID, p_actor UUID)
RETURNS VOID LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE v_total NUMERIC;
BEGIN
  SELECT COALESCE(SUM(COALESCE(actual_amount, round(estimated_amount * (100 - COALESCE(sold_portion_percent, 0)) / 100, 2))), 0)
    INTO v_total FROM public.property_taxes WHERE budget_line_id = p_line_id AND status <> 'cancelled';
  PERFORM private.fin_set_long_tail_amount(p_line_id, v_total, p_actor, 'Property tax');
END;
$$;

-- One year for one jurisdiction: instalments on its due dates, estimate by
-- basis (prior_year_actual | assessed_value | manual), split evenly.
CREATE OR REPLACE FUNCTION public.fn_set_property_tax_year(
  p_project UUID, p_actor UUID, p_year INT, p_jurisdiction_id UUID, p_basis TEXT,
  p_amount NUMERIC, p_assessed NUMERIC, p_rate NUMERIC, p_sold_percent NUMERIC, p_parcel TEXT
)
RETURNS JSONB
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_project public.projects;
  v_j       public.jurisdictions;
  v_line    UUID;
  v_total   NUMERIC;
  v_n       INT;
  v_i       INT := 0;
  v_inst    JSONB;
  v_each    NUMERIC;
BEGIN
  IF NOT private.fin_can(p_actor, ARRAY['project_manager', 'finance']) THEN
    RAISE EXCEPTION 'Only a project manager, finance or admin can set property taxes.' USING ERRCODE = 'PT403';
  END IF;
  v_project := private.fin_lock_project(p_project, FALSE, FALSE);
  IF v_project.budget_status = 'none' THEN
    RAISE EXCEPTION 'Create the budget first: each tax year is a budget line.' USING ERRCODE = 'PT409';
  END IF;
  SELECT * INTO v_j FROM public.jurisdictions WHERE id = p_jurisdiction_id AND deleted_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Choose the city or county the tax is paid to.' USING ERRCODE = 'PT422';
  END IF;
  IF p_year IS NULL OR p_year < 2000 OR p_year > 2200 THEN
    RAISE EXCEPTION 'Enter a valid tax year.' USING ERRCODE = 'PT422';
  END IF;
  IF COALESCE(p_sold_percent, 0) NOT BETWEEN 0 AND 100 THEN
    RAISE EXCEPTION 'The sold portion is a %% between 0 and 100.' USING ERRCODE = 'PT422';
  END IF;

  v_total := CASE p_basis
    -- Last year's bills; an instalment not billed yet counts at its estimate.
    WHEN 'prior_year_actual' THEN (SELECT SUM(COALESCE(actual_amount, estimated_amount)) FROM public.property_taxes
                                    WHERE project_id = p_project AND jurisdiction_id = p_jurisdiction_id
                                      AND tax_year = p_year - 1 AND status <> 'cancelled'
                                   HAVING count(actual_amount) > 0)
    WHEN 'assessed_value' THEN round(p_assessed * p_rate / 100, 2)
    WHEN 'manual' THEN p_amount
  END;
  IF v_total IS NULL OR v_total < 0 THEN
    RAISE EXCEPTION '%', CASE p_basis
      WHEN 'prior_year_actual' THEN format('There is no actual for %s to start from. Enter the amount or the assessed value.', p_year - 1)
      WHEN 'assessed_value' THEN 'Enter the assessed value and the tax rate %.'
      ELSE 'Enter the estimated amount.' END USING ERRCODE = 'PT422';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  SELECT budget_line_id INTO v_line FROM public.property_taxes
   WHERE project_id = p_project AND tax_year = p_year AND budget_line_id IS NOT NULL LIMIT 1;
  IF v_line IS NULL THEN
    v_line := private.fin_new_long_tail_line(p_project, 'property_tax', format('Property tax %s', p_year), p_actor);
  END IF;

  v_n := jsonb_array_length(v_j.tax_installments);
  v_each := round(v_total / v_n, 2);
  FOR v_inst IN SELECT value FROM jsonb_array_elements(v_j.tax_installments) LOOP
    v_i := v_i + 1;
    INSERT INTO public.property_taxes (
      project_id, budget_line_id, tax_year, jurisdiction, jurisdiction_id, parcel_reference, installment_number,
      due_date, estimate_basis, estimated_amount, assessed_value, tax_rate_percent, sold_portion_percent, status, created_by
    ) VALUES (
      p_project, v_line, p_year, v_j.name, v_j.id, NULLIF(btrim(COALESCE(p_parcel, '')), ''), v_i,
      -- Day past the month's end (e.g. 31 in June) becomes the last day.
      LEAST(make_date(p_year, (v_inst ->> 'month')::int, 1) + ((v_inst ->> 'day')::int - 1),
            (make_date(p_year, (v_inst ->> 'month')::int, 1) + INTERVAL '1 month - 1 day')::date),
      p_basis, CASE WHEN v_i = v_n THEN v_total - v_each * (v_n - 1) ELSE v_each END,
      p_assessed, p_rate, p_sold_percent, 'estimated', p_actor
    )
    ON CONFLICT (project_id, tax_year, jurisdiction, installment_number) DO UPDATE
       SET estimate_basis = EXCLUDED.estimate_basis, estimated_amount = EXCLUDED.estimated_amount,
           assessed_value = EXCLUDED.assessed_value, tax_rate_percent = EXCLUDED.tax_rate_percent,
           sold_portion_percent = EXCLUDED.sold_portion_percent, due_date = EXCLUDED.due_date,
           parcel_reference = COALESCE(EXCLUDED.parcel_reference, public.property_taxes.parcel_reference),
           jurisdiction_id = EXCLUDED.jurisdiction_id
     WHERE public.property_taxes.status IN ('estimated', 'billed');
  END LOOP;

  PERFORM private.fin_sync_tax_line(v_line, p_actor);
  PERFORM private.fin_refresh_long_tail_cash(p_project);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN jsonb_build_object('budget_line_id', v_line, 'estimated_total', v_total, 'installments', v_n);
END;
$$;

-- Edit one instalment: billed / actual amount (catches increases), due date, paid, cancelled.
CREATE OR REPLACE FUNCTION public.fn_update_property_tax(
  p_id UUID, p_actor UUID, p_estimated NUMERIC, p_actual NUMERIC, p_due DATE, p_status TEXT, p_sold_percent NUMERIC
)
RETURNS SETOF public.property_taxes
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE v_t public.property_taxes;
BEGIN
  IF NOT private.fin_can(p_actor, ARRAY['project_manager', 'finance']) THEN
    RAISE EXCEPTION 'Only a project manager, finance or admin can change property taxes.' USING ERRCODE = 'PT403';
  END IF;
  SELECT * INTO v_t FROM public.property_taxes WHERE id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Property tax not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_t.project_id, FALSE, FALSE);
  IF p_status IS NOT NULL AND p_status NOT IN ('estimated', 'billed', 'sent_to_finance', 'cancelled') THEN
    RAISE EXCEPTION 'Unknown property tax status' USING ERRCODE = 'PT422';
  END IF;
  IF COALESCE(p_estimated, 0) < 0 OR COALESCE(p_actual, 0) < 0 OR COALESCE(p_sold_percent, 0) NOT BETWEEN 0 AND 100 THEN
    RAISE EXCEPTION 'Amounts must be $0 or more and the sold portion 0 to 100%%.' USING ERRCODE = 'PT422';
  END IF;
  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  UPDATE public.property_taxes SET
    estimated_amount = COALESCE(p_estimated, estimated_amount),
    actual_amount = p_actual,
    due_date = COALESCE(p_due, due_date),
    sold_portion_percent = COALESCE(p_sold_percent, sold_portion_percent),
    status = COALESCE(p_status, CASE WHEN p_actual IS NOT NULL AND status = 'estimated' THEN 'billed' ELSE status END),
    paid_at = CASE WHEN COALESCE(p_status, status) = 'sent_to_finance' THEN COALESCE(paid_at, CURRENT_DATE) ELSE NULL END,
    reminded_days = CASE WHEN p_due IS DISTINCT FROM NULL AND p_due <> due_date THEN NULL ELSE reminded_days END
   WHERE id = p_id RETURNING * INTO v_t;
  PERFORM private.fin_sync_tax_line(v_t.budget_line_id, p_actor);
  PERFORM private.fin_refresh_long_tail_cash(v_t.project_id);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_t;
END;
$$;

-- As lots / homes sell: the sold % on every open instalment from a year on.
CREATE OR REPLACE FUNCTION public.fn_set_tax_sold_portion(p_project UUID, p_actor UUID, p_percent NUMERIC, p_from_year INT)
RETURNS INT
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_line UUID;
  v_n    INT;
BEGIN
  IF NOT private.fin_can(p_actor, ARRAY['project_manager', 'finance']) THEN
    RAISE EXCEPTION 'Only a project manager, finance or admin can change property taxes.' USING ERRCODE = 'PT403';
  END IF;
  IF p_percent IS NULL OR p_percent NOT BETWEEN 0 AND 100 THEN
    RAISE EXCEPTION 'The sold portion is a %% between 0 and 100.' USING ERRCODE = 'PT422';
  END IF;
  PERFORM private.fin_lock_project(p_project, FALSE, FALSE);
  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  UPDATE public.property_taxes SET sold_portion_percent = p_percent
   WHERE project_id = p_project AND tax_year >= COALESCE(p_from_year, 0) AND status IN ('estimated', 'billed')
     AND actual_amount IS NULL;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  FOR v_line IN SELECT DISTINCT budget_line_id FROM public.property_taxes
                 WHERE project_id = p_project AND budget_line_id IS NOT NULL LOOP
    PERFORM private.fin_sync_tax_line(v_line, p_actor);
  END LOOP;
  PERFORM private.fin_refresh_long_tail_cash(p_project);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN v_n;
END;
$$;


-- ============================================================================
-- SECTION F: 5.1 HEALTH INPUTS — long-tail paid counts as spent
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_project_health_inputs(p_project_id UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  SELECT jsonb_build_object(
    'project_id',            p.id,
    'project_name',          p.name,
    'status',                p.status,
    'budget_status',         p.budget_status,
    'archived',              p.archived_at IS NOT NULL,
    'manager_id',            p.manager_id,
    'field_manager_id',      p.field_manager_id,
    'groundbreaking_at',     p.groundbreaking_at,
    'reserve',               p.long_tail_reserve_amount,
    'contingency',           (SELECT b.budget_amount FROM public.budget_lines b
                               WHERE b.project_id = p.id AND b.line_type = 'contingency' AND b.deleted_at IS NULL),
    'contingency_base',      COALESCE(p.contingency_at_groundbreaking,
                               (SELECT cb.approved_amount FROM public.contingency_buckets cb
                                 WHERE cb.project_id = p.id AND cb.bucket_kind = 'initial')),
    'total_budget',          (SELECT COALESCE(SUM(b.budget_amount), 0) FROM public.budget_lines b
                               WHERE b.project_id = p.id AND b.deleted_at IS NULL),
    'lines',                 (SELECT COALESCE(jsonb_agg(jsonb_build_object(
                                'committed',   b.committed_amount,
                                'approved',    COALESCE(pay.approved, 0),
                                'sent',        COALESCE(pay.sent, 0),
                                'land_closed', COALESCE(lc.closed, 0) + COALESCE(lt.paid, 0))), '[]'::jsonb)
                               FROM public.budget_lines b
                               LEFT JOIN LATERAL (
                                 SELECT SUM(x.amount) FILTER (WHERE x.status = 'approved')        AS approved,
                                        SUM(x.amount) FILTER (WHERE x.status = 'sent_to_finance') AS sent
                                   FROM public.payment_approvals x WHERE x.budget_line_id = b.id
                               ) pay ON TRUE
                               LEFT JOIN LATERAL (
                                 SELECT SUM(y.amount) AS closed FROM public.land_closings y
                                  WHERE y.budget_line_id = b.id AND y.status = 'closed'
                               ) lc ON TRUE
                               -- Long-tail: taxes paid, and an escrow's costs once it is released.
                               LEFT JOIN LATERAL (
                                 SELECT COALESCE((SELECT SUM(t.actual_amount) FROM public.property_taxes t
                                                   WHERE t.budget_line_id = b.id AND t.status = 'sent_to_finance'), 0)
                                      + COALESCE((SELECT b.budget_amount FROM public.escrows e
                                                   WHERE b.id IN (e.premium_line_id, e.repair_line_id)
                                                     AND e.status = 'released' LIMIT 1), 0) AS paid
                               ) lt ON b.line_type = 'long_tail'
                              WHERE b.project_id = p.id AND b.deleted_at IS NULL AND b.line_type <> 'contingency'),
    'milestones_total',      ms.total,
    'milestones_completed',  ms.done,
    'near_zero_percent',     COALESCE((SELECT (value #>> '{}')::numeric FROM public.financial_settings
                                        WHERE setting_key = 'contingency_near_zero_percent'), 5)
  )
  FROM public.projects p
  CROSS JOIN LATERAL (
    SELECT count(*) AS total, count(*) FILTER (WHERE m.status = 'completed') AS done
      FROM public.milestones m
      JOIN public.tasks t ON t.id = m.task_id
     WHERE t.project_id = p.id AND t.deleted_at IS NULL AND m.status <> 'cancelled'
  ) ms
  WHERE p.id = p_project_id AND p.deleted_at IS NULL;
$$;


-- ============================================================================
-- SECTION G: 7.5 READ SURFACE
-- ============================================================================
CREATE OR REPLACE VIEW public.v_escrows
WITH (security_invoker = true) AS
SELECT e.id, e.project_id, p.name AS project_name, e.name, e.beneficiary, e.covered_areas, e.security_form,
       e.holder_type, e.holder_name, e.secured_amount, e.premium_amount, e.premium_total, e.premium_frequency,
       e.bond_number, e.bond_expiry_date, e.status, e.posted_date, e.works_built_date, e.inspection_date,
       e.inspection_notes, e.signoff_date, e.signoff_by, e.expected_release_date, e.released_date,
       e.jurisdiction_id, j.name AS jurisdiction_name, e.repair_estimate,
       e.premium_line_id, pl.budget_amount AS premium_line_amount,
       e.repair_line_id, rl.budget_amount AS repair_line_amount,
       COALESCE(d.open_count, 0) AS open_defects, COALESCE(d.total, 0) AS defects_total,
       e.document_path, e.document_name, e.notes, e.created_at, e.updated_at
  FROM public.escrows e
  JOIN public.projects p ON p.id = e.project_id AND p.deleted_at IS NULL
  LEFT JOIN public.jurisdictions j ON j.id = e.jurisdiction_id
  LEFT JOIN public.budget_lines pl ON pl.id = e.premium_line_id
  LEFT JOIN public.budget_lines rl ON rl.id = e.repair_line_id
  LEFT JOIN LATERAL (
    SELECT count(*) FILTER (WHERE status = 'open') AS open_count,
           SUM(repair_cost) FILTER (WHERE status <> 'waived') AS total
      FROM public.escrow_defects WHERE escrow_id = e.id
  ) d ON TRUE
 WHERE e.deleted_at IS NULL;

CREATE OR REPLACE VIEW public.v_property_taxes
WITH (security_invoker = true) AS
SELECT t.id, t.project_id, p.name AS project_name, t.budget_line_id, t.tax_year, t.jurisdiction, t.jurisdiction_id,
       t.parcel_reference, t.installment_number, t.due_date, t.estimate_basis, t.estimated_amount, t.actual_amount,
       t.assessed_value, t.tax_rate_percent, t.sold_portion_percent,
       COALESCE(t.actual_amount, round(t.estimated_amount * (100 - COALESCE(t.sold_portion_percent, 0)) / 100, 2)) AS amount_due,
       t.actual_amount - t.estimated_amount AS increase, t.status, t.paid_at, t.reminded_days,
       p.manager_id, t.created_at, t.updated_at
  FROM public.property_taxes t
  JOIN public.projects p ON p.id = t.project_id AND p.deleted_at IS NULL;

COMMENT ON VIEW public.v_property_taxes IS
  'Property tax instalments with the amount due (actual, else estimate less the sold portion) and the increase of actual over estimate.';


-- ============================================================================
-- SECTION H: PRIVILEGES
-- ============================================================================
REVOKE ALL ON public.v_escrows, public.v_property_taxes FROM PUBLIC, anon;
GRANT SELECT ON public.v_escrows, public.v_property_taxes TO authenticated, service_role;

REVOKE ALL ON FUNCTION private.fin_can(uuid, text[])                                      FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.fin_can(uuid, text[])                                   TO authenticated, service_role;
REVOKE ALL ON FUNCTION private.fin_new_long_tail_line(uuid, text, text, uuid)             FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_set_long_tail_amount(uuid, numeric, uuid, text)        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_escrow_event(public.escrows, text, uuid, text)         FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_refresh_long_tail_cash(uuid)                           FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_sync_escrow(uuid, uuid)                                FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_sync_tax_line(uuid, uuid)                              FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.fin_new_long_tail_line(uuid, text, text, uuid)          TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_set_long_tail_amount(uuid, numeric, uuid, text)     TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_escrow_event(public.escrows, text, uuid, text)      TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_refresh_long_tail_cash(uuid)                        TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_sync_escrow(uuid, uuid)                             TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_sync_tax_line(uuid, uuid)                           TO service_role;

REVOKE ALL ON FUNCTION public.fn_block_escrow_event_mutation() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_save_escrow(uuid, uuid, uuid, jsonb)                                         FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_escrow_transition(uuid, uuid, text, date, text, text)                        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_save_escrow_defect(uuid, uuid, uuid, text, text, numeric, text)              FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_renew_escrow_bond(uuid, uuid, date, numeric)                                 FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_set_property_tax_year(uuid, uuid, int, uuid, text, numeric, numeric, numeric, numeric, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_update_property_tax(uuid, uuid, numeric, numeric, date, text, numeric)       FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_set_tax_sold_portion(uuid, uuid, numeric, int)                               FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_save_escrow(uuid, uuid, uuid, jsonb)                                      TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_escrow_transition(uuid, uuid, text, date, text, text)                     TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_save_escrow_defect(uuid, uuid, uuid, text, text, numeric, text)           TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_renew_escrow_bond(uuid, uuid, date, numeric)                              TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_set_property_tax_year(uuid, uuid, int, uuid, text, numeric, numeric, numeric, numeric, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_update_property_tax(uuid, uuid, numeric, numeric, date, text, numeric)    TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_set_tax_sold_portion(uuid, uuid, numeric, int)                            TO service_role;


-- ============================================================================
-- SECTION I: SETTINGS AND VERSION MARKER
-- ============================================================================
INSERT INTO public.financial_settings (setting_key, value, description) VALUES
  ('bond_renewal_reminder_days', '60'::jsonb, 'Days before a bond expires that the renewal reminder is sent (again at 14 days).')
ON CONFLICT (setting_key) DO NOTHING;

INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.8.0 (20261128_financial_phase7_long_tail)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================