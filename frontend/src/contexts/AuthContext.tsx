import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useMemo,
} from 'react';
import type { Session, User as SupabaseUser, AuthChangeEvent } from '@supabase/supabase-js';
import { supabase } from '@/lib/supabase';
import type { AuthState, UserProfile } from '@/types/auth.types';

// ─── Context Shape ───────────────────────────────────────────────────────
interface AuthContextValue extends AuthState {
  /** Force-refresh the profile from public.users (e.g., after name change). */
  refreshProfile: () => Promise<void>;

  /** Sign out and clear all state. */
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// ─── Provider ────────────────────────────────────────────────────────────
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<SupabaseUser | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true); // starts true — checking session

  // ── Fetch public.users profile ──────────────────────────────────────
  const fetchProfile = useCallback(async (userId: string) => {
    try {
      const { data, error } = await supabase
        .from('users')
        .select('id, email, full_name, role, is_active, created_at, updated_at')
        .eq('id', userId)
        .single();

      if (error) {
        console.error('Failed to fetch user profile:', error.message);
        setProfile(null);
        return;
      }

      // Safety check: if user is soft-deleted or deactivated, treat as unauthenticated.
      // This respects the RLS policy which filters deleted_at IS NULL,
      // but we add a client-side check too for defense-in-depth.
      if (!data.is_active) {
        console.warn('User account is deactivated. Signing out.');
        await supabase.auth.signOut();
        return;
      }

      setProfile(data as UserProfile);
    } catch (err) {
      console.error('Unexpected error fetching profile:', err);
      setProfile(null);
    }
  }, []);

  // ── Public method to refresh profile on demand ──────────────────────
  const refreshProfile = useCallback(async () => {
    if (user?.id) {
      await fetchProfile(user.id);
    }
  }, [user?.id, fetchProfile]);

  // ── Sign out ────────────────────────────────────────────────────────
  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
    // State cleanup happens in onAuthStateChange listener below
  }, []);

  // ── Initialize: check existing session + subscribe to changes ───────
  useEffect(() => {
    let isMounted = true;

    // 1. Check for existing session (user refreshed the page)
    const initializeAuth = async () => {
      try {
        const { data: { session: existingSession } } = await supabase.auth.getSession();

        if (!isMounted) return;

        if (existingSession?.user) {
          setSession(existingSession);
          setUser(existingSession.user);
          await fetchProfile(existingSession.user.id);
        }
      } catch (err) {
        console.error('Error initializing auth:', err);
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    initializeAuth();

    // 2. Subscribe to auth state changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event: AuthChangeEvent, newSession: Session | null) => {
        if (!isMounted) return;

        setSession(newSession);
        setUser(newSession?.user ?? null);

        switch (event) {
          case 'SIGNED_IN':
          case 'TOKEN_REFRESHED':
            // On sign-in or token refresh, (re)fetch the profile.
            // TOKEN_REFRESHED fires automatically — Supabase handles the timing.
            if (newSession?.user) {
              await fetchProfile(newSession.user.id);
            }
            break;

          case 'SIGNED_OUT':
            // Clear everything
            setProfile(null);
            break;

          case 'USER_UPDATED':
            // User changed their email or metadata in Supabase Auth.
            // Refresh our profile to stay in sync.
            if (newSession?.user) {
              await fetchProfile(newSession.user.id);
            }
            break;

          case 'PASSWORD_RECOVERY':
            // User clicked the password reset link in their email.
            // The session is set but they need to enter a new password.
            // Task 2.7 will handle the UI for this.
            break;
        }
      }
    );

    // 3. Cleanup on unmount
    return () => {
      isMounted = false;
      subscription.unsubscribe();
    };
  }, [fetchProfile]);

  // ── Memoized context value (prevents unnecessary re-renders) ────────
  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      user,
      profile,
      isLoading,
      isAuthenticated: !!session && !!profile,
      refreshProfile,
      signOut,
    }),
    [session, user, profile, isLoading, refreshProfile, signOut]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ─── Hook ────────────────────────────────────────────────────────────────
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}