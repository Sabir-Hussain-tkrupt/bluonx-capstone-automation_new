import type { StatusVariant } from '@/components/ui/types';

export const ESCROW_STATUS: Record<string, { label: string; variant: StatusVariant }> = {
  planned: { label: 'Planned', variant: 'neutral' },
  posted: { label: 'Posted', variant: 'info' },
  works_built: { label: 'Works built', variant: 'info' },
  inspection: { label: 'Inspection walk', variant: 'warning' },
  corrections: { label: 'Corrections', variant: 'warning' },
  signed_off: { label: 'Government sign-off', variant: 'success' },
  released: { label: 'Released', variant: 'success' },
  cancelled: { label: 'Cancelled', variant: 'neutral' },
};

/** What each step button says. */
export const STEP_LABEL: Record<string, string> = {
  posted: 'Mark posted',
  works_built: 'Works built',
  inspection: 'Record inspection walk',
  corrections: 'Start corrections',
  signed_off: 'Record government sign-off',
  released: 'Mark released',
  cancelled: 'Cancel escrow',
};

/** Steps the field manager records; the rest are the project manager's. */
export const FIELD_STEPS = new Set(['works_built', 'inspection', 'corrections', 'signed_off']);

export const TAX_STATUS: Record<string, { label: string; variant: StatusVariant }> = {
  estimated: { label: 'Estimated', variant: 'neutral' },
  billed: { label: 'Billed', variant: 'info' },
  in_approval: { label: 'In approval', variant: 'warning' },
  sent_to_finance: { label: 'Paid', variant: 'success' },
  cancelled: { label: 'Cancelled', variant: 'neutral' },
};

export const BENEFICIARY_LABELS: Record<string, string> = { city: 'City', county: 'County', hoa: 'HOA', other: 'Other' };

export const BASIS_LABELS: Record<string, string> = {
  prior_year_actual: "Last year's actual",
  assessed_value: 'Assessed value × rate',
  manual: 'Entered by finance',
};
