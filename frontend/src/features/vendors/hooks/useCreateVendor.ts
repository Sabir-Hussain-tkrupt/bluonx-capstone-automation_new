import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { createVendor } from '@/features/vendors/api/vendor.mutations';
import type { CreateVendorInput } from '@/features/vendors/api/vendor.mutations';

/**
 * Create a new vendor via FastAPI.
 *
 * On success, invalidates all vendor list caches so they refetch.
 *
 * @example
 * const createVendorMutation = useCreateVendor();
 *
 * const handleSubmit = (data: CreateVendorInput) => {
 *   createVendorMutation.mutate(data, {
 *     onSuccess: () => navigate('/vendors'),
 *     onError: (error) => toast.error(error.message),
 *   });
 * };
 */
export function useCreateVendor() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateVendorInput) => createVendor(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.vendors.lists() });
    },
  });
}
