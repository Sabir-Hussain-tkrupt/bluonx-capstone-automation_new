import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchQualifiedVendors } from '@/features/bids/api/bid-package.queries';

export function useQualifiedVendors(taskId: string) {
  return useQuery({
    queryKey: queryKeys.qualifiedVendors.all(taskId),
    queryFn: () => fetchQualifiedVendors(taskId),
    enabled: !!taskId,
  });
}
