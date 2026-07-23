import { useEffect, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { FormProvider, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { Select } from '@/components/ui/Select';
import { FormField } from '@/components/ui/FormField';
import { useToast } from '@/components/ui/Toast/useToast';
import { ROUTES } from '@/constants/routes';
import { Alert } from '@/components/ui/Alert';
import { errorMessage } from '@/lib/api';
import { useBidTemplate } from '@/features/bid-templates/hooks/useBidTemplate';
import { useCreateBidTemplate } from '@/features/bid-templates/hooks/useCreateBidTemplate';
import { useUpdateBidTemplate } from '@/features/bid-templates/hooks/useUpdateBidTemplate';
import { useDuplicateBidTemplate } from '@/features/bid-templates/hooks/useDuplicateBidTemplate';
import { useTrades } from '@/features/vendors/hooks/useTrades';
import { LineItemsEditor } from '@/features/bid-templates/components/LineItemsEditor';
import { BidTemplatePreview } from '@/features/bid-templates/components/BidTemplatePreview';

// ─── Zod Schema ──────────────────────────────────────────────────────

// Shape only. The per-item rules live in the superRefine below so they can be
// skipped entirely for lump-sum templates -- see the note on formSchema.
const itemSchema = z.object({
  description: z.string(),
  item_type: z.enum(['lump_sum', 'unit_price']),
  unit_of_measure: z.string().optional().nullable(),
});

const formSchema = z
  .object({
    // Trim so a whitespace-only name fails here rather than reaching the API,
    // which strips and rejects it with a less specific message.
    name: z.string().trim().min(1, 'Template name is required').max(255),
    trade_id: z.string().optional(),
    is_lump_sum: z.boolean(),
    items: z.array(itemSchema),
  })
  .superRefine((data, ctx) => {
    // Item rules are conditional on the bid format. Validating them
    // unconditionally made the form silently unsubmittable: the items section
    // only renders when !is_lump_sum, so a half-filled item left behind by a
    // toggle to Lump Sum failed validation with the error painted inside a
    // hidden section, and Save just did nothing. onSubmit discards items for
    // lump-sum templates anyway, so there is nothing to validate there.
    if (data.is_lump_sum) return;

    if (data.items.length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'At least one line item is required for structured templates',
        path: ['items'],
      });
      return;
    }

    data.items.forEach((item, index) => {
      if (item.description.trim().length === 0) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Description is required',
          path: ['items', index, 'description'],
        });
      }
      if (
        item.item_type === 'unit_price' &&
        !(item.unit_of_measure && item.unit_of_measure.trim().length > 0)
      ) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Unit of measure is required for unit price items',
          path: ['items', index, 'unit_of_measure'],
        });
      }
    });
  });

type FormValues = z.infer<typeof formSchema>;

// ─── Component ───────────────────────────────────────────────────────

export function BidTemplateFormPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = !!id;
  const navigate = useNavigate();
  const { toast } = useToast();

  const {
    data: template,
    isLoading: isLoadingTemplate,
    isError: isTemplateError,
    error: templateError,
    refetch: refetchTemplate,
    isFetching: isRefetchingTemplate,
  } = useBidTemplate(id);
  const { data: tradesData } = useTrades();
  const trades = tradesData ?? [];

  const createMutation = useCreateBidTemplate();
  const updateMutation = useUpdateBidTemplate();
  const duplicateMutation = useDuplicateBidTemplate();
  const isPending = createMutation.isPending || updateMutation.isPending;

  // Locked when editing a template that a live (non-cancelled) bid_package
  // references. Backend will 409 the PUT, so we surface it pre-emptively.
  // Task 8.1 freeze guards.
  const isLocked = isEdit && template?.is_in_use === true;
  const blocker = template?.referencing_packages?.[0];
  // Use the server-reported total, not array length: the array is capped.
  const blockerCount =
    template?.referencing_packages_total ??
    template?.referencing_packages?.length ??
    0;

  const handleDuplicate = () => {
    if (!id) return;
    duplicateMutation.mutate(id, {
      onSuccess: (newTemplate) => {
        toast({
          variant: 'success',
          message: `Created "${newTemplate.name}". Editing the copy.`,
        });
        navigate(ROUTES.BID_TEMPLATE_EDIT.replace(':id', newTemplate.id));
      },
      onError: (error) =>
        toast({
          variant: 'danger',
          message: errorMessage(error, 'Failed to duplicate template.'),
        }),
    });
  };

  const methods = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: '',
      trade_id: '',
      is_lump_sum: true,
      items: [],
    },
  });

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
  } = methods;

  const isLumpSum = watch('is_lump_sum');
  const watchedItems = watch('items');

  // Populate form on edit
  useEffect(() => {
    if (template && isEdit) {
      reset({
        name: template.name,
        trade_id: template.trade_id || '',
        is_lump_sum: template.is_lump_sum,
        items: template.items.map((item) => ({
          description: item.description,
          item_type: item.item_type as 'lump_sum' | 'unit_price',
          unit_of_measure: item.unit_of_measure || '',
        })),
      });
    }
  }, [template, isEdit, reset]);

  // Trade dropdown options.
  //
  // useTrades only returns active trades. If this template points at one that
  // has since been deactivated, the Select would have no matching option, the
  // browser would fall back to the first ("None"), and saving would silently
  // drop the association. Keep the stored value as an option so it round-trips.
  // It is only ever offered on the template that already holds it.
  const tradeOptions = useMemo(() => {
    const options = [{ value: '', label: 'None \u2014 General Purpose' }];
    for (const trade of trades) {
      options.push({ value: trade.id, label: trade.name });
    }
    if (
      template?.trade_id &&
      !options.some((option) => option.value === template.trade_id)
    ) {
      options.splice(1, 0, {
        value: template.trade_id,
        label: `${template.trade_name ?? 'Unknown trade'} (inactive)`,
      });
    }
    return options;
  }, [trades, template?.trade_id, template?.trade_name]);

  const onSubmit = (data: FormValues) => {
    const payload = {
      name: data.name,
      trade_id: data.trade_id || null,
      is_lump_sum: data.is_lump_sum,
      items: data.is_lump_sum
        ? []
        : data.items.map((item) => ({
            // Trim on the way out so what passed validation is what is stored;
            // the backend strips these too, and disagreeing would mean a value
            // that validates here and 422s there.
            description: item.description.trim(),
            item_type: item.item_type,
            unit_of_measure:
              item.item_type === 'unit_price'
                ? item.unit_of_measure?.trim() || null
                : null,
          })),
    };

    if (isEdit) {
      updateMutation.mutate(
        { id: id!, ...payload },
        {
          onSuccess: () => {
            toast({ variant: 'success', message: 'Template updated successfully.' });
            navigate(ROUTES.BID_TEMPLATES);
          },
          onError: (error) =>
            toast({
              variant: 'danger',
              message: errorMessage(error, 'Failed to update template.'),
            }),
        },
      );
    } else {
      createMutation.mutate(payload, {
        onSuccess: () => {
          toast({ variant: 'success', message: 'Template created successfully.' });
          navigate(ROUTES.BID_TEMPLATES);
        },
        onError: (error) =>
          toast({
            variant: 'danger',
            message: errorMessage(error, 'Failed to create template.'),
          }),
      });
    }
  };

  if (isEdit && isLoadingTemplate) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-600 border-t-transparent" />
      </div>
    );
  }

  if (isEdit && !isLoadingTemplate && (isTemplateError || !template)) {
    // A dropped connection is not a missing template. Saying "doesn't exist"
    // for a 500 sends the user looking for a record that is fine, and offers
    // no way to try again.
    const isMissing = !templateError || templateError.status === 404;

    return (
      <div className="py-12">
        {isMissing ? (
          <Alert variant="danger" title="Template not found">
            The bid template you're trying to edit doesn't exist or has been deleted.
          </Alert>
        ) : (
          <Alert variant="danger" title="Could not load template">
            <div className="space-y-3">
              <p>{errorMessage(templateError, 'Something went wrong. Please try again.')}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => refetchTemplate()}
                isLoading={isRefetchingTemplate}
              >
                Retry
              </Button>
            </div>
          </Alert>
        )}
        <Button variant="outline" className="mt-4" onClick={() => navigate(ROUTES.BID_TEMPLATES)}>
          Back to Templates
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-secondary-900 sm:text-2xl">
            {isEdit ? 'Edit Template' : 'Create Template'}
          </h1>
          <p className="mt-1 text-sm text-secondary-500">
            {isEdit
              ? 'Update the template details and line items.'
              : 'Define a reusable bid template for vendor pricing submissions.'}
          </p>
        </div>
      </div>

      {isLocked && blocker && (
        <Alert variant="info" title="In use - locked">
          This template is in use by a live bid package
          {' '}
          <span className="font-medium">
            ({blocker.task_name}, {blocker.status}
            {blockerCount > 1 ? `, +${blockerCount - 1} more` : ''})
          </span>
          {' '}
          and is locked to keep all vendor bids comparable. Duplicate to change.
        </Alert>
      )}

      <FormProvider {...methods}>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-8">
          {/* Section 1: Template Metadata */}
          <div className="rounded-lg border border-secondary-200 bg-white p-6">
            <h3 className="mb-4 text-sm font-semibold text-secondary-900">
              Template Details
            </h3>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <FormField
                  label="Template Name"
                  required
                  error={errors.name?.message}
                >
                  <TextInput
                    {...register('name')}
                    placeholder="e.g. Grading & Earthwork — Unit Price Breakdown"
                  />
                </FormField>
              </div>

              <FormField label="Trade Affiliation">
                <Select
                  {...register('trade_id')}
                  options={tradeOptions}
                />
              </FormField>

              <FormField
                label="Bid Format"
                hint={
                  isLumpSum
                    ? 'Vendors submit a single total amount.'
                    : 'Vendors fill in quantities and prices for each line item.'
                }
              >
                <label className="inline-flex cursor-pointer items-center gap-3">
                  <span className="text-sm text-secondary-600">Line Items</span>
                  <input
                    type="checkbox"
                    {...register('is_lump_sum')}
                    className="peer sr-only"
                  />
                  <div className="relative h-6 w-11 rounded-full bg-secondary-300 transition-colors after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:bg-white after:transition-transform peer-checked:bg-primary-600 peer-checked:after:translate-x-full peer-focus-visible:ring-2 peer-focus-visible:ring-primary-500/20" />
                  <span className="text-sm text-secondary-600">Lump Sum</span>
                </label>
              </FormField>
            </div>
          </div>

          {/* Section 2: Line Items (hidden when lump sum) */}
          {!isLumpSum && (
            <div className="rounded-lg border border-secondary-200 bg-white p-6">
              <LineItemsEditor />
              {errors.items && 'root' in errors.items && (
                <p className="mt-2 text-sm text-danger-600">
                  {(errors.items as { root?: { message?: string } }).root?.message}
                </p>
              )}
              {typeof errors.items?.message === 'string' && (
                <p className="mt-2 text-sm text-danger-600">
                  {errors.items.message}
                </p>
              )}
            </div>
          )}

          {/* Section 3: Preview */}
          <div className="rounded-lg border border-secondary-200 bg-white p-6">
            <BidTemplatePreview isLumpSum={isLumpSum} items={watchedItems || []} />
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 border-t border-secondary-200 pt-6">
            <Button
              type="button"
              variant="ghost"
              onClick={() => navigate(ROUTES.BID_TEMPLATES)}
              disabled={isPending || duplicateMutation.isPending}
            >
              Cancel
            </Button>
            {isLocked && (
              <Button
                type="button"
                variant="outline"
                onClick={handleDuplicate}
                isLoading={duplicateMutation.isPending}
              >
                Duplicate
              </Button>
            )}
            <Button
              type="submit"
              isLoading={isPending}
              disabled={isLocked || duplicateMutation.isPending}
            >
              {isEdit ? 'Save Changes' : 'Create Template'}
            </Button>
          </div>
        </form>
      </FormProvider>
    </div>
  );
}
