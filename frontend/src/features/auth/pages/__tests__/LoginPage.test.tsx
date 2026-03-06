import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { LoginPage } from '../LoginPage';

// Mock auth service
vi.mock('@/services/auth.service', () => ({
  signIn: vi.fn(),
}));

import { signIn } from '@/services/auth.service';
const mockSignIn = vi.mocked(signIn);

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the login form with email and password fields', () => {
    renderWithRouter(<LoginPage />);

    expect(screen.getByText('Sign in to your account')).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('renders forgot password link', () => {
    renderWithRouter(<LoginPage />);

    const link = screen.getByText(/forgot password/i);
    expect(link).toBeInTheDocument();
    expect(link.closest('a')).toHaveAttribute('href', '/forgot-password');
  });

  it('shows validation errors when submitting empty form', async () => {
    const user = userEvent.setup();
    renderWithRouter(<LoginPage />);

    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(screen.getByText('Email is required')).toBeInTheDocument();
    expect(screen.getByText('Password is required')).toBeInTheDocument();
    expect(mockSignIn).not.toHaveBeenCalled();
  });

  it('shows validation error for invalid email format', async () => {
    const user = userEvent.setup();
    renderWithRouter(<LoginPage />);

    await user.type(screen.getByLabelText(/email/i), 'not-an-email');
    await user.type(screen.getByLabelText(/password/i), 'somepassword');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(screen.getByText('Enter a valid email address')).toBeInTheDocument();
    expect(mockSignIn).not.toHaveBeenCalled();
  });

  it('clears field error when user starts typing', async () => {
    const user = userEvent.setup();
    renderWithRouter(<LoginPage />);

    // Submit empty to trigger errors
    await user.click(screen.getByRole('button', { name: /sign in/i }));
    expect(screen.getByText('Email is required')).toBeInTheDocument();

    // Start typing in email field — error should clear
    await user.type(screen.getByLabelText(/email/i), 'a');
    expect(screen.queryByText('Email is required')).not.toBeInTheDocument();
  });

  it('calls signIn with correct credentials on valid submission', async () => {
    mockSignIn.mockResolvedValueOnce({} as never);
    const user = userEvent.setup();
    renderWithRouter(<LoginPage />);

    await user.type(screen.getByLabelText(/email/i), 'admin@bluonx.dev');
    await user.type(screen.getByLabelText(/password/i), 'TestPassword123!');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(mockSignIn).toHaveBeenCalledWith({
        email: 'admin@bluonx.dev',
        password: 'TestPassword123!',
      });
    });
  });

  it('displays server error from Supabase on failed login', async () => {
    mockSignIn.mockRejectedValueOnce(new Error('Invalid login credentials'));
    const user = userEvent.setup();
    renderWithRouter(<LoginPage />);

    await user.type(screen.getByLabelText(/email/i), 'wrong@email.com');
    await user.type(screen.getByLabelText(/password/i), 'wrongpassword');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText('Invalid login credentials')).toBeInTheDocument();
    });
  });

  it('disables form fields during submission', async () => {
    // signIn that never resolves to keep loading state
    mockSignIn.mockImplementation(() => new Promise(() => {}));
    const user = userEvent.setup();
    renderWithRouter(<LoginPage />);

    await user.type(screen.getByLabelText(/email/i), 'admin@bluonx.dev');
    await user.type(screen.getByLabelText(/password/i), 'TestPassword123!');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/email/i)).toBeDisabled();
      expect(screen.getByLabelText(/password/i)).toBeDisabled();
    });
  });
});
