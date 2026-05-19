import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchRevisionRequests } from '@/features/bids/api/bid-revision.queries';

export function useRevisionRequests(bidPackageId: string) {
  return useQuery({
    queryKey: queryKeys.bidRevisionRequests.list(bidPackageId),
    queryFn: () => fetchRevisionRequests(bidPackageId),
    enabled: !!bidPackageId,
  });
}
