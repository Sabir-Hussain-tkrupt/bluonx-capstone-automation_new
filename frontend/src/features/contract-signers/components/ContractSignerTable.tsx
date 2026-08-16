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
  // The row-action menu opens downward and has no collision-flip, so on the last
  // rows it would be clipped by the Table's overflow container. Flip those rows'
  // menus upward (they have empty space above). Scoped to this table only.
  const flipUpIds = useMemo(() => {
    const FLIP_LAST_N = 2;
    return new Set(
      signers.slice(Math.max(0, signers.length - FLIP_LAST_N)).map((s) => s.id),
    );
  }, [signers]);

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
        accessor: (row) => (
          <ContractSignerRowActions
            signer={row}
            onEdit={onEdit}
            openUpward={flipUpIds.has(row.id)}
          />
        ),
      },
    ],
    [onEdit, flipUpIds],
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
