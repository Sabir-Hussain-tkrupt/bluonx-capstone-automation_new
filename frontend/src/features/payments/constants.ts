import type { StatusVariant } from '@/components/ui/types';
import type { Payment } from './types';

export const PAYMENT_STATUS: Record<string, { label: string; variant: StatusVariant }> = {
  pending: { label: 'Waiting for field confirmation', variant: 'warning' },
  field_approved: { label: 'Field approved', variant: 'info' },
  awaiting_manager: { label: 'Waiting for manager', variant: 'warning' },
  awaiting_executive: { label: 'Waiting for executive', variant: 'warning' },
  approved: { label: 'Manager approved', variant: 'success' },
  sent_to_finance: { label: 'Sent to finance', variant: 'success' },
  rejected: { label: 'Rejected', variant: 'danger' },
  cancelled: { label: 'Withdrawn', variant: 'neutral' },
};

export function kindLabel(p: Pick<Payment, 'payment_kind' | 'progress_percent'>): string {
  if (p.payment_kind === 'progress') return `Progress ${p.progress_percent ? `${Number(p.progress_percent)}%` : ''}`.trim();
  if (p.payment_kind === 'retainage_release') return 'Retainage release';
  return 'Full payment';
}

export const DELIVERY_VARIANT: Record<string, StatusVariant> = {
  delivered: 'success',
  sent: 'info',
  queued: 'neutral',
  pending: 'neutral',
  failed: 'danger',
  bounced: 'danger',
  complained: 'danger',
};
