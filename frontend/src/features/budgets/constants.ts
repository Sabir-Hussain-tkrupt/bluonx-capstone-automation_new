import type { CashBucket, LineSubtype, LineType, ManualLineType } from './types';

export const LINE_TYPE_LABELS: Record<LineType, string> = {
  land: 'Land',
  bid_activity: 'Bid activity',
  internal_tm: 'Internal T&M',
  permit: 'Permit',
  impact_fee: 'Impact fee',
  soft_cost: 'Soft cost',
  contingency: 'Contingency',
  variance: 'Variance',
  long_tail: 'Long-tail',
};

export const LINE_SUBTYPE_LABELS: Record<LineSubtype, string> = {
  land_purchase: 'Land purchase',
  earnest_money: 'Earnest money',
  due_diligence: 'Due diligence',
  engineering: 'Engineering',
  escrow_bond_premium: 'Escrow bond premium',
  escrow_repairs: 'Escrow repairs',
  property_tax: 'Property tax',
  other: 'Other',
  unallocated: 'Unallocated',
};

export const CASH_BUCKET_LABELS: Record<CashBucket, string> = {
  land: 'Land',
  vertical_construction: 'Vertical construction',
  overhead: 'Overhead',
};

/** Line types an admin can add by hand (bid activities come from tasks). */
export const MANUAL_LINE_TYPES: { value: ManualLineType; label: string }[] = [
  { value: 'land', label: 'Land' },
  { value: 'permit', label: 'Permit' },
  { value: 'impact_fee', label: 'Impact fee' },
  { value: 'soft_cost', label: 'Soft cost' },
  { value: 'internal_tm', label: 'Internal T&M' },
  { value: 'long_tail', label: 'Long-tail (escrow, property tax)' },
];

export const SUBTYPES_BY_TYPE: Partial<Record<LineType, LineSubtype[]>> = {
  land: ['land_purchase', 'earnest_money', 'due_diligence'],
  soft_cost: ['engineering', 'other'],
  long_tail: ['escrow_bond_premium', 'escrow_repairs', 'property_tax', 'other'],
};

export const CASH_BUCKET_OPTIONS = (Object.keys(CASH_BUCKET_LABELS) as CashBucket[]).map((value) => ({
  value,
  label: CASH_BUCKET_LABELS[value],
}));
