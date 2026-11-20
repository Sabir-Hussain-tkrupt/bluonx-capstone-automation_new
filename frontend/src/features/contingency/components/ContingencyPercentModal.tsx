import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/ui/FormField';
import { Modal } from '@/components/ui/Modal';
import { TextInput } from '@/components/ui/TextInput';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { useSetContingencyPercent } from '../hooks/useContingency';
import { formatPercent, parsePercentInput } from './shared';

interface ContingencyPercentModalProps {
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
  current: string | null;
  defaultPercent: string;
}

/** Task 3.1 — admins set a per-project % (e.g. higher for a longer deal). */
export function ContingencyPercentModal({ projectId, isOpen, onClose, current, defaultPercent }: ContingencyPercentModalProps) {
  const { toast } = useToast();
  const setPercent = useSetContingencyPercent(projectId);
  // Mounted only while open, so the field always starts at the current %.
  const [value, setValue] = useState(() => (current != null ? String(Number(current)) : ''));
  const [error, setError] = useState<string>();

  const submit = () => {
    const raw = value.trim();
    const parsed = raw === '' ? null : parsePercentInput(raw);
    if (raw !== '' && parsed == null) {
      setError('Enter a number between 0 and 100.');
      return;
    }
    setPercent.mutate(parsed, {
      onSuccess: () => {
        toast({
          variant: 'success',
          message: `Contingency set to ${parsed == null ? `the default (${formatPercent(defaultPercent)})` : formatPercent(parsed)}. The draft budget was recalculated.`,
        });
        onClose();
      },
      onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not change the contingency %.') }),
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => !setPercent.isPending && onClose()}
      title="Project contingency %"
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={setPercent.isPending}>Cancel</Button>
          <Button onClick={submit} isLoading={setPercent.isPending}>Save</Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-secondary-600">
          Contingency is this % of the contingency base (total budget − land − contingency), so escrows, property
          taxes and every other line sit inside the base. Longer deals can carry a higher % to cover inflation.
        </p>
        <FormField
          label="Contingency %"
          htmlFor="contingency-percent"
          error={error}
          hint={`Leave empty to use the default (${formatPercent(defaultPercent)}). Fixed once the budget is baselined.`}
        >
          <TextInput
            id="contingency-percent"
            inputMode="decimal"
            placeholder={String(Number(defaultPercent))}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </FormField>
      </div>
    </Modal>
  );
}
