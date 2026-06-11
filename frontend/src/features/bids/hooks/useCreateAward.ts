import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { createAward } from '@/features/bids/api/award.mutations';
import type { Award, CreateAwardPayload } from '@/features/bids/types';

/**
 * Create an award from the comparison UI (Task 9.2). On success, invalidate the
 * package scores / package detail / task / awards keys so every dependent
 * surface (including the `is_awarded` flag that hides "Request Revision")
 * refetches the authoritative state. No optimistic update — the write is gated
 * server-side and the response is the source of truth.
 */
export function useCreateAward(args: { bidPackageId: string; taskId: string }) {
  const { bidPackageId, taskId } = args;
  const queryClient = useQueryClient();

  return useMutation<Award, unknown, CreateAwardPayload>({
    mutationFn: (payload) => createAward(payload),

    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.bidPackages.scores(bidPackageId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.bidPackages.detail(bidPackageId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.tasks.detail(taskId),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.awards.all });
    },
  });
}
