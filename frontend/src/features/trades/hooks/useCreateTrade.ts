import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { createTrade } from '../api/trade.mutations';
import type { CreateTradeInput } from '../types';

export function useCreateTrade() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateTradeInput) => createTrade(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.trades.all });
    },
  });
}
