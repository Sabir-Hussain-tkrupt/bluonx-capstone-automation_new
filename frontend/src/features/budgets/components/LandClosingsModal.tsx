import { useMemo, useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { DatePicker } from '@/components/ui/DatePicker';
import { FormField } from '@/components/ui/FormField';
import { Alert } from '@/components/ui/Alert';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { formatDateOnly } from '@/lib/format';
import { useAddLandClosing, useLandClosings, useUpdateLandClosing } from '../hooks/useBudget';
import type { BudgetLine, LandClosing } from '../types';
import { formatCents, formatMoney, parseMoneyInput, sumCents, toCents } from '../utils/money';

interface LandClosingsModalProps {
  projectId: string;
  line: BudgetLine | null;
  canEdit: boolean;
  onClose: () => void;
}

/**
 * Task 2.3 — phased takedowns under a land line (e.g. 40 of 100 acres now, 60
 * later). Each closing carries acres, amount and a closing date, and feeds cash
 * flow on its own date. A mismatch with the line amount is a warning, not a
 * block: the deal may still be in negotiation.
 */
export function LandClosingsModal({ projectId, line, canEdit, onClose }: LandClosingsModalProps) {
  const { toast } = useToast();
  const { data: allClosings = [], isLoading } = useLandClosings(projectId, !!line);
  const addClosing = useAddLandClosing(projectId);
  const updateClosing = useUpdateLandClosing(projectId);

  const [amount, setAmount] = useState('');
  const [acres, setAcres] = useState('');
  const [date, setDate] = useState('');
  const [closingDates, setClosingDates] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const closings = useMemo(
    () => allClosings.filter((c) => c.budget_line_id === line?.id),
    [allClosings, line?.id],
  );
  const activeTotal = sumCents(closings.filter((c) => c.status !== 'cancelled').map((c) => c.amount));
  const lineCents = toCents(line?.budget_amount);

  const reset = () => {
    setAmount('');
    setAcres('');
    setDate('');
    setFormError(null);
  };

  const handleAdd = () => {
    if (!line) return;
    const parsed = parseMoneyInput(amount);
    if (!parsed) return setFormError('Enter the closing amount, e.g. 160000 or 160000.50.');
    if (!date) return setFormError('Pick the planned closing date.');
    if (acres && !/^\d+(\.\d{1,4})?$/.test(acres.trim())) return setFormError('Acres must be a number.');
    setFormError(null);
    addClosing.mutate(
      { lineId: line.id, body: { amount: parsed, planned_closing_date: date, acres: acres.trim() || null } },
      {
        onSuccess: () => {
          toast({ variant: 'success', message: 'Closing added.' });
          reset();
        },
        onError: (e) => setFormError(errorMessage(e, 'Could not add the closing.')),
      },
    );
  };

  const setStatus = (closing: LandClosing, status: LandClosing['status']) => {
    const actual = closingDates[closing.id];
    if (status === 'closed' && !actual) {
      toast({ variant: 'warning', message: 'Pick the actual closing date first.' });
      return;
    }
    updateClosing.mutate(
      { closingId: closing.id, body: status === 'closed' ? { status, actual_closing_date: actual } : { status } },
      {
        onSuccess: () => toast({ variant: 'success', message: status === 'closed' ? 'Closing recorded.' : 'Closing cancelled.' }),
        onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not update the closing.') }),
      },
    );
  };

  return (
    <Modal isOpen={!!line} onClose={onClose} title={`Phased closings — ${line?.name ?? ''}`} size="xl"
      footer={<Button variant="ghost" onClick={onClose}>Close</Button>}>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="text-secondary-500">
            Land line: <strong className="text-secondary-900">{formatMoney(line?.budget_amount)}</strong>
          </span>
          <span className="text-secondary-300">|</span>
          <span className="text-secondary-500">
            Scheduled closings: <strong className="text-secondary-900">{formatCents(activeTotal)}</strong>
          </span>
        </div>

        {closings.length > 0 && activeTotal !== lineCents && (
          <Alert variant="warning" title="Closings do not add up to the land line">
            The scheduled closings total {formatCents(activeTotal)}, the land line is {formatMoney(line?.budget_amount)}.
          </Alert>
        )}

        <div className="overflow-x-auto rounded-lg border border-secondary-200">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-secondary-200">
                <th className="px-4 py-3 font-medium text-secondary-500">#</th>
                <th className="px-4 py-3 text-right font-medium text-secondary-500">Acres</th>
                <th className="px-4 py-3 text-right font-medium text-secondary-500">Amount</th>
                <th className="px-4 py-3 font-medium text-secondary-500">Planned</th>
                <th className="px-4 py-3 font-medium text-secondary-500">Actual</th>
                <th className="px-4 py-3 font-medium text-secondary-500">Status</th>
                {canEdit && <th className="px-4 py-3 text-right font-medium text-secondary-500">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-secondary-100">
              {isLoading && (
                <tr><td colSpan={7} className="px-4 py-6 text-center text-secondary-500">Loading…</td></tr>
              )}
              {!isLoading && closings.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-6 text-center text-secondary-500">No phased closings yet.</td></tr>
              )}
              {closings.map((c) => (
                <tr key={c.id}>
                  <td className="px-4 py-3 text-secondary-500">{c.closing_sequence}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{c.acres ?? '—'}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{formatMoney(c.amount)}</td>
                  <td className="px-4 py-3">{formatDateOnly(c.planned_closing_date)}</td>
                  <td className="px-4 py-3">
                    {c.status === 'planned' && canEdit ? (
                      <DatePicker
                        size="sm"
                        aria-label={`Actual date for closing ${c.closing_sequence}`}
                        value={closingDates[c.id] ?? ''}
                        onChange={(e) => setClosingDates((d) => ({ ...d, [c.id]: e.target.value }))}
                      />
                    ) : (
                      formatDateOnly(c.actual_closing_date)
                    )}
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={c.status} size="sm" /></td>
                  {canEdit && (
                    <td className="px-4 py-3 text-right">
                      {c.status === 'planned' && (
                        <div className="flex justify-end gap-2">
                          <Button size="sm" variant="outline" onClick={() => setStatus(c, 'closed')}>Mark closed</Button>
                          <Button size="sm" variant="ghost" onClick={() => setStatus(c, 'cancelled')}>Cancel</Button>
                        </div>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {canEdit && (
          <div className="rounded-lg border border-secondary-200 p-4">
            <h4 className="mb-3 text-sm font-semibold text-secondary-900">Add a closing</h4>
            {formError && <Alert variant="danger" title="Could not add closing">{formError}</Alert>}
            <div className="mt-2 grid grid-cols-1 gap-4 sm:grid-cols-4">
              <FormField label="Amount" htmlFor="closing-amount" required>
                <TextInput id="closing-amount" leftAddon="$" inputMode="decimal" value={amount}
                  onChange={(e) => setAmount(e.target.value)} className="tabular-nums" />
              </FormField>
              <FormField label="Acres" htmlFor="closing-acres">
                <TextInput id="closing-acres" inputMode="decimal" value={acres} onChange={(e) => setAcres(e.target.value)} />
              </FormField>
              <FormField label="Planned closing date" htmlFor="closing-date" required>
                <DatePicker id="closing-date" value={date} onChange={(e) => setDate(e.target.value)} />
              </FormField>
              <div className="flex items-end">
                <Button className="w-full" onClick={handleAdd} isLoading={addClosing.isPending}>Add closing</Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
