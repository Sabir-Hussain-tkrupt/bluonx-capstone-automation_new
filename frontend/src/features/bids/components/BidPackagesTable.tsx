import { Table } from '@/components/ui/Table';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { EmptyState } from '@/components/ui/EmptyState';
import type { Column } from '@/components/ui/Table';
import type { BidPackageListItem } from '@/features/bids/types';

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatDeadline(value: string): string {
  return new Date(value).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const columns: Column<BidPackageListItem>[] = [
  {
    id: 'round_number',
    header: 'Round',
    accessor: (row) => `#${row.round_number}`,
    width: '80px',
  },
  {
    id: 'deadline',
    header: 'Deadline',
    accessor: (row) => formatDeadline(row.deadline),
  },
  {
    id: 'status',
    header: 'Status',
    accessor: (row) => <StatusBadge status={row.status} size="sm" />,
  },
  {
    id: 'invitations',
    header: 'Submitted / Total',
    accessor: (row) => `${row.invitation_submitted} / ${row.invitation_total}`,
    align: 'center',
  },
  {
    id: 'created_at',
    header: 'Created',
    accessor: (row) => formatDate(row.created_at),
  },
];

interface BidPackagesTableProps {
  bidPackages: BidPackageListItem[];
  isLoading: boolean;
  onRowClick: (row: BidPackageListItem) => void;
}

export function BidPackagesTable({ bidPackages, isLoading, onRowClick }: BidPackagesTableProps) {
  return (
    <Table<BidPackageListItem>
      columns={columns}
      data={bidPackages}
      keyExtractor={(row) => row.id}
      onRowClick={onRowClick}
      isLoading={isLoading}
      mobileTitle="round_number"
      emptyState={
        <EmptyState
          title="No bid packages yet"
          description="Start bidding to create the first bid package for this task."
        />
      }
    />
  );
}
