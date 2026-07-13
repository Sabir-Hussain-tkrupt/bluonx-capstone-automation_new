import { StatusBadge } from '@/components/ui/StatusBadge';
import type { ComponentSize } from '@/components/ui/types';

interface MilestoneStatusBadgeProps {
  status: string;
  size?: ComponentSize;
}

/**
 * Milestone status chip. Delegates to the shared StatusBadge for every status
 * except `cancelled`, which renders gray + strikethrough here (the shared badge
 * maps cancelled → danger, which reads as an error rather than a retired plan).
 */
export function MilestoneStatusBadge({ status, size = 'md' }: MilestoneStatusBadgeProps) {
  if (status === 'cancelled') {
    const sizeCls = size === 'lg' ? 'px-3 py-1 text-sm' : 'px-2.5 py-0.5 text-xs';
    return (
      <span
        className={`inline-flex items-center gap-1.5 rounded-full bg-secondary-100 font-medium text-secondary-500 line-through ${sizeCls}`}
        aria-label="Cancelled"
      >
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-secondary-400" aria-hidden="true" />
        Cancelled
      </span>
    );
  }
  return <StatusBadge status={status} size={size} />;
}
