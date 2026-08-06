/**
 * BidTemplateDetailPage: a load failure is not a missing template.
 *
 * The page previously used `if (!template)` for both, telling the user a
 * perfectly healthy record "doesn't exist or has been deleted" whenever the
 * request failed, and offering no way to try again.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { BidTemplateDetailPage } from '../BidTemplateDetailPage';
import { makeApiError } from '@/test/api-error';

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return {
    ...actual,
    useParams: () => ({ id: 'tpl-123' }),
    useNavigate: () => vi.fn(),
  };
});

const useBidTemplateMock = vi.fn();
vi.mock('@/features/bid-templates/hooks/useBidTemplate', () => ({
  useBidTemplate: () => useBidTemplateMock(),
}));

function mockQuery(overrides: Record<string, unknown> = {}) {
  const refetch = vi.fn();
  useBidTemplateMock.mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
    refetch,
    isFetching: false,
    ...overrides,
  });
  return refetch;
}

describe('BidTemplateDetailPage load states', () => {
  beforeEach(() => vi.clearAllMocks());

  it('reports a 404 as not found, with no Retry', () => {
    mockQuery({ error: makeApiError('Bid template not found', 404, 'NOT_FOUND') });

    renderWithRouter(<BidTemplateDetailPage />);

    expect(screen.getByText(/Template not found/i)).toBeInTheDocument();
    // Retrying a 404 just fails again; do not offer it.
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
  });

  it('reports a server error as a load failure, with the message and Retry', () => {
    mockQuery({
      error: makeApiError('Failed to fetch bid template from database', 502),
    });

    renderWithRouter(<BidTemplateDetailPage />);

    expect(screen.getByText(/Could not load template/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Failed to fetch bid template from database/i),
    ).toBeInTheDocument();
    // Must NOT claim the template is missing.
    expect(screen.queryByText(/Template not found/i)).not.toBeInTheDocument();
  });

  it('refetches when Retry is clicked', async () => {
    const user = userEvent.setup();
    const refetch = mockQuery({
      error: makeApiError('Internal Server Error', 500, 'SERVER_ERROR'),
    });

    renderWithRouter(<BidTemplateDetailPage />);
    await user.click(screen.getByRole('button', { name: /retry/i }));

    expect(refetch).toHaveBeenCalledTimes(1);
  });
});
