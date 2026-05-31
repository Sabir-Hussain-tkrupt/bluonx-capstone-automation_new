import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchVendorEmailLog } from '@/features/vendors/api/vendor.queries';

export function useVendorEmailLog(vendorId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.vendors.emailLog(vendorId),
    queryFn: () => fetchVendorEmailLog(vendorId),
    enabled: !!vendorId && enabled,
  });
}
