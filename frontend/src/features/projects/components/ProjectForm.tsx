import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { FormField } from '@/components/ui/FormField';
import { Select } from '@/components/ui/Select';
import type { Project } from '@/features/projects/api/project.queries';

const projectSchema = z.object({
  name: z.string().trim().min(2, 'Project name is required (min 2 characters)').max(255, 'Project name must be 255 characters or fewer'),
  description: z.string().optional(),
  address: z.string().optional(),
  city: z.string().max(100, 'City must be 100 characters or fewer').optional().or(z.literal('')),
  state: z.string().max(50, 'State must be 50 characters or fewer').optional().or(z.literal('')),
  zip_code: z.string().max(20, 'ZIP code must be 20 characters or fewer').optional().or(z.literal('')),
  budget: z.coerce.number().min(0, 'Budget must be >= 0').optional().or(z.literal('')),
  status: z.enum(['planning', 'active', 'on_hold', 'completed', 'cancelled']),
  start_date: z.string().optional(),
  estimated_end_date: z.string().optional(),
}).refine(
  (data) => !data.start_date || !data.estimated_end_date || data.estimated_end_date >= data.start_date,
  { message: 'End date must be on or after start date', path: ['estimated_end_date'] },
);

type ProjectFormValues = z.infer<typeof projectSchema>;

interface ProjectFormProps {
  isOpen: boolean;
  onClose: () => void;
  project?: Project;
  onSubmit: (data: Record<string, unknown>) => void;
  isLoading?: boolean;
}

export function ProjectForm({ isOpen, onClose, project, onSubmit, isLoading = false }: ProjectFormProps) {
  const isEdit = !!project;

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm({
    resolver: zodResolver(projectSchema),
    defaultValues: {
      name: project?.name ?? '',
      description: project?.description ?? '',
      address: project?.address ?? '',
      city: project?.city ?? '',
      state: project?.state ?? '',
      zip_code: project?.zip_code ?? '',
      budget: project?.budget ?? ('' as unknown as number),
      status: project?.status ?? 'planning',
      start_date: project?.start_date ?? '',
      estimated_end_date: project?.estimated_end_date ?? '',
    },
  });

  const handleFormSubmit = (data: Record<string, unknown>) => {
    const values = data as ProjectFormValues;
    const cleanedData: Record<string, unknown> = {
      name: values.name,
      status: values.status,
      description: values.description || undefined,
      address: values.address || undefined,
      city: values.city || undefined,
      state: values.state || undefined,
      zip_code: values.zip_code || undefined,
      budget: values.budget === '' ? undefined : Number(values.budget),
      start_date: values.start_date || undefined,
      estimated_end_date: values.estimated_end_date || undefined,
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
      title={isEdit ? 'Edit Project' : 'New Project'}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="project-form"
            isLoading={isLoading}
          >
            {isEdit ? 'Save Changes' : 'Create Project'}
          </Button>
        </>
      }
    >
      <form
        id="project-form"
        onSubmit={handleSubmit(handleFormSubmit)}
        className="space-y-6"
        noValidate
      >
        {/* Project Information */}
        <div>
          <h3 className="mb-3 text-sm font-semibold text-secondary-900">Project Information</h3>
          <div className="grid grid-cols-1 gap-4">
            <FormField label="Project Name" required error={errors.name?.message}>
              <TextInput {...register('name')} error={errors.name?.message} />
            </FormField>
            <FormField label="Description" error={errors.description?.message}>
              <textarea
                {...register('description')}
                rows={3}
                className="w-full rounded-lg border border-secondary-300 px-3 py-2 text-sm transition-colors focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
              />
            </FormField>
          </div>
        </div>

        {/* Location */}
        <div>
          <h3 className="mb-3 text-sm font-semibold text-secondary-900">Location</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <FormField label="Address" error={errors.address?.message}>
                <TextInput {...register('address')} />
              </FormField>
            </div>
            <FormField label="City" error={errors.city?.message}>
              <TextInput {...register('city')} />
            </FormField>
            <div className="grid grid-cols-2 gap-4">
              <FormField label="State" error={errors.state?.message}>
                <TextInput {...register('state')} placeholder="MO" />
              </FormField>
              <FormField label="ZIP" error={errors.zip_code?.message}>
                <TextInput {...register('zip_code')} placeholder="63101" />
              </FormField>
            </div>
          </div>
        </div>

        {/* Status & Schedule */}
        <div>
          <h3 className="mb-3 text-sm font-semibold text-secondary-900">Status & Schedule</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Status">
              <Select
                {...register('status')}
                options={[
                  { value: 'planning', label: 'Planning' },
                  { value: 'active', label: 'Active' },
                  { value: 'on_hold', label: 'On Hold' },
                  { value: 'completed', label: 'Completed' },
                  { value: 'cancelled', label: 'Cancelled' },
                ]}
              />
            </FormField>
            <FormField label="Budget ($)" error={errors.budget?.message}>
              <TextInput
                type="number"
                step="1000"
                min="0"
                {...register('budget')}
                error={errors.budget?.message}
              />
            </FormField>
            <FormField label="Start Date" error={errors.start_date?.message}>
              <TextInput type="date" {...register('start_date')} />
            </FormField>
            <FormField label="Estimated End Date" error={errors.estimated_end_date?.message}>
              <TextInput type="date" {...register('estimated_end_date')} />
            </FormField>
          </div>
        </div>
      </form>
    </Modal>
  );
}
