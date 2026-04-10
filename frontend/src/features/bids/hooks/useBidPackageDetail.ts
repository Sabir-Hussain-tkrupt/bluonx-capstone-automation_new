import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchBidPackageDetail } from '@/features/bids/api/bid-package.queries';

export function useBidPackageDetail(bidPackageId: string) {
  return useQuery({
    queryKey: queryKeys.bidPackages.detail(bidPackageId),
    queryFn: () => fetchBidPackageDetail(bidPackageId),
    enabled: !!bidPackageId,
  });
}
