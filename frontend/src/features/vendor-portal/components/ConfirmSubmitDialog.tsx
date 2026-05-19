import { Alert, Button, Modal } from '@/components/ui';
import { formatCurrency } from '../utils/currency';

export interface ConfirmSubmitDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  grandTotal: number;
  projectName: string;
  submitting: boolean;
  isRevision?: boolean;
}

export function ConfirmSubmitDialog({
  isOpen,
  onClose,
  onConfirm,
  grandTotal,
  projectName,
  submitting,
  isRevision = false,
}: ConfirmSubmitDialogProps) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={submitting ? () => {} : onClose}
      title={isRevision ? 'Submit your revised bid?' : 'Submit your bid?'}
      size="md"
      closeOnOverlayClick={!submitting}
      mobileCenter
      footer={
        <>
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={submitting}
          >
            Keep editing
          </Button>
          <Button
            type="button"
            variant="primary"
            onClick={onConfirm}
            isLoading={submitting}
          >
            Confirm & Submit
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <p className="text-sm text-secondary-700">
          You are about to submit your bid for{' '}
          <span className="font-semibold text-secondary-900">{projectName}</span>.
        </p>

        <div className="rounded-lg border border-secondary-200 bg-secondary-50 p-4">
          <p className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
            Grand Total
          </p>
          <p className="mt-1 text-2xl font-bold text-primary-700 tabular-nums">
            {formatCurrency(grandTotal)}
          </p>
        </div>

        <Alert variant="warning" title="Once submitted, this bid cannot be changed">
          If you need to update your bid after submission, contact the BluOnX team.
        </Alert>
      </div>
    </Modal>
  );
}
