import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import {
  deleteUser,
  inviteUser,
  resendInvite,
  updateUser,
} from '../api/user.mutations';
import type { UserInviteRequest, UserUpdateRequest } from '../types';

/**
 * Mutation hooks for user management. Each invalidates the whole `users` key on
 * success so the roster refetches from the server (the source of truth for
 * derived status and the guard outcomes). Callers surface `errorMessage` on
 * failure so backend 409 `detail` (self-protection / last-admin) reaches the UI.
 */

export function useInviteUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UserInviteRequest) => inviteUser(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.all });
    },
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: UserUpdateRequest }) =>
      updateUser(id, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.all });
    },
  });
}

export function useResendInvite() {
  return useMutation({
    mutationFn: (id: string) => resendInvite(id),
  });
}

export function useDeleteUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteUser(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.all });
    },
  });
}
