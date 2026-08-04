import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast/useToast';
import { useCancelBidPackage } from '@/features/bids/hooks/useCancelBidPackage';

interface CancelBidPackageDialogProps {
  isOpen: boolean;
  onClose: () => void;
  bidPackageId: string;
  taskId: string;
  /** Invitations whose vendor has submitted a bid. */
  submittedCount: number;
  /** Pending revision requests on this package — cancelled along with it. */
  pendingRevisionCount: number;
}

/**
 * Confirmation for voiding a bidding round.
 *
 * Distinct from closing: closing moves to evaluation and keeps bids awardable,
 * cancelling voids the round entirely. Nothing reopens a package, so this is
 * irreversible — the copy says so plainly, and it warns rather than blocks when
 * bids or pending revisions would be discarded, since voiding a round with a
 * wrong scope is a legitimate thing to need.
 */
export function CancelBidPackageDialog({
  isOpen,
  onClose,
  bidPackageId,
  taskId,
  submittedCount,
  pendingRevisionCount,
}: CancelBidPackageDialogProps) {
  const { toast } = useToast();
  const mutation = useCancelBidPackage(bidPackageId, taskId);

  const hasBids = submittedCount > 0;
  const hasPendingRevisions = pendingRevisionCount > 0;

  const handleConfirm = () => {
    mutation.mutate(undefined, {
      onSuccess: () => {
        toast({
          variant: 'success',
          message: 'Bid package cancelled. This round is now void.',
        });
        onClose();
      },
      onError: (err) => {
        toast({
          variant: 'danger',
          message:
            (err as { message?: string })?.message ||
            'Failed to cancel bid package.',
        });
      },
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={mutation.isPending ? () => {} : onClose}
      title="Cancel bid package"
      size="sm"
      closeOnOverlayClick={!mutation.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
            Keep package
          </Button>
          <Button
            variant="danger"
            onClick={handleConfirm}
            isLoading={mutation.isPending}
          >
            Cancel bid package
          </Button>
        </>
      }
    >
      <div className="space-y-2 text-sm text-secondary-600">
        <p>
          This voids the round. Vendors lose access immediately, and the package
          <strong> cannot be reopened</strong>.
        </p>
        {hasBids && (
          <p>
            <strong>
              {submittedCount} submitted bid{submittedCount === 1 ? '' : 's'}
            </strong>{' '}
            will be kept as history but can no longer be awarded.
          </p>
        )}
        {hasPendingRevisions && (
          <p>
            {pendingRevisionCount} pending revision request
            {pendingRevisionCount === 1 ? '' : 's'} will also be cancelled, and
            those vendors&rsquo; links will stop working.
          </p>
        )}
        <p>You can start a new round for this task afterwards.</p>
      </div>
    </Modal>
  );
}
