import { Table } from '@/components/ui/Table';
import { Button } from '@/components/ui/Button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import type { Column } from '@/components/ui/Table';
import { RevisionStatusBadge } from '@/features/bids/components/RevisionStatusBadge';
import { VendorVersionHistory } from '@/features/bids/components/VendorVersionHistory';
import type {
  BidInvitation,
  BidRevisionRequest,
  InvitationStatus,
} from '@/features/bids/types';

function formatDateTime(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const canResend = (status: InvitationStatus) =>
  status === 'sent' || status === 'opened' || status === 'no_response';

const canMarkStatus = (status: InvitationStatus) =>
  status === 'sent' || status === 'opened';

// A terminal request (or a finalized revision) means there is audit history
// worth expanding even when the current submission is still revision 1.
const hasHistory = (revision?: BidRevisionRequest) =>
  !!revision &&
  (revision.status === 'submitted' ||
    revision.status === 'declined' ||
    revision.status === 'expired');

interface InvitationsTableProps {
  invitations: BidInvitation[];
  isLoading: boolean;
  onResendBidLink: (invitationId: string) => void;
  onMarkDeclined: (invitationId: string) => void;
  onViewBid?: (submissionId: string) => void;
  resendingId: string | null;
  updatingId: string | null;
  /** Most-recent non-cancelled revision request per invitation id. */
  revisionByInvitationId?: Map<string, BidRevisionRequest>;
  expandedInvitationId?: string | null;
  onToggleExpand?: (invitationId: string) => void;
  onRequestRevision?: (invitation: BidInvitation) => void;
  onCancelRevision?: (
    request: BidRevisionRequest,
    invitation: BidInvitation,
  ) => void;
  /** Bid package is still open (cosmetic gate for Request Revision). */
  bidPackageOpen?: boolean;
}

export function InvitationsTable({
  invitations,
  isLoading,
  onResendBidLink,
  onMarkDeclined,
  onViewBid,
  resendingId,
  updatingId,
  revisionByInvitationId,
  expandedInvitationId,
  onToggleExpand,
  onRequestRevision,
  onCancelRevision,
  bidPackageOpen = false,
}: InvitationsTableProps) {
  const revisionFor = (id: string) => revisionByInvitationId?.get(id);

  const columns: Column<BidInvitation>[] = [
    {
      id: 'vendor_company_name',
      header: 'Vendor',
      accessor: (row) => row.vendor_company_name ?? '—',
    },
    {
      id: 'vendor_contact_name',
      header: 'Contact',
      accessor: (row) => row.vendor_contact_name ?? '—',
    },
    {
      id: 'vendor_contact_email',
      header: 'Email',
      accessor: (row) => (
        <span className="text-xs text-secondary-600">
          {row.vendor_contact_email ?? '—'}
        </span>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      accessor: (row) => {
        const revision = revisionFor(row.id);
        if (revision && revision.status !== 'cancelled') {
          return (
            <RevisionStatusBadge
              status={revision.status}
              declineReason={revision.decline_reason}
            />
          );
        }
        return <StatusBadge status={row.status} size="sm" />;
      },
      width: '130px',
    },
    {
      id: 'sent_at',
      header: 'Sent',
      accessor: (row) => (
        <span className="text-xs text-secondary-500">{formatDateTime(row.sent_at)}</span>
      ),
    },
    {
      id: 'opened_at',
      header: 'Opened',
      accessor: (row) => (
        <span className="text-xs text-secondary-500">{formatDateTime(row.opened_at)}</span>
      ),
    },
    {
      id: 'responded_at',
      header: 'Responded',
      accessor: (row) => (
        <span className="text-xs text-secondary-500">{formatDateTime(row.responded_at)}</span>
      ),
    },
    {
      id: 'actions',
      header: 'Actions',
      accessor: (row) => {
        const revision = revisionFor(row.id);
        const isPending = revision?.status === 'pending';
        const showRequestRevision =
          !!onRequestRevision &&
          row.status === 'submitted' &&
          !!row.bid_submission_id &&
          bidPackageOpen &&
          !isPending;
        const showHistory =
          !!onToggleExpand && !!row.bid_submission_id && hasHistory(revision);
        const isExpanded = expandedInvitationId === row.id;

        return (
          <div
            className="flex items-center gap-1"
            onClick={(e) => e.stopPropagation()}
          >
            {row.status === 'submitted' && row.bid_submission_id && onViewBid && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onViewBid(row.bid_submission_id as string)}
              >
                View Bid
              </Button>
            )}
            {showRequestRevision && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onRequestRevision(row)}
              >
                Request Revision
              </Button>
            )}
            {isPending && onCancelRevision && revision && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onCancelRevision(revision, row)}
              >
                Cancel
              </Button>
            )}
            {showHistory && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onToggleExpand(row.id)}
                aria-expanded={isExpanded}
                aria-label={isExpanded ? 'Hide version history' : 'Show version history'}
              >
                {isExpanded ? 'Hide History' : 'History'}
              </Button>
            )}
            {canResend(row.status) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onResendBidLink(row.id)}
                isLoading={resendingId === row.id}
                disabled={!!resendingId || !!updatingId}
              >
                Resend Bid Link
              </Button>
            )}
            {canMarkStatus(row.status) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onMarkDeclined(row.id)}
                isLoading={updatingId === row.id}
                disabled={!!resendingId || !!updatingId}
              >
                Mark Declined
              </Button>
            )}
          </div>
        );
      },
      width: '380px',
    },
  ];

  const expanded = expandedInvitationId
    ? invitations.find((i) => i.id === expandedInvitationId)
    : undefined;

  return (
    <div className="space-y-3">
      <Table<BidInvitation>
        columns={columns}
        data={invitations}
        keyExtractor={(row) => row.id}
        isLoading={isLoading}
        mobileTitle="vendor_company_name"
        emptyState={
          <p className="py-8 text-center text-sm text-secondary-500">No invitations yet.</p>
        }
      />

      {expanded && expanded.bid_submission_id && onViewBid && (
        <div className="overflow-hidden rounded-lg border border-secondary-200">
          <div className="flex items-center justify-between bg-secondary-100 px-6 py-2">
            <span className="text-sm font-medium text-secondary-700">
              {expanded.vendor_company_name ?? 'Vendor'} — version history
            </span>
            {onToggleExpand && (
              <button
                type="button"
                onClick={() => onToggleExpand(expanded.id)}
                className="text-xs font-medium text-secondary-500 hover:text-secondary-700"
              >
                Close
              </button>
            )}
          </div>
          <VendorVersionHistory
            currentSubmissionId={expanded.bid_submission_id}
            revisionRequest={revisionFor(expanded.id)}
            onViewBid={onViewBid}
          />
        </div>
      )}
    </div>
  );
}
