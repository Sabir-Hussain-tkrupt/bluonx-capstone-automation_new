import { cn } from '@/utils/cn';
import { getScoreBandVariant, parseDecimal } from '@/features/bids/utils/score-display';

export interface ScoreBandChipProps {
  /** Decimal-as-string (Pydantic shape) or a number. */
  score: string | number | null;
  showLabel?: boolean;
}

const variantStyles = {
  success: 'bg-success-100 text-success-700',
  warning: 'bg-warning-100 text-warning-700',
  danger: 'bg-danger-100 text-danger-700',
  neutral: 'bg-secondary-100 text-secondary-500',
} as const;

const dotStyles = {
  success: 'bg-success-500',
  warning: 'bg-warning-500',
  danger: 'bg-danger-500',
  neutral: 'bg-secondary-400',
} as const;

/** Compact green/amber/red chip for a single 0-100 sub-score. Models on
 * StatusBadge's visual shape (rounded + dot + light bg + dark text). */
export function ScoreBandChip({ score, showLabel = true }: ScoreBandChipProps) {
  const numeric = typeof score === 'string' ? parseDecimal(score) : score;
  const variant = getScoreBandVariant(numeric);
  const label = numeric == null ? '—' : `${Math.round(numeric)}`;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums',
        variantStyles[variant],
      )}
    >
      <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', dotStyles[variant])} aria-hidden="true" />
      {showLabel ? label : null}
    </span>
  );
}
