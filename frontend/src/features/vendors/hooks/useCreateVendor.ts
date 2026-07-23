import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { createVendor } from '@/features/vendors/api/vendor.mutations';
import type { CreateVendorInput } from '@/features/vendors/api/vendor.mutations';

export function useCreateVendor() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateVendorInput) => createVendor(input),
    onSuccess: () => {
      // vendors.all, not vendors.lists(): a new vendor can carry an insurance
      // expiration inside the 30-day window, which changes the expiring-soon
      // count shown beside the page title. Matches useImportVendors.
      queryClient.invalidateQueries({ queryKey: queryKeys.vendors.all });
    },
  });
}
