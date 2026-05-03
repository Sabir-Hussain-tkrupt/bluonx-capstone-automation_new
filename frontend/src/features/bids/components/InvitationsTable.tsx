import { Table } from '@/components/ui/Table';
import { Button } from '@/components/ui/Button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import type { Column } from '@/components/ui/Table';
import type { BidInvitation, InvitationStatus } from '@/features/bids/types';

function formatDateTime(value: string | null): string {
  if (!value) return '\u2014';
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

interface InvitationsTableProps {
  invitations: BidInvitation[];
  isLoading: boolean;
  onResendBidLink: (invitationId: string) => void;
  onMarkDeclined: (invitationId: string) => void;
  resendingId: string | null;
  updatingId: string | null;
}

export function InvitationsTable({
  invitations,
  isLoading,
  onResendBidLink,
  onMarkDeclined,
  resendingId,
  updatingId,
}: InvitationsTableProps) {
  const columns: Column<BidInvitation>[] = [
    {
      id: 'vendor_company_name',
      header: 'Vendor',
      accessor: (row) => row.vendor_company_name ?? '\u2014',
    },
    {
      id: 'vendor_contact_name',
      header: 'Contact',
      accessor: (row) => row.vendor_contact_name ?? '\u2014',
    },
    {
      id: 'vendor_contact_email',
      header: 'Email',
      accessor: (row) => (
        <span className="text-xs text-secondary-600">
          {row.vendor_contact_email ?? '\u2014'}
        </span>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      accessor: (row) => <StatusBadge status={row.status} size="sm" />,
      width: '110px',
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
      accessor: (row) => (
        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
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
      ),
      width: '280px',
    },
  ];

  return (
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
  );
}
