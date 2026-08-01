import { useState } from 'react';
import { UserPlus } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Alert } from '@/components/ui/Alert';
import { EmptyState } from '@/components/ui/EmptyState';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { useUsers } from '../hooks/useUsers';
import { UserRosterTable } from '../components/UserRosterTable';
import { InviteUserModal } from '../components/InviteUserModal';

export function UserManagementPage() {
  const { profile } = useAuth();
  const { data: users, isLoading, isError, error, refetch } = useUsers();
  const [isInviteOpen, setInviteOpen] = useState(false);

  return (
    <div className="space-y-6">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-secondary-900">User Management</h1>
            <p className="mt-1 text-sm text-secondary-500">
              Invite team members and manage admin / project manager roles.
            </p>
          </div>
          <Button onClick={() => setInviteOpen(true)} leftIcon={<UserPlus className="h-4 w-4" aria-hidden="true" />}>
            Invite user
          </Button>
        </div>
      </div>

      {isError && (
        <Alert
          variant="danger"
          title="Could not load users"
          dismissible
          onDismiss={() => refetch()}
        >
          {errorMessage(error, 'Please try again.')}
        </Alert>
      )}

      <UserRosterTable
        users={users ?? []}
        isLoading={isLoading}
        currentUserId={profile?.id}
        emptyState={
          <EmptyState
            title="No users yet"
            description="Invite your first team member to get started."
          />
        }
      />

      <InviteUserModal isOpen={isInviteOpen} onClose={() => setInviteOpen(false)} />
    </div>
  );
}
