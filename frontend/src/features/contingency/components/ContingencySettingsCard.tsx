import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { FormField } from '@/components/ui/FormField';
import { Skeleton } from '@/components/ui/Skeleton';
import { TextInput } from '@/components/ui/TextInput';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { useContingencySettings, useUpdateContingencySettings } from '../hooks/useContingency';
import type { ContingencySettings } from '../types';
import { parsePercentInput } from './shared';

function toList(raw: string): string[] {
  return raw.split(/[,;\n]/).map((s) => s.trim()).filter(Boolean);
}

/**
 * Task 3.1 / 3.4 / 3.5 — organisation-wide contingency settings (admin): the
 * default %, the bidding target and escalation %, and who besides the finance
 * role hears about approved top-ups.
 */
export function ContingencySettingsCard() {
  const query = useContingencySettings();
  if (query.isLoading || !query.data) return <Skeleton height="200px" />;
  return <ContingencySettingsForm initial={query.data} />;
}

function ContingencySettingsForm({ initial }: { initial: ContingencySettings }) {
  const { toast } = useToast();
  const update = useUpdateContingencySettings();
  const [form, setForm] = useState(() => ({
    def: String(initial.default_contingency_percent ?? ''),
    target: String(initial.bidding_target_contingency_percent ?? ''),
    esc: String(initial.bidding_escalation_percent ?? ''),
    finance: (initial.finance_emails ?? []).join(', '),
    sales: (initial.sales_emails ?? []).join(', '),
  }));
  const [error, setError] = useState<string>();

  const save = () => {
    const def = parsePercentInput(form.def);
    const target = parsePercentInput(form.target);
    const esc = parsePercentInput(form.esc);
    if (def == null || target == null || esc == null) {
      setError('Each % must be a number between 0 and 100.');
      return;
    }
    if (Number(esc) > Number(target)) {
      setError('The escalation % must not be above the target %.');
      return;
    }
    setError(undefined);
    update.mutate(
      {
        default_contingency_percent: def,
        bidding_target_contingency_percent: target,
        bidding_escalation_percent: esc,
        finance_emails: toList(form.finance),
        sales_emails: toList(form.sales),
      },
      {
        onSuccess: () => toast({ variant: 'success', message: 'Contingency settings saved.' }),
        onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not save the settings.') }),
      },
    );
  };

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  return (
    <Card
      title="Contingency settings"
      subtitle="Apply to every project. A project's own % (set on its Budget tab) overrides the default."
      actions={<Button size="sm" onClick={save} isLoading={update.isPending}>Save</Button>}
      padding="md"
    >
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <FormField label="Default contingency %" htmlFor="cs-default" hint="Of the base: total − land − contingency." error={error}>
          <TextInput id="cs-default" inputMode="decimal" value={form.def} onChange={set('def')} />
        </FormField>
        <FormField label="Target left after bidding %" htmlFor="cs-target" hint="Above this nothing happens.">
          <TextInput id="cs-target" inputMode="decimal" value={form.target} onChange={set('target')} />
        </FormField>
        <FormField label="Escalate at or below %" htmlFor="cs-esc" hint="Emails the executives and finance.">
          <TextInput id="cs-esc" inputMode="decimal" value={form.esc} onChange={set('esc')} />
        </FormField>
        <FormField
          label="Finance emails"
          htmlFor="cs-finance"
          hint="Besides users with the Finance role. Separate with commas."
          className="md:col-span-3"
        >
          <TextInput id="cs-finance" value={form.finance} onChange={set('finance')} placeholder="finance@company.com" />
        </FormField>
        <FormField
          label="Sales emails"
          htmlFor="cs-sales"
          hint="Told about every approved top-up before home prices are set."
          className="md:col-span-3"
        >
          <TextInput id="cs-sales" value={form.sales} onChange={set('sales')} placeholder="sales@company.com" />
        </FormField>
      </div>
    </Card>
  );
}
