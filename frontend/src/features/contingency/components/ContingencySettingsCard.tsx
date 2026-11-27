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
import { parseMoneyInput } from '@/features/budgets/utils/money';
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
    limit: String(initial.default_field_approval_limit ?? ''),
    near: String(initial.contingency_near_zero_percent ?? ''),
    exec: typeof initial.executive_approval_threshold === 'number' ? String(initial.executive_approval_threshold) : '',
    land: (initial.land_team_emails ?? []).join(', '),
    po: initial.po_number_format ?? 'PO-{YYYY}-{SEQ:05}',
    poc: initial.po_number_format_contract ?? '{CONTRACT}-{SEQ:03}',
    qb: initial.quickbooks_expense_account ?? 'Job Expenses',
    days: String(initial.alert_escalation_days ?? ''),
    warning: (initial.alert_recipients?.warning ?? []).join(', '),
    urgent: (initial.alert_recipients?.urgent ?? []).join(', '),
    critical: (initial.alert_recipients?.critical ?? []).join(', '),
    finance: (initial.finance_emails ?? []).join(', '),
    sales: (initial.sales_emails ?? []).join(', '),
  }));
  const [error, setError] = useState<string>();
  const [limitError, setLimitError] = useState<string>();
  const [alertError, setAlertError] = useState<string>();

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
    const limit = parseMoneyInput(form.limit);
    if (limit == null) {
      setLimitError('Enter an amount of $0 or more.');
      return;
    }
    const near = parsePercentInput(form.near);
    if (near == null || !/^\d{1,2}$/.test(form.days.trim()) || Number(form.days) < 1 || Number(form.days) > 60) {
      setAlertError('Near zero must be 0 to 100%, and the days 1 to 60.');
      return;
    }
    const exec = form.exec.trim() ? parseMoneyInput(form.exec) : 'off';
    if (exec == null || !form.po.includes('{SEQ') || !form.poc.includes('{SEQ') || !form.qb.trim()) {
      setAlertError('Check the payment settings: a valid executive amount, and {SEQ} in both PO formats.');
      return;
    }
    setError(undefined);
    setLimitError(undefined);
    setAlertError(undefined);
    update.mutate(
      {
        default_contingency_percent: def,
        bidding_target_contingency_percent: target,
        bidding_escalation_percent: esc,
        default_field_approval_limit: limit,
        contingency_near_zero_percent: near,
        alert_escalation_days: Number(form.days),
        executive_approval_threshold: exec,
        land_team_emails: toList(form.land),
        po_number_format: form.po.trim(),
        po_number_format_contract: form.poc.trim(),
        quickbooks_expense_account: form.qb.trim(),
        alert_recipients: { warning: toList(form.warning), urgent: toList(form.urgent), critical: toList(form.critical) },
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
          label="Field manager approval limit ($)"
          htmlFor="cs-limit"
          hint="A variance above this also needs a manager's approval."
          error={limitError}
          className="md:col-span-3"
        >
          <TextInput id="cs-limit" inputMode="decimal" value={form.limit} onChange={set('limit')} />
        </FormField>
        <FormField
          label="Near-zero alert at or below %"
          htmlFor="cs-near"
          hint="Contingency left, against contingency at groundbreaking."
          error={alertError}
        >
          <TextInput id="cs-near" inputMode="decimal" value={form.near} onChange={set('near')} />
        </FormField>
        <FormField
          label="Escalate undecided alerts after (days)"
          htmlFor="cs-days"
          hint="Emails the executives."
          className="md:col-span-2"
        >
          <TextInput id="cs-days" inputMode="numeric" value={form.days} onChange={set('days')} />
        </FormField>
        <FormField
          label="Warning alert emails"
          htmlFor="cs-warning"
          hint="Contingency health and long-tail reserve. Besides the project's manager and field manager."
          className="md:col-span-3"
        >
          <TextInput id="cs-warning" value={form.warning} onChange={set('warning')} />
        </FormField>
        <FormField
          label="Urgent alert emails"
          htmlFor="cs-urgent"
          hint="Contingency near zero, and also negative."
          className="md:col-span-3"
        >
          <TextInput id="cs-urgent" value={form.urgent} onChange={set('urgent')} placeholder="steve@company.com, tom@company.com" />
        </FormField>
        <FormField
          label="Critical alert emails"
          htmlFor="cs-critical"
          hint="Contingency negative only, on top of the urgent list. Executives are always told."
          className="md:col-span-3"
        >
          <TextInput id="cs-critical" value={form.critical} onChange={set('critical')} />
        </FormField>
        <FormField
          label="Executive approval above ($)"
          htmlFor="cs-exec"
          hint="Payments above this also need an executive. Empty = off."
        >
          <TextInput id="cs-exec" inputMode="decimal" placeholder="Off" value={form.exec} onChange={set('exec')} />
        </FormField>
        <FormField label="PO number with a contract" htmlFor="cs-poc" hint="{CONTRACT} {YYYY} {MM} {SEQ:3}">
          <TextInput id="cs-poc" value={form.poc} onChange={set('poc')} />
        </FormField>
        <FormField label="PO number without a contract" htmlFor="cs-po" hint="e.g. PO-{YYYY}-{SEQ:05}">
          <TextInput id="cs-po" value={form.po} onChange={set('po')} />
        </FormField>
        <FormField
          label="Land team emails"
          htmlFor="cs-land"
          hint="Told about every approved payment, with the field manager's boss."
          className="md:col-span-2"
        >
          <TextInput id="cs-land" value={form.land} onChange={set('land')} />
        </FormField>
        <FormField label="QuickBooks expense account" htmlFor="cs-qb" hint="Used in the QuickBooks export.">
          <TextInput id="cs-qb" value={form.qb} onChange={set('qb')} />
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
