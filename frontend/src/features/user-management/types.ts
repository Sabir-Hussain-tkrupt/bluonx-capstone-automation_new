/**
 * Types for the admin User Management feature.
 *
 * Mirrors the Part 2 backend Pydantic models (backend/app/models/users.py).
 * The roster is served by FastAPI GET /users, which merges public.users with
 * Supabase auth to derive `status` and carries `invited_by` — neither is a
 * queryable column, which is why the list must go through the API, not Supabase.
 */

export type UserRole = 'admin' | 'project_manager';

/** Derived account status (backend-computed in list_users). */
export type UserStatus = 'active' | 'pending' | 'deactivated';

/** Shape of a row returned by GET /api/v1/users (UserAdminResponse). */
export interface UserAdminResponse {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  /** Soft-delete timestamp. Non-null means the row is terminal (see note). */
  deleted_at: string | null;
  /** UUID of the admin who sent the invite; null for bootstrap/seeded users. */
  invited_by: string | null;
  status: UserStatus;
}

/** Body for POST /api/v1/users/invite (UserInviteRequest). */
export interface UserInviteRequest {
  email: string;
  full_name: string;
  role: UserRole;
}

/** Partial patch for PATCH /api/v1/users/{id} (UserUpdate). */
export interface UserUpdateRequest {
  full_name?: string;
  role?: UserRole;
  is_active?: boolean;
}
