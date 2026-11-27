import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Modal } from '@/components/ui/Modal';
import { Select } from '@/components/ui/Select';
import { TextInput } from '@/components/ui/TextInput';
import { useToast } from '@/components/ui/Toast';
import { API_ENDPOINTS } from '@/constants/api';
import { errorMessage } from '@/lib/api';
import { parsePercentInput } from '@/features/contingency/components/shared';
import { parseMoneyInput } from '@/features/budgets/utils/money';
import { BASIS_LABELS } from '../constants';
import { useJurisdictions, useLongTailWrite } from '../hooks/useLongTail';
import type { Jurisdiction, PropertyTax } from '../types';

function useSave(onClose: () => void, ok: string) {
  const { toast } = useToast();
  const write = useLongTailWrite();
  const save = (method: 'post' | 'put' | 'patch', url: string, body: unknown) =>
    write.mutate({ method, url, body }, {
      onSuccess: () => {
        toast({ variant: 'success', message: ok });
        onClose();
      },
      onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not save.') }),
    });
  return { save, busy: write.isPending };
}

function Footer({ onClose, onSave, busy }: { onClose: () => void; onSave: () => void; busy: boolean }) {
  return (
    <>
      <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
      <Button onClick={onSave} isLoading={busy}>Save</Button>
    </>
  );
}

/** Task 7.4 — one tax year: a budget line and the city / county's instalments. */
export function TaxYearModal({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const { data: jurisdictions = [] } = useJurisdictions();
  const { save, busy } = useSave(onClose, 'Tax year saved with its instalments.');
  const [f, setF] = useState({ year: String(new Date().getFullYear() + 1), j: '', basis: 'manual', amount: '', assessed: '', rate: '', sold: '', parcel: '' });
  const [error, setError] = useState<string>();
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF((s) => ({ ...s, [k]: e.target.value }));

  const submit = () => {
    const year = Number(f.year);
    if (!f.j || !Number.isInteger(year)) return setError('Choose the year and the city / county.');
    const amount = f.basis === 'manual' ? parseMoneyInput(f.amount) : null;
    const assessed = f.basis === 'assessed_value' ? parseMoneyInput(f.assessed) : null;
    const rate = f.basis === 'assessed_value' ? f.rate.trim() : null;
    if ((f.basis === 'manual' && !amount) || (f.basis === 'assessed_value' && (!assessed || !rate || Number.isNaN(Number(rate))))) {
      return setError('Enter the amount, or the assessed value and the rate.');
    }
    const sold = f.sold.trim() ? parsePercentInput(f.sold) : '0';
    if (sold == null) return setError('The sold portion is a % from 0 to 100.');
    setError(undefined);
    save('post', API_ENDPOINTS.PROJECT_PROPERTY_TAXES(projectId), {
      tax_year: year, jurisdiction_id: f.j, estimate_basis: f.basis, amount, assessed_value: assessed,
      tax_rate_percent: rate, sold_portion_percent: sold, parcel_reference: f.parcel.trim() || null,
    });
  };
  const j = jurisdictions.find((x) => x.id === f.j);

  return (
    <Modal isOpen onClose={() => !busy && onClose()} title="Property tax year" size="md" footer={<Footer onClose={onClose} onSave={submit} busy={busy} />}>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <FormField label="Tax year" htmlFor="ty-year" required error={error}>
          <TextInput id="ty-year" inputMode="numeric" value={f.year} onChange={set('year')} />
        </FormField>
        <FormField label="City / county" htmlFor="ty-j" required hint={j ? `${j.tax_installments.length} instalment(s) a year` : 'Add one under Cities & counties.'}>
          <Select id="ty-j" value={f.j} onChange={set('j')} placeholder="Select" options={jurisdictions.map((x) => ({ value: x.id, label: x.name }))} />
        </FormField>
        <FormField label="Estimate from" htmlFor="ty-basis" className="md:col-span-2">
          <Select id="ty-basis" value={f.basis} onChange={set('basis')} options={Object.entries(BASIS_LABELS).map(([value, label]) => ({ value, label }))} />
        </FormField>
        {f.basis === 'manual' && (
          <FormField label="Estimated tax for the year ($)" htmlFor="ty-amt" className="md:col-span-2">
            <TextInput id="ty-amt" inputMode="decimal" value={f.amount} onChange={set('amount')} />
          </FormField>
        )}
        {f.basis === 'assessed_value' && (
          <>
            <FormField label="Assessed value ($)" htmlFor="ty-av"><TextInput id="ty-av" inputMode="decimal" value={f.assessed} onChange={set('assessed')} /></FormField>
            <FormField label="Tax rate (%)" htmlFor="ty-rate"><TextInput id="ty-rate" inputMode="decimal" value={f.rate} onChange={set('rate')} placeholder="1.25" /></FormField>
          </>
        )}
        {f.basis === 'prior_year_actual' && (
          <p className="text-sm text-secondary-600 md:col-span-2">Uses last year's billed amounts for this city / county.</p>
        )}
        <FormField label="Sold portion (%)" htmlFor="ty-sold" hint="The line is reduced by this share.">
          <TextInput id="ty-sold" inputMode="decimal" value={f.sold} onChange={set('sold')} placeholder="0" />
        </FormField>
        <FormField label="Parcel" htmlFor="ty-parcel"><TextInput id="ty-parcel" value={f.parcel} onChange={set('parcel')} /></FormField>
      </div>
    </Modal>
  );
}

/** Billed / actual amount (catches increases), due date, paid. */
export function TaxEditModal({ tax, onClose }: { tax: PropertyTax; onClose: () => void }) {
  const { save, busy } = useSave(onClose, 'Property tax saved.');
  const [actual, setActual] = useState(tax.actual_amount ? Number(tax.actual_amount).toFixed(2) : '');
  const [due, setDue] = useState(tax.due_date?.slice(0, 10) ?? '');
  const [status, setStatus] = useState<string>(tax.status === 'in_approval' ? 'billed' : tax.status);
  const [error, setError] = useState<string>();
  const submit = () => {
    const a = actual.trim() ? parseMoneyInput(actual) : null;
    if (actual.trim() && a == null) return setError('Enter the billed amount as a number.');
    save('patch', API_ENDPOINTS.PROPERTY_TAX(tax.id), { actual_amount: a, due_date: due || null, status });
  };
  return (
    <Modal isOpen onClose={() => !busy && onClose()} title={`${tax.jurisdiction} ${tax.tax_year} · instalment ${tax.installment_number}`} size="md"
      footer={<Footer onClose={onClose} onSave={submit} busy={busy} />}>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <FormField label="Billed / actual ($)" htmlFor="tx-act" error={error} hint={`Estimate ${tax.estimated_amount}`}>
          <TextInput id="tx-act" inputMode="decimal" value={actual} onChange={(e) => setActual(e.target.value)} />
        </FormField>
        <FormField label="Due date" htmlFor="tx-due"><TextInput id="tx-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} /></FormField>
        <FormField label="Status" htmlFor="tx-st" className="md:col-span-2">
          <Select id="tx-st" value={status} onChange={(e) => setStatus(e.target.value)}
            options={[{ value: 'estimated', label: 'Estimated' }, { value: 'billed', label: 'Billed' }, { value: 'sent_to_finance', label: 'Paid' }, { value: 'cancelled', label: 'Cancelled' }]} />
        </FormField>
      </div>
    </Modal>
  );
}

/** As lots / homes sell: reduce open tax instalments. */
export function SoldPortionModal({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const { save, busy } = useSave(onClose, 'Sold portion applied to the open instalments.');
  const [percent, setPercent] = useState('');
  const [fromYear, setFromYear] = useState(String(new Date().getFullYear()));
  const [error, setError] = useState<string>();
  const submit = () => {
    const p = parsePercentInput(percent);
    if (p == null) return setError('Enter a % from 0 to 100.');
    save('post', API_ENDPOINTS.PROJECT_TAX_SOLD_PORTION(projectId), { percent: p, from_year: Number(fromYear) || null });
  };
  return (
    <Modal isOpen onClose={() => !busy && onClose()} title="Sold portion" size="sm" footer={<Footer onClose={onClose} onSave={submit} busy={busy} />}>
      <div className="space-y-4">
        <FormField label="Share of the land sold (%)" htmlFor="sp-p" required error={error}>
          <TextInput id="sp-p" inputMode="decimal" value={percent} onChange={(e) => setPercent(e.target.value)} />
        </FormField>
        <FormField label="From tax year" htmlFor="sp-y" hint="Open instalments without a bill from this year on.">
          <TextInput id="sp-y" inputMode="numeric" value={fromYear} onChange={(e) => setFromYear(e.target.value)} />
        </FormField>
      </div>
    </Modal>
  );
}

/** Cities / counties: repair standard %, tax due dates, reminder lead time. */
export function JurisdictionModal({ jurisdiction, onClose }: { jurisdiction?: Jurisdiction; onClose: () => void }) {
  const { save, busy } = useSave(onClose, 'City / county saved.');
  const [f, setF] = useState({
    name: jurisdiction?.name ?? '', kind: jurisdiction?.kind ?? 'city', state: jurisdiction?.state ?? '',
    pct: jurisdiction?.repair_estimate_percent ?? '',
    dates: (jurisdiction?.tax_installments ?? [{ month: 12, day: 31 }]).map((i) => `${i.month}/${i.day}`).join(', '),
    lead: String(jurisdiction?.reminder_days_before ?? 30),
  });
  const [error, setError] = useState<string>();
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF((s) => ({ ...s, [k]: e.target.value }));
  const submit = () => {
    const dates = f.dates.split(',').map((d) => d.trim()).filter(Boolean).map((d) => d.split('/').map(Number));
    const ok = dates.length > 0 && dates.every(([m, d]) => m >= 1 && m <= 12 && d >= 1 && d <= 31);
    const pct = f.pct.toString().trim() ? parsePercentInput(f.pct.toString()) : null;
    if (!f.name.trim() || !ok) return setError('Enter the name and due dates as month/day, e.g. 1/31, 6/30.');
    if (f.pct.toString().trim() && pct == null) return setError('The repair % is 0 to 100.');
    const body = {
      name: f.name.trim(), kind: f.kind, state: f.state.trim() || null, repair_estimate_percent: pct,
      tax_installments: dates.map(([month, day]) => ({ month, day })), reminder_days_before: Number(f.lead) || 30,
    };
    save(jurisdiction ? 'put' : 'post', jurisdiction ? API_ENDPOINTS.JURISDICTION(jurisdiction.id) : API_ENDPOINTS.JURISDICTIONS, body);
  };
  return (
    <Modal isOpen onClose={() => !busy && onClose()} title={jurisdiction ? 'Edit city / county' : 'New city / county'} size="md"
      footer={<Footer onClose={onClose} onSave={submit} busy={busy} />}>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <FormField label="Name" htmlFor="jr-name" required error={error}><TextInput id="jr-name" value={f.name} onChange={set('name')} /></FormField>
        <FormField label="Kind" htmlFor="jr-kind">
          <Select id="jr-kind" value={f.kind} onChange={set('kind')}
            options={[{ value: 'city', label: 'City' }, { value: 'county', label: 'County' }, { value: 'hoa', label: 'HOA' }, { value: 'other', label: 'Other' }]} />
        </FormField>
        <FormField label="State" htmlFor="jr-state"><TextInput id="jr-state" value={f.state} onChange={set('state')} /></FormField>
        <FormField label="Repairs to city standard (% of works)" htmlFor="jr-pct" hint="Default escrow repair estimate.">
          <TextInput id="jr-pct" inputMode="decimal" value={f.pct} onChange={set('pct')} />
        </FormField>
        <FormField label="Tax due dates (month/day)" htmlFor="jr-dates" hint="One per instalment, e.g. 1/31, 6/30." className="md:col-span-2">
          <TextInput id="jr-dates" value={f.dates} onChange={set('dates')} />
        </FormField>
        <FormField label="Remind days before" htmlFor="jr-lead" hint="And again 7 days before.">
          <TextInput id="jr-lead" inputMode="numeric" value={f.lead} onChange={set('lead')} />
        </FormField>
      </div>
    </Modal>
  );
}
