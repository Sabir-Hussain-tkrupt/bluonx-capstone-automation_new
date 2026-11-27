/** Contingency health and financial alerts (Phase 5). Money and % arrive as strings. */

export type AlertType =
  | 'contingency_health'
  | 'contingency_near_zero'
  | 'contingency_negative'
  | 'long_tail_reserve';

export type AlertStatus = 'open' | 'acknowledged' | 'proceed_approved' | 'on_hold' | 'resolved' | 'superseded';

export interface FinancialAlert {
  id: string;
  project_id: string;
  project_name: string;
  project_status: string;
  alert_type: AlertType;
  severity: 'warning' | 'urgent' | 'critical';
  status: AlertStatus;
  contingency_left_pct: number | string | null;
  work_left_pct: number | string | null;
  contingency_remaining: number | string | null;
  reserve_required: number | string | null;
  message: string | null;
  decision: 'proceed' | 'hold' | null;
  decision_reason: string | null;
  decided_by_name: string | null;
  decided_at: string | null;
  discussed_with_name: string | null;
  conversation_notes: string | null;
  hold_lifted_by_name: string | null;
  hold_lifted_at: string | null;
  hold_lift_reason: string | null;
  notified_at: string | null;
  escalated_at: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface TeamMember {
  id: string;
  name: string;
  roles: string[];
}

export interface FinancialHealth {
  project_id: string;
  project_status: string;
  live: boolean;
  contingency: string;
  contingency_base: string | null;
  groundbreaking_at: string | null;
  contingency_left_pct: string | null;
  work_left_dollars_pct: string | null;
  work_left_physical_pct: string | null;
  work_left_pct: string | null;
  work_left_basis: 'dollars' | 'physical' | null;
  milestones_total: number;
  milestones_completed: number;
  total_budget: string;
  spent: string;
  spent_committed: string;
  spent_approved: string;
  spent_sent: string;
  spent_land: string;
  reserve: string | null;
  near_zero_percent: string;
  manager_id: string | null;
  field_manager_id: string | null;
  team: TeamMember[];
  alerts: FinancialAlert[];
  financial_hold: boolean;
  permissions: { manage: boolean; record_groundbreaking: boolean };
}

export interface FinancialAlertDetail extends FinancialAlert {
  health: FinancialHealth;
  field_managers: TeamMember[];
  permissions: { can_decide: boolean; can_lift: boolean };
}

export interface HealthSetupInput {
  manager_id?: string | null;
  field_manager_id?: string | null;
  reserve?: string | null;
}

export interface DecisionInput {
  decision: 'proceed' | 'hold';
  reason: string;
  discussed_with: string;
  conversation_notes: string;
}
