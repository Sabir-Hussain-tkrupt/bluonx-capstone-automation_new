import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { updatePassword } from '@/services/auth.service';
import { useToast } from '@/components/ui';
import { SetPasswordForm } from '@/components/auth/SetPasswordForm';
import { ROUTES } from '@/constants/routes';

/**
 * Accept-invite / set-password page (bare route — see routes/index.tsx, C2).
 *
 * The invited user arrives already authenticated but passwordless: clicking the
 * invite link consumes the token at Supabase's /auth/v1/verify, which creates a
 * live session, and the Part 2 trigger already created the public.users row. So
 * we read the LIVE session and call updatePassword on it, then route into the app.
 *
 * Already-onboarded: the Supabase client session exposes no reliable "has a
 * password" signal, so we take the idempotent path (setting a password again is
 * harmless) and show the form whenever a session exists. A dedicated
 * already-onboarded state is deferred (see docs/DEFERRED.md).
 */
export function AcceptInvitePage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { session, profile, isLoading } = useAuth();

  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(password: string) {
    setServerError(null);
    try {
      setIsSubmitting(true);
      await updatePassword(password);
      toast({
        variant: 'success',
        title: 'Welcome to BluOnX',
        message: 'Your password is set. You are all set to go.',
      });
      navigate(ROUTES.DASHBOARD, { replace: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An unexpected error occurred';
      setServerError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  const shell = (children: React.ReactNode) => (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-md p-6">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-primary-700">BluOnX</h1>
          <p className="text-xs text-gray-400">Development Operations Platform</p>
        </div>
        {children}
      </div>
    </div>
  );

  // Still resolving the session — avoid flashing the "invalid link" state.
  if (isLoading) {
    return shell(
      <div className="text-center">
        <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-4 border-primary-200 border-t-primary-600" />
        <p className="text-sm text-gray-500">Loading your invite...</p>
      </div>,
    );
  }

  // No live session — the invite token was never consumed, or the link expired.
  if (!session) {
    return shell(
      <div className="rounded-lg border border-gray-200 bg-white p-6 text-center shadow-sm">
        <h2 className="text-xl font-semibold text-gray-900">Invite link invalid or expired</h2>
        <p className="mt-2 text-sm text-gray-500">
          This invitation link is no longer valid. Ask an administrator to resend your invite.
        </p>
        <Link
          to={ROUTES.LOGIN}
          className="mt-6 inline-block text-sm font-medium text-primary-600 hover:text-primary-700"
        >
          Go to sign in
        </Link>
      </div>,
    );
  }

  return shell(
    <>
      <div className="mb-8 text-center">
        <h2 className="text-2xl font-semibold text-gray-900">Set your password</h2>
        <p className="mt-2 text-sm text-gray-500">
          {profile?.full_name ? `Welcome, ${profile.full_name}. ` : ''}
          Choose a password to finish setting up your account.
        </p>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <SetPasswordForm
          onSubmit={handleSubmit}
          isSubmitting={isSubmitting}
          submitLabel="Set password and continue"
          serverError={serverError}
        />
      </div>
    </>,
  );
}
