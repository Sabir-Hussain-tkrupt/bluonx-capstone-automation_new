import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { addVendorTrades, removeVendorTrade } from '@/features/vendors/api/vendor.mutations';
import type { BulkTradeInput } from '@/features/vendors/api/vendor.mutations';

export function useAddVendorTrades() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: BulkTradeInput) => addVendorTrades(input),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.vendors.detail(variables.vendorId),
      });
    },
  });
}

export function useRemoveVendorTrade() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ vendorId, tradeId }: { vendorId: string; tradeId: string }) =>
      removeVendorTrade(vendorId, tradeId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.vendors.detail(variables.vendorId),
      });
    },
  });
}
