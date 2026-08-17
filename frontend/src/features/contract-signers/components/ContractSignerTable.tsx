import { useMemo } from 'react';
import { Table, StatusBadge, type Column } from '@/components/ui';
import { ContractSignerRowActions } from './ContractSignerRowActions';
import type { ContractSigner } from '../types';

interface ContractSignerTableProps {
  signers: ContractSigner[];
  isLoading: boolean;
  onEdit: (signer: ContractSigner) => void;
  emptyState?: React.ReactNode;
}

export function ContractSignerTable({
  signers,
  isLoading,
  onEdit,
  emptyState,
}: ContractSignerTableProps) {
  const columns: Column<ContractSigner>[] = useMemo(
    () => [
      { id: 'full_name', header: 'Name', accessor: 'full_name' },
      { id: 'email', header: 'Email', accessor: 'email' },
      { id: 'title', header: 'Title', accessor: (row) => row.title || '—' },
      {
        id: 'status',
        header: 'Status',
        accessor: (row) => (
          <StatusBadge status={row.is_active ? 'active' : 'inactive'} minWidth />
        ),
      },
      {
        id: 'actions',
        header: '',
        align: 'right',
        accessor: (row) => <ContractSignerRowActions signer={row} onEdit={onEdit} />,
      },
    ],
    [onEdit],
  );

  return (
    <Table
      // Darker outer edge than the shared default so the list reads as a distinct
      // surface against the page background (matches the user roster).
      className="border-secondary-400"
      columns={columns}
      data={signers}
      keyExtractor={(row) => row.id}
      isLoading={isLoading}
      emptyState={emptyState}
      mobileTitle="full_name"
    />
  );
}
