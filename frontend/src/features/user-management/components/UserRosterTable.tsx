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

  // The row-action menu opens downward and has no collision-flip, so on the last
  // rows it would be clipped by the Table's overflow container. Flip those rows'
  // menus upward (they have empty space above). Scoped to this table only.
  const flipUpIds = useMemo(() => {
    const FLIP_LAST_N = 2;
    return new Set(users.slice(Math.max(0, users.length - FLIP_LAST_N)).map((u) => u.id));
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
        accessor: (row) => (
          <UserRowActions
            user={row}
            currentUserId={currentUserId}
            openUpward={flipUpIds.has(row.id)}
          />
        ),
      },
    ],
    [nameById, currentUserId, flipUpIds],
  );

  return (
    <Table
      // Darker outer edge than the shared default so the list reads as a distinct
      // surface against the page background (matches the vendors/list pages).
      className="border-secondary-400"
      columns={columns}
      data={users}
      keyExtractor={(row) => row.id}
      isLoading={isLoading}
      emptyState={emptyState}
      mobileTitle="full_name"
    />
  );
}
