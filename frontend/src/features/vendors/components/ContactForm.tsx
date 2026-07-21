import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { FormField } from '@/components/ui/FormField';
import { Checkbox } from '@/components/ui/Checkbox';
import type { VendorContact } from '@/features/vendors/api/vendor.queries';
import { emailSchema } from '@/utils/validation';

const contactSchema = z.object({
  // trim() before the length check, so whitespace can't pass as a name.
  full_name: z.string().trim().min(2, 'Name is required'),
  email: emailSchema,
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
  /** Whether the vendor already has a primary contact */
  hasPrimaryContact?: boolean;
  /** Total existing contact count for the vendor */
  contactCount?: number;
}

export function ContactForm({
  contact,
  onSubmit,
  onCancel,
  isLoading = false,
  hasPrimaryContact = false,
  contactCount = 0,
}: ContactFormProps) {
  // Auto-set primary if this is the first contact for the vendor
  const isFirstContact = !contact && contactCount === 0;

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
      is_primary: contact?.is_primary ?? isFirstContact,
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

      <Checkbox
        label="Primary contact"
        {...register('is_primary')}
        disabled={isFirstContact}
        description={
          isFirstContact
            ? 'First contact is automatically the primary contact.'
            : hasPrimaryContact && !contact?.is_primary
              ? 'Setting this will replace the current primary contact.'
              : undefined
        }
      />

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
