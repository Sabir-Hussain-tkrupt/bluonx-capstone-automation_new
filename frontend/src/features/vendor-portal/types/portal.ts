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
}

export interface VendorBidContext {
  vendor: PortalVendor;
  project: PortalProject;
  task: PortalTask;
  bid_package: PortalBidPackage;
  bid_template: PortalBidTemplate;
  project_documents: PortalProjectDocument[];
  existing_draft: BidDraft | null;
}

export interface ValidateTokenResponse {
  jwt: string;
  bid_context: VendorBidContext;
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
