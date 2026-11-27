import { useState } from 'react';
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
import { PAYMENT_STATUS, VARIANCE_STATUS_VARIANT } from '../constants';
import { useApproveVariance, useCancelVariance, useRejectVariance, useVariance } from '../hooks/useVariances';
import { VarianceFormModal } from './VarianceFormModal';

interface VarianceDetailModalProps {
  varianceId: string;
  readOnly?: boolean;
  onClose: () => void;
}

type Action = 'approve' | 'reject' | 'cancel';

/** Task 4.3 / 4.4 — one variance: its payment approval and its history. */
export function VarianceDetailModal({ varianceId, readOnly = false, onClose }: VarianceDetailModalProps) {
  const { toast } = useToast();
  const query = useVariance(varianceId);
  const approve = useApproveVariance(varianceId);
  const reject = useRejectVariance(varianceId);
  const cancel = useCancelVariance(varianceId);
  const [action, setAction] = useState<Action | null>(null);
  const [note, setNote] = useState('');
  const [noteError, setNoteError] = useState<string>();
  const [editing, setEditing] = useState(false);
  const [workDone, setWorkDone] = useState(false);

  const v = query.data;
  const busy = approve.isPending || reject.isPending || cancel.isPending;

  if (editing && v) return <VarianceFormModal variance={v} onClose={() => setEditing(false)} />;

  const start = (a: Action | null) => {
    setAction(a);
    setNote('');
    setNoteError(undefined);
    setWorkDone(false);
  };

  const confirm = () => {
    const text = note.trim();
    if (action === 'reject' && !text) {
      setNoteError('Say why it is rejected.');
      return;
    }
    const options = (message: string) => ({
      onSuccess: () => {
        toast({ variant: 'success' as const, message });
        start(null);
      },
      onError: (e: unknown) =>
        toast({ variant: 'danger' as const, message: errorMessage(e, 'Could not update the variance.') }),
    });
    if (action === 'approve' && v?.permissions.needs_work_confirmation && !workDone) {
      setNoteError('Confirm the work is complete.');
      return;
    }
    if (action === 'approve') {
      approve.mutate({ note: text || null, confirm: workDone }, {
        ...options(''),
        onSuccess: (row) => {
          toast({
            variant: 'success',
            message:
              row.status === 'approved'
                ? 'Variance approved for payment.'
                : `Above your approval limit: sent to ${row.routed_to_name ?? 'a manager'} for approval.`,
          });
          start(null);
        },
      });
    } else if (action === 'reject') {
      reject.mutate(text, options('Variance rejected.'));
    } else if (action === 'cancel') {
      cancel.mutate(text || null, options('Variance cancelled. The amount returned to contingency.'));
    }
  };

  const footer =
    !v || readOnly ? (
      <Button variant="ghost" onClick={onClose}>Close</Button>
    ) : action ? (
      <>
        <Button variant="ghost" onClick={() => start(null)} disabled={busy}>Back</Button>
        <Button variant={action === 'approve' ? 'primary' : 'danger'} onClick={confirm} isLoading={busy}>
          {action === 'approve' ? 'Approve for payment' : action === 'reject' ? 'Reject' : 'Cancel variance'}
        </Button>
      </>
    ) : (
      <>
        <Button variant="ghost" onClick={onClose}>Close</Button>
        {v.permissions.can_cancel && <Button variant="outline" onClick={() => start('cancel')}>Cancel variance</Button>}
        {v.permissions.can_edit && <Button variant="outline" onClick={() => setEditing(true)}>Edit</Button>}
        {v.permissions.can_reject && <Button variant="outline" onClick={() => start('reject')}>Reject</Button>}
        {v.permissions.can_approve && <Button onClick={() => start('approve')}>Approve for payment</Button>}
      </>
    );

  return (
    <Modal isOpen onClose={() => !busy && onClose()} title="Variance" size="lg" footer={footer}>
      {query.isLoading ? (
        <Skeleton height="240px" />
      ) : !v ? (
        <Alert variant="danger" title="Could not load the variance">
          {errorMessage(query.error, 'Something went wrong. Please try again.')}
        </Alert>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={v.status} variant={VARIANCE_STATUS_VARIANT[v.status]} />
            {v.status !== 'cancelled' && (
              <StatusBadge
                status={PAYMENT_STATUS[v.payment_status]?.label ?? v.payment_status}
                variant={PAYMENT_STATUS[v.payment_status]?.variant}
              />
            )}
          </div>
          <p className="whitespace-pre-wrap text-secondary-900">{v.description}</p>
          <dl className="grid grid-cols-1 gap-3 rounded-lg border border-secondary-200 bg-secondary-50 px-3 py-2 text-sm sm:grid-cols-2">
            <Item label="Amount" value={formatMoney(v.amount)} />
            <Item label="First estimate" value={formatMoney(v.estimated_amount)} />
            <Item label="Project" value={v.project_name} />
            <Item label="Under line" value={v.parent_line_name} />
            <Item label="Trade" value={v.trade_name ?? '—'} />
            <Item label="Vendor" value={v.vendor_name ?? '—'} />
            <Item label="Created by" value={`${v.created_by_name ?? '—'} · ${formatDateTime(v.created_at)}`} />
            {v.approved_at && (
              <Item label="Approved by" value={`${v.approved_by_name ?? '—'} · ${formatDateTime(v.approved_at)}`} />
            )}
            {v.payment_status === 'awaiting_manager' && (
              <Item
                label="Waiting for"
                value={`${v.routed_to_name ?? 'Any manager'} (first approval: ${v.field_approved_by_name ?? '—'})`}
              />
            )}
            {v.expected_payment_date && (
              <Item label="Expected payment" value={formatDateOnly(v.expected_payment_date)} />
            )}
          </dl>

          {v.status === 'rejected' && (
            <Alert variant="warning" title={`Rejected by ${v.rejected_by_name ?? '—'}`}>
              {v.rejection_reason} The amount stays out of contingency until the variance is edited (which resubmits it)
              or cancelled.
            </Alert>
          )}
          {v.status === 'approved' && (
            <Alert variant="neutral" title="Approved variances are locked">
              If the cost changes again, add a new variance under the line.
            </Alert>
          )}
          {!readOnly && v.permissions.approve_blocked_reason && (
            <Alert variant="info" title="You cannot approve this variance">{v.permissions.approve_blocked_reason}</Alert>
          )}

          {action === 'approve' && v.permissions.needs_work_confirmation && (
            <Checkbox label="I confirm the work is complete" checked={workDone} onChange={() => setWorkDone((x) => !x)} />
          )}
          {action && (
            <FormField
              label={action === 'reject' ? 'Reason' : 'Note'}
              htmlFor="var-note"
              required={action === 'reject'}
              error={noteError}
              hint={action === 'cancel' ? `${formatMoney(v.amount)} returns to contingency.` : undefined}
            >
              <textarea
                id="var-note"
                rows={3}
                maxLength={2000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className={textareaClass}
              />
            </FormField>
          )}

          <div>
            <h4 className="mb-2 text-sm font-semibold text-secondary-900">History</h4>
            <ol className="space-y-2 border-l-2 border-secondary-200 pl-4 text-sm">
              {[...v.history].reverse().map((e) => (
                <li key={e.id}>
                  <div className="font-medium text-secondary-900">
                    {e.label}
                    {e.event_type === 'amount_changed' || e.event_type === 'cancelled'
                      ? `: ${formatMoney(e.amount_before)} → ${formatMoney(e.amount_after)}`
                      : e.amount_after != null && `: ${formatMoney(e.amount_after)}`}
                  </div>
                  <div className="text-xs text-secondary-500">
                    {e.actor_name ?? '—'} · {formatDateTime(e.created_at)}
                  </div>
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
