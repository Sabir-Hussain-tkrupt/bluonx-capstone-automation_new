import { useState } from 'react';
import { Link } from 'react-router-dom';
import { signIn } from '@/services/auth.service';
import { Button, TextInput, FormField, Alert } from '@/components/ui';
import { ROUTES } from '@/constants/routes';

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function validate(): boolean {
    const newErrors: Record<string, string> = {};

    if (!email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!EMAIL_REGEX.test(email.trim())) {
      newErrors.email = 'Enter a valid email address';
    }

    if (!password) {
      newErrors.password = 'Password is required';
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
      await signIn({ email: email.trim(), password });
      // AuthContext picks up the session → PublicRoute redirects to dashboard
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
        <h1 className="text-2xl font-semibold text-gray-900">Sign in to your account</h1>
        <p className="mt-2 text-sm text-gray-500">
          Enter your credentials to access the platform
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
            <FormField label="Email" htmlFor="login-email" required error={errors.email}>
              <TextInput
                id="login-email"
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

            <FormField label="Password" htmlFor="login-password" required error={errors.password}>
              <TextInput
                id="login-password"
                type="password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  clearFieldError('password');
                }}
                error={!!errors.password}
                placeholder="Enter your password"
                disabled={isSubmitting}
                autoComplete="current-password"
              />
            </FormField>

            <div className="flex justify-end">
              <Link
                to={ROUTES.FORGOT_PASSWORD}
                className="text-sm font-medium text-primary-600 hover:text-primary-500"
              >
                Forgot password?
              </Link>
            </div>

            <Button type="submit" fullWidth isLoading={isSubmitting}>
              Sign in
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
