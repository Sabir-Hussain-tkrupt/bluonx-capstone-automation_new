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
}

export interface BidPackageDetail {
  id: string;
  task_name: string | null;
  round_number: number;
  deadline: string;
  status: string;
  instructions: string | null;
  bid_template: BidTemplateRef | null;
  documents: BidDocument[];
  invitation_summary: InvitationSummary;
  invitations: BidInvitation[];
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
}

// ─── Resend Invitation (POST /v1/bid-invitations/{id}/resend) ───────

export interface ResendInvitationResponse {
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
}
