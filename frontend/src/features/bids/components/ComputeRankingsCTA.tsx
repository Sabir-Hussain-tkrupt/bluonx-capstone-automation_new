import { Button } from '@/components/ui/Button';

export interface ComputeRankingsCTAProps {
  onCompute: () => void;
  isComputing: boolean;
  /** Optional: how many valid live submissions exist (drives the helper line). */
  validSubmissionCount?: number | null;
}

/**
 * Empty state on the Compare route. Shown when GET /scores returns
 * scores:[] (never-computed cohort). The button POSTs /scores, which
 * persists scoring + triggers a refetch via the mutation hook.
 */
export function ComputeRankingsCTA({
  onCompute,
  isComputing,
  validSubmissionCount,
}: ComputeRankingsCTAProps) {
  const count = validSubmissionCount ?? 0;

  return (
    <div
      className="rounded-lg border border-secondary-200 bg-white p-10 text-center shadow-sm"
      data-no-print
    >
      <h3 className="text-base font-semibold text-secondary-900">
        No rankings yet
      </h3>
      <p className="mx-auto mt-2 max-w-md text-sm text-secondary-600">
        {count > 0
          ? `Run scoring to rank ${count} ${
              count === 1 ? 'vendor' : 'vendors'
            } and surface the recommendation. You can recompute at any time.`
          : 'Once vendors submit their bids, you can compute rankings here. The recommendation engine ranks vendors by weighted score and surfaces warning flags.'}
      </p>
      <div className="mt-5">
        <Button
          type="button"
          variant="primary"
          size="md"
          onClick={onCompute}
          isLoading={isComputing}
          disabled={count === 0 || isComputing}
        >
          Compute Rankings
        </Button>
      </div>
    </div>
  );
}
