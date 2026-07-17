import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { ReviewPanel } from '../ReviewPanel';
import type { Milestone } from '@/features/milestones/api/milestone.queries';
import type { VendorPerformanceReview } from '@/features/contracts/api/review.queries';

const createMutateMock = vi.fn();
const updateMutateMock = vi.fn();

vi.mock('@/features/contracts/hooks/useReviewMutations', () => ({
  useCreateReview: () => ({ mutate: createMutateMock, isPending: false }),
  useUpdateReview: () => ({ mutate: updateMutateMock, isPending: false }),
}));

function milestone(overrides: Partial<Milestone> = {}): Milestone {
  return {
    id: 'm-1',
    task_id: 'task-1',
    contract_id: 'c-1',
    name: 'Foundation',
    start_date: '2026-06-01',
    end_date: '2026-06-15',
    baseline_end_date: '2026-06-15',
    actual_start_date: null,
    actual_end_date: '2026-06-20', // finished late
    status: 'completed',
    cycle_number: 1,
    sort_order: 0,
    notes: null,
    created_by: 'u-1',
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-06-01T00:00:00Z',
    ...overrides,
  };
}

function review(overrides: Partial<VendorPerformanceReview> = {}): VendorPerformanceReview {
  return {
    id: 'r-1',
    contract_id: 'c-1',
    vendor_id: 'v-1',
    rating: 3,
    notes: 'Solid work',
    reviewed_by: 'u-1',
    reviewed_at: '2026-07-17T00:00:00Z',
    created_at: '2026-07-17T00:00:00Z',
    updated_at: '2026-07-17T00:00:00Z',
    ...overrides,
  };
}

describe('ReviewPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the decision-support milestone facts, flagging late work', () => {
    renderWithRouter(
      <ReviewPanel contractId="c-1" existingReview={null} milestones={[milestone()]} />,
    );
    expect(screen.getByText(/committed/i)).toBeInTheDocument();
    expect(screen.getByText('late')).toBeInTheDocument();
  });

  it('creates a review from the star input', async () => {
    const user = userEvent.setup();
    renderWithRouter(
      <ReviewPanel contractId="c-1" existingReview={null} milestones={[milestone()]} />,
    );

    await user.click(screen.getByRole('radio', { name: '4 stars' }));
    await user.click(screen.getByRole('button', { name: /save rating/i }));

    expect(createMutateMock).toHaveBeenCalledTimes(1);
    expect(createMutateMock.mock.calls[0][0]).toEqual({ rating: 4, notes: null });
  });

  it('does not submit without a rating', async () => {
    const user = userEvent.setup();
    renderWithRouter(
      <ReviewPanel contractId="c-1" existingReview={null} milestones={[]} />,
    );
    await user.click(screen.getByRole('button', { name: /save rating/i }));
    expect(createMutateMock).not.toHaveBeenCalled();
  });

  it('shows an existing review read-only with an Edit affordance', () => {
    renderWithRouter(
      <ReviewPanel contractId="c-1" existingReview={review()} milestones={[milestone()]} />,
    );
    expect(screen.getByRole('img', { name: '3 out of 5 stars' })).toBeInTheDocument();
    expect(screen.getByText('Solid work')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument();
  });

  it('edits an existing review', async () => {
    const user = userEvent.setup();
    renderWithRouter(
      <ReviewPanel contractId="c-1" existingReview={review()} milestones={[milestone()]} />,
    );

    await user.click(screen.getByRole('button', { name: /edit/i }));
    await user.click(screen.getByRole('radio', { name: '5 stars' }));
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    expect(updateMutateMock).toHaveBeenCalledTimes(1);
    expect(updateMutateMock.mock.calls[0][0]).toEqual({
      reviewId: 'r-1',
      input: { rating: 5, notes: 'Solid work' },
    });
  });
});
