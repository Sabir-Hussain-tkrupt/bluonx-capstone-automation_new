-- ============================================================================
-- BluOnX Bid Management & Vendor Coordination System
-- Complete Database Schema — PostgreSQL / Supabase
-- ============================================================================
-- Version:  3.9
-- Date:     September 2, 2026
-- Author:   Awais Anwer (Tkrupt)
-- Tables:   34
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


-- ============================================================================
-- END OF SCHEMA
-- ============================================================================