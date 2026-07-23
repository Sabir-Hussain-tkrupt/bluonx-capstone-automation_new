import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { updateVendor } from '@/features/vendors/api/vendor.mutations';
import type { UpdateVendorInput } from '@/features/vendors/api/vendor.mutations';

export function useUpdateVendor() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UpdateVendorInput) => updateVendor(input),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.vendors.detail(variables.id),
      });
      // vendors.all rather than lists(): editing insurance_expiration_date
      // changes the expiring-soon count too. Matches useCreateVendor and
      // useDeleteVendor.
      queryClient.invalidateQueries({
        queryKey: queryKeys.vendors.all,
      });
    },
  });
}
