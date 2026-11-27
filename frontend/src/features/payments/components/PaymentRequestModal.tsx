import { useState } from 'react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import { FormField } from '@/components/ui/FormField';
import { Modal } from '@/components/ui/Modal';
import { RadioGroup } from '@/components/ui/RadioGroup';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TextInput } from '@/components/ui/TextInput';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { textareaClass, parsePercentInput } from '@/features/contingency/components/shared';
import { formatCents, formatMoney, toCents } from '@/features/budgets/utils/money';
import type { BudgetLine } from '@/features/budgets/types';
import { PAYMENT_STATUS, kindLabel } from '../constants';
import { useLinePayments, useRequestPayment } from '../hooks/usePayments';
import type { PaymentKind } from '../types';
import { PaymentDetailModal } from './PaymentDetailModal';

/** Task 6.1 — "Approve for payment" on a bid line: full, progress or retainage. */
export function PaymentRequestModal({ line, onClose }: { line: BudgetLine; onClose: () => void }) {
  const { toast } = useToast();
  const query = useLinePayments(line.id);
  const request = useRequestPayment(line.id);
  const [kind, setKind] = useState<PaymentKind>('full');
  const [percent, setPercent] = useState('');
  const [note, setNote] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string>();
  const [openId, setOpenId] = useState<string | null>(null);

  if (openId) return <PaymentDetailModal paymentId={openId} onClose={() => setOpenId(null)} />;

  const o = query.data;
  const remaining = o ? toCents(o.remaining) : 0;
  const total = o ? toCents(o.total) : 0;
  const pct = kind === 'progress' ? parsePercentInput(percent) : null;
  const grossCents =
    kind === 'full' ? remaining : kind === 'progress' && pct ? Math.round((total * Number(pct)) / 100) : 0;
  const retCents = kind === 'retainage_release' || !o?.retainage_percent ? 0 : Math.round((grossCents * Number(o.retainage_percent)) / 100);

  const submit = () => {
    if (kind === 'progress' && !pct) return setError('Enter a % above 0 and up to 100.');
    setError(undefined);
    request.mutate(
      { payment_kind: kind, progress_percent: pct, note: note.trim() || null, confirm_work_complete: confirmed },
      {
        onSuccess: (row) => {
          toast({
            variant: 'success',
            message:
              row.status === 'approved'
                ? 'Approved for payment. Finance, the trade and the land team are being told.'
                : row.status === 'pending'
                  ? 'Payment requested. A field manager confirms the work next.'
                  : `Sent to ${row.status === 'awaiting_executive' ? 'an executive' : (row.routed_to_name ?? 'a manager')} for approval.`,
          });
          onClose();
        },
        onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not request the payment.') }),
      },
    );
  };

  const blocked = o && (o.open_request || !o.has_award);
  return (
    <Modal
      isOpen
      onClose={() => !request.isPending && onClose()}
      title="Approve for payment"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={request.isPending}>Cancel</Button>
          {!blocked && (
            <Button onClick={submit} isLoading={request.isPending}>
              {confirmed ? 'Confirm and approve' : 'Request payment'}
            </Button>
          )}
        </>
      }
    >
      {query.isLoading ? (
        <Skeleton height="240px" />
      ) : !o ? (
        <Alert variant="danger" title="Could not load the line">{errorMessage(query.error, 'Please try again.')}</Alert>
      ) : (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-3 rounded-lg border border-secondary-200 bg-secondary-50 px-3 py-2 text-sm md:grid-cols-4">
            <Item label="Contract" value={formatMoney(o.total)} />
            <Item label="Already approved / requested" value={formatMoney(o.requested)} />
            <Item label="Left to pay" value={formatMoney(o.remaining)} />
            <Item label="Retainage" value={o.retainage_percent ? `${Number(o.retainage_percent)}% · ${formatMoney(o.retainage_held)} held` : 'None'} />
          </dl>

          {!o.has_award ? (
            <Alert variant="info" title="No award yet">This line has no award, so there is nothing to pay.</Alert>
          ) : o.open_request ? (
            <Alert variant="info" title="A payment is already waiting">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <span>
                  {kindLabel(o.open_request)} of {formatMoney(o.open_request.amount)}:{' '}
                  {PAYMENT_STATUS[o.open_request.status]?.label}.
                </span>
                <Button size="sm" variant="outline" onClick={() => setOpenId(o.open_request!.id)}>Open</Button>
              </div>
            </Alert>
          ) : (
            <>
              <RadioGroup
                name="pay-kind"
                legend="Payment"
                value={kind}
                onChange={(v) => setKind(v as PaymentKind)}
                options={[
                  { value: 'full', label: 'Pay on completion', description: `What is left: ${formatMoney(o.remaining)}` },
                  { value: 'progress', label: 'Progress payment', description: 'A % of the contract, e.g. 50% of grading' },
                  {
                    value: 'retainage_release',
                    label: 'Release retainage',
                    description: `${formatMoney(o.retainage_held)} held. Once the whole line is paid.`,
                    disabled: toCents(o.retainage_held) <= 0 || remaining > 0,
                  },
                ]}
              />
              {kind === 'progress' && (
                <FormField label="Progress %" htmlFor="pay-pct" required error={error}>
                  <TextInput id="pay-pct" inputMode="decimal" placeholder="50" value={percent} onChange={(e) => setPercent(e.target.value)} />
                </FormField>
              )}
              {kind !== 'retainage_release' && grossCents > 0 && (
                <p className="text-sm text-secondary-600">
                  Work value {formatCents(grossCents)}
                  {retCents > 0 && ` − retainage ${formatCents(retCents)}`} = <strong>{formatCents(grossCents - retCents)}</strong> to pay.
                </p>
              )}
              <FormField label="Note" htmlFor="pay-note" hint="Optional. Shown to the approvers.">
                <textarea id="pay-note" rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} className={textareaClass} />
              </FormField>
              {o.can_confirm && (
                <Checkbox
                  label="I confirm the work is complete, and approve"
                  description="Leave unticked to send it to the field manager to confirm."
                  checked={confirmed}
                  onChange={() => setConfirmed((v) => !v)}
                />
              )}
            </>
          )}

          {o.history.length > 0 && (
            <div>
              <h4 className="mb-2 text-sm font-semibold text-secondary-900">Payments on this line</h4>
              <ul className="divide-y divide-secondary-100 rounded-lg border border-secondary-200 text-sm">
                {o.history.map((h) => (
                  <li key={h.id} className="flex items-center justify-between gap-2 px-3 py-2">
                    <button type="button" className="text-left hover:text-primary-600 hover:underline" onClick={() => setOpenId(h.id)}>
                      {kindLabel(h)} · {formatMoney(h.amount)}
                      {h.po_number && <span className="ml-2 text-xs text-secondary-500">PO {h.po_number}</span>}
                    </button>
                    <StatusBadge status={PAYMENT_STATUS[h.status]?.label ?? h.status} variant={PAYMENT_STATUS[h.status]?.variant} size="sm" />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-secondary-500">{label}</dt>
      <dd className="tabular-nums text-secondary-900">{value}</dd>
    </div>
  );
}
