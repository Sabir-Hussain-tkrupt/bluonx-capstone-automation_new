import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast/useToast';
import { useCancelRevisionRequest } from '@/features/bids/hooks/useCancelRevisionRequest';

interface CancelRevisionDialogProps {
  isOpen: boolean;
  onClose: () => void;
  revisionRequestId: string;
  vendorName: string;
  bidPackageId: string;
}

export function CancelRevisionDialog({
  isOpen,
  onClose,
  revisionRequestId,
  vendorName,
  bidPackageId,
}: CancelRevisionDialogProps) {
  const { toast } = useToast();
  const mutation = useCancelRevisionRequest(bidPackageId);

  const handleConfirm = () => {
    mutation.mutate(revisionRequestId, {
      onSuccess: () => {
        toast({ variant: 'success', message: 'Revision request cancelled.' });
        onClose();
      },
      onError: (err) => {
        toast({
          variant: 'danger',
          message:
            (err as { message?: string })?.message ||
            'Failed to cancel revision request.',
        });
        onClose();
      },
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={mutation.isPending ? () => {} : onClose}
      title="Cancel Revision Request"
      size="sm"
      closeOnOverlayClick={!mutation.isPending}
      footer={
        <>
          <Button
            variant="ghost"
            onClick={onClose}
            disabled={mutation.isPending}
          >
            Keep Request
          </Button>
          <Button
            variant="danger"
            onClick={handleConfirm}
            isLoading={mutation.isPending}
          >
            Cancel Request
          </Button>
        </>
      }
    >
      <p className="text-sm text-secondary-600">
        Cancel this revision request? {vendorName} will not be notified. Their
        original bid remains in play.
      </p>
    </Modal>
  );
}
