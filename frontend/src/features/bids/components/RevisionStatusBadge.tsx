import { cn } from '@/utils/cn';
import type { RevisionRequestStatus } from '@/features/bids/types';

interface RevisionStatusBadgeProps {
  status: RevisionRequestStatus;
  /** Vendor-supplied reason, shown on hover for the Declined state. */
  declineReason?: string | null;
}

type Variant = 'amber' | 'green' | 'grey';

const CONFIG: Record<
  Exclude<RevisionRequestStatus, 'cancelled'>,
  { label: string; variant: Variant }
> = {
  pending: { label: 'Revision Pending', variant: 'amber' },
  submitted: { label: 'Revised', variant: 'green' },
  declined: { label: 'Declined', variant: 'grey' },
  expired: { label: 'Expired', variant: 'grey' },
};

const variantStyles: Record<Variant, string> = {
  amber: 'bg-warning-100 text-warning-700',
  green: 'bg-success-100 text-success-700',
  grey: 'bg-secondary-100 text-secondary-700',
};

const dotStyles: Record<Variant, string> = {
  amber: 'bg-warning-500',
  green: 'bg-success-500',
  grey: 'bg-secondary-400',
};

/**
 * Revision lifecycle badge for a vendor row. Mirrors StatusBadge styling.
 * `cancelled` renders nothing — a cancelled request behaves as if no request
 * exists (the row falls back to its normal invitation status).
 */
export function RevisionStatusBadge({
  status,
  declineReason,
}: RevisionStatusBadgeProps) {
  if (status === 'cancelled') return null;

  const { label, variant } = CONFIG[status];
  const tooltip =
    status === 'declined' && declineReason ? declineReason : undefined;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
        variantStyles[variant],
        tooltip && 'cursor-help',
      )}
      title={tooltip}
      aria-label={tooltip ? `${label}: ${tooltip}` : label}
    >
      <span
        className={cn('h-1.5 w-1.5 shrink-0 rounded-full', dotStyles[variant])}
        aria-hidden="true"
      />
      {label}
    </span>
  );
}
