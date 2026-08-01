import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { updatePassword } from '@/services/auth.service';
import { useToast } from '@/components/ui';
import { SetPasswordForm } from '@/components/auth/SetPasswordForm';
import { ROUTES } from '@/constants/routes';

/**
 * Password-reset landing page (bare route). The recovery email link lands here
 * and Supabase establishes a session from the URL asynchronously.
 *
 * We gate on that session (via AuthContext) before allowing submit. Without the
 * gate, submitting before the async URL->session exchange finishes calls
 * updateUser with no session and fails with "Auth session missing!". Gating also
 * gives us a clear "link invalid/expired" state for the cases where no session
 * ever forms (one-time token consumed by an email scanner, or an expired link),
 * instead of a cryptic error. Gate on `session` (not `isAuthenticated`): a
 * PASSWORD_RECOVERY session has no public.users profile loaded.
 *
 * Security: this only makes submission stricter. updateUser still requires a
 * server-verified session; nothing here bypasses or weakens a check.
 */
const SESSION_MISSING_MESSAGE =
  'Your reset link is invalid or has expired. Please request a new password reset.';

export function ResetPasswordPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { session, isLoading } = useAuth();

  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(password: string) {
    setServerError(null);
    try {
      setIsSubmitting(true);
      await updatePassword(password);
      toast({
        variant: 'success',
        title: 'Password updated',
        message: 'Your password has been reset successfully. Please sign in with your new password.',
      });
      navigate(ROUTES.LOGIN, { replace: true });
    } catch (err) {
      const raw = err instanceof Error ? err.message : 'An unexpected error occurred';
      // Map the cryptic "Auth session missing!" (session expired between load and
      // submit) to actionable guidance; surface any other error as-is.
      setServerError(/session missing/i.test(raw) ? SESSION_MISSING_MESSAGE : raw);
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

  // Still resolving the recovery session from the URL — don't flash the form or
  // the invalid state before we know whether a session materialized.
  if (isLoading) {
    return shell(
      <div className="text-center">
        <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-4 border-primary-200 border-t-primary-600" />
        <p className="text-sm text-gray-500">Verifying your reset link...</p>
      </div>,
    );
  }

  // No recovery session — the link was never valid here, was already consumed, or
  // has expired. Send the user back to request a fresh one instead of erroring.
  if (!session) {
    return shell(
      <div className="rounded-lg border border-gray-200 bg-white p-6 text-center shadow-sm">
        <h2 className="text-xl font-semibold text-gray-900">Reset link invalid or expired</h2>
        <p className="mt-2 text-sm text-gray-500">
          This password reset link is no longer valid. Request a new one to continue.
        </p>
        <Link
          to={ROUTES.FORGOT_PASSWORD}
          className="mt-6 inline-block text-sm font-medium text-primary-600 hover:text-primary-700"
        >
          Request a new reset link
        </Link>
      </div>,
    );
  }

  return shell(
    <>
      <div className="mb-8 text-center">
        <h2 className="text-2xl font-semibold text-gray-900">Set new password</h2>
        <p className="mt-2 text-sm text-gray-500">
          Choose a strong password with at least 8 characters
        </p>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <SetPasswordForm
          onSubmit={handleSubmit}
          isSubmitting={isSubmitting}
          submitLabel="Update password"
          serverError={serverError}
        />
      </div>
    </>,
  );
}
