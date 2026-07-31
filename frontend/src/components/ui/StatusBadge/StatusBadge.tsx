import { cn } from '@/utils/cn';
import type { ComponentSize, StatusVariant } from '../types';

export interface StatusBadgeProps {
  status: string;
  size?: ComponentSize;
  variant?: StatusVariant;
  dot?: boolean;
  /**
   * Pad short labels to a uniform minimum width and center their content.
   * Opt-in for table columns, where content-sized pills read as ragged
   * ("Active" vs "Suspended"). Off by default so inline usages (detail-page
   * header pills, badges inside text/Fields) keep their natural width.
   */
  minWidth?: boolean;
}

const STATUS_MAP: Record<string, StatusVariant> = {
  // Project statuses
  active: 'success',
  completed: 'success',
  // User-management account statuses (active -> success above; pending -> warning below)
  deactivated: 'danger',
  planning: 'info',
  on_hold: 'warning',
  cancelled: 'danger',
  // Vendor statuses
  approved: 'success',
  suspended: 'danger',
  inactive: 'neutral',
  pending_review: 'warning',
  // Bid statuses
  draft: 'neutral',
  submitted: 'info',
  under_review: 'warning',
  accepted: 'success',
  rejected: 'danger',
  // Task statuses
  not_started: 'neutral',
  in_progress: 'info',
  bidding: 'info',
  evaluating: 'warning',
  awarded: 'success',
  // Contract statuses
  executed: 'success',
  expired: 'danger',
  terminated: 'danger',
  // Milestone statuses
  pending: 'warning',
  overdue: 'danger',
  scheduled: 'neutral',
  delayed: 'warning',
  unresponsive: 'danger',
  // Bid package statuses
  open: 'info',
  closed: 'neutral',
  // Bid invitation statuses
  pending_send: 'neutral',
  sent: 'info',
  send_failed: 'danger',
  opened: 'warning',
  declined: 'danger',
  no_response: 'neutral',
  // Email log statuses
  queued: 'neutral',
  delivered: 'success',
  bounced: 'danger',
  failed: 'danger',
  complained: 'warning',
};

const variantStyles: Record<StatusVariant, string> = {
  success: 'bg-success-100 text-success-700',
  danger: 'bg-danger-100 text-danger-700',
  warning: 'bg-warning-100 text-warning-700',
  info: 'bg-info-100 text-info-700',
  neutral: 'bg-secondary-100 text-secondary-700',
};

const dotStyles: Record<StatusVariant, string> = {
  success: 'bg-success-500',
  danger: 'bg-danger-500',
  warning: 'bg-warning-500',
  info: 'bg-info-500',
  neutral: 'bg-secondary-400',
};

const sizeStyles: Record<ComponentSize, string> = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-2.5 py-0.5 text-xs',
  lg: 'px-3 py-1 text-sm',
};

function formatStatus(status: string): string {
  return status
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function StatusBadge({
  status,
  size = 'md',
  variant,
  dot = true,
  minWidth = false,
}: StatusBadgeProps) {
  const resolved = variant ?? STATUS_MAP[status] ?? 'neutral';
  const label = formatStatus(status);

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full font-medium',
        variantStyles[resolved],
        sizeStyles[size],
        minWidth && 'min-w-[90px] justify-center',
      )}
      aria-label={label}
    >
      {dot && (
        <span
          className={cn('h-1.5 w-1.5 shrink-0 rounded-full', dotStyles[resolved])}
          aria-hidden="true"
        />
      )}
      {label}
    </span>
  );
}
