import type { StatusVariant } from '@/components/ui/types';
import type { AlertStatus, AlertType } from './types';

export const ALERT_TYPE_LABELS: Record<AlertType, string> = {
  contingency_health: 'Contingency health',
  contingency_near_zero: 'Contingency nearly used up',
  contingency_negative: 'Contingency negative',
  long_tail_reserve: 'Long-tail reserve',
};

export const SEVERITY_VARIANT: Record<string, StatusVariant> = {
  warning: 'warning',
  urgent: 'danger',
  critical: 'danger',
};

export const ALERT_STATUS: Record<AlertStatus, { label: string; variant: StatusVariant }> = {
  open: { label: 'Needs decision', variant: 'danger' },
  acknowledged: { label: 'Needs decision', variant: 'danger' },
  proceed_approved: { label: 'OK to proceed', variant: 'success' },
  on_hold: { label: 'On hold', variant: 'warning' },
  resolved: { label: 'Resolved', variant: 'neutral' },
  superseded: { label: 'Superseded', variant: 'neutral' },
};

export const needsDecision = (status: AlertStatus) => status === 'open' || status === 'acknowledged';
