import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchTrades } from '@/features/vendors/api/vendor.queries';

export function useTrades() {
  return useQuery({
    queryKey: queryKeys.trades.list(),
    queryFn: fetchTrades,
  });
}
