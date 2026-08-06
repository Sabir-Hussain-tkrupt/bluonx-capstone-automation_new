import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import type { ApiError } from '@/lib/api';
import { fetchVendors } from '@/features/vendors/api/vendor.queries';
import type { PaginatedVendors, VendorListFilters } from '@/features/vendors/api/vendor.queries';

// The error generic is declared so callers can read `error.message` without
// casting. `fetchVendors` goes through the axios instance, whose response
// interceptor rejects with an ApiError, so the generic is accurate.
export function useVendors(filters?: VendorListFilters) {
  return useQuery<PaginatedVendors, ApiError>({
    queryKey: queryKeys.vendors.list(filters as Record<string, unknown>),
    queryFn: () => fetchVendors(filters),
  });
}
