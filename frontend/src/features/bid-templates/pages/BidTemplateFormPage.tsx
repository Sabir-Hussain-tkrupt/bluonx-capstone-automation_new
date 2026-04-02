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
import { useBidTemplate } from '@/features/bid-templates/hooks/useBidTemplate';
import { useCreateBidTemplate } from '@/features/bid-templates/hooks/useCreateBidTemplate';
import { useUpdateBidTemplate } from '@/features/bid-templates/hooks/useUpdateBidTemplate';
import { useTrades } from '@/features/vendors/hooks/useTrades';
import { LineItemsEditor } from '@/features/bid-templates/components/LineItemsEditor';
import { BidTemplatePreview } from '@/features/bid-templates/components/BidTemplatePreview';

// ─── Zod Schema ──────────────────────────────────────────────────────

const itemSchema = z.object({
  description: z.string().min(1, 'Description is required'),
  item_type: z.enum(['lump_sum', 'unit_price']),
  unit_of_measure: z.string().optional().nullable(),
}).refine(
  (item) => {
    if (item.item_type === 'unit_price') {
      return !!item.unit_of_measure && item.unit_of_measure.trim().length > 0;
    }
    return true;
  },
  {
    message: 'Unit of measure is required for unit price items',
    path: ['unit_of_measure'],
  },
);

const formSchema = z.object({
  name: z.string().min(1, 'Template name is required').max(255),
  trade_id: z.string().optional(),
  is_lump_sum: z.boolean(),
  items: z.array(itemSchema),
}).refine(
  (data) => {
    if (!data.is_lump_sum && data.items.length === 0) {
      return false;
    }
    return true;
  },
  {
    message: 'At least one line item is required for structured templates',
    path: ['items'],
  },
);

type FormValues = z.infer<typeof formSchema>;

// ─── Component ───────────────────────────────────────────────────────

export function BidTemplateFormPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = !!id;
  const navigate = useNavigate();
  const { toast } = useToast();

  const { data: template, isLoading: isLoadingTemplate, isError: isTemplateError } = useBidTemplate(id);
  const { data: tradesData } = useTrades();
  const trades = tradesData ?? [];

  const createMutation = useCreateBidTemplate();
  const updateMutation = useUpdateBidTemplate();
  const isPending = createMutation.isPending || updateMutation.isPending;

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

  // Trade dropdown options
  const tradeOptions = useMemo(() => {
    const options = [{ value: '', label: 'None \u2014 General Purpose' }];
    for (const trade of trades) {
      options.push({ value: trade.id, label: trade.name });
    }
    return options;
  }, [trades]);

  const onSubmit = (data: FormValues) => {
    const payload = {
      name: data.name,
      trade_id: data.trade_id || null,
      is_lump_sum: data.is_lump_sum,
      items: data.is_lump_sum
        ? []
        : data.items.map((item) => ({
            description: item.description,
            item_type: item.item_type,
            unit_of_measure:
              item.item_type === 'unit_price'
                ? item.unit_of_measure || null
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
          onError: (error) => {
            const apiError = error as { message?: string };
            toast({
              variant: 'danger',
              message: apiError.message || 'Failed to update template.',
            });
          },
        },
      );
    } else {
      createMutation.mutate(payload, {
        onSuccess: () => {
          toast({ variant: 'success', message: 'Template created successfully.' });
          navigate(ROUTES.BID_TEMPLATES);
        },
        onError: (error) => {
          const apiError = error as { message?: string };
          toast({
            variant: 'danger',
            message: apiError.message || 'Failed to create template.',
          });
        },
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
    return (
      <div className="py-12 text-center">
        <h2 className="text-lg font-semibold text-secondary-900">Template not found</h2>
        <p className="mt-1 text-sm text-secondary-500">
          The bid template you're trying to edit doesn't exist or has been deleted.
        </p>
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
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button type="submit" isLoading={isPending}>
              {isEdit ? 'Save Changes' : 'Create Template'}
            </Button>
          </div>
        </form>
      </FormProvider>
    </div>
  );
}
