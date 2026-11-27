type Money = number | string;

export interface VariancePermissions {
  can_edit: boolean;
  can_cancel: boolean;
  can_approve: boolean;
  can_reject: boolean;
  approve_blocked_reason: string | null;
    needs_work_confirmation?: boolean;
}

/** Row of v_variances plus what the signed-in user may do. */
export interface Variance {
  id: string;
  project_id: string;
  project_name: string;
  budget_line_id: string;
  parent_budget_line_id: string;
  parent_line_name: string;
  trade_id: string | null;
  trade_name: string | null;
  vendor_id: string | null;
  vendor_name: string | null;
  description: string;
  estimated_amount: Money;
  amount: Money;
  status: 'draft' | 'pending_approval' | 'approved' | 'rejected' | 'cancelled';
  created_by: string;
  created_by_name: string | null;
  created_at: string;
  approved_by_name: string | null;
  approved_at: string | null;
  rejected_by_name: string | null;
  rejected_at: string | null;
  rejection_reason: string | null;
  payment_status: string;
  field_approved_by_name: string | null;
  routed_to_name: string | null;
  expected_payment_date: string | null;
  internal_invoice_id: string | null;
  permissions: VariancePermissions;
}

export interface VarianceEvent {
  id: string;
  event_type: string;
  label: string;
  amount_before: Money | null;
  amount_after: Money | null;
  actor_name: string | null;
  note: string | null;
  created_at: string;
}

export interface VarianceDetail extends Variance {
  history: VarianceEvent[];
}

export interface VarianceInput {
  description: string;
  trade_id?: string;
  vendor_id: string | null;
  amount: string;
  reason?: string | null;
}
