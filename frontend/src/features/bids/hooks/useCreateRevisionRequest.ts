import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { createRevisionRequest } from '@/features/bids/api/bid-revision.mutations';
import type {
  BidRevisionRequest,
  CreateRevisionRequestPayload,
} from '@/features/bids/types';

/**
 * Create a per-vendor revision request with an optimistic "pending" badge.
 *
 * onMutate prepends a synthetic pending row to the cached revision-requests
 * list so the row badge flips to "Revision Pending" immediately; onError
 * rolls back; onSettled refetches the list + the package detail.
 */
export function useCreateRevisionRequest(bidPackageId: string) {
  const queryClient = useQueryClient();
  const listKey = queryKeys.bidRevisionRequests.list(bidPackageId);

  return useMutation({
    mutationFn: (payload: CreateRevisionRequestPayload) =>
      createRevisionRequest(payload),

    onMutate: async (payload) => {
      await queryClient.cancelQueries({ queryKey: listKey });

      const previous =
        queryClient.getQueryData<BidRevisionRequest[]>(listKey);

      const now = new Date().toISOString();
      const optimistic: BidRevisionRequest = {
        id: `optimistic-${now}`,
        bid_invitation_id: payload.bid_invitation_id,
        original_submission_id: '',
        pm_note: payload.pm_note,
        revision_deadline: payload.revision_deadline,
        status: 'pending',
        decline_reason: null,
        requested_by: '',
        requested_at: now,
        responded_at: null,
        created_at: now,
        updated_at: now,
      };

      // List is sorted newest-first; prepend so it wins "most recent".
      queryClient.setQueryData<BidRevisionRequest[]>(listKey, (old) =>
        old ? [optimistic, ...old] : [optimistic],
      );

      return { previous };
    },

    onError: (_err, _payload, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(listKey, context.previous);
      }
    },

    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: listKey });
      queryClient.invalidateQueries({
        queryKey: queryKeys.bidPackages.detail(bidPackageId),
      });
    },
  });
}
