import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { FormField } from '@/components/ui/FormField';
import type { Milestone } from '@/features/milestones/api/milestone.queries';

const milestoneSchema = z
  .object({
    name: z
      .string()
      .min(1, 'Milestone name is required')
      .max(255, 'Name must be 255 characters or fewer'),
    start_date: z.string().min(1, 'Start date is required'),
    end_date: z.string().min(1, 'End date is required'),
    notes: z.string().max(5000, 'Notes must be 5000 characters or fewer').optional(),
  })
  .refine((v) => !v.start_date || !v.end_date || v.end_date >= v.start_date, {
    message: 'End date cannot be before the start date',
    path: ['end_date'],
  });

export type MilestoneFormValues = z.infer<typeof milestoneSchema>;

interface MilestoneFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  milestone?: Milestone;
  onSubmit: (data: MilestoneFormValues) => void;
  isLoading?: boolean;
  /** When true, the start/end date inputs are disabled — a live milestone's dates
   *  can only move via Reschedule (matches the API's date-lock rule). */
  datesLocked?: boolean;
}

export function MilestoneFormModal({
  isOpen,
  onClose,
  milestone,
  onSubmit,
  isLoading = false,
  datesLocked = false,
}: MilestoneFormModalProps) {
  const isEdit = !!milestone;

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<MilestoneFormValues>({
    resolver: zodResolver(milestoneSchema),
    defaultValues: {
      name: milestone?.name ?? '',
      start_date: milestone?.start_date ?? '',
      end_date: milestone?.end_date ?? '',
      notes: milestone?.notes ?? '',
    },
  });

  useEffect(() => {
    if (isOpen) {
      reset({
        name: milestone?.name ?? '',
        start_date: milestone?.start_date ?? '',
        end_date: milestone?.end_date ?? '',
        notes: milestone?.notes ?? '',
      });
    }
  }, [isOpen, milestone, reset]);

  const handleFormSubmit = (data: MilestoneFormValues) => {
    onSubmit({ ...data, notes: data.notes?.trim() ? data.notes : undefined });
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={isEdit ? 'Edit Milestone' : 'New Milestone'}
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button type="submit" form="milestone-form" isLoading={isLoading}>
            {isEdit ? 'Save Changes' : 'Create Milestone'}
          </Button>
        </>
      }
    >
      <form id="milestone-form" onSubmit={handleSubmit(handleFormSubmit)} className="space-y-5">
        <FormField label="Milestone Name" required error={errors.name?.message}>
          <TextInput
            {...register('name')}
            error={errors.name?.message}
            placeholder="e.g. Foundation Pour"
          />
        </FormField>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField label="Start Date" required error={errors.start_date?.message}>
            <TextInput
              type="date"
              {...register('start_date')}
              error={errors.start_date?.message}
              disabled={datesLocked}
            />
          </FormField>
          <FormField label="End Date" required error={errors.end_date?.message}>
            <TextInput
              type="date"
              {...register('end_date')}
              error={errors.end_date?.message}
              disabled={datesLocked}
            />
          </FormField>
        </div>
        {datesLocked && (
          <p className="-mt-2 text-xs text-secondary-500">
            Dates are locked once the milestone is live. Use Reschedule to move the end date.
          </p>
        )}

        <FormField label="Notes" error={errors.notes?.message}>
          <textarea
            {...register('notes')}
            rows={3}
            className="w-full rounded-lg border border-secondary-300 px-3 py-2 text-sm transition-colors focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
            placeholder="Optional notes about this milestone..."
          />
        </FormField>
      </form>
    </Modal>
  );
}
