import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { RequestRevisionModal } from '../RequestRevisionModal';
import type { BidInvitation } from '@/features/bids/types';

const mutate = vi.fn();

vi.mock('@/features/bids/hooks/useCreateRevisionRequest', () => ({
  useCreateRevisionRequest: () => ({ mutate, isPending: false }),
}));

const invitation: BidInvitation = {
  id: 'inv-1',
  vendor_id: 'v-1',
  vendor_company_name: 'Apex Grading',
  vendor_contact_name: 'Jane Roe',
  vendor_contact_email: 'jane@apex.example.com',
  status: 'submitted',
  sent_at: null,
  opened_at: null,
  responded_at: null,
  bid_submission_id: 'sub-1',
};

function renderModal() {
  return renderWithRouter(
    <RequestRevisionModal
      isOpen
      onClose={vi.fn()}
      invitation={invitation}
      bidPackageId="pkg-1"
    />,
  );
}

describe('RequestRevisionModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the note field and deadline picker', () => {
    renderModal();
    expect(screen.getByText(/Note to vendor/i)).toBeInTheDocument();
    expect(screen.getByText(/Revision deadline/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /send request/i }),
    ).toBeInTheDocument();
  });

  it('blocks submit when the note is empty', async () => {
    const user = userEvent.setup();
    renderModal();
    await user.click(screen.getByRole('button', { name: /send request/i }));
    expect(
      await screen.findByText(/A note to the vendor is required/i),
    ).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
  });

  it('blocks submit when the deadline is not in the future', async () => {
    const user = userEvent.setup();
    renderModal();
    await user.type(
      screen.getByPlaceholderText(/Please update line item/i),
      'Please revise scope.',
    );
    fireEvent.change(screen.getByLabelText(/Revision deadline/i), {
      target: { value: '2000-01-01T10:00' },
    });
    await user.click(screen.getByRole('button', { name: /send request/i }));
    expect(
      await screen.findByText(/Deadline must be in the future/i),
    ).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
  });

  it('calls the create mutation with the right payload on a valid submit', async () => {
    const user = userEvent.setup();
    renderModal();
    await user.type(
      screen.getByPlaceholderText(/Please update line item/i),
      'Please revise line item 3.',
    );
    fireEvent.change(screen.getByLabelText(/Revision deadline/i), {
      target: { value: '2099-01-01T10:00' },
    });
    await user.click(screen.getByRole('button', { name: /send request/i }));

    await waitFor(() => expect(mutate).toHaveBeenCalledTimes(1));
    expect(mutate.mock.calls[0][0]).toEqual({
      bid_invitation_id: 'inv-1',
      pm_note: 'Please revise line item 3.',
      revision_deadline: new Date('2099-01-01T10:00').toISOString(),
    });
  });
});
