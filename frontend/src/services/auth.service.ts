import { supabase } from '@/lib/supabase';
import type { SignupData, LoginData } from '@/types/auth.types';

/**
 * Auth service — all Supabase Auth operations in one place.
 *
 * Components should use these functions (via useAuth or directly)
 * rather than calling supabase.auth methods directly. This gives us
 * a single place to add logging, error transformation, or switch
 * auth providers if ever needed.
 */

// ─── Sign Up ──────────────────────────────────────────────────────────
/**
 * Register a new user.
 *
 * What happens under the hood:
 * 1. Supabase creates a row in auth.users
 * 2. Your fn_handle_new_auth_user trigger fires
 * 3. Trigger creates a row in public.users with matching UUID
 *    - full_name comes from raw_user_meta_data.full_name
 *    - role comes from raw_user_meta_data.role
 * 4. If "Confirm Email" is ON in dashboard, user gets a verification email
 * 5. User clicks verification link → session is created → onAuthStateChange fires
 *
 * For dev (Confirm Email OFF): session is created immediately.
 */
export async function signUp({ email, password, full_name, role }: SignupData) {
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      data: {
        // These fields are stored in auth.users.raw_user_meta_data
        // and read by fn_handle_new_auth_user trigger to populate public.users
        full_name,
        role,
      },
      // Where to redirect after email confirmation (if enabled)
      emailRedirectTo: `${window.location.origin}/auth/callback`,
    },
  });

  if (error) throw error;
  return data;
}

// ─── Sign In ──────────────────────────────────────────────────────────
/**
 * Log in with email + password.
 *
 * On success, Supabase returns a session with access_token + refresh_token.
 * The onAuthStateChange listener in AuthContext picks this up and
 * fetches the public.users profile automatically.
 */
export async function signIn({ email, password }: LoginData) {
  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password,
  });

  if (error) throw error;
  return data;
}

// ─── Sign Out ─────────────────────────────────────────────────────────
/**
 * Sign out the current user.
 *
 * Clears the session from localStorage and triggers onAuthStateChange
 * with event = 'SIGNED_OUT', which clears the AuthContext state.
 */
export async function signOut() {
  const { error } = await supabase.auth.signOut();
  if (error) throw error;
}

// ─── Password Reset ──────────────────────────────────────────────────
/**
 * Send a password reset email.
 *
 * The user clicks the link in the email → lands on your app at /auth/callback
 * → onAuthStateChange fires with event = 'PASSWORD_RECOVERY'
 * → your UI (Task 2.7) shows a "set new password" form.
 */
export async function requestPasswordReset(email: string) {
  const { error } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${window.location.origin}/auth/reset-password`,
  });

  if (error) throw error;
}

// ─── Update Password ─────────────────────────────────────────────────
/**
 * Set a new password (used after clicking the reset link).
 *
 * Requires an active session (which Supabase creates when the user
 * clicks the reset link and lands on your app).
 */
export async function updatePassword(newPassword: string) {
  const { error } = await supabase.auth.updateUser({
    password: newPassword,
  });

  if (error) throw error;
}

// ─── Update Profile Metadata ─────────────────────────────────────────
/**
 * Update the user's metadata in auth.users.
 *
 * NOTE: This updates auth.users.raw_user_meta_data, NOT public.users.
 *
 * Do NOT write to public.users from the client. UPDATE on public.users was
 * revoked from the `authenticated` role, so a direct
 * `supabase.from('users').update(...)` now fails. All public.users writes
 * (full_name, role, is_active, etc.) go through the FastAPI user-management
 * endpoints (e.g. PATCH /api/v1/users/{id}), which use the service_role key and
 * enforce admin authorization. This function only touches auth.users metadata via
 * supabase.auth.updateUser, never public.users.
 */
export async function updateUserMetadata(metadata: { full_name?: string }) {
  const { error } = await supabase.auth.updateUser({
    data: metadata,
  });

  if (error) throw error;
}

// ─── Get Current Session ─────────────────────────────────────────────
/**
 * Get the current session. Useful for one-off checks outside of React
 * (e.g., in API utility functions that need the JWT).
 */
export async function getCurrentSession() {
  const { data: { session }, error } = await supabase.auth.getSession();
  if (error) throw error;
  return session;
}

// ─── Get Access Token ────────────────────────────────────────────────
/**
 * Get the current JWT access token for API calls to FastAPI.
 *
 * Usage in API layer (Task 2.4):
 *   const token = await getAccessToken();
 *   fetch('/api/vendors', {
 *     headers: { Authorization: `Bearer ${token}` }
 *   });
 *
 * Returns null if not authenticated.
 */
export async function getAccessToken(): Promise<string | null> {
  const { data: { session } } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}