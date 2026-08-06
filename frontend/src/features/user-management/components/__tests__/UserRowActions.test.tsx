import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { UserRowActions } from '../UserRowActions';
import type { UserAdminResponse } from '../../types';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import { api } from '@/lib/api';
import { makeApiError } from '@/test/api-error';
const mockPatch = vi.mocked(api.patch);
const mockPost = vi.mocked(api.post);
const mockDelete = vi.mocked(api.delete);

const ADMIN_ID = 'admin-1';

function user(overrides: Partial<UserAdminResponse> = {}): UserAdminResponse {
  return {
    id: 'u-1',
    email: 'person@bluonx.dev',
    full_name: 'Person One',
    role: 'project_manager',
    is_active: true,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    deleted_at: null,
    invited_by: ADMIN_ID,
    status: 'active',
    ...overrides,
  };
}

function render(u: UserAdminResponse, currentUserId = 'someone-else') {
  return renderWithRouter(<UserRowActions user={u} currentUserId={currentUserId} />);
}

async function openMenu(ue: ReturnType<typeof userEvent.setup>, name: string) {
  await ue.click(screen.getByRole('button', { name: new RegExp(`actions for ${name}`, 'i') }));
}

describe('UserRowActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPatch.mockResolvedValue({ data: {} });
    mockPost.mockResolvedValue({ data: {} });
    mockDelete.mockResolvedValue({ data: {} });
  });

  it('change role PATCHes the new role', async () => {
    const ue = userEvent.setup();
    render(user());
    await openMenu(ue, 'Person One');
    await ue.click(screen.getByRole('menuitem', { name: /change role to admin/i }));

    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith('/users/u-1', { role: 'admin' }),
    );
  });

  it('deactivate PATCHes is_active:false after confirming', async () => {
    const ue = userEvent.setup();
    render(user());
    await openMenu(ue, 'Person One');
    await ue.click(screen.getByRole('menuitem', { name: /deactivate/i }));
    await ue.click(screen.getByRole('button', { name: 'Deactivate' }));

    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith('/users/u-1', { is_active: false }),
    );
  });

  it('reactivate PATCHes is_active:true for a deactivated (non-deleted) user', async () => {
    const ue = userEvent.setup();
    render(user({ is_active: false, status: 'deactivated' }));
    await openMenu(ue, 'Person One');
    await ue.click(screen.getByRole('menuitem', { name: /reactivate/i }));

    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith('/users/u-1', { is_active: true }),
    );
  });

  it('resend invite POSTs for a pending user', async () => {
    const ue = userEvent.setup();
    render(user({ status: 'pending' }));
    await openMenu(ue, 'Person One');
    await ue.click(screen.getByRole('menuitem', { name: /resend invite/i }));

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/users/u-1/resend-invite'),
    );
  });

  it('soft-delete DELETEs after confirming', async () => {
    const ue = userEvent.setup();
    render(user());
    await openMenu(ue, 'Person One');
    await ue.click(screen.getByRole('menuitem', { name: /delete user/i }));
    await ue.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/users/u-1'));
  });

  it('disables self-affecting actions on the current admin own row (G1 mirror)', async () => {
    const ue = userEvent.setup();
    const me = user({ id: ADMIN_ID, full_name: 'Ada Admin', role: 'admin' });
    render(me, ADMIN_ID);
    await openMenu(ue, 'Ada Admin');

    expect(screen.getByRole('menuitem', { name: /change role/i })).toBeDisabled();
    expect(screen.getByRole('menuitem', { name: /deactivate/i })).toBeDisabled();
    expect(screen.getByRole('menuitem', { name: /delete user/i })).toBeDisabled();
  });

  it('surfaces the server 409 detail when a guard rejects a mutation', async () => {
    mockPatch.mockRejectedValueOnce(
      makeApiError('Cannot remove the last active admin.', 409, 'CONFLICT'),
    );
    const ue = userEvent.setup();
    render(user({ role: 'admin', full_name: 'Other Admin' }));
    await openMenu(ue, 'Other Admin');
    await ue.click(screen.getByRole('menuitem', { name: /deactivate/i }));
    await ue.click(screen.getByRole('button', { name: 'Deactivate' }));

    expect(
      await screen.findByText('Cannot remove the last active admin.'),
    ).toBeInTheDocument();
  });
});
