import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { createVendor } from '@/features/vendors/api/vendor.mutations';
import type { CreateVendorInput } from '@/features/vendors/api/vendor.mutations';

export function useCreateVendor() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateVendorInput) => createVendor(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.vendors.lists() });
    },
  });
}
