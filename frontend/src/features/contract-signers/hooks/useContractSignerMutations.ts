import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import {
  createContractSigner,
  updateContractSigner,
} from '../api/contractSigner.mutations';
import type {
  ContractSignerCreateRequest,
  ContractSignerUpdateRequest,
} from '../types';

/**
 * Mutation hooks for the signer roster. Each invalidates the whole
 * `contract_signers` key on success so both the settings table and the award
 * dropdown refetch — the server is the source of truth for the guard outcomes.
 * No optimistic updates: a create can be rejected by either duplicate branch and
 * a deactivate by the last-signer guard, so the local row would often be wrong.
 * Callers surface `errorMessage` so the backend 409 `detail` reaches the UI.
 */

export function useCreateContractSigner() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ContractSignerCreateRequest) => createContractSigner(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contractSigners.all });
    },
  });
}

export function useUpdateContractSigner() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: ContractSignerUpdateRequest }) =>
      updateContractSigner(id, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contractSigners.all });
    },
  });
}
