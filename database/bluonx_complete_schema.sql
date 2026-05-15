-- ============================================================================
-- BluOnX Bid Management & Vendor Coordination System
-- Complete Database Schema — PostgreSQL / Supabase
-- ============================================================================
-- Version:  2.31
-- Date:     May 14, 2026
-- Author:   Awais Anwer (Tkrupt)
-- Tables:   29
-- Engine:   PostgreSQL via Supabase
-- ============================================================================
--
-- TABLE GROUPS:
--   1. Access Control            (1 table)
--   2. Trade & Vendor Management (5 tables)
--   3. Project & Task Management (3 tables)
--   4. Bid Lifecycle             (11 tables)  ← was 10; +bid_revision_requests
--   5. Award & Contract          (3 tables)
--   6. Milestone Tracking        (3 tables)
--   7. Communication & Audit     (3 tables)
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
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at    TIMESTAMPTZ
);

COMMENT ON TABLE  users           IS 'Internal user profiles extending Supabase auth.users.';
COMMENT ON COLUMN users.id        IS 'Matches auth.users.id — set on insert, not auto-generated.';
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
  file_type     VARCHAR(50),
  file_size     BIGINT,
  uploaded_by   UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  uploaded_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  project_documents           IS 'Docs uploaded at project level. Shared to vendors via bid_package_documents.';
COMMENT ON COLUMN project_documents.file_path IS 'Reference path in Supabase Storage (project-documents bucket).';


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
  status        VARCHAR(20)   NOT NULL DEFAULT 'open'
                              CHECK (status IN ('open', 'closed', 'evaluating', 'cancelled')),

  bid_template_id UUID        REFERENCES bid_templates(id) ON DELETE RESTRICT,
  created_by    UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  bid_packages              IS 'A bidding round for a task. Multiple rounds via round_number for rebidding. RULE: must not be created for tasks with bid_type = internal (enforced at application layer).';
COMMENT ON COLUMN bid_packages.round_number IS 'Auto-set by trigger: round 1 = first attempt, round 2 = rebid, etc.';
COMMENT ON COLUMN bid_packages.instructions IS 'Optional PM-supplied bid-submission instructions shown to vendors in the bid portal and invitation email. Distinct from tasks.description (scope of work). Examples: include mobilization as separate line item, bid held firm for 30 days, unit prices all-inclusive.';


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
                                  CHECK (status IN ('sent', 'opened', 'submitted', 'declined',
                                                    'expired', 'no_response')),
  sent_at           TIMESTAMPTZ,
  opened_at         TIMESTAMPTZ,
  responded_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  UNIQUE (bid_package_id, vendor_id)
);

COMMENT ON TABLE bid_invitations IS 'Individual invitation per vendor per bid package. Tracks delivery and response status.';


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
  supersedes_submission_id UUID    REFERENCES bid_submissions(id) ON DELETE RESTRICT,
  is_superseded       BOOLEAN       NOT NULL DEFAULT FALSE,
  revision_number     INTEGER       NOT NULL DEFAULT 1 CHECK (revision_number >= 1),
  created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_bid_submissions_supersedes_not_self
    CHECK (supersedes_submission_id IS NULL OR supersedes_submission_id != id),
);

COMMENT ON TABLE  bid_submissions              IS 'Vendor bid response. One per invitation. Supports draft state for auto-save.';
COMMENT ON COLUMN bid_submissions.is_draft     IS 'TRUE while vendor is editing. Set FALSE on final submission.';
COMMENT ON COLUMN bid_submissions.is_direct_assign IS 'TRUE for synthetic submissions created via direct_assign flow. Distinguishes from competitive bids.';
COMMENT ON COLUMN bid_submissions.vendor_id    IS 'Denormalized for query perf. Enforced = bid_invitations.vendor_id by trigger.';
COMMENT ON COLUMN bid_submissions.supersedes_submission_id IS 'Chain pointer to the predecessor submission this row supersedes. NULL = original. RESTRICT delete (audit chain).';
COMMENT ON COLUMN bid_submissions.is_superseded IS 'TRUE when a newer revision exists. Trigger-maintained by fn_flip_superseded_on_revision_finalize.';
COMMENT ON COLUMN bid_submissions.revision_number IS 'Human-visible version number. 1 = original. Each revision increments by 1 (enforced by fn_enforce_supersession_chain).';


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
  file_type           VARCHAR(50),
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
  has_override            BOOLEAN       NOT NULL DEFAULT FALSE,
  override_justification  TEXT,
  validation_results      JSONB,
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


-- Contracts: one per accepted award
CREATE TABLE contracts (
  id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  award_id          UUID          NOT NULL UNIQUE REFERENCES awards(id) ON DELETE RESTRICT,
  vendor_id         UUID          NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,
  task_id           UUID          NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
  contract_number   VARCHAR(50)   NOT NULL UNIQUE,
  start_date        DATE,
  end_date          DATE,
  contract_amount   DECIMAL(15,2) NOT NULL CHECK (contract_amount >= 0),
  payment_terms     TEXT,
  status            VARCHAR(20)   NOT NULL DEFAULT 'draft'
                                  CHECK (status IN ('draft', 'sent_for_signature', 'executed',
                                                    'active', 'completed', 'terminated')),
  signed_at         TIMESTAMPTZ,
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  contracts              IS 'Contract record. One per accepted award. Partial unique on task_id allows re-contracting. RULE: must not be created for tasks with bid_type = internal (enforced at application layer).';
COMMENT ON COLUMN contracts.vendor_id   IS 'Denormalized for query perf. Enforced = awards.vendor_id by trigger.';
COMMENT ON COLUMN contracts.task_id     IS 'Denormalized for query perf. Enforced = awards.task_id (via bid_submission) by trigger.';


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
  actual_start_date DATE,
  actual_end_date   DATE,
  status            VARCHAR(20)   NOT NULL DEFAULT 'scheduled'
                                  CHECK (status IN ('scheduled', 'started', 'on_track', 'delayed', 'completed')),
  sort_order        INTEGER       NOT NULL DEFAULT 0,
  notes             TEXT,
  created_by        UUID          NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  milestones                    IS 'Work milestones for awarded tasks. Tracked via automated email check-ins. RULE: must not be created for tasks with bid_type = internal (enforced at application layer).';
COMMENT ON COLUMN milestones.task_id            IS 'Denormalized for query perf. Enforced = contracts.task_id by trigger.';
COMMENT ON COLUMN milestones.actual_start_date  IS 'Set when vendor confirms start. Compared with planned start_date.';


-- Milestone responses: vendor yes/no from email links (immutable audit)
CREATE TABLE milestone_responses (
  id                    UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  milestone_id          UUID          NOT NULL REFERENCES milestones(id) ON DELETE RESTRICT,
  response_type         VARCHAR(30)   NOT NULL
                                      CHECK (response_type IN ('start_confirmation', 'progress_check',
                                                                'completion_confirmation')),
  response_value        VARCHAR(10)   NOT NULL CHECK (response_value IN ('yes', 'no')),
  response_token_hash   VARCHAR(255)  NOT NULL,
  vendor_contact_id     UUID          NOT NULL REFERENCES vendor_contacts(id) ON DELETE RESTRICT,
  responded_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE milestone_responses IS 'Logs every vendor email-link response. Immutable audit record.';


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
  response_token_hash   VARCHAR(255),
  created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  milestone_alerts             IS 'Milestone-specific email tracking. References email_log for delivery details (no duplication).';
COMMENT ON COLUMN milestone_alerts.email_log_id IS 'FK to email_log. Delivery status lives there, milestone context lives here.';


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
  status            VARCHAR(20)   NOT NULL DEFAULT 'queued'
                                  CHECK (status IN ('queued', 'sent', 'delivered', 'bounced', 'failed')),
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
-- SECTION 3: DEFERRED FOREIGN KEYS
-- (for tables created before their referenced tables)
-- ============================================================================

-- milestone_alerts → email_log FK (email_log created after milestone_alerts)
ALTER TABLE milestone_alerts
  ADD CONSTRAINT fk_milestone_alerts_email_log
  FOREIGN KEY (email_log_id) REFERENCES email_log(id) ON DELETE SET NULL;


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

-- ---- Group 5: Award & Contract ----
CREATE INDEX idx_awards_task_id                     ON awards (task_id);
CREATE INDEX idx_awards_vendor_id                   ON awards (vendor_id);
CREATE INDEX idx_awards_status                      ON awards (status);
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

-- ---- Group 7: Communication & Audit ----
CREATE INDEX idx_email_log_type_status              ON email_log (email_type, status);
CREATE INDEX idx_email_log_reference                ON email_log (reference_type, reference_id);
CREATE INDEX idx_email_log_sent_at                  ON email_log (sent_at);
CREATE INDEX idx_vendor_flags_vendor_id             ON vendor_flags (vendor_id);
CREATE INDEX idx_vendor_flags_unresolved            ON vendor_flags (vendor_id, is_resolved)
                                                    WHERE is_resolved = FALSE;
CREATE INDEX idx_notifications_user_unread          ON notifications (user_id, is_read)
                                                    WHERE is_read = FALSE;


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
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- NOTE: This trigger is on auth.users (Supabase managed schema).
-- Run this AFTER the public schema is deployed.
CREATE TRIGGER trg_on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION fn_handle_new_auth_user();




-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
-- Total tables:    29
-- Total indexes:   55 custom (51 regular + 4 partial unique) + auto PK/UNIQUE
-- Total triggers:  29 (28 active + 1 disabled onboarding sync)
-- Total functions: 14 (13 active + 1 disabled onboarding sync)
-- ============================================================================
