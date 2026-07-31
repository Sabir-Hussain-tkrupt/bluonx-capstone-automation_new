import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type { UserAdminResponse } from '../types';

/**
 * Fetch the full user roster through FastAPI (NOT Supabase, by design — C1).
 *
 * RLS (users_select_authenticated) hides inactive/soft-deleted rows from the
 * `authenticated` role, and `status` / `invited_by` are backend-computed. A
 * direct Supabase read would show the admin a partial, incorrect roster.
 */
export async function fetchUsers(): Promise<UserAdminResponse[]> {
  const { data } = await api.get(API_ENDPOINTS.USERS);
  return data as UserAdminResponse[];
}
