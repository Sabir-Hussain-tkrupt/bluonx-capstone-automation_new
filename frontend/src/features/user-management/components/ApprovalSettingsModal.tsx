import { useState } from 'react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Modal } from '@/components/ui/Modal';
import { Select } from '@/components/ui/Select';
import { Skeleton } from '@/components/ui/Skeleton';
import { TextInput } from '@/components/ui/TextInput';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { parseMoneyInput } from '@/features/budgets/utils/money';
import { useApproverSettings, useUpdateApproverSettings } from '@/features/payments/hooks/usePayments';
import type { ApproverSettings } from '@/features/payments/types';
import type { UserAdminResponse } from '../types';

/** Task 6.2 / 6.3 — a person's approval limit, manager, backup and away date. */
export function ApprovalSettingsModal({ user, onClose }: { user: UserAdminResponse; onClose: () => void }) {
  const query = useApproverSettings();
  const me = query.data?.find((u) => u.id === user.id);
  return (
    <Modal isOpen onClose={onClose} title="Payment approvals" size="md">
      {query.isLoading ? (
        <Skeleton height="240px" />
      ) : !me || !query.data ? (
        <Alert variant="danger" title="Could not load the settings">{errorMessage(query.error, 'Please try again.')}</Alert>
      ) : (
        <Form me={me} everyone={query.data} onClose={onClose} />
      )}
    </Modal>
  );
}

function Form({ me, everyone, onClose }: { me: ApproverSettings; everyone: ApproverSettings[]; onClose: () => void }) {
  const { toast } = useToast();
  const update = useUpdateApproverSettings(me.id);
  const [limit, setLimit] = useState(me.approval_limit ?? '');
  const [manager, setManager] = useState(me.reports_to ?? '');
  const [backup, setBackup] = useState(me.backup_approver_id ?? '');
  const [away, setAway] = useState(me.away_until ? me.away_until.slice(0, 10) : '');
  const [error, setError] = useState<string>();

  const people = [
    { value: '', label: 'Nobody' },
    ...everyone.filter((u) => u.id !== me.id && u.is_active && u.is_employee).map((u) => ({ value: u.id, label: u.name })),
  ];
  const manages = me.roles.some((r) => ['project_manager', 'executive', 'admin'].includes(r));

  const save = () => {
    const raw = limit.trim();
    const parsed = raw ? parseMoneyInput(raw) : null;
    if (raw && parsed == null) return setError('Enter an amount, or leave it empty for the default.');
    if (away && !backup) return setError('Choose a backup approver: approvals go to them while this person is away.');
    setError(undefined);
    update.mutate(
      {
        approval_limit: parsed,
        reports_to: manager || null,
        backup_approver_id: backup || null,
        away_until: away ? new Date(`${away}T23:59:59`).toISOString() : null,
      },
      {
        onSuccess: () => {
          toast({ variant: 'success', message: 'Approval settings saved.' });
          onClose();
        },
        onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not save the settings.') }),
      },
    );
  };

  return (
    <div className="space-y-4">
      {!me.is_employee && (
        <Alert variant="info" title="External field manager">Can confirm work, never authorise payment.</Alert>
      )}
      <FormField
        label="Approval limit ($)"
        htmlFor="as-limit"
        error={error}
        hint={manages ? 'Empty = no limit for managers.' : 'Empty = the default field manager limit (Contingency settings).'}
      >
        <TextInput id="as-limit" inputMode="decimal" placeholder="Default" value={limit} onChange={(e) => setLimit(e.target.value)} />
      </FormField>
      <FormField label="Reports to" htmlFor="as-manager" hint="Gets this person's over-limit and external approvals.">
        <Select id="as-manager" options={people} value={manager} onChange={(e) => setManager(e.target.value)} />
      </FormField>
      <FormField label="Backup approver" htmlFor="as-backup" hint="Approves when this person is away or inactive.">
        <Select id="as-backup" options={people} value={backup} onChange={(e) => setBackup(e.target.value)} />
      </FormField>
      <FormField label="Away until" htmlFor="as-away" hint="While away, approvals routed to this person go to the backup. Empty = not away.">
        <TextInput id="as-away" type="date" value={away} onChange={(e) => setAway(e.target.value)} />
      </FormField>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose} disabled={update.isPending}>Cancel</Button>
        <Button onClick={save} isLoading={update.isPending}>Save</Button>
      </div>
    </div>
  );
}
