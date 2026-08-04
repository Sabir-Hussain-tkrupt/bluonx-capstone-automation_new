import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { CancelBidPackageDialog } from '../CancelBidPackageDialog';

const mutate = vi.fn();
let isPending = false;

vi.mock('@/features/bids/hooks/useCancelBidPackage', () => ({
  useCancelBidPackage: () => ({ mutate, isPending }),
}));

function renderDialog(
  overrides: { submittedCount?: number; pendingRevisionCount?: number } = {},
) {
  return renderWithRouter(
    <CancelBidPackageDialog
      isOpen
      onClose={vi.fn()}
      bidPackageId="pkg-1"
      taskId="task-1"
      submittedCount={overrides.submittedCount ?? 0}
      pendingRevisionCount={overrides.pendingRevisionCount ?? 0}
    />,
  );
}

describe('CancelBidPackageDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    isPending = false;
  });

  it('always states that the package cannot be reopened', () => {
    // Nothing anywhere sets a package back to open, so this is irreversible.
    renderDialog();

    expect(screen.getByText(/cannot be reopened/i)).toBeInTheDocument();
  });

  it('tells the PM a new round is still possible', () => {
    renderDialog();

    expect(screen.getByText(/start a new round/i)).toBeInTheDocument();
  });

  describe('with submitted bids', () => {
    it('warns that existing bids stop being awardable', () => {
      renderDialog({ submittedCount: 3 });

      expect(screen.getByText(/no longer be awarded/i)).toBeInTheDocument();
      expect(screen.getByText(/3 submitted bids/i)).toBeInTheDocument();
    });

    it('singularises a lone bid', () => {
      renderDialog({ submittedCount: 1 });

      expect(screen.getByText(/1 submitted bid$/i)).toBeInTheDocument();
    });

    it('says nothing about bids when there are none', () => {
      renderDialog({ submittedCount: 0 });

      expect(screen.queryByText(/no longer be awarded/i)).toBeNull();
    });
  });

  describe('with pending revision requests', () => {
    // These are cancelled server-side; their tokens outlive the package status
    // flip, so the PM should know those vendors lose access too.
    it('warns that pending revisions are cancelled as well', () => {
      renderDialog({ pendingRevisionCount: 2 });

      expect(
        screen.getByText(/2 pending revision requests will also be cancelled/i),
      ).toBeInTheDocument();
    });

    it('says nothing about revisions when there are none', () => {
      renderDialog({ pendingRevisionCount: 0 });

      expect(screen.queryByText(/revision request/i)).toBeNull();
    });
  });

  it('calls the cancel mutation on confirm', async () => {
    const user = userEvent.setup();
    renderDialog({ submittedCount: 2 });

    await user.click(
      screen.getByRole('button', { name: /cancel bid package/i }),
    );
    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it('does not fire the mutation when the PM keeps the package', async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole('button', { name: /keep package/i }));
    expect(mutate).not.toHaveBeenCalled();
  });

  it('disables the escape button while the cancel is in flight', () => {
    isPending = true;
    renderDialog();

    expect(screen.getByRole('button', { name: /keep package/i })).toBeDisabled();
  });
});
