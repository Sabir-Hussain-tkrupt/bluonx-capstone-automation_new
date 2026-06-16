import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { closeBidding } from '@/features/bids/api/bid-package.mutations';

/**
 * Manually close bidding early (open -> evaluating). On success, invalidate the
 * package detail / list / task keys so the status badge and gating refetch.
 */
export function useCloseBidding(bidPackageId: string, taskId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => closeBidding(bidPackageId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.bidPackages.detail(bidPackageId),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.bidPackages.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.detail(taskId) });
    },
  });
}
