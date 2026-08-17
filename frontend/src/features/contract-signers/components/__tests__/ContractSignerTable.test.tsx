import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { ContractSignerTable } from '../ContractSignerTable';
import { signer } from './fixtures';

// The row-action menu uses the api client via mutation hooks; stub it so nothing
// hits the network at render time.
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

// The shared Table renders a desktop table AND mobile cards, so each value
// appears more than once in jsdom; assert presence rather than uniqueness.
const present = (text: string) => expect(screen.getAllByText(text).length).toBeGreaterThan(0);

describe('ContractSignerTable', () => {
  it('renders a row per signer with name, email and title', () => {
    renderWithRouter(
      <ContractSignerTable
        signers={[
          signer(),
          signer({ id: 'cs-2', full_name: 'Sam Okoro', email: 'sam@bluonx.dev', title: 'COO' }),
        ]}
        isLoading={false}
        onEdit={vi.fn()}
      />,
    );

    present('Dana Reyes');
    present('dana@bluonx.dev');
    present('VP of Development');
    present('Sam Okoro');
    present('COO');
  });

  it('shows a placeholder when a signer has no title', () => {
    renderWithRouter(
      <ContractSignerTable
        signers={[signer({ title: null })]}
        isLoading={false}
        onEdit={vi.fn()}
      />,
    );

    present('—');
  });

  it('distinguishes active from deactivated signers', () => {
    renderWithRouter(
      <ContractSignerTable
        signers={[signer(), signer({ id: 'cs-2', full_name: 'Sam Okoro', is_active: false })]}
        isLoading={false}
        onEdit={vi.fn()}
      />,
    );

    expect(screen.getAllByLabelText('Active').length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText('Inactive').length).toBeGreaterThan(0);
  });

  it('shows the empty state when the roster is empty', () => {
    renderWithRouter(
      <ContractSignerTable
        signers={[]}
        isLoading={false}
        onEdit={vi.fn()}
        emptyState={<div>No contract signers yet</div>}
      />,
    );

    expect(screen.getByText('No contract signers yet')).toBeInTheDocument();
  });

  it('does not render data rows while loading', () => {
    renderWithRouter(
      <ContractSignerTable signers={[signer()]} isLoading onEdit={vi.fn()} />,
    );

    expect(screen.queryByText('Dana Reyes')).not.toBeInTheDocument();
  });
});
