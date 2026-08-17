import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { AwardDialog } from '../AwardDialog';
import type { PreAwardValidationResult } from '../../types';

vi.mock('@/features/bids/api/award.queries', () => ({
  fetchAwardValidation: vi.fn(),
}));

vi.mock('@/features/contract-signers/api/contractSigner.queries', () => ({
  fetchContractSigners: vi.fn(),
  fetchActiveContractSigners: vi.fn(),
}));

import { fetchAwardValidation } from '@/features/bids/api/award.queries';
import { fetchActiveContractSigners } from '@/features/contract-signers/api/contractSigner.queries';

const mockValidation = vi.mocked(fetchAwardValidation);
const mockSigners = vi.mocked(fetchActiveContractSigners);

function cleanResult(): PreAwardValidationResult {
  return {
    rubric_version: 'preaward-v1',
    can_award: true,
    has_blocking: false,
    has_warnings: false,
    requires_override: false,
    validated_at: '2026-08-01T00:00:00Z',
    award_amount: '50000.00',
    checks: [],
  };
}

function activeSigner(overrides = {}) {
  return {
    id: 'cs-1',
    full_name: 'Dana Reyes',
    email: 'dana@bluonx.dev',
    title: 'VP of Development',
    is_active: true,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...overrides,
  };
}

function render(onConfirm = vi.fn()) {
  renderWithRouter(
    <AwardDialog
      bidSubmissionId="sub-1"
      vendorName="Acme Grading LLC"
      isOpen
      onClose={vi.fn()}
      onConfirm={onConfirm}
      isSubmitting={false}
    />,
  );
  return { onConfirm };
}

describe('AwardDialog signer selection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockValidation.mockResolvedValue(cleanResult());
    mockSigners.mockResolvedValue([activeSigner()]);
  });

  it('labels an option with the title in parentheses when one is set', async () => {
    render();
    expect(await screen.findByRole('option', { name: 'Dana Reyes (VP of Development)' }))
      .toBeInTheDocument();
  });

  it('falls back to the bare name when a signer has no title', async () => {
    mockSigners.mockResolvedValue([activeSigner({ title: null })]);
    render();
    expect(await screen.findByRole('option', { name: 'Dana Reyes' })).toBeInTheDocument();
  });

  it('blocks confirm until a signer is chosen, then passes signer_id through', async () => {
    const ue = userEvent.setup();
    const { onConfirm } = render();

    const confirm = await screen.findByRole('button', { name: /confirm award/i });
    await waitFor(() => expect(confirm).toBeDisabled());

    await ue.selectOptions(await screen.findByLabelText(/bluonx signer/i), 'cs-1');
    await waitFor(() => expect(confirm).toBeEnabled());
    await ue.click(confirm);

    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({ signer_id: 'cs-1' }),
    );
  });

  it('refuses to award at all when the roster has no active signers', async () => {
    mockSigners.mockResolvedValue([]);
    render();

    expect(
      await screen.findByText(
        'No active contract signers are configured. An administrator must add one under Settings before a task can be awarded.',
      ),
    ).toBeInTheDocument();
    // There is no way to proceed: no select to pick from, and confirm stays dead.
    expect(screen.queryByLabelText(/bluonx signer/i)).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /confirm award/i })).toBeDisabled(),
    );
  });
});
