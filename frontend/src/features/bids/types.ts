// ─── Qualified Vendors (GET /v1/tasks/{id}/qualified-vendors) ─────────

export interface VendorContact {
  id: string;
  full_name: string;
  email: string;
  phone: string | null;
}

export interface QualifiedVendor {
  vendor_id: string;
  company_name: string;
  primary_contact: VendorContact | null;
  contact_warning: string | null;
  distance_miles: number | null;
  insurance_expiration_date: string | null;
  insurance_days_remaining: number | null;
  bonding_capacity: number | null;
  max_active_jobs: number | null;
  current_active_jobs: number;
  available_capacity: number | null;
  onboarding_status: string;
  has_unresolved_flags: boolean;
  unresolved_flag_count: number;
  flag_reasons: string[];
  qualification_status: 'qualified' | 'disqualified';
  disqualification_reasons: string[];
}

export interface FilterCriteria {
  radius_miles: number;
  trade_id: string;
  trade_name: string | null;
  min_bonding: number | null;
  insurance_cutoff_date: string;
}

export interface QualifiedVendorsResponse {
  task_id: string;
  task_name: string;
  trade_name: string | null;
  project_id: string;
  project_name: string;
  filter_criteria: FilterCriteria;
  qualified_vendors: QualifiedVendor[];
  disqualified_vendors: QualifiedVendor[];
  total_qualified: number;
  total_disqualified: number;
  warnings: string[];
}

// ─── Bid Package Detail (GET /v1/bid-packages/{id}) ──────────────────

export interface BidTemplateRef {
  id: string;
  name: string;
  is_lump_sum: boolean | null;
}

export interface BidDocument {
  id: string;
  file_name: string | null;
}

export interface InvitationSummary {
  total: number;
  sent: number;
  opened: number;
  submitted: number;
  declined: number;
  expired: number;
  no_response: number;
}

export type InvitationStatus = 'sent' | 'opened' | 'submitted' | 'declined' | 'expired' | 'no_response';

export interface BidInvitation {
  id: string;
  vendor_id: string | null;
  vendor_company_name: string | null;
  vendor_contact_name: string | null;
  vendor_contact_email: string | null;
  status: InvitationStatus;
  sent_at: string | null;
  opened_at: string | null;
  responded_at: string | null;
  bid_submission_id: string | null;
  /** True when the task has an active award — the PM cannot request a
   *  revision (the backend create endpoint 409s). Drives button visibility. */
  is_awarded: boolean;
}

export interface SubmittedBid {
  vendor_company_name: string;
  total_amount: number | null;
}

export interface BidPackageDetail {
  id: string;
  task_name: string | null;
  round_number: number;
  deadline: string;
  status: string;
  instructions: string | null;
  /** PM-set target start date (Task 8.1.5). ISO date string or null. */
  desired_start_date: string | null;
  bid_template: BidTemplateRef | null;
  documents: BidDocument[];
  invitation_summary: InvitationSummary;
  invitations: BidInvitation[];
  submitted_bids: SubmittedBid[];
}

// ─── Bid Submission Detail (GET /v1/bid-submissions/{id}) ───────────

export interface BidSubmissionLineItem {
  id: string;
  description: string;
  item_type: 'lump_sum' | 'unit_price';
  quantity: number | null;
  unit_of_measure: string | null;
  unit_price: number | null;
  lump_sum_amount: number | null;
  line_total: number;
  sort_order: number;
}

export interface BidSubmissionAttachment {
  id: string;
  file_name: string;
  file_size: number;
  file_type: string | null;
  uploaded_at: string;
  download_url: string;
  download_url_expires_in: number;
}

export interface BidSubmissionDetail {
  id: string;
  bid_invitation_id: string;
  status: string;
  is_direct_assign: boolean;
  is_draft: boolean;
  is_superseded: boolean;
  revision_number: number;
  supersedes_submission_id: string | null;
  total_amount: number | null;
  vendor_notes: string | null;
  submitted_at: string | null;
  /** Vendor's committed start date (Task 8.1.5). ISO date string or null. */
  proposed_start_date: string | null;
  vendor_company_name: string | null;
  vendor_contact_name: string | null;
  vendor_contact_email: string | null;
  line_items: BidSubmissionLineItem[];
  attachments: BidSubmissionAttachment[];
}

// ─── Bid Revision Requests (/v1/bid-revision-requests) ──────────────

export type RevisionRequestStatus =
  | 'pending'
  | 'submitted'
  | 'declined'
  | 'expired'
  | 'cancelled';

export interface BidRevisionRequest {
  id: string;
  bid_invitation_id: string;
  original_submission_id: string;
  pm_note: string;
  revision_deadline: string;
  status: RevisionRequestStatus;
  decline_reason: string | null;
  requested_by: string;
  requested_at: string;
  responded_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateRevisionRequestPayload {
  bid_invitation_id: string;
  pm_note: string;
  revision_deadline: string;
}

export interface CreateRevisionRequestResponse {
  revision_request: BidRevisionRequest;
  magic_link_token: string;
  portal_url: string;
}

// ─── Create Bid Package (POST /v1/tasks/{id}/bid-packages) ──────────

export interface VendorSelection {
  vendor_id: string;
  vendor_contact_id: string;
}

export interface CreateBidPackageRequest {
  deadline: string;
  bid_template_id: string;
  project_document_ids: string[];
  vendor_selections: VendorSelection[];
  instructions?: string;
  /** Optional PM target start date (Task 8.1.5). ISO date (YYYY-MM-DD). */
  desired_start_date?: string;
}

export interface FailedVendor {
  vendor_id: string;
  error: string;
}

export interface CreateBidPackageResponse {
  bid_package_id: string;
  round_number: number;
  invitations_sent: number;
  invitations_failed: number;
  failed_vendors: FailedVendor[];
  deadline: string;
  instructions?: string | null;
  desired_start_date?: string | null;
}

// ─── Resend Bid Link (POST /v1/bid-invitations/{id}/resend-link) ────

export interface ResendBidLinkResponse {
  invitation_id: string;
  vendor_id: string;
  new_token_generated: boolean;
  email_status: string;
}

// ─── Update Invitation Status (PUT /v1/bid-invitations/{id}/status) ─

export interface UpdateInvitationStatusRequest {
  status: 'declined' | 'expired' | 'no_response';
}

// ─── Email Log (GET /v1/bid-packages/{id}/email-log) ────────────────

export interface EmailLogItem {
  id: string | null;
  recipient_email: string | null;
  email_type: string | null;
  subject: string | null;
  status: string | null;
  sent_at: string | null;
  error_message: string | null;
}

export interface EmailLogResponse {
  items: EmailLogItem[];
}

// ─── Bid Package List Item (Supabase read for task detail) ──────────

export interface BidPackageListItem {
  id: string;
  task_id: string;
  round_number: number;
  deadline: string;
  status: string;
  created_at: string;
  invitation_total: number;
  invitation_submitted: number;
}

// ─── Project Document (GET /v1/projects/{id}/documents) ─────────────

export interface ProjectDocument {
  id: string;
  project_id: string;
  file_name: string;
  file_path: string;
  file_type: string | null;
  file_size: number | null;
  uploaded_by: string;
  uploaded_at: string;
}

// ─── Wizard State ───────────────────────────────────────────────────

export interface WizardData {
  deadline: string;
  bidTemplateId: string | null;
  documentIds: string[];
  vendorSelections: VendorSelection[];
  instructions: string;
  /** Optional PM-set desired start date (Task 8.1.5). ISO date or "". */
  desiredStartDate: string | null;
}

// ─── Bid Scoring & Recommendation (Task 8.2 / 8.3 / 8.4) ────────────

export type WarningFlagCode =
  | 'over_budget'
  | 'late_start'
  | 'insurance_window'
  | 'onboarding_incomplete';

export type ScoreDimension =
  | 'price'
  | 'compliance'
  | 'performance'
  | 'capacity'
  | 'timeline';

export interface ScoringMetadataInputs {
  this_total: string | null;
  lowest_valid_total: string | null;
  onboarding_status: string | null;
  insurance_expiration: string | null;
  deadline: string | null;
  max_active_jobs: number | null;
  current_active_jobs: number;
  proposed_start_date: string | null;
  desired_start_date: string | null;
}

export interface ScoringMetadata {
  rubric_version: string;
  weights: Record<string, number>;
  inputs: ScoringMetadataInputs;
  sub_scores: Record<ScoreDimension, number>;
  cohort_size: number;
  computed_at: string;
  /** Present only when the package has no desired_start_date (Task 8.2). */
  basis?: 'no_desired_date';
}

export interface BidScoreRow {
  id: string;
  bid_submission_id: string;
  vendor_company_name: string | null;
  price_score: string | null;
  compliance_score: string | null;
  performance_score: string | null;
  capacity_score: string | null;
  timeline_score: string | null;
  total_weighted_score: string | null;
  scoring_metadata: ScoringMetadata;
  scored_at: string | null;
  scored_by: string | null;
}

export interface RankedVendor {
  rank: number;
  bid_submission_id: string;
  vendor_company_name: string | null;
  total_weighted_score: string | null;
  this_total: string | null;
  warning_flags: WarningFlagCode[];
}

export interface BidRecommendation {
  recommended_bid_submission_id: string;
  justification: string;
  ranking: RankedVendor[];
}

export interface BidScoreCohort {
  bid_package_id: string;
  rubric_version: string;
  cohort_size: number;
  scores: BidScoreRow[];
  budget_estimate: string | null;
  valid_submission_count: number | null;
  latest_submission_at: string | null;
  recommendation: BidRecommendation | null;
}

// ── Pre-award validation (Task 9.1 result / 9.2 override gate) ────────────

export type PreAwardSeverity = 'block' | 'warn' | 'pass' | 'skipped';
export type PreAwardCheckStatus = 'pass' | 'fail' | 'skipped';

/** One validation check. `inputs` is a self-describing raw blob — kept open. */
export interface PreAwardCheck {
  check: string;
  severity: PreAwardSeverity;
  status: PreAwardCheckStatus;
  message: string;
  inputs: Record<string, unknown>;
}

/** Byte-compatible with the backend PreAwardValidationResult / the
 *  awards.validation_results snapshot. Returned by GET /awards/validate/{id}
 *  and echoed in the 422 body when the override gate trips. */
export interface PreAwardValidationResult {
  rubric_version: string;
  can_award: boolean;
  has_blocking: boolean;
  has_warnings: boolean;
  requires_override: boolean;
  validated_at: string;
  award_amount: string | null;
  checks: PreAwardCheck[];
}

/** POST /awards request body (Task 9.2). award_amount / task_id / vendor_id are
 *  server-derived; only the submission + override decision come from the PM. */
export interface CreateAwardPayload {
  bid_submission_id: string;
  has_override?: boolean;
  override_justification?: string;
  /** Optional PM-authored guidance (mobilization, site access, etc.), rendered in the award email. */
  instructions?: string;
}

export interface Award {
  id: string;
  task_id: string;
  bid_submission_id: string;
  vendor_id: string;
  awarded_by: string;
  awarded_at: string;
  award_amount: string;
  has_override: boolean;
  override_justification: string | null;
  validation_results: PreAwardValidationResult | null;
  status: string;
  created_at: string;
  updated_at: string;
}
