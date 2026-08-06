import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import type { ApiError } from '@/lib/api';
import { fetchVendorById } from '@/features/vendors/api/vendor.queries';
import type { VendorDetail } from '@/features/vendors/api/vendor.queries';

// The error generic is declared so callers can branch on `error.status`
// without casting. `fetchVendorById` reads Supabase directly and rejects with
// an ApiError on every failure path, so the generic is accurate.
export function useVendor(id: string) {
  return useQuery<VendorDetail, ApiError>({
    queryKey: queryKeys.vendors.detail(id),
    queryFn: () => fetchVendorById(id),
    enabled: !!id,
  });
}
