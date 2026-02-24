import type { Session, User as SupabaseUser } from '@supabase/supabase-js';

/**
 * The app-level user profile from public.users table.
 * This is NOT the same as the Supabase auth.users record.
 *
 * Supabase auth.users → managed by Supabase (credentials, sessions)
 * public.users        → managed by us (role, full_name, is_active)
 *
 * They share the same UUID. The fn_handle_new_auth_user trigger
 * creates the public.users row automatically on signup.
 */
export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  role: 'admin' | 'project_manager';
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * Combined auth state available throughout the app via AuthContext.
 */
export interface AuthState {
  /** Supabase session (contains JWT tokens). null = not logged in. */
  session: Session | null;

  /** Supabase auth user (from auth.users). null = not logged in. */
  user: SupabaseUser | null;

  /** App-level profile (from public.users). null = not loaded yet or not logged in. */
  profile: UserProfile | null;

  /** True while initial session check is in progress (prevents flash of login page). */
  isLoading: boolean;

  /** True if session exists AND profile is loaded. The "fully ready" state. */
  isAuthenticated: boolean;
}

/**
 * Signup form data. Maps to what fn_handle_new_auth_user expects
 * in raw_user_meta_data.
 */
export interface SignupData {
  email: string;
  password: string;
  full_name: string;
  role: 'admin' | 'project_manager';
}

/**
 * Login form data.
 */
export interface LoginData {
  email: string;
  password: string;
}