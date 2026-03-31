import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchNearbyVendors } from '@/features/vendors/api/nearby-vendors.queries';

interface UseNearbyVendorsOptions {
  projectId: string | null | undefined;
  radius?: number;
  tradeId?: string;
}

export function useNearbyVendors({ projectId, radius = 75, tradeId }: UseNearbyVendorsOptions) {
  return useQuery({
    queryKey: queryKeys.nearbyVendors.list(projectId!, { radius, tradeId }),
    queryFn: () => fetchNearbyVendors(projectId!, { radius, tradeId }),
    enabled: !!projectId,
  });
}
