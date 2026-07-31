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
import { useInviteUser } from '../hooks/useUserMutations';

const inviteSchema = z.object({
  email: z.string().trim().min(1, 'Email is required').email('Enter a valid email address'),
  full_name: z.string().trim().min(1, 'Full name is required').max(255),
  role: z.enum(['admin', 'project_manager']),
});

type InviteFormValues = z.infer<typeof inviteSchema>;

const roleOptions = [
  { value: 'project_manager', label: 'Project Manager' },
  { value: 'admin', label: 'Admin' },
];

interface InviteUserModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function InviteUserModal({ isOpen, onClose }: InviteUserModalProps) {
  const { toast } = useToast();
  const inviteUser = useInviteUser();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<InviteFormValues>({
    resolver: zodResolver(inviteSchema),
    defaultValues: { email: '', full_name: '', role: 'project_manager' },
  });

  const resetAndClose = () => {
    reset();
    setSubmitError(null);
    onClose();
  };

  const handleClose = () => {
    if (inviteUser.isPending) return;
    resetAndClose();
  };

  const onSubmit = (data: InviteFormValues) => {
    setSubmitError(null);
    inviteUser.mutate(
      { email: data.email.trim(), full_name: data.full_name.trim(), role: data.role },
      {
        onSuccess: (user) => {
          toast({
            variant: 'success',
            title: 'Invite sent',
            message: `An invite was sent to ${user.email}.`,
          });
          resetAndClose();
        },
        onError: (error: unknown) => {
          // Keep the modal open and surface the server message (e.g. the 409
          // "A user with this email already exists." from Part 2).
          setSubmitError(errorMessage(error, 'Could not send the invite. Please try again.'));
        },
      },
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Invite user"
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose} disabled={inviteUser.isPending}>
            Cancel
          </Button>
          <Button type="submit" form="invite-user-form" isLoading={inviteUser.isPending}>
            Send invite
          </Button>
        </>
      }
    >
      <form id="invite-user-form" onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {submitError && (
          <Alert variant="danger" title="Could not send invite">
            {submitError}
          </Alert>
        )}

        <FormField label="Full name" htmlFor="invite-full-name" required error={errors.full_name?.message}>
          <TextInput
            id="invite-full-name"
            {...register('full_name')}
            placeholder="e.g. Jordan Rivera"
            error={errors.full_name?.message}
            autoFocus
          />
        </FormField>

        <FormField label="Email" htmlFor="invite-email" required error={errors.email?.message}>
          <TextInput
            id="invite-email"
            {...register('email')}
            type="email"
            placeholder="name@company.com"
            error={errors.email?.message}
          />
        </FormField>

        <FormField
          label="Role"
          htmlFor="invite-role"
          required
          error={errors.role?.message}
          hint="Admins manage users, vendors, and trades. Project managers run the bid process."
        >
          <Select id="invite-role" {...register('role')} options={roleOptions} error={errors.role?.message} />
        </FormField>

        <p className="rounded-lg border border-secondary-200 bg-secondary-50 px-3 py-2 text-xs text-secondary-600">
          The user receives an email invite and sets their own password. They appear here as
          &ldquo;pending&rdquo; until they accept.
        </p>
      </form>
    </Modal>
  );
}
