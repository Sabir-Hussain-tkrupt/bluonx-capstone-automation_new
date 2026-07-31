import { useState } from 'react';
import {
  MoreHorizontal,
  Send,
  Trash2,
  UserCheck,
  UserCog,
  UserX,
} from 'lucide-react';
import { DropdownMenu, DropdownMenuItem, IconButton } from '@/components/ui';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import {
  useDeleteUser,
  useResendInvite,
  useUpdateUser,
} from '../hooks/useUserMutations';
import type { UserAdminResponse } from '../types';

interface UserRowActionsProps {
  user: UserAdminResponse;
  /** The signed-in admin's id — used to disable self-affecting actions (G1). */
  currentUserId: string | undefined;
}

/**
 * Per-row action menu for the user roster.
 *
 * Self-guard (G1): the current admin's own row disables change-role,
 * deactivate, and delete with an explanatory tooltip, mirroring the backend so
 * the UI never offers what the API returns 409 for. The last-admin guard (G2)
 * is intentionally NOT replicated client-side (the client can't know the live
 * active-admin count) — those attempts hit the API and surface its 409 `detail`.
 */
export function UserRowActions({ user, currentUserId }: UserRowActionsProps) {
  const { toast } = useToast();
  const updateUser = useUpdateUser();
  const resendInvite = useResendInvite();
  const deleteUser = useDeleteUser();

  const [confirm, setConfirm] = useState<'deactivate' | 'delete' | null>(null);

  const isSelf = currentUserId === user.id;
  const isDeleted = user.deleted_at !== null;
  const nextRole = user.role === 'admin' ? 'project_manager' : 'admin';
  const nextRoleLabel = nextRole === 'admin' ? 'Admin' : 'Project Manager';

  function onError(fallback: string) {
    return (error: unknown) =>
      toast({ variant: 'danger', title: 'Action failed', message: errorMessage(error, fallback) });
  }

  function handleChangeRole() {
    updateUser.mutate(
      { id: user.id, patch: { role: nextRole } },
      {
        onSuccess: () =>
          toast({
            variant: 'success',
            title: 'Role updated',
            message: `${user.full_name} is now ${nextRoleLabel}.`,
          }),
        onError: onError('Could not change the role.'),
      },
    );
  }

  function handleReactivate() {
    updateUser.mutate(
      { id: user.id, patch: { is_active: true } },
      {
        onSuccess: () =>
          toast({ variant: 'success', title: 'User reactivated', message: `${user.full_name} can sign in again.` }),
        onError: onError('Could not reactivate the user.'),
      },
    );
  }

  function handleResend() {
    resendInvite.mutate(user.id, {
      onSuccess: () =>
        toast({ variant: 'success', title: 'Invite resent', message: `A new invite was sent to ${user.email}.` }),
      onError: onError('Could not resend the invite.'),
    });
  }

  function handleDeactivate() {
    updateUser.mutate(
      { id: user.id, patch: { is_active: false } },
      {
        onSuccess: () => {
          toast({ variant: 'success', title: 'User deactivated', message: `${user.full_name} can no longer sign in.` });
          setConfirm(null);
        },
        onError: (error) => {
          onError('Could not deactivate the user.')(error);
          setConfirm(null);
        },
      },
    );
  }

  function handleDelete() {
    deleteUser.mutate(user.id, {
      onSuccess: () => {
        toast({ variant: 'success', title: 'User deleted', message: `${user.full_name} has been removed.` });
        setConfirm(null);
      },
      onError: (error) => {
        onError('Could not delete the user.')(error);
        setConfirm(null);
      },
    });
  }

  return (
    <>
      <DropdownMenu
        trigger={<IconButton icon={<MoreHorizontal className="h-4 w-4" />} aria-label={`Actions for ${user.full_name}`} />}
      >
        <DropdownMenuItem
          icon={<UserCog className="h-4 w-4" />}
          disabled={isSelf}
          onClick={handleChangeRole}
        >
          {isSelf ? (
            <span title="You cannot change your own role.">Change role to {nextRoleLabel}</span>
          ) : (
            <>Change role to {nextRoleLabel}</>
          )}
        </DropdownMenuItem>

        {user.status === 'pending' && (
          <DropdownMenuItem icon={<Send className="h-4 w-4" />} onClick={handleResend}>
            Resend invite
          </DropdownMenuItem>
        )}

        {user.is_active ? (
          <DropdownMenuItem
            icon={<UserX className="h-4 w-4" />}
            disabled={isSelf}
            onClick={() => setConfirm('deactivate')}
          >
            {isSelf ? (
              <span title="You cannot deactivate your own account.">Deactivate</span>
            ) : (
              <>Deactivate</>
            )}
          </DropdownMenuItem>
        ) : (
          !isDeleted && (
            <DropdownMenuItem icon={<UserCheck className="h-4 w-4" />} onClick={handleReactivate}>
              Reactivate
            </DropdownMenuItem>
          )
        )}

        {!isDeleted && (
          <DropdownMenuItem
            icon={<Trash2 className="h-4 w-4" />}
            destructive
            disabled={isSelf}
            onClick={() => setConfirm('delete')}
          >
            {isSelf ? (
              <span title="You cannot delete your own account.">Delete user</span>
            ) : (
              <>Delete user</>
            )}
          </DropdownMenuItem>
        )}
      </DropdownMenu>

      <ConfirmDialog
        isOpen={confirm === 'deactivate'}
        title="Deactivate user?"
        message={
          <>
            <strong>{user.full_name}</strong> will be signed out and blocked from signing in until
            reactivated.
          </>
        }
        confirmText="Deactivate"
        isLoading={updateUser.isPending}
        onConfirm={handleDeactivate}
        onCancel={() => setConfirm(null)}
      />

      <ConfirmDialog
        isOpen={confirm === 'delete'}
        title="Delete user?"
        message={
          <>
            <strong>{user.full_name}</strong> will be removed and blocked from signing in. This cannot
            be undone from the app.
          </>
        }
        confirmText="Delete"
        isLoading={deleteUser.isPending}
        onConfirm={handleDelete}
        onCancel={() => setConfirm(null)}
      />
    </>
  );
}
