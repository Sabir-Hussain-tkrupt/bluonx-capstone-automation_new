import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchBidPackageEmailLog } from '@/features/bids/api/bid-package.queries';

export function useBidPackageEmailLog(bidPackageId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.bidInvitations.emailLog(bidPackageId),
    queryFn: () => fetchBidPackageEmailLog(bidPackageId),
    enabled: !!bidPackageId && enabled,
  });
}
