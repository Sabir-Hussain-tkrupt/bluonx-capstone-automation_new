import { cn } from '@/utils/cn';
import type { WarningFlagCode } from '@/features/bids/types';
import { WARNING_FLAG_LABELS } from '@/features/bids/utils/score-display';

export interface WarningFlagChipProps {
  code: WarningFlagCode;
}

type Variant = 'danger' | 'warning';

const FLAG_VARIANT: Record<WarningFlagCode, Variant> = {
  // over_budget is the only one mapped to danger — it's the single flag that
  // touches money. The other three are operational/process warnings.
  over_budget: 'danger',
  late_start: 'warning',
  insurance_window: 'warning',
  onboarding_incomplete: 'warning',
};

const variantStyles: Record<Variant, string> = {
  danger: 'bg-danger-100 text-danger-700',
  warning: 'bg-warning-100 text-warning-700',
};

const dotStyles: Record<Variant, string> = {
  danger: 'bg-danger-500',
  warning: 'bg-warning-500',
};

export function WarningFlagChip({ code }: WarningFlagChipProps) {
  const variant = FLAG_VARIANT[code];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
        variantStyles[variant],
      )}
      data-flag-code={code}
    >
      <span
        className={cn('h-1.5 w-1.5 shrink-0 rounded-full', dotStyles[variant])}
        aria-hidden="true"
      />
      {WARNING_FLAG_LABELS[code]}
    </span>
  );
}
