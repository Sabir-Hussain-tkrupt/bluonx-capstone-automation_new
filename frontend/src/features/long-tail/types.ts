/** Long-tail items: escrows and property taxes (Phase 7). Money arrives as strings. */

export type EscrowStatus =
  | 'planned'
  | 'posted'
  | 'works_built'
  | 'inspection'
  | 'corrections'
  | 'signed_off'
  | 'released'
  | 'cancelled';

export interface Escrow {
  id: string;
  project_id: string;
  name: string;
  beneficiary: 'city' | 'county' | 'hoa' | 'other';
  covered_areas: string[];
  security_form: 'cash' | 'bond';
  holder_type: 'insurance_company' | 'bank' | 'other' | null;
  holder_name: string | null;
  secured_amount: string;
  premium_amount: string;
  premium_total: string;
  premium_frequency: 'one_time' | 'yearly';
  bond_number: string | null;
  bond_expiry_date: string | null;
  status: EscrowStatus;
  posted_date: string | null;
  works_built_date: string | null;
  inspection_date: string | null;
  inspection_notes: string | null;
  signoff_date: string | null;
  signoff_by: string | null;
  expected_release_date: string | null;
  released_date: string | null;
  jurisdiction_id: string | null;
  jurisdiction_name: string | null;
  repair_estimate: string;
  premium_line_amount: string;
  repair_line_amount: string;
  open_defects: number;
  defects_total: string;
  document_path: string | null;
  document_name: string | null;
  notes: string | null;
}

export interface EscrowDefect {
  id: string;
  description: string;
  location: string | null;
  repair_cost: string;
  status: 'open' | 'repaired' | 'waived';
  repaired_at: string | null;
}

export interface EscrowDetail extends Escrow {
  next_steps: EscrowStatus[];
  defects: EscrowDefect[];
  history: { id: string; label: string; actor_name: string | null; note: string | null; created_at: string }[];
  permissions: LongTailPermissions;
}

export interface PropertyTax {
  id: string;
  project_id: string;
  budget_line_id: string;
  tax_year: number;
  jurisdiction: string;
  jurisdiction_id: string | null;
  parcel_reference: string | null;
  installment_number: number;
  due_date: string | null;
  estimate_basis: 'prior_year_actual' | 'assessed_value' | 'manual';
  estimated_amount: string;
  actual_amount: string | null;
  sold_portion_percent: string | null;
  amount_due: string;
  increase: string | null;
  status: 'estimated' | 'billed' | 'in_approval' | 'sent_to_finance' | 'cancelled';
  paid_at: string | null;
}

export interface LongTailPermissions {
  manage_escrows: boolean;
  record_works: boolean;
  manage_taxes: boolean;
  renew_bonds: boolean;
}

export interface LongTailOverview {
  project_id: string;
  budget_status: string;
  escrows: Escrow[];
  taxes: PropertyTax[];
  upcoming_taxes: PropertyTax[];
  totals: {
    open_escrows: number;
    open_escrow_costs: string;
    open_taxes: string;
    long_tail_open: string;
    cash_posted: string;
    reserve_required: string | null;
    contingency: string;
    below_reserve: boolean;
    tax_increase: string;
  };
  permissions: LongTailPermissions;
}

export interface Jurisdiction {
  id: string;
  name: string;
  kind: 'city' | 'county' | 'hoa' | 'other';
  state: string | null;
  repair_estimate_percent: string | null;
  tax_installments: { month: number; day: number }[];
  reminder_days_before: number;
  notes: string | null;
}
