import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { Select } from '@/components/ui/Select';
import { FormField } from '@/components/ui/FormField';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { useCreateTrade } from '../hooks/useCreateTrade';
import { TRADE_PHASE_LABELS, TRADE_PHASE_ORDER } from '../types';

const tradeSchema = z.object({
  name: z
    .string()
    .trim()
    .min(2, 'Name must be at least 2 characters')
    .max(100, 'Name must be 100 characters or fewer'),
  phase: z.enum(['due_diligence', 'development', 'both']),
});

type TradeFormValues = z.infer<typeof tradeSchema>;

interface CreateTradeModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CreateTradeModal({ isOpen, onClose }: CreateTradeModalProps) {
  const { toast } = useToast();
  const createTrade = useCreateTrade();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<TradeFormValues>({
    resolver: zodResolver(tradeSchema),
    defaultValues: {
      name: '',
      phase: 'due_diligence',
    },
  });

  const resetAndClose = () => {
    reset();
    setSubmitError(null);
    onClose();
  };

  const handleClose = () => {
    if (createTrade.isPending) return;
    resetAndClose();
  };

  const onSubmit = (data: TradeFormValues) => {
    setSubmitError(null);
    createTrade.mutate(
      { name: data.name.trim(), phase: data.phase },
      {
        onSuccess: (trade) => {
          toast({
            variant: 'success',
            title: 'Trade created',
            message: `${trade.name} has been added.`,
          });
          resetAndClose();
        },
        onError: (error: unknown) => {
          setSubmitError(errorMessage(error, 'Failed to create trade. Please try again.'));
        },
      },
    );
  };

  const phaseOptions = TRADE_PHASE_ORDER.map((phase) => ({
    value: phase,
    label: TRADE_PHASE_LABELS[phase],
  }));

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Add New Trade"
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose} disabled={createTrade.isPending}>
            Cancel
          </Button>
          <Button type="submit" form="create-trade-form" isLoading={createTrade.isPending}>
            Create Trade
          </Button>
        </>
      }
    >
      <form id="create-trade-form" onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {submitError && (
          <Alert variant="danger" title="Could not create trade">
            {submitError}
          </Alert>
        )}

        <FormField label="Trade Name" required error={errors.name?.message}>
          <TextInput
            {...register('name')}
            placeholder="e.g. Electrical, Grading, Geotech"
            error={errors.name?.message}
            autoFocus
          />
        </FormField>

        <FormField
          label="Phase"
          required
          error={errors.phase?.message}
          hint="Which project phase this trade applies to."
        >
          <Select
            {...register('phase')}
            options={phaseOptions}
            error={errors.phase?.message}
          />
        </FormField>

        <p className="rounded-lg border border-secondary-200 bg-secondary-50 px-3 py-2 text-xs text-secondary-600">
          Trades cannot be edited or deleted after creation, since other records
          (tasks, vendor coverage, bid packages) depend on them. Double-check the
          name and phase before saving.
        </p>
      </form>
    </Modal>
  );
}
