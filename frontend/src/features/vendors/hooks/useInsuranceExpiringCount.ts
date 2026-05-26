import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchInsuranceExpiringCount } from '@/features/vendors/api/vendor.queries';

const POLL_MS = 60_000;

export function useInsuranceExpiringCount() {
  return useQuery({
    queryKey: queryKeys.vendors.insuranceExpiringCount(),
    queryFn: fetchInsuranceExpiringCount,
    refetchInterval: POLL_MS,
    refetchOnWindowFocus: true,
  });
}
