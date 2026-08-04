import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { CloseBiddingDialog } from '../CloseBiddingDialog';

const mutate = vi.fn();
let isPending = false;

vi.mock('@/features/bids/hooks/useCloseBidding', () => ({
  useCloseBidding: () => ({ mutate, isPending }),
}));

function renderDialog(overrides: { totalInvited?: number; submittedCount?: number } = {}) {
  return renderWithRouter(
    <CloseBiddingDialog
      isOpen
      onClose={vi.fn()}
      bidPackageId="pkg-1"
      taskId="task-1"
      totalInvited={overrides.totalInvited ?? 5}
      submittedCount={overrides.submittedCount ?? 3}
    />,
  );
}

describe('CloseBiddingDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    isPending = false;
  });

  describe('with bids in hand', () => {
    it('shows the routine copy with the outstanding count', () => {
      renderDialog({ totalInvited: 5, submittedCount: 3 });

      expect(screen.getByText(/2/)).toBeInTheDocument();
      expect(
        screen.getByText(/stops new bids immediately/i),
      ).toBeInTheDocument();
    });

    it('does not warn about having nothing to award', () => {
      renderDialog({ totalInvited: 5, submittedCount: 3 });

      expect(screen.queryByText(/nothing to award/i)).toBeNull();
    });

    it('singularises the outstanding vendor count', () => {
      renderDialog({ totalInvited: 4, submittedCount: 3 });

      expect(screen.getByText(/invited vendor have not submitted/i)).toBeInTheDocument();
    });
  });

  describe('with zero submitted bids', () => {
    // Closing here is unrecoverable: no code path reopens a package, and
    // Cancel Bid Package is not implemented. The PM must be told before, not
    // after.
    it('warns that the round will have nothing to award', () => {
      renderDialog({ totalInvited: 5, submittedCount: 0 });

      expect(screen.getByText(/nothing to award/i)).toBeInTheDocument();
      expect(
        screen.getByText(/No vendor has submitted a bid yet/i),
      ).toBeInTheDocument();
    });

    it('states that the action cannot be undone or reopened', () => {
      renderDialog({ totalInvited: 5, submittedCount: 0 });

      expect(
        screen.getByText(/cannot be undone and the package cannot be reopened/i),
      ).toBeInTheDocument();
    });

    it('uses a distinct title so the case is visibly different', () => {
      renderDialog({ totalInvited: 5, submittedCount: 0 });

      expect(screen.getByText(/Close bidding with no bids\?/i)).toBeInTheDocument();
    });

    it('still allows the PM to proceed — it warns, it does not block', async () => {
      const user = userEvent.setup();
      renderDialog({ totalInvited: 5, submittedCount: 0 });

      await user.click(screen.getByRole('button', { name: /close bidding/i }));
      expect(mutate).toHaveBeenCalledTimes(1);
    });
  });

  it('calls the close mutation on confirm', async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole('button', { name: /close bidding/i }));
    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it('does not fire the mutation when the PM keeps the package open', async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole('button', { name: /keep open/i }));
    expect(mutate).not.toHaveBeenCalled();
  });

  it('disables the escape button while the close is in flight', () => {
    isPending = true;
    renderDialog();

    expect(screen.getByRole('button', { name: /keep open/i })).toBeDisabled();
  });
});
