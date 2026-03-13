import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchVendorById } from '@/features/vendors/api/vendor.queries';

export function useVendor(id: string) {
  return useQuery({
    queryKey: queryKeys.vendors.detail(id),
    queryFn: () => fetchVendorById(id),
    enabled: !!id,
  });
}
