import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchBidPackagesForTask } from '@/features/bids/api/bid-package.queries';

export function useBidPackagesForTask(taskId: string) {
  return useQuery({
    queryKey: queryKeys.bidPackages.forTask(taskId),
    queryFn: () => fetchBidPackagesForTask(taskId),
    enabled: !!taskId,
  });
}
