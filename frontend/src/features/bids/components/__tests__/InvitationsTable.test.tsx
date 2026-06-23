import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InvitationsTable } from '../InvitationsTable';
import type { BidInvitation, InvitationStatus } from '@/features/bids/types';

function makeInvitation(overrides: Partial<BidInvitation> = {}): BidInvitation {
  return {
    id: 'inv-1',
    vendor_id: 'v-1',
    vendor_company_name: 'Apex Grading',
    vendor_contact_name: 'Jane Roe',
    vendor_contact_email: 'jane@apex.example.com',
    status: 'sent',
    sent_at: '2026-04-30T10:00:00Z',
    opened_at: null,
    responded_at: null,
    bid_submission_id: null,
    is_awarded: false,
    ...overrides,
  };
}

function renderTable(invitations: BidInvitation[], onViewBid?: (id: string) => void) {
  return render(
    <InvitationsTable
      invitations={invitations}
      isLoading={false}
      onResendBidLink={vi.fn()}
      onMarkDeclined={vi.fn()}
      onViewBid={onViewBid}
      resendingId={null}
      updatingId={null}
    />,
  );
}

describe('InvitationsTable — View Bid action', () => {
  it('renders View Bid only for submitted rows with a bid_submission_id', () => {
    const submitted = makeInvitation({
      id: 'inv-sub',
      status: 'submitted',
      bid_submission_id: 'sub-123',
      vendor_company_name: 'Submitted Vendor',
    });
    const sent = makeInvitation({ id: 'inv-sent', status: 'sent' });
    const opened = makeInvitation({ id: 'inv-opened', status: 'opened' });
    const declined = makeInvitation({ id: 'inv-decl', status: 'declined' });
    const expired = makeInvitation({ id: 'inv-exp', status: 'expired' });
    const noResp = makeInvitation({ id: 'inv-nr', status: 'no_response' });

    renderTable([submitted, sent, opened, declined, expired, noResp], vi.fn());

    // The Table primitive renders both mobile and desktop views, so a single
    // submitted row produces 2 View Bid buttons (one per layout).
    const viewBidButtons = screen.getAllByRole('button', { name: 'View Bid' });
    expect(viewBidButtons).toHaveLength(2);
  });

  it('does NOT render View Bid for any non-submitted status', () => {
    const statuses: InvitationStatus[] = [
      'sent',
      'opened',
      'declined',
      'expired',
      'no_response',
    ];
    const invitations = statuses.map((s, i) =>
      makeInvitation({ id: `inv-${i}`, status: s, bid_submission_id: null }),
    );

    renderTable(invitations, vi.fn());
    expect(screen.queryByRole('button', { name: 'View Bid' })).toBeNull();
  });

  it('does NOT render View Bid when bid_submission_id is null even if submitted', () => {
    const submittedNoId = makeInvitation({
      status: 'submitted',
      bid_submission_id: null,
    });
    renderTable([submittedNoId], vi.fn());
    expect(screen.queryByRole('button', { name: 'View Bid' })).toBeNull();
  });

  it('invokes onViewBid with the bid_submission_id when clicked', async () => {
    const user = userEvent.setup();
    const onViewBid = vi.fn();
    const submitted = makeInvitation({
      status: 'submitted',
      bid_submission_id: 'sub-abc',
    });
    renderTable([submitted], onViewBid);

    const buttons = screen.getAllByRole('button', { name: 'View Bid' });
    await user.click(buttons[0]);
    expect(onViewBid).toHaveBeenCalledWith('sub-abc');
  });
});

describe('InvitationsTable — Request Revision visibility', () => {
  function renderWithRevision(invitation: BidInvitation) {
    return render(
      <InvitationsTable
        invitations={[invitation]}
        isLoading={false}
        onResendBidLink={vi.fn()}
        onMarkDeclined={vi.fn()}
        resendingId={null}
        updatingId={null}
        onRequestRevision={vi.fn()}
        bidPackageOpen
      />,
    );
  }

  it('renders Request Revision for a submitted bid when the task is not awarded', () => {
    renderWithRevision(
      makeInvitation({
        status: 'submitted',
        bid_submission_id: 'sub-1',
        is_awarded: false,
      }),
    );
    expect(
      screen.getAllByRole('button', { name: 'Request Revision' }).length,
    ).toBeGreaterThan(0);
  });

  it('hides Request Revision when the task is already awarded', () => {
    renderWithRevision(
      makeInvitation({
        status: 'submitted',
        bid_submission_id: 'sub-1',
        is_awarded: true,
      }),
    );
    expect(
      screen.queryByRole('button', { name: 'Request Revision' }),
    ).toBeNull();
  });
});

describe('InvitationsTable — Resend / Send Bid Link action', () => {
  it('labels the action "Send Bid Link" for never-delivered statuses', () => {
    const pending = makeInvitation({ id: 'inv-pend', status: 'pending_send' });
    const failed = makeInvitation({ id: 'inv-fail', status: 'send_failed' });

    renderTable([pending, failed]);

    // Table renders mobile + desktop, so each row yields 2 buttons.
    expect(
      screen.getAllByRole('button', { name: 'Send Bid Link' }).length,
    ).toBe(4);
    expect(
      screen.queryByRole('button', { name: 'Resend Bid Link' }),
    ).toBeNull();
  });

  it('labels the action "Resend Bid Link" for an already-delivered status', () => {
    renderTable([makeInvitation({ id: 'inv-sent', status: 'sent' })]);

    expect(
      screen.getAllByRole('button', { name: 'Resend Bid Link' }).length,
    ).toBe(2);
    expect(
      screen.queryByRole('button', { name: 'Send Bid Link' }),
    ).toBeNull();
  });

  it('invokes onResendBidLink with the invitation id for a send_failed row', async () => {
    const user = userEvent.setup();
    const onResend = vi.fn();
    render(
      <InvitationsTable
        invitations={[makeInvitation({ id: 'inv-fail', status: 'send_failed' })]}
        isLoading={false}
        onResendBidLink={onResend}
        onMarkDeclined={vi.fn()}
        resendingId={null}
        updatingId={null}
      />,
    );

    const buttons = screen.getAllByRole('button', { name: 'Send Bid Link' });
    await user.click(buttons[0]);
    expect(onResend).toHaveBeenCalledWith('inv-fail');
  });
});
