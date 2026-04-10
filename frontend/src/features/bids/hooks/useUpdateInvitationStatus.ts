import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { updateInvitationStatus } from '@/features/bids/api/bid-package.mutations';
import type { UpdateInvitationStatusRequest } from '@/features/bids/types';

interface UpdateStatusInput {
  invitationId: string;
  status: UpdateInvitationStatusRequest['status'];
}

export function useUpdateInvitationStatus(bidPackageId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ invitationId, status }: UpdateStatusInput) =>
      updateInvitationStatus(invitationId, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bidPackages.detail(bidPackageId) });
    },
  });
}
