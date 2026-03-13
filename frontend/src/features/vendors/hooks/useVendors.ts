import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchVendors } from '@/features/vendors/api/vendor.queries';
import type { VendorListFilters } from '@/features/vendors/api/vendor.queries';

export function useVendors(filters?: VendorListFilters) {
  return useQuery({
    queryKey: queryKeys.vendors.list(filters as Record<string, unknown>),
    queryFn: () => fetchVendors(filters),
  });
}
