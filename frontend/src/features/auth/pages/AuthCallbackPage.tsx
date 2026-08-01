import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/lib/supabase';
import { ROUTES } from '@/constants/routes';

/**
 * Handles Supabase auth redirects (email confirmation, password recovery).
 * Waits for Supabase to process the URL hash token before navigating.
 * Falls back to /login after 5 seconds if no auth event fires.
 */
export function AuthCallbackPage() {
  const navigate = useNavigate();

  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event) => {
      if (event === 'SIGNED_IN') {
        // Defense-in-depth: an invite verify emits SIGNED_IN. Invites normally
        // redirect straight to /accept-invite, but if one ever lands here, route
        // a passwordless invite session to set-password instead of the dashboard.
        const isInvite =
          window.location.hash.includes('type=invite') ||
          window.location.search.includes('type=invite');
        navigate(isInvite ? ROUTES.ACCEPT_INVITE : ROUTES.DASHBOARD, { replace: true });
      } else if (event === 'PASSWORD_RECOVERY') {
        navigate(ROUTES.AUTH_RESET_PASSWORD, { replace: true });
      }
    });

    // Fallback: if no auth event fires within 5s, redirect to login
    const timeout = setTimeout(() => {
      navigate(ROUTES.LOGIN, { replace: true });
    }, 5000);

    return () => {
      subscription.unsubscribe();
      clearTimeout(timeout);
    };
  }, [navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="text-center">
        <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-4 border-primary-200 border-t-primary-600" />
        <p className="text-sm text-gray-500">Processing authentication...</p>
      </div>
    </div>
  );
}
