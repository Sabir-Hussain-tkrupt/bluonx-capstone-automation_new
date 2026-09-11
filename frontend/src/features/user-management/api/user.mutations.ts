import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  UserAdminResponse,
  UserInviteRequest,
  UserUpdateRequest,
} from '../types';

/** POST /users/invite — invite a new admin/PM by email. */
export async function inviteUser(
  body: UserInviteRequest,
): Promise<UserAdminResponse> {
  const { data } = await api.post(API_ENDPOINTS.USER_INVITE, body);
  return data as UserAdminResponse;
}

/**
 * PATCH /users/{id} — change role and/or toggle is_active.
 *
 * The backend enforces self-protection (G1) and last-admin (G2) guards and
 * returns a 409 with a `detail` message we surface verbatim.
 */
export async function updateUser(
  id: string,
  patch: UserUpdateRequest,
): Promise<UserAdminResponse> {
  const { data } = await api.patch(API_ENDPOINTS.USER(id), patch);
  return data as UserAdminResponse;
}

/** POST /users/{id}/restore — restore a soft-deleted/deactivated user. */
export async function restoreUser(id: string): Promise<UserAdminResponse> {
  const { data } = await api.post(API_ENDPOINTS.USER_RESTORE(id));
  return data as UserAdminResponse;
}

/** POST /users/{id}/resend-invite — re-send the invite to a pending user. */
export async function resendInvite(id: string): Promise<void> {
  await api.post(API_ENDPOINTS.USER_RESEND_INVITE(id));
}

/** DELETE /users/{id} — soft-delete (terminal; cannot be undone via the API). */
export async function deleteUser(id: string): Promise<void> {
  await api.delete(API_ENDPOINTS.USER(id));
}
