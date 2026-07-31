import { useMemo } from 'react';
import { Table, StatusBadge, type Column } from '@/components/ui';
import type { UserAdminResponse } from '../types';
import { UserRowActions } from './UserRowActions';

const ROLE_LABELS: Record<UserAdminResponse['role'], string> = {
  admin: 'Admin',
  project_manager: 'Project Manager',
};

interface UserRosterTableProps {
  users: UserAdminResponse[];
  isLoading: boolean;
  /** The signed-in admin's id — forwarded to row actions for the G1 self-guard. */
  currentUserId: string | undefined;
  emptyState?: React.ReactNode;
}

export function UserRosterTable({
  users,
  isLoading,
  currentUserId,
  emptyState,
}: UserRosterTableProps) {
  // Resolve invited_by (a UUID) to the inviter's name using the roster itself.
  const nameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const u of users) map.set(u.id, u.full_name);
    return map;
  }, [users]);

  const columns: Column<UserAdminResponse>[] = useMemo(
    () => [
      { id: 'full_name', header: 'Name', accessor: 'full_name' },
      { id: 'email', header: 'Email', accessor: 'email' },
      {
        id: 'role',
        header: 'Role',
        accessor: (row) => ROLE_LABELS[row.role],
      },
      {
        id: 'status',
        header: 'Status',
        accessor: (row) => <StatusBadge status={row.status} minWidth />,
      },
      {
        id: 'invited_by',
        header: 'Invited by',
        accessor: (row) =>
          row.invited_by ? nameById.get(row.invited_by) ?? 'Unknown' : '—',
      },
      {
        id: 'actions',
        header: '',
        align: 'right',
        accessor: (row) => <UserRowActions user={row} currentUserId={currentUserId} />,
      },
    ],
    [nameById, currentUserId],
  );

  return (
    <Table
      columns={columns}
      data={users}
      keyExtractor={(row) => row.id}
      isLoading={isLoading}
      emptyState={emptyState}
      mobileTitle="full_name"
    />
  );
}
