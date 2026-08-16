import { useState } from 'react';
import { MoreHorizontal, Pencil, UserCheck, UserX } from 'lucide-react';
import { DropdownMenu, DropdownMenuItem, IconButton } from '@/components/ui';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { useUpdateContractSigner } from '../hooks/useContractSignerMutations';
import type { ContractSigner } from '../types';

interface ContractSignerRowActionsProps {
  signer: ContractSigner;
  onEdit: (signer: ContractSigner) => void;
  /**
   * Open the menu above the trigger instead of below. Set for the last rows so
   * the panel is not clipped by the Table's overflow container (the menu has no
   * collision-flip of its own). Scoped to this feature only.
   */
  openUpward?: boolean;
}

/**
 * Per-row action menu for the signer roster.
 *
 * There is no delete: revocation is `is_active = false`, and `awards.signer_id`
 * is ON DELETE RESTRICT because issued contracts reference the choice. The
 * last-signer guard is deliberately NOT mirrored client-side (the client cannot
 * know the live active count) — that attempt hits the API and surfaces its 409.
 */
export function ContractSignerRowActions({
  signer,
  onEdit,
  openUpward = false,
}: ContractSignerRowActionsProps) {
  const { toast } = useToast();
  const updateSigner = useUpdateContractSigner();

  const [confirmDeactivate, setConfirmDeactivate] = useState(false);

  function onError(fallback: string) {
    return (error: unknown) =>
      toast({
        variant: 'danger',
        title: 'Action failed',
        message: errorMessage(error, fallback),
      });
  }

  function handleReactivate() {
    updateSigner.mutate(
      { id: signer.id, patch: { is_active: true } },
      {
        onSuccess: () =>
          toast({
            variant: 'success',
            title: 'Signer reactivated',
            message: `${signer.full_name} can be selected on new awards again.`,
          }),
        onError: onError('Could not reactivate the signer.'),
      },
    );
  }

  function handleDeactivate() {
    updateSigner.mutate(
      { id: signer.id, patch: { is_active: false } },
      {
        onSuccess: () => {
          toast({
            variant: 'success',
            title: 'Signer deactivated',
            message: `${signer.full_name} can no longer be selected on new awards.`,
          });
          setConfirmDeactivate(false);
        },
        onError: (error) => {
          onError('Could not deactivate the signer.')(error);
          setConfirmDeactivate(false);
        },
      },
    );
  }

  return (
    <>
      <DropdownMenu
        side={openUpward ? 'top' : 'bottom'}
        trigger={
          <IconButton
            icon={<MoreHorizontal className="h-4 w-4" />}
            aria-label={`Actions for ${signer.full_name}`}
          />
        }
      >
        <DropdownMenuItem
          icon={<Pencil className="h-4 w-4" />}
          onClick={() => onEdit(signer)}
        >
          Edit
        </DropdownMenuItem>

        {signer.is_active ? (
          <DropdownMenuItem
            icon={<UserX className="h-4 w-4" />}
            onClick={() => setConfirmDeactivate(true)}
          >
            Deactivate
          </DropdownMenuItem>
        ) : (
          <DropdownMenuItem icon={<UserCheck className="h-4 w-4" />} onClick={handleReactivate}>
            Activate
          </DropdownMenuItem>
        )}
      </DropdownMenu>

      <ConfirmDialog
        isOpen={confirmDeactivate}
        title="Deactivate signer?"
        message={
          <>
            <strong>{signer.full_name}</strong> will no longer appear when awarding a task.
            Contracts already issued in their name are unaffected and still route to them.
          </>
        }
        confirmText="Deactivate"
        isLoading={updateSigner.isPending}
        onConfirm={handleDeactivate}
        onCancel={() => setConfirmDeactivate(false)}
      />
    </>
  );
}
