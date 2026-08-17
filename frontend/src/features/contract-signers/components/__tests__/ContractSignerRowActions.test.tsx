import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { ContractSignerRowActions } from '../ContractSignerRowActions';
import { signer } from './fixtures';
import type { ContractSigner } from '../../types';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import { api } from '@/lib/api';
import { makeApiError } from '@/test/api-error';
const mockPatch = vi.mocked(api.patch);
const mockDelete = vi.mocked(api.delete);

function render(s: ContractSigner, onEdit = vi.fn()) {
  renderWithRouter(<ContractSignerRowActions signer={s} onEdit={onEdit} />);
  return { onEdit };
}

async function openMenu(ue: ReturnType<typeof userEvent.setup>, name: string) {
  await ue.click(screen.getByRole('button', { name: new RegExp(`actions for ${name}`, 'i') }));
}

describe('ContractSignerRowActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPatch.mockResolvedValue({ data: {} });
  });

  it('edit hands the row back to the page rather than mutating', async () => {
    const ue = userEvent.setup();
    const { onEdit } = render(signer());
    await openMenu(ue, 'Dana Reyes');
    await ue.click(screen.getByRole('menuitem', { name: /edit/i }));

    expect(onEdit).toHaveBeenCalledWith(signer());
    expect(mockPatch).not.toHaveBeenCalled();
  });

  it('deactivate PATCHes is_active:false after confirming', async () => {
    const ue = userEvent.setup();
    render(signer());
    await openMenu(ue, 'Dana Reyes');
    await ue.click(screen.getByRole('menuitem', { name: /deactivate/i }));
    await ue.click(await screen.findByRole('button', { name: 'Deactivate' }));

    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith('/contract-signers/cs-1', { is_active: false }),
    );
  });

  it('activate PATCHes is_active:true without a confirm step', async () => {
    const ue = userEvent.setup();
    render(signer({ is_active: false }));
    await openMenu(ue, 'Dana Reyes');
    await ue.click(screen.getByRole('menuitem', { name: /activate/i }));

    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith('/contract-signers/cs-1', { is_active: true }),
    );
  });

  it('offers no delete — revocation is deactivation', async () => {
    const ue = userEvent.setup();
    render(signer());
    await openMenu(ue, 'Dana Reyes');

    expect(screen.queryByRole('menuitem', { name: /delete/i })).not.toBeInTheDocument();
    expect(mockDelete).not.toHaveBeenCalled();
  });

  it('surfaces the server 409 when the last-signer guard rejects a deactivate', async () => {
    mockPatch.mockRejectedValueOnce(
      makeApiError('Cannot deactivate the last active contract signer.', 409, 'CONFLICT'),
    );
    const ue = userEvent.setup();
    render(signer());
    await openMenu(ue, 'Dana Reyes');
    await ue.click(screen.getByRole('menuitem', { name: /deactivate/i }));
    await ue.click(await screen.findByRole('button', { name: 'Deactivate' }));

    expect(
      await screen.findByText('Cannot deactivate the last active contract signer.'),
    ).toBeInTheDocument();
  });
});
