import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import {
  fetchBidPackagesList,
  type BidPackageListFilters,
} from '@/features/bids/api/bid-packages-list.queries';

export function useBidPackagesList(filters?: BidPackageListFilters) {
  return useQuery({
    queryKey: queryKeys.bidPackages.list(
      filters as Record<string, unknown> | undefined,
    ),
    queryFn: () => fetchBidPackagesList(filters),
  });
}
