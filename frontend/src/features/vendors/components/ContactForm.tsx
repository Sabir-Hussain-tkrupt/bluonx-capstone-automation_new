import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { FormField } from '@/components/ui/FormField';
import { Checkbox } from '@/components/ui/Checkbox';
import type { VendorContact } from '@/features/vendors/api/vendor.queries';

const contactSchema = z.object({
  full_name: z.string().min(2, 'Name is required'),
  email: z.string().email('Valid email is required'),
  phone: z.string().optional(),
  title: z.string().optional(),
  is_primary: z.boolean().optional(),
});

type ContactFormValues = z.infer<typeof contactSchema>;

interface ContactFormProps {
  contact?: VendorContact;
  onSubmit: (data: ContactFormValues) => void;
  onCancel: () => void;
  isLoading?: boolean;
}

export function ContactForm({ contact, onSubmit, onCancel, isLoading = false }: ContactFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ContactFormValues>({
    resolver: zodResolver(contactSchema),
    defaultValues: {
      full_name: contact?.full_name ?? '',
      email: contact?.email ?? '',
      phone: contact?.phone ?? '',
      title: contact?.title ?? '',
      is_primary: contact?.is_primary ?? false,
    },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormField label="Full Name" required error={errors.full_name?.message}>
          <TextInput {...register('full_name')} error={errors.full_name?.message} />
        </FormField>
        <FormField label="Email" required error={errors.email?.message}>
          <TextInput type="email" {...register('email')} error={errors.email?.message} />
        </FormField>
        <FormField label="Phone" error={errors.phone?.message}>
          <TextInput {...register('phone')} />
        </FormField>
        <FormField label="Title" error={errors.title?.message}>
          <TextInput {...register('title')} placeholder="e.g., Project Manager" />
        </FormField>
      </div>

      <Checkbox label="Primary contact" {...register('is_primary')} />

      <div className="flex justify-end gap-3">
        <Button type="button" variant="ghost" onClick={onCancel} disabled={isLoading}>
          Cancel
        </Button>
        <Button type="submit" isLoading={isLoading}>
          {contact ? 'Update Contact' : 'Add Contact'}
        </Button>
      </div>
    </form>
  );
}
