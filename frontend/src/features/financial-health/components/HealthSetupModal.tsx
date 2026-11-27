import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Modal } from '@/components/ui/Modal';
import { Select } from '@/components/ui/Select';
import { TextInput } from '@/components/ui/TextInput';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { parseMoneyInput } from '@/features/budgets/utils/money';
import { useUpdateHealthSetup } from '../hooks/useFinancialHealth';
import type { FinancialHealth, TeamMember } from '../types';

interface HealthSetupModalProps {
  health: FinancialHealth;
  onClose: () => void;
}

function people(team: TeamMember[], roles: string[], current: string | null, none: string) {
  return [
    { value: '', label: none },
    ...team
      .filter((m) => m.id === current || m.roles.some((r) => roles.includes(r)))
      .map((m) => ({ value: m.id, label: m.name })),
  ];
}

/** Task 5.3 — who gets the project's alerts, and the long-tail reserve. */
export function HealthSetupModal({ health, onClose }: HealthSetupModalProps) {
  const { toast } = useToast();
  const update = useUpdateHealthSetup(health.project_id);
  const [manager, setManager] = useState(health.manager_id ?? '');
  const [field, setField] = useState(health.field_manager_id ?? '');
  const [reserve, setReserve] = useState(health.reserve ?? '');
  const [error, setError] = useState<string>();

  const completed = health.project_status === 'completed';
  const save = () => {
    const raw = reserve.trim();
    const parsed = raw ? parseMoneyInput(raw) : null;
    if (raw && (parsed == null || Number(parsed) < 0)) {
      setError('Enter an amount of $0 or more.');
      return;
    }
    setError(undefined);
    update.mutate(
      { manager_id: manager || null, field_manager_id: field || null, reserve: parsed },
      {
        onSuccess: () => {
          toast({ variant: 'success', message: 'Health setup saved.' });
          onClose();
        },
        onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not save the setup.') }),
      },
    );
  };

  return (
    <Modal
      isOpen
      onClose={() => !update.isPending && onClose()}
      title="Health setup"
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={update.isPending}>Cancel</Button>
          <Button onClick={save} isLoading={update.isPending}>Save</Button>
        </>
      }
    >
      <div className="space-y-4">
        <FormField label="Project manager" htmlFor="hs-manager" hint="Gets the alerts and decides. Empty = every project manager gets them.">
          <Select
            id="hs-manager"
            options={people(health.team, ['project_manager', 'executive', 'admin'], health.manager_id, 'Not assigned')}
            value={manager}
            onChange={(e) => setManager(e.target.value)}
          />
        </FormField>
        <FormField label="Field manager" htmlFor="hs-field" hint="Users with the Field Manager role. Empty = all of them get the alerts.">
          <Select
            id="hs-field"
            options={people(health.team, ['field_manager'], health.field_manager_id, 'Not assigned')}
            value={field}
            onChange={(e) => setField(e.target.value)}
          />
        </FormField>
        <FormField
          label="Long-tail reserve ($)"
          htmlFor="hs-reserve"
          error={error}
          hint={
            completed
              ? 'The project is completed: clear the amount to release the reserve.'
              : 'Kept in contingency for open escrows and property taxes. After groundbreaking it can be raised, but only released once the project is completed.'
          }
        >
          <TextInput
            id="hs-reserve"
            inputMode="decimal"
            placeholder="No reserve"
            value={reserve}
            onChange={(e) => setReserve(e.target.value)}
          />
        </FormField>
      </div>
    </Modal>
  );
}
