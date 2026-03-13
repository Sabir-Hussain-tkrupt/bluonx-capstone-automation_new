import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { updatePassword } from '@/services/auth.service';
import { Button, TextInput, FormField, Alert, useToast } from '@/components/ui';
import { ROUTES } from '@/constants/routes';

export function ResetPasswordPage() {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function validate(): boolean {
    const newErrors: Record<string, string> = {};

    if (!password) {
      newErrors.password = 'Password is required';
    } else if (password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters';
    }

    if (!confirmPassword) {
      newErrors.confirmPassword = 'Please confirm your password';
    } else if (password && confirmPassword !== password) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setServerError(null);

    if (!validate()) return;

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

  function clearFieldError(field: string) {
    if (errors[field]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
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
          {serverError && (
            <div className="mb-4">
              <Alert variant="danger">{serverError}</Alert>
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate>
            <div className="space-y-4">
              <FormField
                label="New password"
                htmlFor="new-password"
                required
                error={errors.password}
                hint="Minimum 8 characters"
              >
                <TextInput
                  id="new-password"
                  type="password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    clearFieldError('password');
                  }}
                  error={!!errors.password}
                  placeholder="Enter new password"
                  disabled={isSubmitting}
                  autoComplete="new-password"
                  autoFocus
                />
              </FormField>

              <FormField
                label="Confirm password"
                htmlFor="confirm-password"
                required
                error={errors.confirmPassword}
              >
                <TextInput
                  id="confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => {
                    setConfirmPassword(e.target.value);
                    clearFieldError('confirmPassword');
                  }}
                  error={!!errors.confirmPassword}
                  placeholder="Confirm new password"
                  disabled={isSubmitting}
                  autoComplete="new-password"
                />
              </FormField>

              <Button type="submit" fullWidth isLoading={isSubmitting}>
                Update password
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
