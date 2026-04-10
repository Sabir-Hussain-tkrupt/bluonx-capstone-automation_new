import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { createBidPackage } from '@/features/bids/api/bid-package.mutations';
import type { CreateBidPackageRequest } from '@/features/bids/types';

export function useCreateBidPackage(taskId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateBidPackageRequest) => createBidPackage(taskId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bidPackages.forTask(taskId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.detail(taskId) });
    },
  });
}
