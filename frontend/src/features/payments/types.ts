/** Payment approvals and the finance hand-off (Phase 6). Money arrives as strings. */

export type PaymentStatus =
  | 'pending'
  | 'field_approved'
  | 'awaiting_manager'
  | 'awaiting_executive'
  | 'approved'
  | 'sent_to_finance'
  | 'rejected'
  | 'cancelled';

export type PaymentKind = 'full' | 'progress' | 'retainage_release';

export interface PaymentPermissions {
  can_approve: boolean;
  approve_label: string;
  needs_work_confirmation: boolean;
  approve_blocked_reason: string | null;
  can_reject: boolean;
  can_resubmit: boolean;
  can_cancel: boolean;
  executive_needed: boolean;
}

export interface Payment {
  id: string;
  project_id: string;
  project_name: string;
  budget_line_id: string;
  line_name: string;
  line_type: string;
  trade_name: string | null;
  vendor_name: string | null;
  invoice_number: string | null;
  variance_id: string | null;
  contract_number: string | null;
  retainage_percent: string | null;
  amount: string;
  gross_amount: string;
  retainage_amount: string;
  payment_kind: PaymentKind;
  progress_percent: string | null;
  status: PaymentStatus;
  comments: string | null;
  requested_by_name: string | null;
  created_at: string;
  work_confirmed_by_name: string | null;
  work_confirmed_at: string | null;
  confirmed_by_external: boolean;
  field_approved_by_name: string | null;
  routed_to_name: string | null;
  manager_approved_by_name: string | null;
  manager_approved_at: string | null;
  executive_required: boolean;
  executive_approved_by_name: string | null;
  executive_approved_at: string | null;
  rejected_by_name: string | null;
  rejection_reason: string | null;
  approved_at: string | null;
  expected_payment_date: string | null;
  handoff_id: string | null;
  po_number: string | null;
  handoff_status: string | null;
  handoff_delivery_status: string | null;
  permissions: PaymentPermissions;
}

export interface PaymentEvent {
  id: string;
  event_type: string;
  label: string;
  status_after: string;
  actor_name: string | null;
  note: string | null;
  created_at: string;
}

export interface PaymentDetail extends Payment {
  history: PaymentEvent[];
}

export interface LinePayments {
  line_id: string;
  line_name: string;
  line_type: string;
  has_award: boolean;
  total: string;
  requested: string;
  remaining: string;
  retainage_percent: string | null;
  retainage_held: string;
  contract_number: string | null;
  open_request: Payment | null;
  history: Payment[];
  can_confirm: boolean;
}

export interface PaymentRequestInput {
  payment_kind: PaymentKind;
  progress_percent?: string | null;
  note?: string | null;
  confirm_work_complete: boolean;
}

export interface FinanceHandoff {
  id: string;
  payment_approval_id: string;
  project_name: string;
  po_number: string;
  amount: string;
  payload: {
    trade?: string | null;
    vendor?: string | null;
    line?: string | null;
    approved_on?: string | null;
    expected_payment_date?: string | null;
  };
  document_path: string | null;
  status: 'pending' | 'sent' | 'delivered' | 'failed';
  sent_at: string | null;
  exported_at: string | null;
  handoff_error: string | null;
  delivered_to: string | null;
  delivery_status: string | null;
  created_at: string;
}

export interface ApproverSettings {
  id: string;
  name: string;
  is_active: boolean;
  roles: string[];
  is_employee: boolean;
  approval_limit: string | null;
  reports_to: string | null;
  backup_approver_id: string | null;
  away_until: string | null;
}
