import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { resendBidLink } from '@/features/bids/api/bid-package.mutations';

export function useResendBidLink(bidPackageId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (invitationId: string) => resendBidLink(invitationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bidPackages.detail(bidPackageId) });
    },
  });
}
