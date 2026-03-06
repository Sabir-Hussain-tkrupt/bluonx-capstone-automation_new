import { useState } from 'react';
import { Link } from 'react-router-dom';
import { requestPasswordReset } from '@/services/auth.service';
import { Button, TextInput, FormField, Alert } from '@/components/ui';
import { ROUTES } from '@/constants/routes';

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  function validate(): boolean {
    const newErrors: Record<string, string> = {};

    if (!email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!EMAIL_REGEX.test(email.trim())) {
      newErrors.email = 'Enter a valid email address';
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
      await requestPasswordReset(email.trim());
      setIsSuccess(true);
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
    <div>
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-semibold text-gray-900">Reset your password</h1>
        <p className="mt-2 text-sm text-gray-500">
          Enter your email and we&apos;ll send you a reset link
        </p>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        {isSuccess ? (
          <div>
            <Alert variant="success" title="Check your email">
              If an account exists with that email address, you&apos;ll receive a password
              reset link shortly. Please check your inbox and spam folder.
            </Alert>
            <div className="mt-6 text-center">
              <Link
                to={ROUTES.LOGIN}
                className="text-sm font-medium text-primary-600 hover:text-primary-500"
              >
                Back to sign in
              </Link>
            </div>
          </div>
        ) : (
          <>
            {serverError && (
              <div className="mb-4">
                <Alert variant="danger">{serverError}</Alert>
              </div>
            )}

            <form onSubmit={handleSubmit} noValidate>
              <div className="space-y-4">
                <FormField label="Email" htmlFor="reset-email" required error={errors.email}>
                  <TextInput
                    id="reset-email"
                    type="email"
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      clearFieldError('email');
                    }}
                    error={!!errors.email}
                    placeholder="you@company.com"
                    disabled={isSubmitting}
                    autoComplete="email"
                    autoFocus
                  />
                </FormField>

                <Button type="submit" fullWidth isLoading={isSubmitting}>
                  Send reset link
                </Button>

                <div className="text-center">
                  <Link
                    to={ROUTES.LOGIN}
                    className="text-sm font-medium text-primary-600 hover:text-primary-500"
                  >
                    Back to sign in
                  </Link>
                </div>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
