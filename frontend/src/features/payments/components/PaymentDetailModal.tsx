import { useState } from 'react';
import { FileText } from 'lucide-react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import { FormField } from '@/components/ui/FormField';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { formatDateOnly } from '@/lib/format';
import { formatDateTime, textareaClass } from '@/features/contingency/components/shared';
import { formatMoney } from '@/features/budgets/utils/money';
import { PAYMENT_STATUS, kindLabel } from '../constants';
import { openHandoffDocument, usePayment, usePaymentAction } from '../hooks/usePayments';

type Mode = 'approve' | 'reject' | 'resubmit' | 'cancel' | null;

/** Tasks 6.1 / 6.3 — one payment: who approved it, what is next, its history. */
export function PaymentDetailModal({ paymentId, onClose }: { paymentId: string; onClose: () => void }) {
  const { toast } = useToast();
  const query = usePayment(paymentId);
  const act = usePaymentAction(paymentId);
  const [mode, setMode] = useState<Mode>(null);
  const [note, setNote] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string>();

  const p = query.data;
  const start = (m: Mode) => {
    setMode(m);
    setNote('');
    setConfirmed(false);
    setError(undefined);
  };

  const submit = () => {
    if (!mode || !p) return;
    if (mode === 'reject' && !note.trim()) return setError('Say why it is rejected.');
    if (mode === 'approve' && p.permissions.needs_work_confirmation && !confirmed) {
      return setError('Confirm the work is complete.');
    }
    const body =
      mode === 'reject'
        ? { reason: note.trim() }
        : mode === 'approve'
          ? { note: note.trim() || null, confirm_work_complete: confirmed }
          : { note: note.trim() || null };
    act.mutate(
      { action: mode, body },
      {
        onSuccess: (row) => {
          const messages: Record<string, string> = {
            approved: 'Approved for payment. Finance, the trade and the land team are being told.',
            awaiting_manager: `Sent to ${row.routed_to_name ?? 'a manager'} for the second approval.`,
            awaiting_executive: 'Sent to an executive for approval.',
            rejected: 'Rejected. It goes back to the field manager; the trade is not told.',
            pending: 'Resubmitted for approval.',
            cancelled: 'Payment withdrawn.',
          };
          toast({ variant: 'success', message: messages[row.status] ?? 'Saved.' });
          start(null);
        },
        onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not update the payment.') }),
      },
    );
  };

  const footer = !p ? (
    <Button variant="ghost" onClick={onClose}>Close</Button>
  ) : mode ? (
    <>
      <Button variant="ghost" onClick={() => start(null)} disabled={act.isPending}>Back</Button>
      <Button variant={mode === 'reject' || mode === 'cancel' ? 'danger' : 'primary'} onClick={submit} isLoading={act.isPending}>
        {mode === 'approve' ? p.permissions.approve_label : mode === 'reject' ? 'Reject' : mode === 'resubmit' ? 'Resubmit' : 'Withdraw'}
      </Button>
    </>
  ) : (
    <>
      <Button variant="ghost" onClick={onClose}>Close</Button>
      {p.permissions.can_cancel && <Button variant="outline" onClick={() => start('cancel')}>Withdraw</Button>}
      {p.permissions.can_resubmit && <Button variant="outline" onClick={() => start('resubmit')}>Resubmit</Button>}
      {p.permissions.can_reject && <Button variant="outline" onClick={() => start('reject')}>Reject</Button>}
      {p.permissions.can_approve && <Button onClick={() => start('approve')}>{p.permissions.approve_label}</Button>}
    </>
  );

  return (
    <Modal isOpen onClose={() => !act.isPending && onClose()} title="Payment approval" size="lg" footer={footer}>
      {query.isLoading ? (
        <Skeleton height="260px" />
      ) : !p ? (
        <Alert variant="danger" title="Could not load the payment">
          {errorMessage(query.error, 'Something went wrong. Please try again.')}
        </Alert>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={PAYMENT_STATUS[p.status]?.label ?? p.status} variant={PAYMENT_STATUS[p.status]?.variant} />
            {p.confirmed_by_external && <StatusBadge status="Confirmed by external field manager" variant="info" />}
            {p.executive_required && <StatusBadge status="Executive approval required" variant="info" />}
            {p.po_number && <StatusBadge status={`PO ${p.po_number}`} variant="neutral" />}
          </div>
          <dl className="grid grid-cols-1 gap-3 rounded-lg border border-secondary-200 bg-secondary-50 px-3 py-2 text-sm sm:grid-cols-2">
            <Item label="Project" value={p.project_name} />
            <Item label="Line" value={`${p.line_name}${p.trade_name ? ` · ${p.trade_name}` : ''}`} />
            <Item label="Pay to" value={p.vendor_name ?? '—'} />
            <Item label="Payment" value={kindLabel(p)} />
            <Item label="Work value" value={formatMoney(p.gross_amount)} />
            <Item
              label="Retainage held"
              value={`${formatMoney(p.retainage_amount)}${p.retainage_percent ? ` (${Number(p.retainage_percent)}% per contract)` : ''}`}
            />
            <Item label="Amount to pay" value={formatMoney(p.amount)} />
            <Item label="Contract / invoice" value={p.contract_number ?? p.invoice_number ?? '—'} />
            <Item label="Requested by" value={`${p.requested_by_name ?? '—'} · ${formatDateTime(p.created_at)}`} />
            {p.work_confirmed_by_name && (
              <Item label="Work confirmed by" value={`${p.work_confirmed_by_name} · ${formatDateTime(p.work_confirmed_at)}`} />
            )}
            {p.manager_approved_by_name && (
              <Item label="Manager approval" value={`${p.manager_approved_by_name} · ${formatDateTime(p.manager_approved_at)}`} />
            )}
            {p.executive_approved_by_name && (
              <Item label="Executive approval" value={`${p.executive_approved_by_name} · ${formatDateTime(p.executive_approved_at)}`} />
            )}
            {['awaiting_manager', 'awaiting_executive'].includes(p.status) && (
              <Item label="Waiting for" value={p.routed_to_name ?? (p.status === 'awaiting_executive' ? 'Any executive' : 'Any manager')} />
            )}
            {p.expected_payment_date && <Item label="Expected payment" value={formatDateOnly(p.expected_payment_date)} />}
          </dl>
          {p.comments && <p className="text-sm text-secondary-700">Note: {p.comments}</p>}

          {p.status === 'rejected' && (
            <Alert variant="warning" title={`Rejected by ${p.rejected_by_name ?? '—'}`}>
              {p.rejection_reason} The trade was not told. Fix it and resubmit.
            </Alert>
          )}
          {p.permissions.approve_blocked_reason && (
            <Alert variant="info" title="You cannot approve this payment">{p.permissions.approve_blocked_reason}</Alert>
          )}
          {p.handoff_id && (
            <div className="flex flex-wrap items-center gap-2 text-sm text-secondary-600">
              <span>
                Finance hand-off: {p.handoff_status}
                {p.handoff_delivery_status ? ` (email ${p.handoff_delivery_status})` : ''}
              </span>
              <Button
                size="sm"
                variant="outline"
                leftIcon={<FileText className="h-4 w-4" />}
                onClick={() => openHandoffDocument(p.handoff_id!).catch((e) => toast({ variant: 'danger', message: errorMessage(e, 'The PO is not ready yet.') }))}
              >
                PO record
              </Button>
            </div>
          )}

          {mode && (
            <div className="space-y-3">
              {mode === 'approve' && p.permissions.needs_work_confirmation && (
                <Checkbox
                  label="I confirm the work is complete"
                  description="Required before the first approval."
                  checked={confirmed}
                  onChange={() => setConfirmed((v) => !v)}
                />
              )}
              <FormField label={mode === 'reject' ? 'Reason' : 'Comment'} htmlFor="pay-note" required={mode === 'reject'} error={error}>
                <textarea id="pay-note" rows={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} className={textareaClass} />
              </FormField>
            </div>
          )}

          <div>
            <h4 className="mb-2 text-sm font-semibold text-secondary-900">History</h4>
            <ol className="space-y-2 border-l-2 border-secondary-200 pl-4 text-sm">
              {[...p.history].reverse().map((e) => (
                <li key={e.id}>
                  <div className="font-medium text-secondary-900">{e.label}</div>
                  <div className="text-xs text-secondary-500">{e.actor_name ?? '—'} · {formatDateTime(e.created_at)}</div>
                  {e.note && <div className="text-secondary-700">{e.note}</div>}
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </Modal>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-secondary-500">{label}</dt>
      <dd className="text-secondary-900">{value}</dd>
    </div>
  );
}
