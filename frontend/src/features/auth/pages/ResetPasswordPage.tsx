import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { updatePassword } from '@/services/auth.service';
import { useToast } from '@/components/ui';
import { SetPasswordForm } from '@/components/auth/SetPasswordForm';
import { ROUTES } from '@/constants/routes';

export function ResetPasswordPage() {
  const navigate = useNavigate();
  const { toast } = useToast();

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
      const message =
        err instanceof Error ? err.message : 'An unexpected error occurred';
      setServerError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-md p-6">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-primary-700">BluOnX</h1>
          <p className="text-xs text-gray-400">Development Operations Platform</p>
        </div>

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
      </div>
    </div>
  );
}
