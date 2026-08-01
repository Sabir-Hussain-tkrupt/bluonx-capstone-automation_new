import { Table } from '@/components/ui/Table';
import { StatusBadge } from '@/components/ui/StatusBadge';
import type { Column, TablePagination } from '@/components/ui/Table';
import type { EmailLogItem } from '@/features/bids/types';

function formatDateTime(value: string | null): string {
  if (!value) return '\u2014';
  return new Date(value).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const columns: Column<EmailLogItem>[] = [
  {
    id: 'recipient_email',
    header: 'Recipient',
    accessor: (row) => row.recipient_email ?? '\u2014',
  },
  {
    id: 'email_type',
    header: 'Type',
    accessor: (row) => (
      <span className="text-xs capitalize">{row.email_type?.replace(/_/g, ' ') ?? '\u2014'}</span>
    ),
  },
  {
    id: 'subject',
    header: 'Subject',
    accessor: (row) => (
      <span className="max-w-xs truncate text-xs">{row.subject ?? '\u2014'}</span>
    ),
  },
  {
    id: 'status',
    header: 'Status',
    accessor: (row) =>
      row.status ? <StatusBadge status={row.status} size="sm" /> : '\u2014',
    width: '100px',
  },
  {
    id: 'sent_at',
    header: 'Sent At',
    accessor: (row) => (
      <span className="text-xs text-secondary-500">{formatDateTime(row.sent_at)}</span>
    ),
  },
  {
    id: 'error_message',
    header: 'Error',
    accessor: (row) =>
      row.error_message ? (
        <span className="text-xs text-danger-600">{row.error_message}</span>
      ) : (
        '\u2014'
      ),
  },
];

interface EmailLogTableProps {
  items: EmailLogItem[];
  isLoading: boolean;
  /**
   * Server-side pagination. Both email logs are unbounded in principle — a
   * long-standing vendor accumulates thousands of rows — so callers page
   * through them rather than fetching the lot.
   */
  pagination?: TablePagination;
}

export function EmailLogTable({ items, isLoading, pagination }: EmailLogTableProps) {
  return (
    <Table<EmailLogItem>
      columns={columns}
      data={items}
      keyExtractor={(row) => row.id ?? `${row.recipient_email}-${row.sent_at}`}
      isLoading={isLoading}
      mobileTitle="recipient_email"
      pagination={pagination}
      emptyState={
        <p className="py-6 text-center text-sm text-secondary-500">No emails logged yet.</p>
      }
    />
  );
}
