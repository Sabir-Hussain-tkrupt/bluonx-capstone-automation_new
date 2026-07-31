import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { AcceptInvitePage } from '../AcceptInvitePage';

vi.mock('@/services/auth.service', () => ({
  updatePassword: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

import { updatePassword } from '@/services/auth.service';
const mockUpdatePassword = vi.mocked(updatePassword);

const liveSession = {
  session: { access_token: 't' },
  profile: { id: 'u-1', full_name: 'New Person' },
  isLoading: false,
};

describe('AcceptInvitePage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sets the password on the live session and routes into the app', async () => {
    mockUseAuth.mockReturnValue(liveSession);
    mockUpdatePassword.mockResolvedValueOnce(undefined);
    const ue = userEvent.setup();
    renderWithRouter(<AcceptInvitePage />);

    await ue.type(screen.getByLabelText(/new password/i), 'NewPassword123!');
    await ue.type(screen.getByLabelText(/confirm password/i), 'NewPassword123!');
    await ue.click(screen.getByRole('button', { name: /set password/i }));

    await waitFor(() => expect(mockUpdatePassword).toHaveBeenCalledWith('NewPassword123!'));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true }));
  });

  it('blocks a too-short password before calling updatePassword', async () => {
    mockUseAuth.mockReturnValue(liveSession);
    const ue = userEvent.setup();
    renderWithRouter(<AcceptInvitePage />);

    await ue.type(screen.getByLabelText(/new password/i), 'short');
    await ue.type(screen.getByLabelText(/confirm password/i), 'short');
    await ue.click(screen.getByRole('button', { name: /set password/i }));

    expect(screen.getByText('Password must be at least 8 characters')).toBeInTheDocument();
    expect(mockUpdatePassword).not.toHaveBeenCalled();
  });

  it('shows an invalid-link state (not the form) when there is no session', () => {
    mockUseAuth.mockReturnValue({ session: null, profile: null, isLoading: false });
    renderWithRouter(<AcceptInvitePage />);

    expect(screen.getByText(/invite link invalid or expired/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/new password/i)).not.toBeInTheDocument();
  });

  it('shows a loading state while the session resolves', () => {
    mockUseAuth.mockReturnValue({ session: null, profile: null, isLoading: true });
    renderWithRouter(<AcceptInvitePage />);

    expect(screen.getByText(/loading your invite/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/new password/i)).not.toBeInTheDocument();
  });
});
