import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { AuthCallbackPage } from '../AuthCallbackPage';

// Mock Supabase client
const mockOnAuthStateChange = vi.fn(() => ({
  data: { subscription: { unsubscribe: vi.fn() } },
}));

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      onAuthStateChange: (...args: unknown[]) => mockOnAuthStateChange(...args),
    },
  },
}));

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

describe('AuthCallbackPage', () => {
  it('renders loading spinner and processing text', () => {
    renderWithRouter(<AuthCallbackPage />);

    expect(screen.getByText('Processing authentication...')).toBeInTheDocument();
  });

  it('subscribes to auth state changes on mount', () => {
    renderWithRouter(<AuthCallbackPage />);

    expect(mockOnAuthStateChange).toHaveBeenCalled();
  });

  it('navigates to dashboard on SIGNED_IN event', () => {
    renderWithRouter(<AuthCallbackPage />);

    // Get the callback that was passed to onAuthStateChange
    const callback = mockOnAuthStateChange.mock.calls[0]?.[0] as (event: string) => void;
    expect(callback).toBeDefined();

    callback('SIGNED_IN');

    expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true });
  });

  it('navigates to reset-password on PASSWORD_RECOVERY event', () => {
    mockOnAuthStateChange.mockClear();
    mockNavigate.mockClear();

    renderWithRouter(<AuthCallbackPage />);

    const callback = mockOnAuthStateChange.mock.calls[0]?.[0] as (event: string) => void;
    callback('PASSWORD_RECOVERY');

    expect(mockNavigate).toHaveBeenCalledWith('/auth/reset-password', { replace: true });
  });
});
