import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Modal } from '@/components/ui/Modal';
import { TextInput } from '@/components/ui/TextInput';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { formatMoney, parseMoneyInput } from '@/features/budgets/utils/money';
import { useRequestTopUp } from '../hooks/useContingency';
import { textareaClass } from './shared';

interface TopUpRequestModalProps {
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
}

/** Task 3.5 — ask for more contingency. Only an executive can approve it. */
export function TopUpRequestModal({ projectId, isOpen, onClose }: TopUpRequestModalProps) {
  const { toast } = useToast();
  const request = useRequestTopUp(projectId);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [errors, setErrors] = useState<{ amount?: string; reason?: string }>({});

  const close = () => {
    if (request.isPending) return;
    setAmount('');
    setReason('');
    setErrors({});
    onClose();
  };

  const submit = () => {
    const parsed = parseMoneyInput(amount);
    const next: typeof errors = {};
    if (!parsed || Number(parsed) <= 0) next.amount = 'Enter an amount greater than $0.';
    if (!reason.trim()) next.reason = 'Explain why more contingency is needed.';
    setErrors(next);
    if (next.amount || next.reason || !parsed) return;

    request.mutate(
      { amount: parsed, reason: reason.trim() },
      {
        onSuccess: () => {
          toast({ variant: 'success', message: `Top-up of ${formatMoney(parsed)} requested. The executives have been notified.` });
          setAmount('');
          setReason('');
          onClose();
        },
        onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not request the top-up.') }),
      },
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title="Request contingency top-up"
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={close} disabled={request.isPending}>Cancel</Button>
          <Button onClick={submit} isLoading={request.isPending}>Send request</Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-secondary-600">
          An executive approves or rejects the request. Once approved, the amount is added to this project's
          contingency and to its total budget, recorded as its own entry in the ledger, and finance and sales are
          notified.
        </p>
        <FormField label="Amount" htmlFor="top-up-amount" required error={errors.amount}>
          <TextInput
            id="top-up-amount"
            inputMode="decimal"
            placeholder="25,000.00"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </FormField>
        <FormField label="Reason" htmlFor="top-up-reason" required error={errors.reason}>
          <textarea
            id="top-up-reason"
            rows={4}
            maxLength={2000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className={textareaClass}
            placeholder="e.g. Grading came in $40,000 over budget after rock was found on site."
          />
        </FormField>
      </div>
    </Modal>
  );
}
