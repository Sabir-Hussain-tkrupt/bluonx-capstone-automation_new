import { useEffect, useMemo } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { FormField } from '@/components/ui/FormField';
import { Select } from '@/components/ui/Select';
import { useTrades } from '@/features/tasks/hooks/useTrades';
import type { Task } from '@/features/tasks/api/task.queries';

const taskSchema = z.object({
  name: z
    .string()
    .min(2, 'Task name is required (min 2 characters)')
    .max(255, 'Task name must be 255 characters or fewer'),
  description: z
    .string()
    .max(5000, 'Description must be 5000 characters or fewer')
    .optional()
    .or(z.literal('')),
  phase: z.enum(['due_diligence', 'development'], {
    required_error: 'Phase is required',
  }),
  trade_id: z.string().min(1, 'Trade is required'),
  bid_type: z.enum(['competitive', 'direct_assign', 'internal'], {
    required_error: 'Bid type is required',
  }),
  budget_estimate: z.coerce
    .number()
    .min(0, 'Budget must be >= 0')
    .optional()
    .or(z.literal('')),
});

type TaskFormValues = z.infer<typeof taskSchema>;

interface TaskFormProps {
  isOpen: boolean;
  onClose: () => void;
  task?: Task;
  onSubmit: (data: Record<string, unknown>) => void;
  isLoading?: boolean;
}

export function TaskForm({ isOpen, onClose, task, onSubmit, isLoading = false }: TaskFormProps) {
  const isEdit = !!task;
  const { data: trades = [] } = useTrades();

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
    setValue,
    control,
  } = useForm<TaskFormValues>({
    resolver: zodResolver(taskSchema),
    defaultValues: {
      name: task?.name ?? '',
      description: task?.description ?? '',
      phase: task?.phase ?? ('' as unknown as 'due_diligence'),
      trade_id: task?.trade_id ?? '',
      bid_type: task?.bid_type ?? ('' as unknown as 'competitive'),
      budget_estimate: task?.budget_estimate ?? ('' as unknown as number),
    },
  });

  const selectedPhase = watch('phase');

  // Filter trades by selected phase
  const filteredTrades = useMemo(() => {
    if (!selectedPhase) return [];
    return trades.filter(
      (t) => t.phase === 'both' || t.phase === selectedPhase,
    );
  }, [trades, selectedPhase]);

  // Reset trade_id when phase changes (only if current trade is not valid for new phase)
  useEffect(() => {
    if (!selectedPhase) return;
    const currentTradeId = watch('trade_id');
    if (currentTradeId) {
      const isValid = filteredTrades.some((t) => t.id === currentTradeId);
      if (!isValid) {
        setValue('trade_id', '');
      }
    }
  }, [selectedPhase, filteredTrades, setValue, watch]);

  // Reset form when task changes (edit mode) or modal opens
  useEffect(() => {
    if (isOpen) {
      reset({
        name: task?.name ?? '',
        description: task?.description ?? '',
        phase: task?.phase ?? ('' as unknown as 'due_diligence'),
        trade_id: task?.trade_id ?? '',
        bid_type: task?.bid_type ?? ('' as unknown as 'competitive'),
        budget_estimate: task?.budget_estimate ?? ('' as unknown as number),
      });
    }
  }, [isOpen, task, reset]);

  const handleFormSubmit = (data: TaskFormValues) => {
    const cleanedData: Record<string, unknown> = {
      name: data.name,
      phase: data.phase,
      trade_id: data.trade_id,
      bid_type: data.bid_type,
      description: data.description || undefined,
      budget_estimate: data.budget_estimate === '' ? undefined : Number(data.budget_estimate),
    };
    onSubmit(cleanedData);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={isEdit ? 'Edit Task' : 'New Task'}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button type="submit" form="task-form" isLoading={isLoading}>
            {isEdit ? 'Save Changes' : 'Create Task'}
          </Button>
        </>
      }
    >
      <form id="task-form" onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
        {/* Task Information */}
        <div>
          <h3 className="mb-3 text-sm font-semibold text-secondary-900">Task Information</h3>
          <div className="grid grid-cols-1 gap-4">
            <FormField label="Task Name" required error={errors.name?.message}>
              <TextInput {...register('name')} error={errors.name?.message} placeholder="e.g. Mass Grading - Phase 1" />
            </FormField>
            <FormField label="Description" error={errors.description?.message}>
              <textarea
                {...register('description')}
                rows={3}
                className="w-full rounded-lg border border-secondary-300 px-3 py-2 text-sm transition-colors focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
                placeholder="Describe the scope of work for this task..."
              />
            </FormField>
          </div>
        </div>

        {/* Phase & Trade */}
        <div>
          <h3 className="mb-3 text-sm font-semibold text-secondary-900">Phase & Trade</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Phase" required error={errors.phase?.message}>
              <Controller
                control={control}
                name="phase"
                render={({ field }) => (
                  <Select
                    {...field}
                    placeholder="Select phase"
                    error={errors.phase?.message}
                    options={[
                      { value: 'due_diligence', label: 'Due Diligence' },
                      { value: 'development', label: 'Development' },
                    ]}
                  />
                )}
              />
            </FormField>
            <FormField label="Trade" required error={errors.trade_id?.message}>
              <Controller
                control={control}
                name="trade_id"
                render={({ field }) => (
                  <Select
                    {...field}
                    placeholder={selectedPhase ? 'Select trade' : 'Select phase first'}
                    disabled={!selectedPhase}
                    error={errors.trade_id?.message}
                    options={filteredTrades.map((t) => ({
                      value: t.id,
                      label: t.name,
                    }))}
                  />
                )}
              />
            </FormField>
          </div>
        </div>

        {/* Bid Type & Budget */}
        <div>
          <h3 className="mb-3 text-sm font-semibold text-secondary-900">Bid Type & Budget</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Bid Type" required error={errors.bid_type?.message}>
              <Controller
                control={control}
                name="bid_type"
                render={({ field }) => (
                  <Select
                    {...field}
                    placeholder="Select bid type"
                    error={errors.bid_type?.message}
                    options={[
                      { value: 'competitive', label: 'Competitive' },
                      { value: 'direct_assign', label: 'Direct Assign' },
                      { value: 'internal', label: 'Internal' },
                    ]}
                  />
                )}
              />
            </FormField>
            <FormField label="Budget Estimate ($)" error={errors.budget_estimate?.message}>
              <TextInput
                type="number"
                step="0.01"
                min="0"
                {...register('budget_estimate')}
                error={errors.budget_estimate?.message}
                placeholder="0.00"
              />
            </FormField>
          </div>
          {/* Bid type hints */}
          <div className="mt-2 text-xs text-secondary-500">
            {watch('bid_type') === 'competitive' && 'Full pipeline: invite vendors, collect bids, compare, award.'}
            {watch('bid_type') === 'direct_assign' && 'PM picks vendor directly. No bidding phase.'}
            {watch('bid_type') === 'internal' && 'Budget line item only. No vendor involvement.'}
          </div>
        </div>
      </form>
    </Modal>
  );
}
