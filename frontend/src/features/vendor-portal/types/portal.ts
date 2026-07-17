/**
 * Vendor Portal — types that mirror the response contracts from
 * Task 5.2 (POST /v1/vendor-auth/validate-token) and Task 5.3
 * (/v1/vendor-portal/*). Frontend-only for now: real endpoints
 * will swap into portalApi.ts without changing these types.
 */

export type TemplateItemType = 'lump_sum' | 'unit_price';

export interface PortalVendor {
  id: string;
  company_name: string;
  primary_contact_name: string;
  email: string;
  phone: string | null;
}

export interface PortalProject {
  id: string;
  name: string;
  location: string;
  address: string;
}

export interface PortalTask {
  id: string;
  name: string;
  description: string;
  trade_name: string;
}

export interface PortalBidPackage {
  id: string;
  round_number: number;
  deadline: string;
  instructions: string;
  /** PM-set target start date (Task 8.1.5). ISO date string or null. */
  desired_start_date: string | null;
  /** PM-pinned Scope of Work the vendor must review and attest to. */
  scope_of_work_document_id: string | null;
  scope_of_work_file_name: string | null;
}

export interface PortalTemplateItem {
  id: string;
  description: string;
  item_type: TemplateItemType;
  unit_of_measure: string | null;
  sort_order: number;
}

export interface PortalBidTemplate {
  id: string;
  name: string;
  is_lump_sum: boolean;
  items: PortalTemplateItem[];
}

export interface PortalProjectDocument {
  id: string;
  file_name: string;
  file_size_bytes: number;
  uploaded_at: string;
}

export interface BidDraftLineItem {
  template_item_id: string;
  quantity: number | null;
  unit_price: number | null;
  lump_sum_amount: number | null;
}

export interface BidDraft {
  id: string;
  vendor_notes: string;
  total_amount: number | null;
  line_items: BidDraftLineItem[];
  attachment_ids: string[];
  last_saved_at: string;
  /** Vendor's committed start date (Task 8.1.5). ISO date string or null. */
  proposed_start_date: string | null;
  /** Vendor's typed CAPS SoW attestation (saved on draft, re-typed on revision). */
  sow_attested_name: string | null;
}

/**
 * Present only when the vendor entered via a revision magic link
 * (mirrors backend VendorRevisionContextModel). `null`/absent on
 * initial-bid tokens — the initial flow must not branch on this.
 */
export interface VendorRevisionContext {
  bid_revision_request_id: string;
  pm_note: string;
  revision_deadline: string; // ISO 8601 timestamptz
  original_submission_id: string;
  original_revision_number: number;
}

export interface VendorBidContext {
  vendor: PortalVendor;
  project: PortalProject;
  task: PortalTask;
  bid_package: PortalBidPackage;
  bid_template: PortalBidTemplate;
  project_documents: PortalProjectDocument[];
  existing_draft: BidDraft | null;
  revision_context?: VendorRevisionContext | null;
}

// ─── Revision prefill (GET /vendor-portal/submissions/{id}/revision-prefill) ─
// Decimal fields arrive as strings over the wire (Pydantic Decimal).

export interface RevisionPrefillLineItem {
  template_item_id: string;
  description: string;
  item_type: TemplateItemType;
  quantity: string | null;
  unit_of_measure: string | null;
  unit_price: string | null;
  lump_sum_amount: string | null;
  line_total: string | null;
  sort_order: number;
}

export interface RevisionPrefillResponse {
  total_amount: string | null;
  vendor_notes: string;
  line_items: RevisionPrefillLineItem[];
  attachment_ids: string[];
  /** Carry the prior submission's proposed_start_date forward (Task 8.1.5). */
  proposed_start_date: string | null;
}

/** Metadata for the original submission's attachments (read-only display). */
export interface SubmissionAttachmentMeta {
  id: string;
  file_name: string;
  file_size: number;
  file_type: string | null;
  uploaded_at: string;
}

export interface ValidateTokenResponse {
  jwt: string;
  bid_context: VendorBidContext;
}

// ─── Milestone check-in (Phase 10.2) ────────────────────────────────
// A fully separate portal surface from the bid flow. The vendor answers
// ONE Yes/No question chosen by `check_type`.

export type MilestoneCheckType = 'start' | 'progress' | 'completion';

/** Mirrors backend MilestoneContextModel. Held in its own context slot. */
export interface VendorMilestoneContext {
  milestone_alert_id: string;
  milestone_id: string;
  milestone_name: string;
  project_name: string;
  task_name: string;
  vendor_company_name: string;
  check_type: MilestoneCheckType;
  end_date: string; // ISO date
  cycle_number: number;
}

/**
 * Result of POST /vendor-auth/validate-milestone-token. Discriminated by
 * `outcome`: 'actionable' carries jwt + milestone_context; 'already_answered'
 * carries the recorded value + date (no jwt). Stale / terminal check-ins come
 * back as a 410 PortalApiError, not an outcome here.
 */
export interface MilestoneValidateResponse {
  outcome: 'actionable' | 'already_answered';
  jwt?: string | null;
  milestone_context?: VendorMilestoneContext | null;
  recorded_value?: 'yes' | 'no' | null;
  recorded_at?: string | null;
}

/** Result of POST /vendor-portal/milestones/{id}/respond. */
export interface MilestoneRespondResult {
  outcome: 'recorded' | 'already_answered';
  recorded_value: 'yes' | 'no';
  recorded_at: string;
  milestone_status: string;
}

// ─── Error codes (mirror real HTTP responses) ───────────────────────

export type PortalApiErrorCode =
  | 'TOKEN_EXPIRED'      // → /bid/expired  (real: 410)
  | 'TOKEN_INVALID'      // → /bid/invalid  (real: 404)
  | 'BIDDING_CLOSED'     // → /bid/closed   (real: 423, package.status != open)
  | 'ALREADY_SUBMITTED'  // → /bid/already-submitted (real: 409)
  | 'DEADLINE_PASSED'    // 423 on a write after deadline during session — shows modal
  | 'VALIDATION_FAILED'  // 422 on submit with per-field errors
  | 'DRAFT_CONFLICT'     // 409 on POST /submissions with existing_submission_id
  | 'NETWORK'
  | 'UNKNOWN';

export interface PortalFieldError {
  field: string;
  message: string;
}

export class PortalApiError extends Error {
  code: PortalApiErrorCode;
  status: number;
  /** Populated for VALIDATION_FAILED — per-field server-side errors from submit. */
  validationErrors?: PortalFieldError[];
  /** Populated for DRAFT_CONFLICT — the draft id the UI should adopt and PUT against. */
  existingSubmissionId?: string;
  constructor(
    code: PortalApiErrorCode,
    message: string,
    status: number,
    extras: {
      validationErrors?: PortalFieldError[];
      existingSubmissionId?: string;
    } = {},
  ) {
    super(message);
    this.code = code;
    this.status = status;
    this.validationErrors = extras.validationErrors;
    this.existingSubmissionId = extras.existingSubmissionId;
  }
}

// ─── Form state (useReducer) ──────────────────────────────────────

export type StepIndex = 1 | 2 | 3 | 4;

export interface FormLineItem {
  template_item_id: string;
  description: string;
  item_type: TemplateItemType;
  unit_of_measure: string | null;
  sort_order: number;
  quantity: number | null;
  unit_price: number | null;
  lump_sum_amount: number | null;
}

export interface FormAttachment {
  id: string;
  file: File;
  name: string;
  size: number;
  uploadedAt: string;
}

export interface BidFormState {
  step: StepIndex;
  completedSteps: number[];
  dirty: boolean;
  companyInfo: {
    vendor_notes: string;
    /** Vendor's proposed start date (Task 8.1.5). ISO date string or null. */
    proposed_start_date: string | null;
    /** Vendor's typed CAPS SoW attestation. Empty until the vendor types it. */
    sow_attested_name: string;
  };
  pricing: {
    total_amount: number | null;
    line_items: FormLineItem[];
  };
  attachments: FormAttachment[];
  submissionId: string | null;
}

export interface SubmitBidResult {
  id: string;
  submitted_at: string;
  /**
   * Fields returned by the real backend (Task 5.7). Optional at the type
   * level so `portalApi.mock.ts` — a permanent demo/E2E fixture — can
   * keep its existing payload shape without modification. In real mode
   * these are always populated.
   */
  total_amount?: number | string | null;
  vendor_email?: string;
  vendor_company_name?: string;
  project_name?: string;
  task_name?: string;
  attachment_count?: number;
  confirmation_email_sent?: boolean;
  /**
   * Legacy display field retained purely for mock compatibility.
   * The real backend no longer issues confirmation numbers
   * (`bid_submissions.id` is the stable reference). The confirmation
   * page does NOT render this value.
   */
  confirmation_number?: string;
}
