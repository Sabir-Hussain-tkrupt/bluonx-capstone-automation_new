import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { resendInvitation } from '@/features/bids/api/bid-package.mutations';

export function useResendInvitation(bidPackageId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (invitationId: string) => resendInvitation(invitationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bidPackages.detail(bidPackageId) });
    },
  });
}
