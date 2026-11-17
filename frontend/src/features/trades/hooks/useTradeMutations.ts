import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { deleteTrade, fetchTradeUsage, updateTrade } from '../api/trade.mutations';
import type { UpdateTradeInput } from '../types';

/** Where a trade is used. Always fresh: it decides whether edit / delete is allowed. */
export function useTradeUsage(tradeId: string | null) {
  return useQuery({
    queryKey: [...queryKeys.trades.all, 'usage', tradeId ?? ''] as const,
    queryFn: () => fetchTradeUsage(tradeId!),
    enabled: !!tradeId,
    staleTime: 0,
    gcTime: 0,
  });
}

export function useUpdateTrade() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: UpdateTradeInput }) => updateTrade(id, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.trades.all }),
  });
}

export function useDeleteTrade() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteTrade(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.trades.all }),
  });
}
