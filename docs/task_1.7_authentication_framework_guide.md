# Task 1.7 — Authentication Framework Setup Guide

**Project:** BluOnX Bid Management & Vendor Coordination System  
**Estimated Hours:** 5  
**Prerequisites:** Task 1.1 (Supabase project), Task 1.2 (schema with `fn_handle_new_auth_user` trigger), Task 2.1 (React + Vite scaffold)  
**Last Updated:** February 24, 2026

---

## Table of Contents

1. [What This Task Covers](#1-what-this-task-covers)
2. [Architecture Overview](#2-architecture-overview)
3. [Step 1: Supabase Dashboard Configuration](#step-1-supabase-dashboard-configuration)
4. [Step 2: Install Supabase Client Library](#step-2-install-supabase-client-library)
5. [Step 3: Supabase Client Initialization](#step-3-supabase-client-initialization)
6. [Step 4: TypeScript Types for Auth](#step-4-typescript-types-for-auth)
7. [Step 5: Auth Context & Provider](#step-5-auth-context--provider)
8. [Step 6: Auth API Service Layer](#step-6-auth-api-service-layer)
9. [Step 7: Protected Route Component](#step-7-protected-route-component)
10. [Step 8: Environment Variables](#step-8-environment-variables)
11. [Step 9: FastAPI Auth Utility Stub](#step-9-fastapi-auth-utility-stub)
12. [Step 10: Verification Checklist](#step-10-verification-checklist)
13. [File Tree Summary](#file-tree-summary)
14. [How This Connects to Future Tasks](#how-this-connects-to-future-tasks)

---

## 1. What This Task Covers

Task 1.7 sets up the **authentication framework** — the plumbing, not the UI. You're building the infrastructure that Tasks 2.7 (auth UI pages) and 2.8 (dashboard layout) will plug into.

**In scope (this task):**
- Supabase Auth dashboard configuration (email/password provider)
- Supabase JS client initialization with environment variables
- React AuthContext + AuthProvider (session state management)
- Automatic token refresh (handled by Supabase client)
- User metadata storage strategy (connects to your existing `fn_handle_new_auth_user` trigger)
- Protected route wrapper component (shell — no actual routes yet)
- Auth service layer (signup, login, logout, password reset functions)
- Lightweight FastAPI JWT validation stub (file structure only)

**Out of scope (future tasks):**
- Login/signup UI pages → Task 2.7
- Dashboard layout with user menu → Task 2.8
- FastAPI full middleware implementation → Task 2.6
- Role-based UI rendering → Task 2.7

---

## 2. Architecture Overview

Think of the auth system like a **building with a lobby, a badge system, and a security desk**:

```
┌─────────────────────────────────────────────────────────────┐
│                      SUPABASE AUTH                          │
│                   (The Badge Printer)                       │
│  - Stores credentials in auth.users                        │
│  - Issues JWTs (the "badges")                              │
│  - Handles email verification, password reset              │
│  - Triggers fn_handle_new_auth_user → public.users row     │
└──────────────────────┬──────────────────────────────────────┘
                       │ JWT (access_token + refresh_token)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    REACT FRONTEND                           │
│                   (The Lobby)                               │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Supabase     │  │ AuthContext   │  │ ProtectedRoute   │  │
│  │ Client       │→ │ & Provider   │→ │ Wrapper          │  │
│  │ (badge       │  │ (who's       │  │ (checks badge    │  │
│  │  reader)     │  │  logged in?) │  │  at the door)    │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                             │
│  Auth Service Layer (login, signup, logout, resetPassword)  │
└──────────────────────┬──────────────────────────────────────┘
                       │ JWT in Authorization header
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND                          │
│                   (The Security Desk)                       │
│                                                             │
│  - Validates JWT on every request                          │
│  - Extracts user_id from token                             │
│  - Uses service_role key for DB writes (bypasses RLS)      │
│  - Stub created now, full implementation in Task 2.6       │
└─────────────────────────────────────────────────────────────┘
```

**Key insight:** Supabase Auth manages the hard parts (hashing, sessions, tokens). Your job is to wire the frontend to listen for auth state changes and store the current user in React context.

---

## Step 1: Supabase Dashboard Configuration

> **Time estimate: ~20 minutes**

### 1a. Enable Email/Password Provider

1. Go to **Supabase Dashboard → Authentication → Providers**
2. Confirm **Email** provider is enabled (it's on by default)
3. Settings to configure:

| Setting | Value | Why |
|---------|-------|-----|
| Enable Email Signup | ✅ ON | Allow new user registration |
| Confirm Email | ✅ ON (for production) | Prevents fake accounts. For **dev**, you can toggle OFF to skip email verification during testing |
| Secure Email Change | ✅ ON | Requires email verification for changes |
| Double Confirm Email Changes | OFF | Unnecessary for small internal team |
| Minimum Password Length | 8 | Industry standard minimum |

### 1b. Disable All Other Providers

Since we're strictly email/password (no OAuth):

1. **Phone** → OFF
2. **Google** → OFF (the project plan mentioned it, but it was confirmed as a mistake)
3. All other social providers → OFF

### 1c. Configure Email Templates

Go to **Authentication → Email Templates**. Customize these four templates:

| Template | When It's Sent | Customize |
|----------|---------------|-----------|
| Confirm Signup | After registration | Subject: "Welcome to BluOnX — Confirm Your Email" |
| Reset Password | Password reset request | Subject: "BluOnX — Reset Your Password" |
| Magic Link | Not used for internal auth, but used for vendor portal later | Leave default for now |
| Change Email | When email is updated | Subject: "BluOnX — Confirm Email Change" |

> **Note:** For development, the emails go to Supabase's built-in Inbucket (fake SMTP). You can view them at **Authentication → Email Templates → Click "Inbucket"** link. In production (Phase 12), you'll configure a real email provider (AWS SES or SendGrid).

### 1d. Configure URL Settings

Go to **Authentication → URL Configuration**:

| Setting | Development Value | Production Value (later) |
|---------|-------------------|--------------------------|
| Site URL | `http://localhost:5173` | `https://app.bluonx.com` (your domain) |
| Redirect URLs | `http://localhost:5173/**` | `https://app.bluonx.com/**` |

> **Why `/**`?** The wildcard allows redirects to any path on your domain (e.g., after email confirmation, redirect to `/dashboard` or `/login`).

### 1e. Configure Session Settings

Go to **Authentication → Settings** (or check under Auth config):

| Setting | Value | Why |
|---------|-------|-----|
| JWT Expiry | 3600 (1 hour) | Default. Supabase auto-refreshes before expiry. |
| Refresh Token Rotation | ✅ Enabled | Security: each refresh token is single-use |
| Refresh Token Reuse Interval | 10 (seconds) | Grace period for concurrent requests using same refresh token |

---

## Step 2: Install Supabase Client Library

```bash
cd frontend
npm install @supabase/supabase-js
```

This single package gives you:
- Auth client (signup, login, logout, session management)
- Database client (reads via RLS policies you already set up)
- Storage client (for file uploads)
- Realtime client (for Task 6.1 later)

---

## Step 3: Supabase Client Initialization

> **Analogy:** This is like setting up the badge reader hardware — it doesn't check badges yet, it just knows how to talk to the badge printer (Supabase Auth).

Create the Supabase client as a singleton that the entire app shares.

### File: `frontend/src/lib/supabase.ts`

```typescript
import { createClient } from '@supabase/supabase-js';
import type { Database } from '@/types/database.types';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    'Missing Supabase environment variables. ' +
    'Ensure VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are set in .env.local'
  );
}

export const supabase = createClient<Database>(supabaseUrl, supabaseAnonKey, {
  auth: {
    // Use localStorage for session persistence across browser tabs/refreshes.
    // When the user closes the browser and reopens, they stay logged in
    // until the refresh token expires (default: 7 days in Supabase).
    persistSession: true,

    // Supabase stores session data in localStorage under this key.
    // Custom key prevents collision if other Supabase projects run on localhost.
    storageKey: 'bluonx-auth',

    // Automatically refresh the JWT before it expires.
    // Supabase handles this internally — it refreshes ~60 seconds before expiry.
    // You don't need to write any refresh logic yourself.
    autoRefreshToken: true,

    // Listen for auth events across browser tabs (login in one tab = logged in everywhere).
    detectSessionInUrl: true,
  },
});
```

**What's happening here:**
- `createClient<Database>` — the generic `<Database>` is a TypeScript type that gives you autocomplete for your tables. We'll create a placeholder for now (Step 4) and generate the real one later with the Supabase CLI.
- `persistSession: true` — stores the JWT in `localStorage` so users stay logged in across page refreshes. Think of it like a "remember me" that's always on.
- `autoRefreshToken: true` — the client automatically gets a new JWT before the old one expires. This is the "session management" part of Task 1.7 — Supabase handles it for you.
- `detectSessionInUrl: true` — when Supabase redirects back after email confirmation or password reset, the tokens are in the URL hash. This setting tells the client to pick them up automatically.

---

## Step 4: TypeScript Types for Auth

### 4a. Database Types Placeholder

> We'll generate proper types from your schema later using `supabase gen types typescript`. For now, create a placeholder so the code compiles.

### File: `frontend/src/types/database.types.ts`

```typescript
/**
 * Placeholder for Supabase-generated database types.
 *
 * Generate the real types by running:
 *   npx supabase gen types typescript --project-id <your-project-id> > src/types/database.types.ts
 *
 * This gives you full autocomplete for all 28 tables, their columns,
 * and the correct TypeScript types for each column.
 */
export type Database = {
  public: {
    Tables: {
      users: {
        Row: {
          id: string;
          email: string;
          full_name: string;
          role: 'admin' | 'project_manager';
          is_active: boolean;
          created_at: string;
          updated_at: string;
          deleted_at: string | null;
        };
        Insert: {
          id: string;
          email: string;
          full_name: string;
          role: 'admin' | 'project_manager';
          is_active?: boolean;
        };
        Update: {
          full_name?: string;
          role?: 'admin' | 'project_manager';
          is_active?: boolean;
          deleted_at?: string | null;
        };
      };
      // Other tables will be auto-generated.
      // This placeholder only includes 'users' since auth needs it.
      [key: string]: any;
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
  };
};
```

### 4b. Auth-Specific Types

### File: `frontend/src/types/auth.types.ts`

```typescript
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
```

---

## Step 5: Auth Context & Provider

> **Analogy:** The AuthProvider is like a security camera monitor room. It watches the "front door" (Supabase auth events) at all times and broadcasts to every room in the building (React components) who's currently inside.

This is the core of Task 1.7. The provider does four things:
1. **Subscribes first:** Listens for auth state changes so no events are missed
2. **On mount:** Checks if there's an existing session (user refreshed the page)
3. **Fetches profile:** When a session exists, loads the `public.users` row
4. **Timeout safety:** Aborts hanging queries after 10 seconds to prevent UI lockup

> **Lessons learned during implementation:** Two critical patterns are used here:
>
> **1. AbortController timeout on fetchProfile.** The Supabase query to `public.users` can hang if RLS policy evaluation stalls (e.g., `private.is_active_user()` has a circular dependency during SDK type inference issues). The 10-second timeout ensures `isLoading` always resolves.
>
> **2. Synchronous `onAuthStateChange` callback.** The callback must NOT be `async` with `await fetchProfile(...)` inside it. Supabase's internal listener doesn't handle long-running async callbacks well — the `await` blocks subsequent auth events. Instead, use fire-and-forget with `.finally()` to manage `isLoading`.

### File: `frontend/src/contexts/AuthContext.tsx`

```tsx
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
  // Includes a 10-second AbortController timeout. If the Supabase query
  // hangs (RLS stall, network issue, SDK type inference problem with
  // placeholder database.types.ts), the abort fires, the catch block
  // handles it, and execution continues to the finally block so
  // isLoading always resolves.
  const fetchProfile = useCallback(async (userId: string) => {
    try {
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

      // Safety check: if user is soft-deleted or deactivated, treat as unauthenticated.
      // This respects the RLS policy which filters deleted_at IS NULL,
      // but we add a client-side check too for defense-in-depth.
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
    //    CRITICAL: This callback is intentionally NOT async.
    //    Using async/await here blocks Supabase's internal listener and
    //    can prevent subsequent auth events from being processed.
    //    Instead, we fire-and-forget the profile fetch with .finally().
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event: AuthChangeEvent, newSession: Session | null) => {
        if (!isMounted) return;

        setSession(newSession);
        setUser(newSession?.user ?? null);

        switch (event) {
          case 'SIGNED_IN':
          case 'TOKEN_REFRESHED':
          case 'USER_UPDATED':
            if (newSession?.user) {
              // If init already ran, we manage isLoading ourselves.
              if (initialized) setIsLoading(true);
              // Fire-and-forget — do NOT await this.
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
            // User clicked the password reset link in their email.
            // The session is set but they need to enter a new password.
            // Task 2.7 will handle the UI for this.
            break;
        }
      }
    );

    // 2. Check for existing session (user refreshed the page)
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
```

### Wire the Provider into Your App

### File: `frontend/src/App.tsx` (or wherever your root component is)

```tsx
import { AuthProvider } from '@/contexts/AuthContext';
// import { BrowserRouter } from 'react-router-dom';  // Task 2.2

function App() {
  return (
    // <BrowserRouter>       {/* Task 2.2 */}
      <AuthProvider>
        {/* Your routes and layout will go here in Task 2.2 / 2.8 */}
        <div className="min-h-screen">
          <p>Auth framework loaded. Build login UI in Task 2.7.</p>
        </div>
      </AuthProvider>
    // </BrowserRouter>
  );
}

export default App;
```

---

## Step 6: Auth API Service Layer

> **Analogy:** If the AuthContext is the security camera room, this service layer is the **instruction manual** for the guards — how to process a new badge (signup), verify someone (login), revoke access (logout), etc.

This keeps auth logic out of your components. Components call these functions; they don't touch `supabase.auth` directly.

### File: `frontend/src/services/auth.service.ts`

```typescript
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
 * To update public.users (full_name, etc.), use a FastAPI endpoint
 * (Task 2.6) or direct Supabase update:
 *
 *   supabase.from('users').update({ full_name: 'New Name' }).eq('id', userId)
 *
 * The RLS policy users_update_admin_or_self allows users to update their own row.
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
```

---

## Step 7: Protected Route Component

> This is a shell that checks if the user is authenticated before rendering child routes. It handles the three states: loading, not authenticated, and authenticated.

### File: `frontend/src/components/auth/ProtectedRoute.tsx`

```tsx
import { useAuth } from '@/contexts/AuthContext';
// import { Navigate, useLocation } from 'react-router-dom';  // Task 2.2

interface ProtectedRouteProps {
  children: React.ReactNode;
  /** Optional: restrict to specific role. If not set, any authenticated user can access. */
  requiredRole?: 'admin' | 'project_manager';
}

/**
 * Wraps routes that require authentication.
 *
 * Usage (in Task 2.2 when routing is set up):
 *
 *   <Route path="/dashboard" element={
 *     <ProtectedRoute>
 *       <DashboardLayout />
 *     </ProtectedRoute>
 *   } />
 *
 *   <Route path="/admin/users" element={
 *     <ProtectedRoute requiredRole="admin">
 *       <UserManagement />
 *     </ProtectedRoute>
 *   } />
 */
export function ProtectedRoute({ children, requiredRole }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, profile } = useAuth();
  // const location = useLocation();  // Task 2.2

  // 1. Still checking session — show nothing (prevents flash of login page)
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-gray-500">Loading...</p>
        {/* Replace with a proper spinner component in Task 2.5 */}
      </div>
    );
  }

  // 2. Not authenticated — redirect to login
  if (!isAuthenticated) {
    // Task 2.2: Replace with Navigate component
    // return <Navigate to="/login" state={{ from: location }} replace />;
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-red-500">Not authenticated. Login page will be built in Task 2.7.</p>
      </div>
    );
  }

  // 3. Authenticated but wrong role — show unauthorized
  if (requiredRole && profile?.role !== requiredRole) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-red-500">
          Unauthorized. This page requires the "{requiredRole}" role.
        </p>
      </div>
    );
  }

  // 4. All good — render the protected content
  return <>{children}</>;
}
```

---

## Step 8: Environment Variables

### File: `frontend/.env.local` (create this, DO NOT commit to Git)

```env
# Supabase — from Dashboard → Settings → API
VITE_SUPABASE_URL=https://your-project-id.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### File: `frontend/.env.example` (commit this as a template for other devs)

```env
# Supabase Configuration
# Get these from: Supabase Dashboard → Settings → API
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
```

### Update `.gitignore`

Make sure your `frontend/.gitignore` includes:

```
.env.local
.env.*.local
```

> **Important:** The `VITE_` prefix is required. Vite only exposes env vars with this prefix to client code. Never put the `service_role` key in frontend env vars — that's backend-only (Task 2.6).

---

## Step 9: FastAPI Auth Utility Stub

> This is a **placeholder** — just enough structure so you don't start from zero in Task 2.6. No implementation needed yet.

### File: `backend/app/core/auth.py`

```python
"""
FastAPI JWT Authentication Utilities (Stub)
============================================
Full implementation: Task 2.6

This module will:
1. Validate Supabase JWTs on incoming requests
2. Extract user_id from the token
3. Provide a dependency for protected endpoints
4. Use the Supabase JWT secret to verify signatures

Architecture:
  - All writes go through FastAPI using service_role key (bypasses RLS)
  - JWT validation confirms the caller is a legitimate authenticated user
  - User role/permissions checked against public.users table
"""

# TODO (Task 2.6): Implement the following
#
# from fastapi import Depends, HTTPException, status
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# import jwt  # PyJWT library
#
# SUPABASE_JWT_SECRET = settings.SUPABASE_JWT_SECRET  # from env
#
# async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
#     """
#     Dependency that validates the JWT and returns the user_id.
#
#     Usage:
#       @router.get("/vendors")
#       async def list_vendors(user_id: str = Depends(get_current_user)):
#           ...
#     """
#     token = credentials.credentials
#     payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
#     return payload["sub"]  # sub = user UUID
#
# async def require_admin(user_id: str = Depends(get_current_user)):
#     """
#     Dependency that requires the admin role.
#     Queries public.users to check role.
#     """
#     # Query public.users where id = user_id and role = 'admin'
#     pass
```

### File: `backend/app/core/__init__.py`

```python
# Core utilities package
```

---

## Step 10: Verification Checklist

Create a temporary `AuthDebug.tsx` component (see below) that mounts inside `AuthProvider` in `App.tsx`. This gives you an interactive test panel running inside your actual React app with real code paths.

### Temporary Test Component: `frontend/src/components/auth/AuthDebug.tsx`

> **Delete this file after verification is complete.**

Create a component with buttons for each test (Signup, Login, Logout, Isolated Query, Password Reset) that displays the current `AuthState` from `useAuth()` and shows success/error messages. Use `useRef` alongside `useState` for status messages — auth state changes trigger re-renders that can wipe `useState` before your success message displays.

### Verification Steps

1. Run `npm run dev` and open `http://localhost:5173`
2. **Test Signup** → Check Supabase Dashboard: Auth → Users (new user) + Table Editor → users (profile row created by `fn_handle_new_auth_user` trigger with correct `full_name` and `role`)
3. **Test Login** → Auth State should show `isAuthenticated: true` with full profile
4. **Refresh the page (F5)** → Auth State should still show `isAuthenticated: true` (session persistence from localStorage)
5. **Test Isolated Query** → Should return the user profile data directly (bypasses AuthContext, confirms RLS + query work)
6. **Test Logout** → Auth State resets to `isAuthenticated: false`, `profile: null`
7. **Test Password Reset** → Check Supabase Inbucket for the reset email (use a valid email domain like `.com`, not `.dev`)
8. **Clean up:** Delete test user from Supabase Dashboard (Auth → Users + Table Editor → users), delete `AuthDebug.tsx`, revert `App.tsx`

---

## File Tree Summary

After completing this task, your new/modified files:

```
bluonx-capstone-automation/
├── frontend/
│   ├── .env.local                          ← NEW (not committed)
│   ├── .env.example                        ← NEW (committed — template)
│   ├── .gitignore                          ← UPDATED (ensure .env.local excluded)
│   ├── src/
│   │   ├── App.tsx                         ← UPDATED (wrap with AuthProvider)
│   │   ├── lib/
│   │   │   └── supabase.ts                ← NEW (Supabase client singleton)
│   │   ├── types/
│   │   │   ├── database.types.ts          ← NEW (placeholder, generate later)
│   │   │   └── auth.types.ts              ← NEW (UserProfile, AuthState, etc.)
│   │   ├── contexts/
│   │   │   └── AuthContext.tsx             ← NEW (AuthProvider + useAuth hook)
│   │   ├── services/
│   │   │   └── auth.service.ts            ← NEW (signup, login, logout, etc.)
│   │   └── components/
│   │       └── auth/
│   │           └── ProtectedRoute.tsx     ← NEW (route guard shell)
│   └── package.json                        ← UPDATED (@supabase/supabase-js added)
├── backend/
│   └── app/
│       └── core/
│           ├── __init__.py                ← NEW (empty package init)
│           └── auth.py                    ← NEW (JWT validation stub)
└── docs/
    └── TASK_1_7_AUTH_FRAMEWORK.md         ← This guide
```

---

## How This Connects to Future Tasks

| Future Task | What It Uses from 1.7 |
|---|---|
| **2.2 — Routing** | `ProtectedRoute` wraps authenticated routes. Replace placeholder redirects with `<Navigate>`. |
| **2.3 — Supabase Client State** | `supabase.ts` client is already initialized. Add Realtime subscriptions here. |
| **2.4 — React Query** | `getAccessToken()` from auth.service provides the JWT for API calls to FastAPI. |
| **2.5 — UI Components** | Replace the loading/error placeholders in `ProtectedRoute` with real components. |
| **2.6 — FastAPI Backend** | Implement `backend/app/core/auth.py` stub with real JWT validation. Use `SUPABASE_JWT_SECRET` from env. |
| **2.7 — Auth System UI** | Build login, signup, password reset pages that call `auth.service` functions. Handle `PASSWORD_RECOVERY` event. |
| **2.8 — Dashboard Layout** | Use `useAuth()` to show user name, role, logout button in the header/sidebar. |

---

## Important Notes

### On the `fn_handle_new_auth_user` Trigger

Your schema already handles the critical "auth → profile" bridge:

```sql
-- From bluonx_complete_schema_v2_2.sql (Section 6.6)
CREATE OR REPLACE FUNCTION fn_handle_new_auth_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, email, full_name, role)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data ->> 'full_name', split_part(NEW.email, '@', 1)),
    COALESCE(NEW.raw_user_meta_data ->> 'role', 'project_manager')
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

This means:
- The `signUp()` function in auth.service passes `full_name` and `role` via `options.data`
- Supabase stores them in `auth.users.raw_user_meta_data`
- The trigger reads them and inserts into `public.users`
- If `full_name` is missing, it falls back to the email prefix
- If `role` is missing, it defaults to `project_manager`

**This is already deployed in your schema — no additional work needed.**

### On Token Refresh

Supabase handles this automatically:
- JWT expires after 1 hour (configurable in dashboard)
- `autoRefreshToken: true` in the client config makes Supabase refresh ~60 seconds before expiry
- `onAuthStateChange` fires with `TOKEN_REFRESHED` event
- Your AuthContext re-fetches the profile (in case role/status changed)
- **You write zero refresh logic yourself**

### On the `onAuthStateChange` Callback Pattern

**The callback must be synchronous (not `async`).** This was discovered during implementation — using `async/await` inside `onAuthStateChange` blocks Supabase's internal event listener, which can prevent subsequent auth events from being processed and cause the UI to hang permanently on `isLoading: true`.

The correct pattern is fire-and-forget with `.finally()`:

```tsx
// ✅ CORRECT — synchronous callback, fire-and-forget fetch
supabase.auth.onAuthStateChange((event, newSession) => {
  if (event === 'SIGNED_IN' && newSession?.user) {
    fetchProfile(newSession.user.id).finally(() => setIsLoading(false));
  }
});

// ❌ WRONG — async callback blocks the listener
supabase.auth.onAuthStateChange(async (event, newSession) => {
  if (event === 'SIGNED_IN' && newSession?.user) {
    await fetchProfile(newSession.user.id); // This hangs the listener
  }
});
```

### On the AbortController Timeout

The `fetchProfile` function includes a 10-second `AbortController` timeout as a safety net. If the Supabase query hangs (due to RLS policy evaluation stalling, network issues, or SDK type inference problems with placeholder `database.types.ts`), the abort fires, the `catch` block handles it gracefully, and `isLoading` always resolves. This prevents the UI from being stuck in a permanent loading state.

### On Security

- The `anon` key in the frontend is **public** — it's designed to be exposed. RLS policies (Task 1.4) protect your data.
- The `service_role` key is **secret** — it goes in the backend only (Task 2.6).
- All writes go through FastAPI with `service_role` — the frontend only reads via the anon key + RLS.
- The `private.is_active_user()` and `private.is_admin()` RLS helpers (from your rls_policies.sql) work seamlessly with the JWT that Supabase sets on authenticated requests.
