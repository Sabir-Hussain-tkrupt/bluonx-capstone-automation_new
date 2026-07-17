import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import {
  createReview,
  updateReview,
  type ReviewInput,
} from '@/features/contracts/api/contract.mutations';

/** Create the one review for a completed contract. */
export function useCreateReview(contractId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: ReviewInput) => createReview(contractId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.reviews.forContract(contractId),
      });
    },
  });
}

/** Correct an existing review. `contractId` is used only to invalidate its query. */
export function useUpdateReview(contractId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ reviewId, input }: { reviewId: string; input: ReviewInput }) =>
      updateReview(reviewId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.reviews.forContract(contractId),
      });
    },
  });
}
