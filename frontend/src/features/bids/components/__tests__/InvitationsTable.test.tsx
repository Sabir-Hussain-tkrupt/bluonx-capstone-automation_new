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

function renderTable(
  invitations: BidInvitation[],
  onViewBid?: (id: string) => void,
  // Most cases describe a live package; the closed-package cases opt out
  // explicitly. The component itself defaults this to false (fail closed).
  bidPackageOpen = true,
) {
  return render(
    <InvitationsTable
      invitations={invitations}
      isLoading={false}
      onResendBidLink={vi.fn()}
      onMarkDeclined={vi.fn()}
      onViewBid={onViewBid}
      resendingId={null}
      updatingId={null}
      bidPackageOpen={bidPackageOpen}
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
  function renderWithRevision(
    invitation: BidInvitation,
    bidPackageOpen = true,
  ) {
    return render(
      <InvitationsTable
        invitations={[invitation]}
        isLoading={false}
        onResendBidLink={vi.fn()}
        onMarkDeclined={vi.fn()}
        resendingId={null}
        updatingId={null}
        onRequestRevision={vi.fn()}
        bidPackageOpen={bidPackageOpen}
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

  it('still renders Request Revision once the package is no longer open', () => {
    // create_revision_request has no package-status guard, and evaluating is
    // precisely when a PM reviews bids and asks for a revision. The button must
    // track the backend, not the package status.
    renderWithRevision(
      makeInvitation({
        status: 'submitted',
        bid_submission_id: 'sub-1',
        is_awarded: false,
      }),
      false,
    );
    expect(
      screen.getAllByRole('button', { name: 'Request Revision' }).length,
    ).toBeGreaterThan(0);
  });

  it('hides Request Revision on a closed package once the task is awarded', () => {
    // Guards the risk the alignment introduces: is_awarded is task-scoped, so
    // a non-winning row on an awarded package must not offer an action the
    // backend would reject with 409.
    renderWithRevision(
      makeInvitation({
        status: 'submitted',
        bid_submission_id: 'sub-1',
        is_awarded: true,
      }),
      false,
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
        bidPackageOpen
      />,
    );

    const buttons = screen.getAllByRole('button', { name: 'Send Bid Link' });
    await user.click(buttons[0]);
    expect(onResend).toHaveBeenCalledWith('inv-fail');
  });
});

describe('InvitationsTable — actions are gated on the package being open', () => {
  // resend_bid_link and update_invitation_status both refuse a non-open
  // package, so offering these actions produces a guaranteed error. This is
  // the state a package lands in after the deadline passes or the PM closes
  // bidding early: rows converge to no_response on an 'evaluating' package.
  const RESENDABLE: InvitationStatus[] = [
    'no_response',
    'pending_send',
    'send_failed',
    'sent',
    'opened',
  ];

  it.each(RESENDABLE)(
    'hides the resend action for a %s row when the package is not open',
    (status) => {
      renderTable([makeInvitation({ status })], undefined, false);

      expect(screen.queryByRole('button', { name: 'Resend Bid Link' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Send Bid Link' })).toBeNull();
    },
  );

  it.each(RESENDABLE)(
    'still shows the resend action for a %s row while the package is open',
    (status) => {
      renderTable([makeInvitation({ status })], undefined, true);

      const resend = screen.queryAllByRole('button', { name: 'Resend Bid Link' });
      const send = screen.queryAllByRole('button', { name: 'Send Bid Link' });
      expect(resend.length + send.length).toBeGreaterThan(0);
    },
  );

  it.each(['sent', 'opened'] as InvitationStatus[])(
    'hides Mark Declined for a %s row when the package is not open',
    (status) => {
      renderTable([makeInvitation({ status })], undefined, false);

      expect(screen.queryByRole('button', { name: 'Mark Declined' })).toBeNull();
    },
  );

  it.each(['sent', 'opened'] as InvitationStatus[])(
    'still shows Mark Declined for a %s row while the package is open',
    (status) => {
      renderTable([makeInvitation({ status })], undefined, true);

      expect(
        screen.getAllByRole('button', { name: 'Mark Declined' }).length,
      ).toBeGreaterThan(0);
    },
  );

  it('defaults to closed when bidPackageOpen is omitted', () => {
    // Fail-closed: an omitted prop must never expose an action the API refuses.
    render(
      <InvitationsTable
        invitations={[makeInvitation({ status: 'sent' })]}
        isLoading={false}
        onResendBidLink={vi.fn()}
        onMarkDeclined={vi.fn()}
        resendingId={null}
        updatingId={null}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Resend Bid Link' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Mark Declined' })).toBeNull();
  });
});
