import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Modal } from '@/components/ui/Modal';
import { TextInput } from '@/components/ui/TextInput';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { formatMoney, parseMoneyInput } from '@/features/budgets/utils/money';
import { useDecideTopUp } from '../hooks/useContingency';
import type { TopUpRequest } from '../types';
import { formatDateTime, textareaClass } from './shared';

interface TopUpDecisionModalProps {
  projectId: string;
  request: TopUpRequest;
  onClose: () => void;
}

/**
 * Task 3.5 — executive approval. The amount may be lowered before approving.
 * Mount it with `key={request.id}` so each request starts with a fresh form.
 */
export function TopUpDecisionModal({ projectId, request, onClose }: TopUpDecisionModalProps) {
  const { toast } = useToast();
  const decide = useDecideTopUp(projectId);
  const [amount, setAmount] = useState(() => Number(request.requested_amount).toFixed(2));
  const [note, setNote] = useState('');
  const [error, setError] = useState<string>();
  const [pending, setPending] = useState<'approve' | 'reject' | null>(null);

  const submit = (approve: boolean) => {
    let approved: string | null = null;
    if (approve) {
      approved = parseMoneyInput(amount);
      if (!approved || Number(approved) <= 0) {
        setError('Enter an amount greater than $0.');
        return;
      }
    } else if (!note.trim()) {
      setError(undefined);
      toast({ variant: 'warning', message: 'Add a note so the requester knows why it was rejected.' });
      return;
    }
    setPending(approve ? 'approve' : 'reject');
    decide.mutate(
      { bucketId: request.id, body: { approve, approved_amount: approved, note: note.trim() || null } },
      {
        onSuccess: () => {
          toast({
            variant: 'success',
            message: approve
              ? `Top-up of ${formatMoney(approved)} approved. Finance and sales have been notified.`
              : 'Top-up rejected.',
          });
          setPending(null);
          onClose();
        },
        onError: (e) => {
          setPending(null);
          toast({ variant: 'danger', message: errorMessage(e, 'Could not record the decision.') });
        },
      },
    );
  };

  return (
    <Modal
      isOpen
      onClose={() => !decide.isPending && onClose()}
      title="Contingency top-up request"
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={decide.isPending}>Cancel</Button>
          <Button variant="outline" onClick={() => submit(false)} isLoading={pending === 'reject'} disabled={decide.isPending}>
            Reject
          </Button>
          <Button onClick={() => submit(true)} isLoading={pending === 'approve'} disabled={decide.isPending}>
            Approve
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <dl className="grid grid-cols-1 gap-2 rounded-lg border border-secondary-200 bg-secondary-50 px-3 py-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-secondary-500">Requested</dt>
            <dd className="font-medium tabular-nums text-secondary-900">{formatMoney(request.requested_amount)}</dd>
          </div>
          <div>
            <dt className="text-secondary-500">By</dt>
            <dd className="text-secondary-900">
              {request.requested_by_name ?? '—'} · {formatDateTime(request.requested_at)}
            </dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-secondary-500">Reason</dt>
            <dd className="whitespace-pre-wrap text-secondary-900">{request.reason}</dd>
          </div>
        </dl>
        <FormField
          label="Amount to approve"
          htmlFor="top-up-approve-amount"
          error={error}
          hint="Added to contingency and to the project's total budget."
        >
          <TextInput
            id="top-up-approve-amount"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </FormField>
        <FormField label="Note" htmlFor="top-up-note" hint="Required when rejecting. Shared with the requester.">
          <textarea
            id="top-up-note"
            rows={3}
            maxLength={2000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className={textareaClass}
          />
        </FormField>
      </div>
    </Modal>
  );
}
