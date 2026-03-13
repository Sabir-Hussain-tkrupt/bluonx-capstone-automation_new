import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import {
  createContact,
  updateContact,
  deleteContact,
} from '@/features/vendors/api/vendor.mutations';
import type { CreateContactInput, UpdateContactInput } from '@/features/vendors/api/vendor.mutations';

export function useCreateContact() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateContactInput) => createContact(input),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.vendors.detail(variables.vendorId),
      });
    },
  });
}

export function useUpdateContact() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UpdateContactInput) => updateContact(input),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.vendors.detail(variables.vendorId),
      });
    },
  });
}

export function useDeleteContact() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ vendorId, contactId }: { vendorId: string; contactId: string }) =>
      deleteContact(vendorId, contactId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.vendors.detail(variables.vendorId),
      });
    },
  });
}
