import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchVendors } from '@/features/vendors/api/vendor.queries';
import type { VendorListFilters } from '@/features/vendors/api/vendor.queries';

/**
 * Fetch the vendor list via Supabase direct read (RLS protected).
 *
 * @example
 * const { data: vendors, isLoading, error } = useVendors();
 * const { data: vendors } = useVendors({ status: 'approved' });
 */
export function useVendors(filters?: VendorListFilters) {
  return useQuery({
    queryKey: queryKeys.vendors.list(filters as Record<string, unknown>),
    queryFn: () => fetchVendors(filters),
  });
}
