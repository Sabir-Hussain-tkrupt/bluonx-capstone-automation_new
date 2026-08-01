import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { ResetPasswordPage } from '../ResetPasswordPage';

vi.mock('@/services/auth.service', () => ({
  updatePassword: vi.fn(),
}));

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

// The page now gates on the recovery session from AuthContext.
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

import { updatePassword } from '@/services/auth.service';
const mockUpdatePassword = vi.mocked(updatePassword);

describe('ResetPasswordPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: a live recovery session is present, so the form renders.
    mockUseAuth.mockReturnValue({ session: { access_token: 't' }, isLoading: false });
  });

  it('renders the reset password form', () => {
    renderWithRouter(<ResetPasswordPage />);

    expect(screen.getByText('Set new password')).toBeInTheDocument();
    expect(screen.getByLabelText(/new password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /update password/i })).toBeInTheDocument();
  });

  it('shows hint about minimum 8 characters', () => {
    renderWithRouter(<ResetPasswordPage />);

    expect(screen.getByText(/minimum 8 characters/i)).toBeInTheDocument();
  });

  it('shows validation errors when submitting empty form', async () => {
    const user = userEvent.setup();
    renderWithRouter(<ResetPasswordPage />);

    await user.click(screen.getByRole('button', { name: /update password/i }));

    expect(screen.getByText('Password is required')).toBeInTheDocument();
    expect(screen.getByText('Please confirm your password')).toBeInTheDocument();
    expect(mockUpdatePassword).not.toHaveBeenCalled();
  });

  it('shows error when password is too short', async () => {
    const user = userEvent.setup();
    renderWithRouter(<ResetPasswordPage />);

    await user.type(screen.getByLabelText(/new password/i), 'short');
    await user.type(screen.getByLabelText(/confirm password/i), 'short');
    await user.click(screen.getByRole('button', { name: /update password/i }));

    expect(screen.getByText('Password must be at least 8 characters')).toBeInTheDocument();
    expect(mockUpdatePassword).not.toHaveBeenCalled();
  });

  it('shows error when passwords do not match', async () => {
    const user = userEvent.setup();
    renderWithRouter(<ResetPasswordPage />);

    await user.type(screen.getByLabelText(/new password/i), 'NewPassword123!');
    await user.type(screen.getByLabelText(/confirm password/i), 'DifferentPassword');
    await user.click(screen.getByRole('button', { name: /update password/i }));

    expect(screen.getByText('Passwords do not match')).toBeInTheDocument();
    expect(mockUpdatePassword).not.toHaveBeenCalled();
  });

  it('calls updatePassword and navigates to login on success', async () => {
    mockUpdatePassword.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    renderWithRouter(<ResetPasswordPage />);

    await user.type(screen.getByLabelText(/new password/i), 'NewPassword123!');
    await user.type(screen.getByLabelText(/confirm password/i), 'NewPassword123!');
    await user.click(screen.getByRole('button', { name: /update password/i }));

    await waitFor(() => {
      expect(mockUpdatePassword).toHaveBeenCalledWith('NewPassword123!');
    });

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/login', { replace: true });
    });
  });

  it('displays server error on failure', async () => {
    mockUpdatePassword.mockRejectedValueOnce(new Error('Session expired'));
    const user = userEvent.setup();
    renderWithRouter(<ResetPasswordPage />);

    await user.type(screen.getByLabelText(/new password/i), 'NewPassword123!');
    await user.type(screen.getByLabelText(/confirm password/i), 'NewPassword123!');
    await user.click(screen.getByRole('button', { name: /update password/i }));

    await waitFor(() => {
      expect(screen.getByText('Session expired')).toBeInTheDocument();
    });
  });

  it('maps "Auth session missing!" to actionable guidance', async () => {
    mockUpdatePassword.mockRejectedValueOnce(new Error('Auth session missing!'));
    const user = userEvent.setup();
    renderWithRouter(<ResetPasswordPage />);

    await user.type(screen.getByLabelText(/new password/i), 'NewPassword123!');
    await user.type(screen.getByLabelText(/confirm password/i), 'NewPassword123!');
    await user.click(screen.getByRole('button', { name: /update password/i }));

    await waitFor(() => {
      expect(screen.getByText(/reset link is invalid or has expired/i)).toBeInTheDocument();
    });
    // The raw Supabase message is never shown to the user.
    expect(screen.queryByText('Auth session missing!')).not.toBeInTheDocument();
  });

  it('shows an invalid-link state (not the form) when there is no recovery session', () => {
    mockUseAuth.mockReturnValue({ session: null, isLoading: false });
    renderWithRouter(<ResetPasswordPage />);

    expect(screen.getByText(/reset link invalid or expired/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/new password/i)).not.toBeInTheDocument();
  });

  it('shows a loading state while the recovery session resolves', () => {
    mockUseAuth.mockReturnValue({ session: null, isLoading: true });
    renderWithRouter(<ResetPasswordPage />);

    expect(screen.getByText(/verifying your reset link/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/new password/i)).not.toBeInTheDocument();
  });
});
