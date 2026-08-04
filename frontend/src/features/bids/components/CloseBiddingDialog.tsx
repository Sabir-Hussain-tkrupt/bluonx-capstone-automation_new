import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast/useToast';
import { useCloseBidding } from '@/features/bids/hooks/useCloseBidding';

interface CloseBiddingDialogProps {
  isOpen: boolean;
  onClose: () => void;
  bidPackageId: string;
  taskId: string;
  /** Invitations on the package. */
  totalInvited: number;
  /** Invitations whose vendor has submitted a bid. */
  submittedCount: number;
}

/**
 * Confirmation for the PM's early "close bidding" action (open -> evaluating).
 *
 * Closing with zero submitted bids is unrecoverable: nothing sets a package
 * back to 'open', so the round ends with nothing to award and no way to
 * reopen. That case gets its own copy and a danger-styled confirm rather than
 * the routine primary one. It is a warning, not a block — ending a dead round
 * is a legitimate thing for a PM to want.
 */
export function CloseBiddingDialog({
  isOpen,
  onClose,
  bidPackageId,
  taskId,
  totalInvited,
  submittedCount,
}: CloseBiddingDialogProps) {
  const { toast } = useToast();
  const mutation = useCloseBidding(bidPackageId, taskId);

  const noBids = submittedCount === 0;
  const outstanding = totalInvited - submittedCount;

  const handleConfirm = () => {
    mutation.mutate(undefined, {
      onSuccess: () => {
        toast({
          variant: 'success',
          message: 'Bidding closed. The package is now under evaluation.',
        });
        onClose();
      },
      onError: (err) => {
        toast({
          variant: 'danger',
          message:
            (err as { message?: string })?.message || 'Failed to close bidding.',
        });
      },
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={mutation.isPending ? () => {} : onClose}
      title={noBids ? 'Close bidding with no bids?' : 'Close bidding'}
      size="sm"
      closeOnOverlayClick={!mutation.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
            Keep open
          </Button>
          <Button
            variant={noBids ? 'danger' : 'primary'}
            onClick={handleConfirm}
            isLoading={mutation.isPending}
          >
            Close bidding
          </Button>
        </>
      }
    >
      {noBids ? (
        <div className="space-y-2 text-sm text-secondary-600">
          <p>
            <strong>No vendor has submitted a bid yet</strong>, so this round will
            have nothing to award.
          </p>
          <p>
            Closing cannot be undone and the package cannot be reopened. If you
            are waiting on vendors, keep it open until the deadline instead.
          </p>
        </div>
      ) : (
        <p className="text-sm text-secondary-600">
          This stops new bids immediately and moves the package to evaluation.{' '}
          <strong>
            {outstanding} of {totalInvited}
          </strong>{' '}
          invited vendor{outstanding === 1 ? '' : 's'} have not submitted yet.
          Vendors with an in-flight revision request can still submit until their
          revision deadline.
        </p>
      )}
    </Modal>
  );
}
