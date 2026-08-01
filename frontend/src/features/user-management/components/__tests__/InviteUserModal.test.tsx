import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { InviteUserModal } from '../InviteUserModal';

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  errorMessage: (err: { message?: string } | undefined, fallback: string) =>
    err?.message ?? fallback,
}));

import { api } from '@/lib/api';
const mockPost = vi.mocked(api.post);

describe('InviteUserModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  async function fillAndSubmit(
    user: ReturnType<typeof userEvent.setup>,
    { email, name }: { email: string; name: string },
  ) {
    await user.type(screen.getByLabelText(/full name/i), name);
    await user.type(screen.getByLabelText(/email/i), email);
    await user.click(screen.getByRole('button', { name: /send invite/i }));
  }

  it('posts email, full_name and role on valid submit', async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 'u-9', email: 'new@bluonx.dev' } });
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderWithRouter(<InviteUserModal isOpen onClose={onClose} />);

    await fillAndSubmit(user, { email: 'new@bluonx.dev', name: 'New Person' });

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/users/invite', {
        email: 'new@bluonx.dev',
        full_name: 'New Person',
        role: 'project_manager',
      });
    });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('blocks an invalid email client-side and never calls the API', async () => {
    const user = userEvent.setup();
    renderWithRouter(<InviteUserModal isOpen onClose={vi.fn()} />);

    await fillAndSubmit(user, { email: 'not-an-email', name: 'Bad Email' });

    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('surfaces the server 409 detail and keeps the modal open', async () => {
    mockPost.mockRejectedValueOnce({ message: 'A user with this email already exists.' });
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderWithRouter(<InviteUserModal isOpen onClose={onClose} />);

    await fillAndSubmit(user, { email: 'dupe@bluonx.dev', name: 'Dupe Person' });

    expect(
      await screen.findByText('A user with this email already exists.'),
    ).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
