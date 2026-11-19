import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchVendorStates } from '@/features/vendors/api/vendor.queries';

/** States used by vendors, for the list's "State" filter. */
export function useVendorStates() {
  return useQuery({
    queryKey: queryKeys.vendors.states(),
    queryFn: fetchVendorStates,
    staleTime: 60_000,
  });
}
