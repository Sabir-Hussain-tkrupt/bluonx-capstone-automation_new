import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchTrades } from '../api/trade.queries';

export function useTrades() {
  return useQuery({
    queryKey: queryKeys.trades.lists(),
    queryFn: fetchTrades,
    staleTime: 60_000,
  });
}
