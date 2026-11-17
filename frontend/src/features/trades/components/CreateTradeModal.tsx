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
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { useCreateTrade } from '../hooks/useCreateTrade';
import { useTradeUsage, useUpdateTrade } from '../hooks/useTradeMutations';
import { TRADE_PHASE_LABELS, TRADE_PHASE_ORDER } from '../types';
import type { Trade, TradePhase } from '../types';
import { describeTradeUsage } from './tradeUsageText';

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
  /** Set to add a subtrade under this trade. */
  parent?: Trade | null;
  /** Set to edit this trade / subtrade instead of creating one. */
  trade?: Trade | null;
  /** The parent of `trade` when it is a subtrade (for the heading). */
  tradeParent?: Trade | null;
}

/**
 * Create a trade, add a subtrade under a trade, or edit either.
 *
 * Mount per open (the panel keys it), so the form always starts from the
 * trade being edited without a reset effect.
 */
export function CreateTradeModal({ isOpen, onClose, parent = null, trade = null, tradeParent = null }: CreateTradeModalProps) {
  const { toast } = useToast();
  const createTrade = useCreateTrade();
  const updateTrade = useUpdateTrade();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const isEdit = !!trade;
  const isSubtrade = isEdit ? !!trade?.parent_trade_id : !!parent;
  const usage = useTradeUsage(isEdit && isOpen ? trade!.id : null);
  const locked = isEdit && usage.data ? !usage.data.can_edit : false;
  const pending = createTrade.isPending || updateTrade.isPending;

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<TradeFormValues>({
    resolver: zodResolver(tradeSchema),
    defaultValues: {
      name: trade?.name ?? '',
      phase: (trade?.phase ?? parent?.phase ?? 'due_diligence') as TradePhase,
    },
  });

  const handleClose = () => {
    if (pending) return;
    setSubmitError(null);
    onClose();
  };

  const onSubmit = (data: TradeFormValues) => {
    setSubmitError(null);
    const name = data.name.trim();
    const onError = (error: unknown) =>
      setSubmitError(errorMessage(error, isEdit ? 'Failed to save the trade.' : 'Failed to create trade. Please try again.'));

    if (isEdit && trade) {
      updateTrade.mutate(
        { id: trade.id, input: isSubtrade ? { name } : { name, phase: data.phase } },
        {
          onSuccess: (saved) => {
            toast({ variant: 'success', title: isSubtrade ? 'Subtrade updated' : 'Trade updated', message: `${saved.name} has been saved.` });
            onClose();
          },
          onError,
        },
      );
      return;
    }

    createTrade.mutate(
      parent ? { name, parent_trade_id: parent.id } : { name, phase: data.phase },
      {
        onSuccess: (created) => {
          toast({
            variant: 'success',
            title: parent ? 'Subtrade created' : 'Trade created',
            message: parent ? `${created.name} has been added under ${parent.name}.` : `${created.name} has been added.`,
          });
          onClose();
        },
        onError,
      },
    );
  };

  const phaseOptions = TRADE_PHASE_ORDER.map((phase) => ({
    value: phase,
    label: TRADE_PHASE_LABELS[phase],
  }));

  const owner = parent ?? tradeParent;
  const title = isEdit
    ? isSubtrade ? 'Edit Subtrade' : 'Edit Trade'
    : parent ? `Add Subtrade to ${parent.name}` : 'Add New Trade';
  const submitLabel = isEdit ? 'Save Changes' : parent ? 'Create Subtrade' : 'Create Trade';

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={title}
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose} disabled={pending}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="create-trade-form"
            isLoading={pending}
            disabled={isEdit && (usage.isLoading || locked)}
          >
            {submitLabel}
          </Button>
        </>
      }
    >
      <form id="create-trade-form" onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {submitError && (
          <Alert variant="danger" title={isEdit ? 'Could not save' : 'Could not create trade'}>
            {submitError}
          </Alert>
        )}

        {isEdit && usage.isLoading && <Skeleton variant="rectangular" height="40px" />}

        {isEdit && usage.isError && (
          <Alert variant="danger" title="Could not check where this trade is used">
            {errorMessage(usage.error, 'Please try again.')}
          </Alert>
        )}

        {locked && usage.data && (
          <Alert variant="warning" title="This trade is in use">
            {trade!.name} is used by {describeTradeUsage(usage.data, { excludeSubtrades: true })}, so its name and
            phase cannot be changed.
          </Alert>
        )}

        {isSubtrade && owner && (
          <p className="text-sm text-secondary-600">
            Subtrade of <span className="font-medium text-secondary-900">{owner.name}</span> · phase{' '}
            {TRADE_PHASE_LABELS[owner.phase]} (always the same as its trade).
          </p>
        )}

        <FormField label={isSubtrade ? 'Subtrade Name' : 'Trade Name'} required error={errors.name?.message}>
          <TextInput
            {...register('name')}
            placeholder={isSubtrade ? 'e.g. Commercial, Residential' : 'e.g. Electrical, Grading, Geotech'}
            error={errors.name?.message}
            disabled={locked}
            autoFocus
          />
        </FormField>

        {!isSubtrade && (
          <FormField
            label="Phase"
            required
            error={errors.phase?.message}
            hint={trade && !locked ? 'Its subtrades follow this phase.' : 'Which project phase this trade applies to.'}
          >
            <Select
              {...register('phase')}
              options={phaseOptions}
              error={errors.phase?.message}
              disabled={locked}
            />
          </FormField>
        )}

        {!isEdit && (
          <p className="rounded-lg border border-secondary-200 bg-secondary-50 px-3 py-2 text-xs text-secondary-600">
            {parent
              ? `Once ${parent.name} has a subtrade, tasks, vendors and templates must pick one of its subtrades instead of ${parent.name} itself.`
              : 'A trade can be renamed or deleted only while no task, vendor or template uses it. Add subtrades later from the trade’s menu.'}
          </p>
        )}
      </form>
    </Modal>
  );
}
