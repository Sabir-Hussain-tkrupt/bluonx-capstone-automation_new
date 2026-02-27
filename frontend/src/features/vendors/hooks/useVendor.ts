import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchVendorById } from '@/features/vendors/api/vendor.queries';

/**
 * Fetch a single vendor by ID via Supabase direct read.
 *
 * @example
 * const { id } = useParams<{ id: string }>();
 * const { data: vendor, isLoading } = useVendor(id!);
 */
export function useVendor(id: string) {
  return useQuery({
    queryKey: queryKeys.vendors.detail(id),
    queryFn: () => fetchVendorById(id),
    enabled: !!id,
  });
}
