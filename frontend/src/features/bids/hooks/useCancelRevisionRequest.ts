import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { cancelRevisionRequest } from '@/features/bids/api/bid-revision.mutations';

/**
 * Cancel a pending revision request. No optimistic update — the caller keeps
 * the "Revision Pending" badge until the server confirms (and surfaces a
 * toast on error).
 */
export function useCancelRevisionRequest(bidPackageId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (revisionRequestId: string) =>
      cancelRevisionRequest(revisionRequestId),

    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.bidRevisionRequests.list(bidPackageId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.bidPackages.detail(bidPackageId),
      });
    },
  });
}
