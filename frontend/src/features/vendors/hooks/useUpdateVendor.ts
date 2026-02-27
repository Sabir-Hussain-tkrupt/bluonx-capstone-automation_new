import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { updateVendor } from '@/features/vendors/api/vendor.mutations';
import type { UpdateVendorInput } from '@/features/vendors/api/vendor.mutations';

/**
 * Update an existing vendor via FastAPI.
 *
 * On success, invalidates both the specific vendor detail
 * and all vendor list caches.
 *
 * @example
 * const updateVendorMutation = useUpdateVendor();
 *
 * updateVendorMutation.mutate(
 *   { id: vendorId, company_name: 'New Name' },
 *   {
 *     onSuccess: () => toast.success('Vendor updated'),
 *     onError: (error) => toast.error(error.message),
 *   },
 * );
 */
export function useUpdateVendor() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UpdateVendorInput) => updateVendor(input),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.vendors.detail(variables.id),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.vendors.lists(),
      });
    },
  });
}
