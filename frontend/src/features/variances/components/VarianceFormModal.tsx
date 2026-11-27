import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Modal } from '@/components/ui/Modal';
import { Select } from '@/components/ui/Select';
import { TextInput } from '@/components/ui/TextInput';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { textareaClass } from '@/features/contingency/components/shared';
import { useTrades } from '@/features/trades/hooks/useTrades';
import { assignableTradeOptions } from '@/features/trades/utils/tradeTree';
import { useVendors } from '@/features/vendors/hooks/useVendors';
import type { BudgetLine } from '@/features/budgets/types';
import { formatCents, formatMoney, parseMoneyInput, toCents } from '@/features/budgets/utils/money';
import { useCreateVariance, useUpdateVariance } from '../hooks/useVariances';
import type { Variance } from '../types';

interface VarianceFormModalProps {
  /** Create: the line the variance goes under. */
  parentLine?: BudgetLine;
  /** Create: shown as before → after. */
  contingencyNow?: number | string;
  /** Create: warn when the variance takes contingency below this reserve. */
  reserve?: string | null;
  /** Edit: the variance to change. */
  variance?: Variance;
  onClose: () => void;
}

/** Task 4.1 / 4.2 — create or edit a variance. Mount it with a `key`. */
export function VarianceFormModal({ parentLine, contingencyNow, reserve, variance, onClose }: VarianceFormModalProps) {
  const { toast } = useToast();
  const create = useCreateVariance(parentLine?.id ?? '');
  const update = useUpdateVariance(variance?.id ?? '');
  const { data: trades = [] } = useTrades();
  const { data: vendors } = useVendors({ page: 1, page_size: 100 });
  const pending = create.isPending || update.isPending;
  const fromInvoice = !!variance?.internal_invoice_id;

  const [description, setDescription] = useState(variance?.description ?? '');
  const [tradeChoice, setTradeChoice] = useState<string | null>(variance?.trade_id ?? null);
  const [vendorId, setVendorId] = useState(variance?.vendor_id ?? parentLine?.vendor_id ?? '');
  const [amount, setAmount] = useState(variance ? Number(variance.amount).toFixed(2) : '');
  const [reason, setReason] = useState('');
  const [errors, setErrors] = useState<{ description?: string; trade?: string; amount?: string }>({});

  const activeTrades = trades.filter((t) => t.is_active || t.id === variance?.trade_id);
  const tradeOptions = assignableTradeOptions(activeTrades, variance?.trade_id);
  // Until the user picks one, a new variance takes its line's own trade.
  const lineTrade = parentLine?.trade_name
    ? activeTrades.find((t) => t.name === parentLine.trade_name && tradeOptions.some((o) => o.value === t.id))?.id
    : undefined;
  const tradeId = tradeChoice ?? lineTrade ?? '';

  const vendorOptions = [{ value: '', label: 'No vendor' }, ...(vendors?.items ?? []).map((v) => ({ value: v.id, label: v.company_name }))];
  const currentVendorName = variance?.vendor_name ?? parentLine?.vendor_name;
  if (vendorId && currentVendorName && !vendorOptions.some((o) => o.value === vendorId)) {
    vendorOptions.push({ value: vendorId, label: currentVendorName });
  }

  const parsed = parseMoneyInput(amount);
  const deltaCents = variance && parsed ? toCents(parsed) - toCents(variance.amount) : 0;

  const submit = () => {
    const next: typeof errors = {};
    if (!description.trim()) next.description = 'Describe what was found.';
    if (!tradeId && !fromInvoice) next.trade = 'Select a trade.';
    if (!parsed || Number(parsed) <= 0) next.amount = 'Enter an amount greater than $0.';
    setErrors(next);
    if (Object.keys(next).length || !parsed) return;

    const body = {
      description: description.trim(),
      ...(tradeId ? { trade_id: tradeId } : {}),
      vendor_id: vendorId || null,
      amount: parsed,
    };
    if (variance) {
      update.mutate(
        { ...body, reason: reason.trim() || null },
        {
          onSuccess: () => {
            toast({ variant: 'success', message: 'Variance saved.' });
            onClose();
          },
          onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not save the variance.') }),
        },
      );
    } else {
      create.mutate(body, {
        onSuccess: () => {
          toast({ variant: 'success', message: `Variance of ${formatMoney(parsed)} created from contingency.` });
          onClose();
        },
        onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not create the variance.') }),
      });
    }
  };

  return (
    <Modal
      isOpen
      onClose={() => !pending && onClose()}
      title={variance ? 'Edit variance' : 'Add variance'}
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>Cancel</Button>
          <Button onClick={submit} isLoading={pending}>{variance ? 'Save' : 'Create variance'}</Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-secondary-600">
          Under <strong className="text-secondary-900">{variance?.parent_line_name ?? parentLine?.name}</strong>. The
          amount comes from contingency, so the total budget stays the same. Someone else must approve it for payment.
        </p>
        <FormField label="Description" htmlFor="var-desc" required error={errors.description}>
          <textarea
            id="var-desc"
            rows={3}
            maxLength={2000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className={textareaClass}
            placeholder="e.g. Trade encountered rock; PM approved up to $5,000"
          />
        </FormField>
        <FormField label="Trade" htmlFor="var-trade" required={!fromInvoice} error={errors.trade}>
          <Select
            id="var-trade"
            placeholder="Select a trade"
            options={tradeOptions}
            value={tradeId}
            onChange={(e) => setTradeChoice(e.target.value)}
          />
        </FormField>
        <FormField label="Vendor" htmlFor="var-vendor" hint="Who is paid. Starts with the vendor awarded on the line.">
          <Select id="var-vendor" options={vendorOptions} value={vendorId} onChange={(e) => setVendorId(e.target.value)} />
        </FormField>
        <FormField
          label={variance ? 'Amount' : 'Estimated amount'}
          htmlFor="var-amount"
          required
          error={errors.amount}
          hint={fromInvoice ? 'Set by the invoice, so it cannot be changed here.' : undefined}
        >
          <TextInput
            id="var-amount"
            inputMode="decimal"
            placeholder="5,000.00"
            value={amount}
            disabled={fromInvoice}
            onChange={(e) => setAmount(e.target.value)}
          />
        </FormField>
        {!variance && parsed && contingencyNow != null && (
          <p className="text-sm text-secondary-600">
            Contingency: {formatMoney(contingencyNow)} → {formatCents(toCents(contingencyNow) - toCents(parsed))}
          </p>
        )}
        {!variance && parsed && contingencyNow != null && reserve != null &&
          toCents(contingencyNow) - toCents(parsed) < toCents(reserve) && (
            <p className="text-sm text-warning-700">
              This takes contingency below the {formatMoney(reserve)} long-tail reserve, so an alert will be raised.
            </p>
          )}
        {variance && deltaCents !== 0 && (
          <p className="text-sm text-secondary-600">
            {deltaCents < 0
              ? `${formatCents(-deltaCents)} returns to contingency.`
              : `${formatCents(deltaCents)} more comes out of contingency.`}
            {variance.payment_status === 'awaiting_manager' && ' The approval starts again.'}
          </p>
        )}
        {variance && (
          <FormField label="Reason for the change" htmlFor="var-reason" hint="Optional. Kept in the history.">
            <TextInput id="var-reason" maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
          </FormField>
        )}
      </div>
    </Modal>
  );
}
