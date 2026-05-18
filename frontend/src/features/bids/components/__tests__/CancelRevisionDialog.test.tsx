import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { CancelRevisionDialog } from '../CancelRevisionDialog';

const mutate = vi.fn();

vi.mock('@/features/bids/hooks/useCancelRevisionRequest', () => ({
  useCancelRevisionRequest: () => ({ mutate, isPending: false }),
}));

describe('CancelRevisionDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the confirmation copy with the vendor name', () => {
    renderWithRouter(
      <CancelRevisionDialog
        isOpen
        onClose={vi.fn()}
        revisionRequestId="rev-1"
        vendorName="Apex Grading"
        bidPackageId="pkg-1"
      />,
    );
    expect(
      screen.getByText(/Apex Grading will not be notified/i),
    ).toBeInTheDocument();
  });

  it('calls the cancel mutation with the revision request id on confirm', async () => {
    const user = userEvent.setup();
    renderWithRouter(
      <CancelRevisionDialog
        isOpen
        onClose={vi.fn()}
        revisionRequestId="rev-1"
        vendorName="Apex Grading"
        bidPackageId="pkg-1"
      />,
    );
    await user.click(screen.getByRole('button', { name: /cancel request/i }));
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toBe('rev-1');
  });
});
