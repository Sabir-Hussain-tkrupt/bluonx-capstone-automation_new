import { useMemo, useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Select } from '@/components/ui/Select';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import type { BudgetLine, BudgetStatus } from '@/features/budgets/types';
import { formatCents, formatMoney, toCents } from '@/features/budgets/utils/money';
import type { Invoice } from '../api/invoice.api';
import { useCategoriseInvoice } from '../hooks/useInvoices';

interface CategoriseInvoiceModalProps {
  projectId: string;
  invoice: Invoice | null;
  lines: BudgetLine[];
  budgetStatus: BudgetStatus;
  onClose: () => void;
}

/**
 * Assign an invoice to an internal T&M line and start payment approval. The
 * preview mirrors fn_categorise_internal_invoice: allowance = line budget −
 * invoices already categorised to it; on a baselined budget anything above that
 * becomes a variance funded from contingency.
 */
export function CategoriseInvoiceModal({ projectId, invoice, lines, budgetStatus, onClose }: CategoriseInvoiceModalProps) {
  const { toast } = useToast();
  const categorise = useCategoriseInvoice(projectId);
  const [lineId, setLineId] = useState('');
  const [error, setError] = useState<string | null>(null);

  const tmLines = useMemo(() => lines.filter((l) => l.line_type === 'internal_tm'), [lines]);
  const selected = tmLines.find((l) => l.id === lineId) ?? null;

  const allowanceCents = selected ? Math.max(toCents(selected.budget_amount) - toCents(selected.invoiced), 0) : 0;
  const overageCents = selected && invoice ? Math.max(toCents(invoice.amount) - allowanceCents, 0) : 0;

  const close = () => {
    if (categorise.isPending) return;
    setLineId('');
    setError(null);
    onClose();
  };

  const submit = () => {
    if (!invoice || !lineId) return;
    setError(null);
    categorise.mutate(
      { invoiceId: invoice.id, lineId },
      {
        onSuccess: (res) => {
          const over = toCents(res.overage);
          toast({
            variant: 'success',
            message:
              over > 0 && res.variance_id
                ? `Sent for approval. ${formatCents(over)} over the allowance became a variance funded from contingency.`
                : 'Invoice categorised and sent for payment approval.',
          });
          setLineId('');
          onClose();
        },
        onError: (e) => setError(errorMessage(e, 'Could not categorise the invoice.')),
      },
    );
  };

  return (
    <Modal
      isOpen={!!invoice}
      onClose={close}
      title="Categorise invoice"
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={close} disabled={categorise.isPending}>Cancel</Button>
          <Button onClick={submit} isLoading={categorise.isPending} disabled={!lineId}>Send for approval</Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger" title="Could not categorise">{error}</Alert>}
        <p className="text-sm text-secondary-600">
          {invoice?.payee_name ?? invoice?.vendor_name}
          {invoice?.invoice_number ? ` · ${invoice.invoice_number}` : ''} ·{' '}
          <strong className="text-secondary-900">{formatMoney(invoice?.amount)}</strong>
        </p>
        {tmLines.length === 0 ? (
          <Alert variant="warning" title="No internal T&M lines">
            Add an internal T&amp;M line to the budget (or a task with bid type “Internal”) first.
          </Alert>
        ) : (
          <FormField label="Budget line" htmlFor="invoice-line" required>
            <Select
              id="invoice-line"
              value={lineId}
              onChange={(e) => setLineId(e.target.value)}
              placeholder="Select an internal T&M line…"
              options={tmLines.map((l) => ({
                value: l.id,
                label: `${l.name} — ${formatCents(Math.max(toCents(l.budget_amount) - toCents(l.invoiced), 0))} left`,
              }))}
            />
          </FormField>
        )}
        {selected && overageCents > 0 && (
          <Alert variant="warning" title="Invoice is over the line's allowance">
            {budgetStatus === 'baselined' ? (
              <>
                This invoice is {formatMoney(invoice?.amount)} and the line has {formatCents(allowanceCents)} left.
                A <strong>{formatCents(overageCents)}</strong> variance will be created, funded from contingency, and
                sent for approval with the invoice.
              </>
            ) : (
              <>
                The line has {formatCents(allowanceCents)} left. Because the budget is still a draft, no variance is
                created — raise the line amount before baselining.
              </>
            )}
          </Alert>
        )}
      </div>
    </Modal>
  );
}
