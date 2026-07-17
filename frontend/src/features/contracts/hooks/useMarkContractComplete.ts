import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { markContractComplete } from '@/features/contracts/api/contract.mutations';

/**
 * Mark a contract complete. Invalidates the contract list (the task panel re-reads
 * the active contract's status) and milestone surfaces (nothing changes there, but
 * the gate is derived from them so keep them fresh).
 */
export function useMarkContractComplete() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (contractId: string) => markContractComplete(contractId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contracts.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.lists() });
    },
  });
}
