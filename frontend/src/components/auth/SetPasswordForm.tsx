import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { Button, TextInput, FormField, Alert } from '@/components/ui';

interface SetPasswordFormProps {
  /** Called with the validated password when the form is submitted. */
  onSubmit: (password: string) => void;
  /** True while the parent's async submit is in flight. */
  isSubmitting: boolean;
  /** Submit button label (e.g. "Update password" / "Set password and continue"). */
  submitLabel: string;
  /** Server-side error to show above the fields (e.g. an expired session). */
  serverError?: string | null;
}

/**
 * Shared password-setting form: two inputs + min-8 / match validation.
 *
 * Extracted from ResetPasswordPage so the password-reset and accept-invite flows
 * share ONE implementation. The parent owns the async call (updatePassword),
 * navigation, and any server error text; this component owns field validation.
 */
export function SetPasswordForm({
  onSubmit,
  isSubmitting,
  submitLabel,
  serverError,
}: SetPasswordFormProps) {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

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

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    onSubmit(password);
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
    <>
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
              type={showPassword ? 'text' : 'password'}
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
              rightAddon={
                <button
                  type="button"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  onClick={() => setShowPassword((visible) => !visible)}
                  className="flex items-center"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              }
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
              type={showConfirmPassword ? 'text' : 'password'}
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(e.target.value);
                clearFieldError('confirmPassword');
              }}
              error={!!errors.confirmPassword}
              placeholder="Confirm new password"
              disabled={isSubmitting}
              autoComplete="new-password"
              rightAddon={
                <button
                  type="button"
                  aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
                  onClick={() => setShowConfirmPassword((visible) => !visible)}
                  className="flex items-center"
                >
                  {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              }
            />
          </FormField>

          <Button type="submit" fullWidth isLoading={isSubmitting}>
            {submitLabel}
          </Button>
        </div>
      </form>
    </>
  );
}
