import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { cancelBidPackage } from '@/features/bids/api/bid-package.mutations';

/**
 * Void a bidding round (open | evaluating -> cancelled). On success, invalidate
 * the package detail / list / task keys so the status badge, the action buttons
 * and the cancellation callout all refetch.
 */
export function useCancelBidPackage(bidPackageId: string, taskId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => cancelBidPackage(bidPackageId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.bidPackages.detail(bidPackageId),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.bidPackages.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.detail(taskId) });
    },
  });
}
