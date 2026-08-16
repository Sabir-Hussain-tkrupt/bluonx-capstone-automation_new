import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { ContractSignersPage } from '../ContractSignersPage';
import { signer } from '../../components/__tests__/fixtures';

// The roster is read straight from Supabase (RLS lets any active user see every
// row, inactive included), so the query module is what a page test stands in for.
vi.mock('../../api/contractSigner.queries', () => ({
  fetchContractSigners: vi.fn(),
  fetchActiveContractSigners: vi.fn(),
}));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import { fetchContractSigners } from '../../api/contractSigner.queries';
const mockFetch = vi.mocked(fetchContractSigners);

// The shared Table renders desktop rows AND mobile cards, so every value and
// every row-action trigger is in the DOM twice.
const firstActionsButton = (name: string) =>
  screen.getAllByRole('button', { name: new RegExp(`actions for ${name}`, 'i') })[0];

describe('ContractSignersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockResolvedValue([
      signer(),
      signer({ id: 'cs-2', full_name: 'Sam Okoro', email: 'sam@bluonx.dev', is_active: false }),
    ]);
  });

  it('renders the roster including deactivated signers', async () => {
    renderWithRouter(<ContractSignersPage />);

    expect((await screen.findAllByText('Dana Reyes')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Sam Okoro').length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText('Inactive').length).toBeGreaterThan(0);
  });

  it('opens the add modal from the header button', async () => {
    const ue = userEvent.setup();
    renderWithRouter(<ContractSignersPage />);
    await screen.findAllByText('Dana Reyes');

    await ue.click(screen.getByRole('button', { name: /add signer/i }));

    expect(await screen.findByRole('heading', { name: 'Add signer' })).toBeInTheDocument();
  });

  it('opens the edit modal seeded with the chosen row', async () => {
    const ue = userEvent.setup();
    renderWithRouter(<ContractSignersPage />);
    await screen.findAllByText('Dana Reyes');

    await ue.click(firstActionsButton('Dana Reyes'));
    await ue.click(screen.getByRole('menuitem', { name: /edit/i }));

    expect(await screen.findByRole('heading', { name: 'Edit signer' })).toBeInTheDocument();
    expect(screen.getByLabelText(/full name/i)).toHaveValue('Dana Reyes');
  });

  it('surfaces a read failure without blanking the page', async () => {
    mockFetch.mockRejectedValue(new Error('network down'));
    renderWithRouter(<ContractSignersPage />);

    await waitFor(() =>
      expect(screen.getByText('Could not load contract signers')).toBeInTheDocument(),
    );
  });
});
