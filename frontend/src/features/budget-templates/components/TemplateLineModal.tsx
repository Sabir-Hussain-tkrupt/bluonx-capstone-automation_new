import { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Select } from '@/components/ui/Select';
import { TextInput } from '@/components/ui/TextInput';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { useTrades } from '@/features/trades';
import { CASH_BUCKET_OPTIONS, LINE_SUBTYPE_LABELS, LINE_TYPE_LABELS, SUBTYPES_BY_TYPE } from '@/features/budgets/constants';
import { useAddTemplateLine, useUpdateTemplateLine } from '@/features/budgets/hooks/useBudget';
import type { BudgetTemplateLine, CashBucket, LineSubtype, LineType } from '@/features/budgets/types';
import { parseMoneyInput } from '@/features/budgets/utils/money';

const TEMPLATE_TYPES: Exclude<LineType, 'variance'>[] = [
  'land', 'soft_cost', 'permit', 'impact_fee', 'bid_activity', 'internal_tm', 'contingency', 'long_tail',
];

interface TemplateLineModalProps {
  templateId: string;
  isOpen: boolean;
  line: BudgetTemplateLine | null;
  onClose: () => void;
}

export function TemplateLineModal({ templateId, isOpen, line, onClose }: TemplateLineModalProps) {
  if (!isOpen) return null;
  // Mounted per open (keyed by line) so the fields start from the line itself.
  return <TemplateLineForm key={line?.id ?? 'new'} templateId={templateId} line={line} onClose={onClose} />;
}

function TemplateLineForm({ templateId, line, onClose }: Omit<TemplateLineModalProps, 'isOpen'>) {
  const { toast } = useToast();
  const { data: trades = [] } = useTrades();
  const addLine = useAddTemplateLine(templateId);
  const updateLine = useUpdateTemplateLine();
  const isPending = addLine.isPending || updateLine.isPending;

  const [lineType, setLineType] = useState<Exclude<LineType, 'variance'>>(line?.line_type ?? 'soft_cost');
  const [subtype, setSubtype] = useState(line?.line_subtype ?? '');
  const [name, setName] = useState(line?.name ?? '');
  const [section, setSection] = useState(line?.section_name ?? '');
  const [tradeId, setTradeId] = useState(line?.trade_id ?? '');
  const [amount, setAmount] = useState(line?.default_amount != null ? Number(line.default_amount).toFixed(2) : '');
  const [terms, setTerms] = useState(line?.default_payment_terms_days != null ? String(line.default_payment_terms_days) : '');
  const [bucket, setBucket] = useState<CashBucket>(line?.default_cash_bucket ?? 'land');
  const [error, setError] = useState<string | null>(null);

  const isActivity = lineType === 'bid_activity' || lineType === 'internal_tm';
  const subtypes = SUBTYPES_BY_TYPE[lineType] ?? [];

  const close = () => {
    if (!isPending) onClose();
  };

  const save = () => {
    if (!name.trim()) return setError('Enter a name.');
    const parsedAmount = amount.trim() ? parseMoneyInput(amount) : null;
    if (amount.trim() && !parsedAmount) return setError('Default amount must be like 1234.56.');
    if (terms.trim() && (!/^\d{1,3}$/.test(terms.trim()) || Number(terms) > 365)) return setError('Payment terms must be 0–365 days.');
    setError(null);
    const body = {
      line_subtype: (subtype || null) as LineSubtype | null,
      name: name.trim(),
      section_name: section.trim() || null,
      trade_id: isActivity && tradeId ? tradeId : null,
      default_amount: isActivity || lineType === 'contingency' ? null : parsedAmount,
      default_payment_terms_days: terms.trim() ? Number(terms) : null,
      default_cash_bucket: bucket,
    };
    const onError = (e: unknown) => setError(errorMessage(e, 'Could not save the template line.'));
    if (line) {
      updateLine.mutate({ lineId: line.id, body }, {
        onSuccess: () => { toast({ variant: 'success', message: `${body.name} updated.` }); onClose(); },
        onError,
      });
    } else {
      addLine.mutate({ ...body, line_type: lineType }, {
        onSuccess: () => { toast({ variant: 'success', message: `${body.name} added to the template.` }); onClose(); },
        onError,
      });
    }
  };

  return (
    <Modal
      isOpen
      onClose={close}
      title={line ? 'Edit template line' : 'Add template line'}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={close} disabled={isPending}>Cancel</Button>
          <Button onClick={save} isLoading={isPending}>{line ? 'Save changes' : 'Add line'}</Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="danger" title="Could not save">{error}</Alert>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField label="Type" htmlFor="tl-type" required hint={line ? 'The type cannot change; remove and re-add instead.' : undefined}>
            <Select id="tl-type" value={lineType} disabled={!!line}
              onChange={(e) => { setLineType(e.target.value as Exclude<LineType, 'variance'>); setSubtype(''); }}
              options={TEMPLATE_TYPES.map((t) => ({ value: t, label: LINE_TYPE_LABELS[t] }))} />
          </FormField>
          {subtypes.length > 0 && (
            <FormField label="Kind" htmlFor="tl-subtype">
              <Select id="tl-subtype" value={subtype} onChange={(e) => setSubtype(e.target.value)} placeholder="Select…"
                options={subtypes.map((s) => ({ value: s, label: LINE_SUBTYPE_LABELS[s] }))} />
            </FormField>
          )}
          <FormField label="Name" htmlFor="tl-name" required
            hint={isActivity ? 'Tasks with this name (or trade) are placed here.' : undefined}>
            <TextInput id="tl-name" value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField label="Heading" htmlFor="tl-section" hint="e.g. Land, Soft costs, Site work">
            <TextInput id="tl-section" value={section} onChange={(e) => setSection(e.target.value)} />
          </FormField>
          {isActivity && (
            <FormField label="Trade" htmlFor="tl-trade" hint="Tasks of this trade are placed here when no name matches.">
              <Select id="tl-trade" value={tradeId} onChange={(e) => setTradeId(e.target.value)} placeholder="Any trade"
                options={trades.map((t) => ({ value: t.id, label: t.name }))} />
            </FormField>
          )}
          {!isActivity && lineType !== 'contingency' && (
            <FormField label="Default amount" htmlFor="tl-amount" hint="Optional starting amount">
              <TextInput id="tl-amount" leftAddon="$" inputMode="decimal" className="tabular-nums" value={amount}
                onChange={(e) => setAmount(e.target.value)} />
            </FormField>
          )}
          <FormField label="Default payment terms (days)" htmlFor="tl-terms" hint="Empty = 30">
            <TextInput id="tl-terms" inputMode="numeric" value={terms} onChange={(e) => setTerms(e.target.value)} />
          </FormField>
          <FormField label="Cash bucket" htmlFor="tl-bucket">
            <Select id="tl-bucket" value={bucket} onChange={(e) => setBucket(e.target.value as CashBucket)} options={CASH_BUCKET_OPTIONS} />
          </FormField>
        </div>
      </div>
    </Modal>
  );
}
