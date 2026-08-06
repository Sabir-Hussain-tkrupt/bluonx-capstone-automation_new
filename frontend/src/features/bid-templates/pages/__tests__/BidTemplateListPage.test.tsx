/**
 * BidTemplateListPage: load-failure surfacing and the delete guard.
 *
 * Two defects pinned here:
 *  - isError was never read, so a failed fetch rendered "No bid templates
 *    found" and looked like an empty list.
 *  - Delete was offered on templates the RESTRICT FK can never allow to be
 *    deleted. is_deletable, not is_in_use, is the correct flag: is_in_use
 *    ignores cancelled packages, which still block the delete.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { BidTemplateListPage } from '../BidTemplateListPage';
import type { BidTemplate } from '@/features/bid-templates/api/bid-template.queries';
import { makeApiError } from '@/test/api-error';

// The shared Table renders a desktop table and a mobile card list from the
// same data, so every row action appears twice. Assert against the first.
function deleteButton() {
  return screen.getAllByRole('button', { name: /delete template/i })[0];
}

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return { ...actual, useNavigate: () => vi.fn() };
});

vi.mock('@/features/vendors/hooks/useTrades', () => ({
  useTrades: () => ({ data: [] }),
}));

const deleteMutationMock = { mutate: vi.fn(), isPending: false };
vi.mock('@/features/bid-templates/hooks/useDeleteBidTemplate', () => ({
  useDeleteBidTemplate: () => deleteMutationMock,
}));

const useBidTemplatesMock = vi.fn();
vi.mock('@/features/bid-templates/hooks/useBidTemplates', () => ({
  useBidTemplates: () => useBidTemplatesMock(),
}));

function makeTemplate(overrides: Partial<BidTemplate> = {}): BidTemplate {
  return {
    id: 'tpl-1',
    name: 'Standard Grading Template',
    trade_id: null,
    is_lump_sum: false,
    created_by: 'pm-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    trade_name: 'Grading',
    item_count: 2,
    is_in_use: false,
    is_deletable: true,
    ...overrides,
  };
}

function mockQuery(overrides: Record<string, unknown> = {}) {
  const refetch = vi.fn();
  useBidTemplatesMock.mockReturnValue({
    data: { items: [], total: 0, page: 1, page_size: 25 },
    isLoading: false,
    isError: false,
    error: null,
    refetch,
    isFetching: false,
    ...overrides,
  });
  return refetch;
}

describe('BidTemplateListPage load failures', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows an error alert with the server message instead of the empty state', () => {
    mockQuery({
      data: undefined,
      isError: true,
      error: makeApiError('Failed to fetch bid templates from database', 502),
    });

    renderWithRouter(<BidTemplateListPage />);

    expect(screen.getByText(/Could not load bid templates/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Failed to fetch bid templates from database/i),
    ).toBeInTheDocument();
    // The empty state must stop claiming there are simply no templates.
    expect(screen.queryByText(/No bid templates found/i)).not.toBeInTheDocument();
  });

  it('retries the query when Retry is clicked', async () => {
    const user = userEvent.setup();
    const refetch = mockQuery({
      data: undefined,
      isError: true,
      error: makeApiError('Network error', 0, 'NETWORK_ERROR'),
    });

    renderWithRouter(<BidTemplateListPage />);
    await user.click(screen.getByRole('button', { name: /retry/i }));

    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('shows the normal empty state when the query succeeds with no rows', () => {
    mockQuery();
    renderWithRouter(<BidTemplateListPage />);

    expect(screen.getByText(/No bid templates found/i)).toBeInTheDocument();
    expect(screen.queryByText(/Could not load bid templates/i)).not.toBeInTheDocument();
  });
});

describe('BidTemplateListPage delete guard', () => {
  beforeEach(() => vi.clearAllMocks());

  it('enables Delete for a template with no referencing packages', () => {
    mockQuery({
      data: { items: [makeTemplate()], total: 1, page: 1, page_size: 25 },
    });

    renderWithRouter(<BidTemplateListPage />);

    expect(deleteButton()).toBeEnabled();
  });

  it('disables Delete when the template is referenced', () => {
    mockQuery({
      data: {
        items: [makeTemplate({ is_deletable: false, is_in_use: true })],
        total: 1,
        page: 1,
        page_size: 25,
      },
    });

    renderWithRouter(<BidTemplateListPage />);

    expect(deleteButton()).toBeDisabled();
  });

  it('disables Delete for a cancelled-only reference, which is_in_use misses', () => {
    // The exact case is_deletable exists for: editable, but the FK still
    // blocks the delete permanently.
    mockQuery({
      data: {
        items: [makeTemplate({ is_deletable: false, is_in_use: false })],
        total: 1,
        page: 1,
        page_size: 25,
      },
    });

    renderWithRouter(<BidTemplateListPage />);

    const del = deleteButton();
    expect(del).toBeDisabled();
    expect(del).toHaveAttribute('title', expect.stringContaining('bid history'));
  });

  it('surfaces the server 409 message when the delete is rejected', async () => {
    const user = userEvent.setup();
    mockQuery({
      data: { items: [makeTemplate()], total: 1, page: 1, page_size: 25 },
    });

    renderWithRouter(<BidTemplateListPage />);

    await user.click(deleteButton());
    await user.click(screen.getByRole('button', { name: /^delete$/i }));

    expect(deleteMutationMock.mutate).toHaveBeenCalledTimes(1);

    // Drive the mutation's onError the way React Query would.
    const onError = deleteMutationMock.mutate.mock.calls[0][1].onError;
    onError(
      makeApiError(
        'This template is referenced by bid package(s) (Rough Grading (open)).',
        409,
        'CONFLICT',
      ),
    );

    expect(await screen.findByText(/Rough Grading \(open\)/)).toBeInTheDocument();
  });
});
