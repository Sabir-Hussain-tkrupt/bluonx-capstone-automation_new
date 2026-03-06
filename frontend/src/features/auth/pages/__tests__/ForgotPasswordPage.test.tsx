import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { ForgotPasswordPage } from '../ForgotPasswordPage';

vi.mock('@/services/auth.service', () => ({
  requestPasswordReset: vi.fn(),
}));

import { requestPasswordReset } from '@/services/auth.service';
const mockReset = vi.mocked(requestPasswordReset);

describe('ForgotPasswordPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the forgot password form', () => {
    renderWithRouter(<ForgotPasswordPage />);

    expect(screen.getByText('Reset your password')).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send reset link/i })).toBeInTheDocument();
  });

  it('renders back to sign in link', () => {
    renderWithRouter(<ForgotPasswordPage />);

    const link = screen.getByText(/back to sign in/i);
    expect(link).toBeInTheDocument();
    expect(link.closest('a')).toHaveAttribute('href', '/login');
  });

  it('shows validation error when submitting empty email', async () => {
    const user = userEvent.setup();
    renderWithRouter(<ForgotPasswordPage />);

    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    expect(screen.getByText('Email is required')).toBeInTheDocument();
    expect(mockReset).not.toHaveBeenCalled();
  });

  it('shows validation error for invalid email format', async () => {
    const user = userEvent.setup();
    renderWithRouter(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText(/email/i), 'bad-email');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    expect(screen.getByText('Enter a valid email address')).toBeInTheDocument();
    expect(mockReset).not.toHaveBeenCalled();
  });

  it('calls requestPasswordReset and shows success message', async () => {
    mockReset.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    renderWithRouter(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText(/email/i), 'admin@bluonx.dev');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(mockReset).toHaveBeenCalledWith('admin@bluonx.dev');
    });

    // Success message replaces the form
    expect(screen.getByText('Check your email')).toBeInTheDocument();
    expect(screen.getByText(/password reset link/i)).toBeInTheDocument();

    // Form should no longer be visible
    expect(screen.queryByRole('button', { name: /send reset link/i })).not.toBeInTheDocument();
  });

  it('displays server error on failure', async () => {
    mockReset.mockRejectedValueOnce(new Error('Rate limit exceeded'));
    const user = userEvent.setup();
    renderWithRouter(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText(/email/i), 'admin@bluonx.dev');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByText('Rate limit exceeded')).toBeInTheDocument();
    });
  });
});
