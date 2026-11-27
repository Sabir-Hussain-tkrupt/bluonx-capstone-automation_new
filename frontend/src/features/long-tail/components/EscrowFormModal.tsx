import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Modal } from '@/components/ui/Modal';
import { RadioGroup } from '@/components/ui/RadioGroup';
import { Select } from '@/components/ui/Select';
import { TextInput } from '@/components/ui/TextInput';
import { useToast } from '@/components/ui/Toast';
import { API_ENDPOINTS } from '@/constants/api';
import { errorMessage } from '@/lib/api';
import { textareaClass } from '@/features/contingency/components/shared';
import { formatCents, parseMoneyInput, toCents } from '@/features/budgets/utils/money';
import { useJurisdictions, useLongTailWrite } from '../hooks/useLongTail';
import type { Escrow } from '../types';

interface Props {
  projectId: string;
  escrow?: Escrow;
  onClose: () => void;
}

/** Tasks 7.1 / 7.2 — set up an escrow; its two cost lines follow. */
export function EscrowFormModal({ projectId, escrow, onClose }: Props) {
  const { toast } = useToast();
  const save = useLongTailWrite();
  const { data: jurisdictions = [] } = useJurisdictions();
  const [f, setF] = useState({
    name: escrow?.name ?? '',
    beneficiary: escrow?.beneficiary ?? 'city',
    areas: (escrow?.covered_areas ?? []).join(', '),
    form: escrow?.security_form ?? 'bond',
    holder_type: escrow?.holder_type ?? 'insurance_company',
    holder_name: escrow?.holder_name ?? '',
    secured: escrow ? Number(escrow.secured_amount).toFixed(2) : '',
    premium: escrow ? Number(escrow.premium_amount).toFixed(2) : '',
    frequency: escrow?.premium_frequency ?? 'yearly',
    bond_number: escrow?.bond_number ?? '',
    expiry: escrow?.bond_expiry_date?.slice(0, 10) ?? '',
    jurisdiction: escrow?.jurisdiction_id ?? '',
    repair: escrow ? Number(escrow.repair_estimate).toFixed(2) : '',
    release: escrow?.expected_release_date?.slice(0, 10) ?? '',
    notes: escrow?.notes ?? '',
  });
  const [error, setError] = useState<string>();
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF((s) => ({ ...s, [k]: e.target.value }));

  const pct = jurisdictions.find((j) => j.id === f.jurisdiction)?.repair_estimate_percent;
  const secured = parseMoneyInput(f.secured);
  const suggested = secured && pct != null ? Math.round((toCents(secured) * Number(pct)) / 100) : null;

  const submit = () => {
    const areas = f.areas.split(/[,;\n]/).map((a) => a.trim()).filter(Boolean);
    const premium = f.premium.trim() ? parseMoneyInput(f.premium) : '0';
    const repair = f.repair.trim() ? parseMoneyInput(f.repair) : null;
    if (!f.name.trim() || !areas.length || !secured) return setError('Enter a name, the areas and the value of the works.');
    if (premium == null || (f.repair.trim() && repair == null)) return setError('Check the amounts.');
    if (f.form === 'bond' && !f.holder_name.trim()) return setError('A bond needs its holder.');
    setError(undefined);
    const body = {
      name: f.name.trim(), beneficiary: f.beneficiary, covered_areas: areas, security_form: f.form,
      holder_type: f.form === 'bond' ? f.holder_type : null, holder_name: f.holder_name.trim() || null,
      secured_amount: secured, premium_amount: f.form === 'bond' ? premium : '0', premium_frequency: f.frequency,
      bond_number: f.bond_number.trim() || null, bond_expiry_date: f.form === 'bond' && f.expiry ? f.expiry : null,
      jurisdiction_id: f.jurisdiction || null, repair_estimate: repair,
      expected_release_date: f.release || null, notes: f.notes.trim() || null,
    };
    save.mutate(
      escrow
        ? { method: 'put', url: API_ENDPOINTS.ESCROW(escrow.id), body }
        : { method: 'post', url: API_ENDPOINTS.PROJECT_ESCROWS(projectId), body },
      {
        onSuccess: () => {
          toast({ variant: 'success', message: escrow ? 'Escrow saved.' : 'Escrow set up with its premium and repairs lines.' });
          onClose();
        },
        onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not save the escrow.') }),
      },
    );
  };

  return (
    <Modal
      isOpen
      onClose={() => !save.isPending && onClose()}
      title={escrow ? 'Edit escrow' : 'New escrow'}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={save.isPending}>Cancel</Button>
          <Button onClick={submit} isLoading={save.isPending}>Save</Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <FormField label="Name" htmlFor="es-name" required error={error} className="md:col-span-2">
          <TextInput id="es-name" value={f.name} onChange={set('name')} placeholder="e.g. Phase 1 roads" />
        </FormField>
        <FormField label="Owed to" htmlFor="es-ben">
          <Select id="es-ben" value={f.beneficiary} onChange={set('beneficiary')}
            options={[{ value: 'city', label: 'City' }, { value: 'county', label: 'County' }, { value: 'hoa', label: 'HOA' }, { value: 'other', label: 'Other' }]} />
        </FormField>
        <FormField label="Areas covered" htmlFor="es-areas" required hint="One or several, separated by commas.">
          <TextInput id="es-areas" value={f.areas} onChange={set('areas')} placeholder="roads  /  landscaping, trails, benches" />
        </FormField>
        <div className="md:col-span-2">
          <RadioGroup
            name="es-form"
            legend="Posted as"
            orientation="horizontal"
            value={f.form}
            onChange={(v) => setF((s) => ({ ...s, form: v as 'cash' | 'bond' }))}
            options={[
              { value: 'bond', label: 'Bond (insurance policy)', description: 'Equal to the value of the works' },
              { value: 'cash', label: 'Cash', description: 'Goes out when posted, comes back on release' },
            ]}
          />
        </div>
        <FormField label="Value of the works ($)" htmlFor="es-sec" required>
          <TextInput id="es-sec" inputMode="decimal" value={f.secured} onChange={set('secured')} />
        </FormField>
        <FormField label="City / county standard" htmlFor="es-j" hint="Sets the default repair estimate %.">
          <Select id="es-j" value={f.jurisdiction} onChange={set('jurisdiction')}
            options={[{ value: '', label: 'Not set' }, ...jurisdictions.map((j) => ({ value: j.id, label: j.name }))]} />
        </FormField>
        {f.form === 'bond' && (
          <>
            <FormField label="Holder" htmlFor="es-ht">
              <Select id="es-ht" value={f.holder_type} onChange={set('holder_type')}
                options={[{ value: 'insurance_company', label: 'Insurance company' }, { value: 'bank', label: 'Bank' }, { value: 'other', label: 'Other entity' }]} />
            </FormField>
            <FormField label="Holder name" htmlFor="es-hn" required>
              <TextInput id="es-hn" value={f.holder_name} onChange={set('holder_name')} />
            </FormField>
            <FormField label="Premium ($)" htmlFor="es-prem" hint="Cost 1: a hard cost in the budget.">
              <TextInput id="es-prem" inputMode="decimal" value={f.premium} onChange={set('premium')} />
            </FormField>
            <FormField label="Premium paid" htmlFor="es-freq">
              <Select id="es-freq" value={f.frequency} onChange={set('frequency')}
                options={[{ value: 'yearly', label: 'Every year until released' }, { value: 'one_time', label: 'Once' }]} />
            </FormField>
            <FormField label="Bond number" htmlFor="es-bn">
              <TextInput id="es-bn" value={f.bond_number} onChange={set('bond_number')} />
            </FormField>
            <FormField label="Bond expiry" htmlFor="es-exp" hint="Renewal reminders are sent before it.">
              <TextInput id="es-exp" type="date" value={f.expiry} onChange={set('expiry')} />
            </FormField>
          </>
        )}
        <FormField
          label="Repairs to city standard ($)"
          htmlFor="es-rep"
          hint={suggested != null ? `Cost 2. Empty = ${pct}% of the works: ${formatCents(suggested)}.` : 'Cost 2. Internal estimate, e.g. cut out and re-pour a road section.'}
        >
          <TextInput id="es-rep" inputMode="decimal" value={f.repair} onChange={set('repair')} />
        </FormField>
        <FormField label="Expected release" htmlFor="es-rel" hint="Often a year or more after the project starts.">
          <TextInput id="es-rel" type="date" value={f.release} onChange={set('release')} />
        </FormField>
        <FormField label="Notes" htmlFor="es-notes" className="md:col-span-2">
          <textarea id="es-notes" rows={2} value={f.notes} onChange={set('notes')} className={textareaClass} />
        </FormField>
      </div>
    </Modal>
  );
}
