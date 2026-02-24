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
    console.log('[AUTH] fetchProfile called for:', userId);
    try {
      // Race the Supabase query against a 10-second timeout so a hanging
      // RLS check or network issue doesn't lock the UI forever.
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10_000);

      const { data, error } = await supabase
        .from('users')
        .select('id, email, full_name, role, is_active, created_at, updated_at')
        .eq('id', userId)
        .abortSignal(controller.signal)
        .returns<UserProfile[]>()
        .single();

      clearTimeout(timeout);

      console.log('[AUTH] fetchProfile query returned:', { data: !!data, error: error?.message });

      if (error) {
        console.error('Failed to fetch user profile:', error.message);
        setProfile(null);
        return;
      }

      if (!data) {
        console.error('No profile found for user:', userId);
        setProfile(null);
        return;
      }

      if (!data.is_active) {
        console.warn('User account is deactivated. Signing out.');
        await supabase.auth.signOut();
        return;
      }

      setProfile(data);
    } catch (err) {
      // AbortError means our 10s timeout fired — the query hung.
      if (err instanceof DOMException && err.name === 'AbortError') {
        console.error('[AUTH] fetchProfile timed out after 10s — check RLS policies and network');
      } else {
        console.error('Unexpected error fetching profile:', err);
      }
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
    // Track whether initializeAuth has finished so the onAuthStateChange
    // handler knows whether to manage isLoading itself.
    let initialized = false;

    // 1. Subscribe to auth state changes FIRST so we never miss events.
    //    Use a non-async wrapper — fire-and-forget the profile fetch so
    //    the Supabase listener callback doesn't block internally.
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event: AuthChangeEvent, newSession: Session | null) => {
        if (!isMounted) return;

        console.log('[AUTH] onAuthStateChange:', event, 'session:', !!newSession);

        setSession(newSession);
        setUser(newSession?.user ?? null);

        switch (event) {
          case 'SIGNED_IN':
          case 'TOKEN_REFRESHED':
          case 'USER_UPDATED':
            if (newSession?.user) {
              // If init already ran, we manage isLoading ourselves.
              if (initialized) setIsLoading(true);
              fetchProfile(newSession.user.id).finally(() => {
                if (isMounted && initialized) setIsLoading(false);
              });
            }
            break;

          case 'SIGNED_OUT':
            setProfile(null);
            setIsLoading(false);
            break;

          case 'PASSWORD_RECOVERY':
            // Task 2.7 handles the UI for this.
            break;
        }
      }
    );

    // 2. Check for existing session (user refreshed the page)
    const initializeAuth = async () => {
      try {
        console.log('[AUTH] initializeAuth starting...');
        const { data: { session: existingSession } } = await supabase.auth.getSession();
        console.log('[AUTH] getSession returned:', !!existingSession);

        if (!isMounted) return;

        if (existingSession?.user) {
          setSession(existingSession);
          setUser(existingSession.user);
          await fetchProfile(existingSession.user.id);
        }
      } catch (err) {
        console.error('Error initializing auth:', err);
      } finally {
        initialized = true;
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    initializeAuth();

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