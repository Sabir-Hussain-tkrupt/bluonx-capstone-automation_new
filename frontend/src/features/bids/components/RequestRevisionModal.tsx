import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { Alert } from '@/components/ui/Alert';
import { FormField } from '@/components/ui/FormField';
import { useToast } from '@/components/ui/Toast/useToast';
import { useCreateRevisionRequest } from '@/features/bids/hooks/useCreateRevisionRequest';
import { cn } from '@/utils/cn';
import type { BidInvitation } from '@/features/bids/types';

const PM_NOTE_MAX = 2000;

const schema = z.object({
  pm_note: z
    .string()
    .min(1, 'A note to the vendor is required')
    .max(PM_NOTE_MAX, `Note must be ${PM_NOTE_MAX} characters or fewer`),
  revision_deadline: z
    .string()
    .min(1, 'A revision deadline is required')
    .refine(
      (v) => {
        const t = new Date(v).getTime();
        return !Number.isNaN(t) && t > Date.now();
      },
      { message: 'Deadline must be in the future' },
    ),
});

type FormValues = z.infer<typeof schema>;

interface RequestRevisionModalProps {
  isOpen: boolean;
  onClose: () => void;
  invitation: BidInvitation;
  bidPackageId: string;
}

export function RequestRevisionModal({
  isOpen,
  onClose,
  invitation,
  bidPackageId,
}: RequestRevisionModalProps) {
  const { toast } = useToast();
  const mutation = useCreateRevisionRequest(bidPackageId);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { pm_note: '', revision_deadline: '' },
  });

  useEffect(() => {
    if (isOpen) {
      reset({ pm_note: '', revision_deadline: '' });
      setServerError(null);
    }
  }, [isOpen, reset]);

  const noteLength = watch('pm_note')?.length ?? 0;

  const onSubmit = (values: FormValues) => {
    setServerError(null);
    mutation.mutate(
      {
        bid_invitation_id: invitation.id,
        pm_note: values.pm_note,
        // datetime-local is local wall time; normalize to ISO/UTC.
        revision_deadline: new Date(values.revision_deadline).toISOString(),
      },
      {
        onSuccess: () => {
          toast({
            variant: 'success',
            message: `Revision requested from ${
              invitation.vendor_company_name ?? 'vendor'
            }.`,
          });
          onClose();
        },
        onError: (err) => {
          setServerError(
            (err as { message?: string })?.message ||
              'Failed to request revision. Please try again.',
          );
        },
      },
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Request Revision — ${invitation.vendor_company_name ?? 'Vendor'}`}
      size="lg"
      footer={
        <>
          <Button
            variant="ghost"
            onClick={onClose}
            disabled={mutation.isPending}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            form="request-revision-form"
            isLoading={mutation.isPending}
          >
            Send Request
          </Button>
        </>
      }
    >
      <form
        id="request-revision-form"
        onSubmit={handleSubmit(onSubmit)}
        className="space-y-5"
      >
        {serverError && (
          <Alert variant="danger" title="Could not send request">
            {serverError}
          </Alert>
        )}

        <p className="text-sm text-secondary-600">
          {invitation.vendor_company_name ?? 'This vendor'} will receive a
          personalized email with a magic link to submit a revised bid. Other
          vendors are not affected.
        </p>

        <FormField
          label="Note to vendor"
          htmlFor="pm_note"
          required
          error={errors.pm_note?.message}
          hint="Explain what you'd like the vendor to revise."
        >
          <textarea
            id="pm_note"
            rows={5}
            maxLength={PM_NOTE_MAX}
            aria-invalid={errors.pm_note ? true : undefined}
            className={cn(
              'w-full rounded-lg border bg-white px-3 py-2 text-sm transition-colors',
              'focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none',
              'placeholder:text-secondary-400',
              errors.pm_note
                ? 'border-danger-500 focus:border-danger-500 focus:ring-danger-500/20'
                : 'border-secondary-300',
            )}
            placeholder="e.g. Please update line item 3 to reflect the revised scope."
            {...register('pm_note')}
          />
          <p className="text-right text-xs text-secondary-400">
            {noteLength}/{PM_NOTE_MAX}
          </p>
        </FormField>

        <FormField
          label="Revision deadline"
          htmlFor="revision_deadline"
          required
          error={errors.revision_deadline?.message}
        >
          <input
            id="revision_deadline"
            type="datetime-local"
            aria-invalid={errors.revision_deadline ? true : undefined}
            className={cn(
              'w-full rounded-lg border bg-white px-3 py-2 text-sm transition-colors',
              'focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none',
              errors.revision_deadline
                ? 'border-danger-500 focus:border-danger-500 focus:ring-danger-500/20'
                : 'border-secondary-300',
            )}
            {...register('revision_deadline')}
          />
        </FormField>
      </form>
    </Modal>
  );
}
