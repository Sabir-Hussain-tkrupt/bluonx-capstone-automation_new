import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { sendContractForAward } from '@/features/contracts/api/contract.mutations';

/**
 * Deliver the contract for an award whose post-commit envelope send failed.
 *
 * On success the contract list is invalidated so the task detail read picks up the
 * new envelope row and swaps the recovery Alert for the Contract card. Errors are
 * deliberately NOT handled here: the caller renders the server's `detail` inside
 * the Alert, where the PM can read it and pass it on, rather than in a toast that
 * vanishes.
 */
export function useSendContract() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (awardId: string) => sendContractForAward(awardId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contracts.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.awards.all });
    },
  });
}
