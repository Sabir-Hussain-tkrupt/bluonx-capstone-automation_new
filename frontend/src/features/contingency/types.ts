/** Contingency engine (Phase 3). Money arrives as strings, exact to the cent. */

export type Money = string;

export interface ContingencySnapshot {
  contingency: Money;
  base: Money;
  land: Money;
  total: Money;
  /** Contingency ÷ base × 100; null when the base is 0. */
  left_percent: string | null;
  /** The project's own %, or null when it uses the default. */
  contingency_percent: string | null;
  effective_percent: string;
  default_percent: string;
  target_percent: string;
  escalation_percent: string;
}

export interface ContingencyBucket {
  id: string;
  kind: 'initial' | 'top_up';
  label: string;
  reason: string | null;
  decided_at: string | null;
  starting_amount: Money;
  drawn: Money;
  returned: Money;
  remaining: Money;
  remaining_percent: string | null;
}

export type TopUpStatus = 'pending' | 'approved' | 'rejected' | 'cancelled';

export interface TopUpRequest {
  id: string;
  status: TopUpStatus;
  requested_amount: Money;
  approved_amount: Money | null;
  reason: string;
  requested_by: string;
  requested_by_name: string | null;
  requested_at: string;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_note: string | null;
}

export type CheckpointOutcome = 'on_target' | 'below_target' | 'escalated' | 'no_base';

export interface ContingencyOverview extends ContingencySnapshot {
  project_id: string;
  budget_status: 'none' | 'draft' | 'baselined';
  starting_amount: Money | null;
  top_ups_approved_total: Money;
  total_in: Money;
  total_out: Money;
  buckets: ContingencyBucket[];
  top_ups: TopUpRequest[];
  pending_top_ups: TopUpRequest[];
  bidding: {
    completed_at: string | null;
    completed_by_name: string | null;
    left_percent: string | null;
    note: string | null;
    outcome: CheckpointOutcome | null;
    alert: { id: string; severity: 'warning' | 'urgent' | 'critical'; message: string | null } | null;
  };
  permissions: {
    set_percent: boolean;
    request_top_up: boolean;
    decide_top_up: boolean;
    complete_bidding: boolean;
    reopen_bidding: boolean;
    is_executive: boolean;
  };
}

export interface LedgerAllocation {
  bucket_id: string;
  bucket_label: string;
  amount: Money;
  bucket_balance_after: Money;
}

export interface LedgerEntry {
  id: string;
  entry_no: number;
  created_at: string;
  movement_type: string;
  movement_label: string;
  direction: 'in' | 'out' | 'none';
  amount: Money;
  balance_before: Money;
  balance_after: Money;
  source_line_id: string | null;
  source_line_name: string | null;
  actor_user_id: string | null;
  actor_name: string | null;
  reason: string | null;
  allocations: LedgerAllocation[];
}

export interface ContingencyLedger {
  entries: LedgerEntry[];
  buckets: ContingencyBucket[];
  total_in: Money;
  total_out: Money;
}

export interface OpenBidTask {
  id: string;
  name: string;
  bid_type: string;
  status: string | null;
}

export interface CheckpointPreview extends ContingencySnapshot {
  budget_status: string;
  bidding_completed_at: string | null;
  open_tasks: OpenBidTask[];
  predicted_outcome: CheckpointOutcome;
}

export interface CheckpointResult extends Partial<ContingencySnapshot> {
  outcome: CheckpointOutcome;
  severity: 'warning' | 'critical' | null;
  alert_id: string | null;
  open_tasks: OpenBidTask[];
}

export interface ContingencySettings {
  default_contingency_percent: number | string;
  bidding_target_contingency_percent: number | string;
  bidding_escalation_percent: number | string;
  finance_emails: string[];
  sales_emails: string[];
}
