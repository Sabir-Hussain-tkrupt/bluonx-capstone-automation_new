import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { FormField } from '@/components/ui/FormField';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import {
  useCreateContractSigner,
  useUpdateContractSigner,
} from '../hooks/useContractSignerMutations';
import type { ContractSigner } from '../types';

const signerSchema = z.object({
  full_name: z.string().trim().min(1, 'Full name is required').max(255),
  email: z
    .string()
    .trim()
    .min(1, 'Email is required')
    .email('Enter a valid email address'),
  title: z.string().trim().max(100).optional(),
});

type SignerFormValues = z.infer<typeof signerSchema>;

const EMPTY: SignerFormValues = { full_name: '', email: '', title: '' };

interface ContractSignerModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** The row being edited, or null to add a new signer. */
  signer: ContractSigner | null;
}

/**
 * Add / edit a contract signer.
 *
 * Two error channels, as elsewhere in settings: Zod field errors render inline
 * under each input, while a server rejection goes to local state and renders as
 * an in-modal Alert with the modal staying open. That matters most on create,
 * where the 409 body is the only place the admin learns that the email belongs
 * to a deactivated entry they should reactivate instead.
 */
export function ContractSignerModal({ isOpen, onClose, signer }: ContractSignerModalProps) {
  const { toast } = useToast();
  const createSigner = useCreateContractSigner();
  const updateSigner = useUpdateContractSigner();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const isEdit = signer !== null;
  const isPending = createSigner.isPending || updateSigner.isPending;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<SignerFormValues>({
    resolver: zodResolver(signerSchema),
    defaultValues: EMPTY,
  });

  // The modal is mounted once and reused for every row, so the form has to be
  // re-seeded whenever the target changes rather than on mount alone. Only
  // `reset` belongs here, since it drives react-hook-form, an external store.
  // `submitError` is cleared by handleClose and again at the top of onSubmit,
  // and every close path (Cancel, Escape, overlay, post-save) routes through
  // handleClose, so a stale error cannot survive into the next open.
  useEffect(() => {
    if (!isOpen) return;
    reset(
      signer
        ? {
            full_name: signer.full_name,
            email: signer.email,
            title: signer.title ?? '',
          }
        : EMPTY,
    );
  }, [isOpen, signer, reset]);

  const handleClose = () => {
    if (isPending) return;
    setSubmitError(null);
    onClose();
  };

  const onSubmit = (data: SignerFormValues) => {
    setSubmitError(null);
    const body = {
      full_name: data.full_name.trim(),
      email: data.email.trim(),
      title: data.title?.trim() || null,
    };

    const onError = (error: unknown) => {
      // Keep the modal open and surface the server message verbatim — the 409
      // detail distinguishes a live duplicate from a deactivated entry.
      setSubmitError(
        errorMessage(error, 'Could not save the signer. Please try again.'),
      );
    };

    if (signer) {
      updateSigner.mutate(
        { id: signer.id, patch: body },
        {
          onSuccess: (saved) => {
            toast({
              variant: 'success',
              title: 'Signer updated',
              message: `${saved.full_name} has been updated.`,
            });
            handleClose();
          },
          onError,
        },
      );
      return;
    }

    createSigner.mutate(body, {
      onSuccess: (saved) => {
        toast({
          variant: 'success',
          title: 'Signer added',
          message: `${saved.full_name} can now be selected when awarding a task.`,
        });
        handleClose();
      },
      onError,
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={isEdit ? 'Edit signer' : 'Add signer'}
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose} disabled={isPending}>
            Cancel
          </Button>
          <Button type="submit" form="contract-signer-form" isLoading={isPending}>
            {isEdit ? 'Save changes' : 'Add signer'}
          </Button>
        </>
      }
    >
      <form
        id="contract-signer-form"
        onSubmit={handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
      >
        {submitError && (
          <Alert variant="danger" title="Could not save signer">
            {submitError}
          </Alert>
        )}

        <FormField
          label="Full name"
          htmlFor="signer-full-name"
          required
          error={errors.full_name?.message}
          hint="Appears on the contract and in the DocuSign request."
        >
          <TextInput
            id="signer-full-name"
            {...register('full_name')}
            placeholder="e.g. Dana Reyes"
            error={errors.full_name?.message}
            autoFocus
          />
        </FormField>

        <FormField
          label="Email"
          htmlFor="signer-email"
          required
          error={errors.email?.message}
          hint="Where the signature request is sent."
        >
          <TextInput
            id="signer-email"
            {...register('email')}
            type="email"
            placeholder="name@bluonx.dev"
            error={errors.email?.message}
          />
        </FormField>

        <FormField label="Title (optional)" htmlFor="signer-title" error={errors.title?.message}>
          <TextInput
            id="signer-title"
            {...register('title')}
            placeholder="e.g. VP of Development"
            error={errors.title?.message}
          />
        </FormField>

        <p className="rounded-lg border border-secondary-200 bg-secondary-50 px-3 py-2 text-xs text-secondary-600">
          Editing a signer affects future awards only. Contracts already sent keep the name
          and email they were issued with.
        </p>
      </form>
    </Modal>
  );
}
