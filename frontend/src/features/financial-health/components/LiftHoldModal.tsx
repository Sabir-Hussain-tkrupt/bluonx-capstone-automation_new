import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Modal } from '@/components/ui/Modal';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { textareaClass } from '@/features/contingency/components/shared';
import { useLiftHold } from '../hooks/useFinancialHealth';

/** Task 5.4 — lift a financial hold with a reason. */
export function LiftHoldModal({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const { toast } = useToast();
  const lift = useLiftHold(projectId);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string>();

  const confirm = () => {
    if (!reason.trim()) {
      setError('Say why the hold is lifted.');
      return;
    }
    lift.mutate(reason.trim(), {
      onSuccess: () => {
        toast({ variant: 'success', message: 'Hold lifted. Work can continue.' });
        onClose();
      },
      onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not lift the hold.') }),
    });
  };

  return (
    <Modal
      isOpen
      onClose={() => !lift.isPending && onClose()}
      title="Lift the hold"
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={lift.isPending}>Cancel</Button>
          <Button onClick={confirm} isLoading={lift.isPending}>Lift hold</Button>
        </>
      }
    >
      <FormField
        label="Reason"
        htmlFor="lift-reason"
        required
        error={error}
        hint="For example savings planned elsewhere, or a top-up approved. The project returns to its earlier status."
      >
        <textarea
          id="lift-reason"
          rows={3}
          maxLength={2000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className={textareaClass}
        />
      </FormField>
    </Modal>
  );
}
