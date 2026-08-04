import { cn } from '@/utils/cn';
import { StatusBadge } from '@/components/ui/StatusBadge';
import type { ComponentSize } from '@/components/ui/types';

interface MilestoneStatusBadgeProps {
  status: string;
  size?: ComponentSize;
  /** Pad short labels to a uniform minimum width, see StatusBadge. */
  minWidth?: boolean;
}

/**
 * Milestone status chip. Delegates to the shared StatusBadge for every status
 * except `cancelled`, which renders gray + strikethrough here (the shared badge
 * maps cancelled → danger, which reads as an error rather than a retired plan).
 */
export function MilestoneStatusBadge({ status, size = 'md', minWidth = false }: MilestoneStatusBadgeProps) {
  if (status === 'cancelled') {
    const sizeCls = size === 'lg' ? 'px-3 py-1 text-sm' : 'px-2.5 py-0.5 text-xs';
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1.5 rounded-full bg-secondary-100 font-medium text-secondary-500 line-through',
          sizeCls,
          minWidth && 'min-w-[90px] justify-center',
        )}
        aria-label="Cancelled"
      >
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-secondary-400" aria-hidden="true" />
        Cancelled
      </span>
    );
  }
  return <StatusBadge status={status} size={size} minWidth={minWidth} />;
}
