import { Button } from '@/components/ui/Button';
import type { StalenessHint as StalenessHintShape } from '@/features/bids/utils/score-display';

export interface StalenessHintProps {
  hint: StalenessHintShape;
  onRecompute: () => void;
  isRecomputing: boolean;
}

/**
 * Tiny inline footer above the comparison table — "Scored {when} · {K} new
 * bids since" with a Recompute button. The Recompute action POSTs /scores; the
 * mutation hook invalidates the GET on success so the page refetches with the
 * fresh recommendation.
 */
export function StalenessHint({
  hint,
  onRecompute,
  isRecomputing,
}: StalenessHintProps) {
  return (
    <div
      className="flex flex-wrap items-center gap-3 text-xs text-secondary-500"
      data-no-print
    >
      <span>
        Scored <span className="font-medium text-secondary-700">{hint.scoredLabel}</span>
        {hint.newBidsCount > 0 && (
          <>
            {' · '}
            <span className="font-medium text-warning-700">
              {hint.newBidsCount} new {hint.newBidsCount === 1 ? 'bid' : 'bids'} since
            </span>
          </>
        )}
      </span>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onRecompute}
        isLoading={isRecomputing}
      >
        Recompute
      </Button>
    </div>
  );
}
