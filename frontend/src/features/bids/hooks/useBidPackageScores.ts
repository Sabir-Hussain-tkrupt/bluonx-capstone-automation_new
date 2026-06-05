import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchBidPackageScores } from '@/features/bids/api/bid-scores.queries';

export function useBidPackageScores(bidPackageId: string) {
  return useQuery({
    queryKey: queryKeys.bidPackages.scores(bidPackageId),
    queryFn: () => fetchBidPackageScores(bidPackageId),
    enabled: !!bidPackageId,
  });
}
