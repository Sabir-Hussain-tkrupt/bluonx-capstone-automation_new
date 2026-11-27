import type { StatusVariant } from '@/components/ui/types';

export const VARIANCE_STATUS_VARIANT: Record<string, StatusVariant> = {
  draft: 'neutral',
  pending_approval: 'warning',
  approved: 'success',
  rejected: 'danger',
  cancelled: 'neutral',
};

export const VARIANCE_STATUS_LABELS: Record<string, string> = {
  pending_approval: 'Pending approval',
  approved: 'Approved',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
};

/** A variance's own payment, independent of its bid line. */
export const PAYMENT_STATUS: Record<string, { label: string; variant: StatusVariant }> = {
  not_requested: { label: 'Payment not approved', variant: 'neutral' },
  pending: { label: 'Payment pending', variant: 'warning' },
  field_approved: { label: 'Field approved', variant: 'info' },
  awaiting_manager: { label: 'Awaiting manager', variant: 'warning' },
  awaiting_executive: { label: 'Awaiting executive', variant: 'warning' },
  approved: { label: 'Approved for payment', variant: 'success' },
  sent_to_finance: { label: 'Sent to finance', variant: 'success' },
  rejected: { label: 'Payment rejected', variant: 'danger' },
};
