import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { computeBidPackageScores } from '@/features/bids/api/bid-scores.queries';

/**
 * POST /bid-packages/{id}/scores to (re)compute the cohort. On success, the
 * scores query is invalidated so the page refetches via GET, which is the
 * authoritative enriched + recommendation-bearing shape (POST returns the
 * slimmer Task 8.2 compute response without enrichment).
 */
export function useComputeBidPackageScores(bidPackageId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => computeBidPackageScores(bidPackageId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.bidPackages.scores(bidPackageId),
      });
    },
  });
}
