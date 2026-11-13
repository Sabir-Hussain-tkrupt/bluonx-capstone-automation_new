/**
 * Types for the financial module's Budget tab and Budget Template settings.
 *
 * Reads come from the Supabase views v_budget_lines / v_project_budget_summary
 * (RLS-protected, any active user); writes go through FastAPI (admin only).
 * Mirrors backend/app/models/budgets.py and the Phase 2 migration.
 */

export type LineType =
  | 'land'
  | 'bid_activity'
  | 'internal_tm'
  | 'permit'
  | 'impact_fee'
  | 'soft_cost'
  | 'contingency'
  | 'variance'
  | 'long_tail';

export type ManualLineType = 'land' | 'permit' | 'impact_fee' | 'soft_cost' | 'long_tail' | 'internal_tm';

export type LineSubtype =
  | 'land_purchase'
  | 'earnest_money'
  | 'due_diligence'
  | 'engineering'
  | 'escrow_bond_premium'
  | 'escrow_repairs'
  | 'property_tax'
  | 'other'
  /** Balancing line that keeps a draft budget at the project's Budget value. */
  | 'unallocated';

export type CashBucket = 'land' | 'vertical_construction' | 'overhead';

export type BudgetStatus = 'none' | 'draft' | 'baselined';

/** Row of v_budget_lines. Money fields are numbers (PostgREST numeric). */
export interface BudgetLine {
  id: string;
  project_id: string;
  task_id: string | null;
  template_line_id: string | null;
  parent_line_id: string | null;
  line_type: LineType;
  line_subtype: LineSubtype | null;
  name: string;
  description: string | null;
  section_name: string | null;
  sort_order: number;
  original_estimate: number | null;
  budget_amount: number;
  committed_amount: number;
  award_id: string | null;
  contract_id: string | null;
  is_locked: boolean;
  locked_at: string | null;
  lock_reason: string | null;
  anticipated_start_date: string | null;
  anticipated_end_date: string | null;
  payment_terms_days: number;
  cash_bucket: CashBucket;
  approval_state: string;
  is_payment_exempt: boolean;
  task_name: string | null;
  task_status: string | null;
  task_bid_type: string | null;
  trade_name: string | null;
  award_status: string | null;
  award_amount: number | null;
  vendor_id: string | null;
  vendor_name: string | null;
  contract_number: string | null;
  contract_status: string | null;
  variance_id: string | null;
  variance_status: string | null;
  variance_total: number;
  variance_count: number;
  invoiced: number;
  committed: number;
  spent: number;
  pending_approval: number;
  /** Budget − committed. Null for the contingency line (a reserve). */
  remaining: number | null;
  bid_vs_estimate: number | null;
  has_dates: boolean;
  closings_total: number;
  closings_count: number;
}

/** Row of v_project_budget_summary. */
export interface BudgetSummary {
  project_id: string;
  project_name: string;
  budget_status: BudgetStatus;
  approved_budget_total: number | null;
  contingency_percent: number | null;
  budget_baselined_at: string | null;
  total_budget: number;
  committed: number;
  spent: number;
  remaining: number;
  pending_approval: number;
  contingency_now: number;
  contingency_at_baseline: number | null;
  land_total: number;
  contingency_base: number;
  line_count: number;
  lines_missing_dates: number;
  tasks_without_line: number;
  flat_ok: boolean;
  /** The project's own Budget value (Overview tab); the total when set. */
  project_budget: number | null;
  /** Amount on the Unallocated balancing line. */
  unallocated: number;
  /** Lines total − project budget (positive = over). Null when no project budget. */
  over_project_budget: number | null;
}

export interface LandClosing {
  id: string;
  project_id: string;
  budget_line_id: string;
  closing_sequence: number;
  acres: number | null;
  amount: number;
  planned_closing_date: string;
  actual_closing_date: string | null;
  status: 'planned' | 'closed' | 'cancelled';
  notes: string | null;
}

export interface BudgetTemplate {
  id: string;
  name: string;
  description: string | null;
  is_default: boolean;
}

export interface BudgetTemplateLine {
  id: string;
  budget_template_id: string;
  line_type: Exclude<LineType, 'variance'>;
  line_subtype: LineSubtype | null;
  name: string;
  section_name: string | null;
  trade_id: string | null;
  sort_order: number;
  default_amount: number | null;
  default_payment_terms_days: number | null;
  default_cash_bucket: CashBucket | null;
  is_active: boolean;
}

/** Body shared by add / edit line (amounts as exact strings). */
export interface BudgetLineInput {
  line_type?: ManualLineType;
  line_subtype?: LineSubtype | null;
  name?: string;
  description?: string | null;
  section_name?: string | null;
  parent_line_id?: string | null;
  budget_amount?: string;
  anticipated_start_date?: string | null;
  anticipated_end_date?: string | null;
  payment_terms_days?: number;
  cash_bucket?: CashBucket;
}

export interface ImportPreviewRow {
  row_number: number;
  name: string;
  section_name: string | null;
  line_type: string | null;
  budget_amount: string | null;
  anticipated_start_date: string | null;
  anticipated_end_date: string | null;
  payment_terms_days?: number;
  cash_bucket?: CashBucket;
  action: 'update' | 'add' | 'error';
  line_id: string | null;
  current_amount?: number | string;
  errors: string[];
  warnings: string[];
}

export interface ImportPreview {
  rows: ImportPreviewRow[];
  summary: { update: number; add: number; error: number };
}
