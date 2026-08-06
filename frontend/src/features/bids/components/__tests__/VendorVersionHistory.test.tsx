import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { VendorVersionHistory } from '../VendorVersionHistory';
import type { BidSubmissionDetail } from '@/features/bids/types';
import { makeBidSubmissionDetail } from '@/features/bids/test/fixtures';

const useVendorVersionHistory = vi.fn();

vi.mock('@/features/bids/hooks/useVendorVersionHistory', () => ({
  useVendorVersionHistory: (...args: unknown[]) =>
    useVendorVersionHistory(...args),
}));

const makeSubmission = (overrides: Partial<BidSubmissionDetail>) =>
  makeBidSubmissionDetail(overrides);

describe('VendorVersionHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a 2-version history with state labels and a signed delta', () => {
    useVendorVersionHistory.mockReturnValue({
      data: [
        makeSubmission({
          id: 'sub-1',
          revision_number: 1,
          is_superseded: true,
          total_amount: 52800,
        }),
        makeSubmission({
          id: 'sub-2',
          revision_number: 2,
          is_superseded: false,
          total_amount: 50800,
          supersedes_submission_id: 'sub-1',
        }),
      ],
      isLoading: false,
      error: null,
    });

    render(
      <VendorVersionHistory
        currentSubmissionId="sub-2"
        onViewBid={vi.fn()}
      />,
    );

    expect(screen.getByText('Original')).toBeInTheDocument();
    expect(screen.getByText('Superseded')).toBeInTheDocument();
    expect(screen.getByText('Revised')).toBeInTheDocument();
    expect(screen.getByText('Current')).toBeInTheDocument();
    // Lower revised amount => negative delta.
    expect(screen.getByText('-$2,000')).toBeInTheDocument();
  });

  it('invokes onViewBid with the submission id of the row', async () => {
    const user = userEvent.setup();
    const onViewBid = vi.fn();
    useVendorVersionHistory.mockReturnValue({
      data: [makeSubmission({ id: 'sub-1', total_amount: 100 })],
      isLoading: false,
      error: null,
    });

    render(
      <VendorVersionHistory
        currentSubmissionId="sub-1"
        onViewBid={onViewBid}
      />,
    );

    await user.click(
      screen.getByRole('button', { name: /view full bid/i }),
    );
    expect(onViewBid).toHaveBeenCalledWith('sub-1');
  });
});
