import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { ContractSignerModal } from '../ContractSignerModal';
import { signer } from './fixtures';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import { api } from '@/lib/api';
import { makeApiError } from '@/test/api-error';
const mockPost = vi.mocked(api.post);
const mockPatch = vi.mocked(api.patch);

const REACTIVATION_409 =
  'A contract signer with this email already exists but is deactivated. ' +
  'Reactivate the existing entry instead of adding a new one.';

describe('ContractSignerModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPost.mockResolvedValue({ data: signer() });
    mockPatch.mockResolvedValue({ data: signer() });
  });

  it('POSTs a trimmed new signer', async () => {
    const ue = userEvent.setup();
    renderWithRouter(<ContractSignerModal isOpen onClose={vi.fn()} signer={null} />);

    await ue.type(screen.getByLabelText(/full name/i), '  Priya Raman  ');
    await ue.type(screen.getByLabelText(/^email/i), 'priya@bluonx.dev');
    await ue.type(screen.getByLabelText(/title/i), 'Director');
    await ue.click(screen.getByRole('button', { name: /add signer/i }));

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/contract-signers', {
        full_name: 'Priya Raman',
        email: 'priya@bluonx.dev',
        title: 'Director',
      }),
    );
  });

  it('seeds the form from the row being edited and PATCHes it', async () => {
    const ue = userEvent.setup();
    renderWithRouter(<ContractSignerModal isOpen onClose={vi.fn()} signer={signer()} />);

    expect(screen.getByLabelText(/full name/i)).toHaveValue('Dana Reyes');
    expect(screen.getByLabelText(/^email/i)).toHaveValue('dana@bluonx.dev');

    await ue.clear(screen.getByLabelText(/title/i));
    await ue.type(screen.getByLabelText(/title/i), 'Chief Operating Officer');
    await ue.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith('/contract-signers/cs-1', {
        full_name: 'Dana Reyes',
        email: 'dana@bluonx.dev',
        title: 'Chief Operating Officer',
      }),
    );
  });

  it('validates required fields inline without calling the API', async () => {
    const ue = userEvent.setup();
    renderWithRouter(<ContractSignerModal isOpen onClose={vi.fn()} signer={null} />);

    await ue.click(screen.getByRole('button', { name: /add signer/i }));

    expect(await screen.findByText('Full name is required')).toBeInTheDocument();
    expect(screen.getByText('Email is required')).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('keeps the modal open and surfaces the reactivation 409 verbatim', async () => {
    mockPost.mockRejectedValueOnce(makeApiError(REACTIVATION_409, 409, 'CONFLICT'));
    const onClose = vi.fn();
    const ue = userEvent.setup();
    renderWithRouter(<ContractSignerModal isOpen onClose={onClose} signer={null} />);

    await ue.type(screen.getByLabelText(/full name/i), 'Dana Reyes');
    await ue.type(screen.getByLabelText(/^email/i), 'dana@bluonx.dev');
    await ue.click(screen.getByRole('button', { name: /add signer/i }));

    // The distinction between "already on the roster" and "revoked, reactivate
    // it" only reaches the admin through this message, so it must not be
    // swallowed or replaced with a generic fallback.
    expect(await screen.findByText(REACTIVATION_409)).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('surfaces a server error from the edit path too', async () => {
    mockPatch.mockRejectedValueOnce(
      makeApiError('A contract signer with this email already exists.', 409, 'CONFLICT'),
    );
    const ue = userEvent.setup();
    renderWithRouter(<ContractSignerModal isOpen onClose={vi.fn()} signer={signer()} />);

    await ue.click(screen.getByRole('button', { name: /save changes/i }));

    expect(
      await screen.findByText('A contract signer with this email already exists.'),
    ).toBeInTheDocument();
  });
});
