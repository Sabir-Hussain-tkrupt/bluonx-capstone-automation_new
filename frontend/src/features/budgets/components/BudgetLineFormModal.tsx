import { useEffect, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { Select } from '@/components/ui/Select';
import { DatePicker } from '@/components/ui/DatePicker';
import { FormField } from '@/components/ui/FormField';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import {
  CASH_BUCKET_OPTIONS,
  LINE_SUBTYPE_LABELS,
  LINE_TYPE_LABELS,
  MANUAL_LINE_TYPES,
  SUBTYPES_BY_TYPE,
} from '../constants';
import { useAddBudgetLine, useUpdateBudgetLine } from '../hooks/useBudget';
import type { BudgetLine, BudgetLineInput, BudgetStatus, CashBucket, LineSubtype, ManualLineType } from '../types';
import { parseMoneyInput } from '../utils/money';

const YMD = /^\d{4}-\d{2}-\d{2}$/;

const lineSchema = z
  .object({
    line_type: z.string(),
    line_subtype: z.string(),
    name: z.string().trim().min(1, 'Name is required').max(255, 'Name must be 255 characters or fewer'),
    section_name: z.string().trim().max(100, 'Heading must be 100 characters or fewer'),
    budget_amount: z
      .string()
      .refine((v) => parseMoneyInput(v === '' ? '0' : v) !== null, 'Enter an amount like 1234.56 (no negatives, at most 2 decimals)'),
    anticipated_start_date: z.string(),
    anticipated_end_date: z.string(),
    payment_terms_days: z
      .string()
      .refine((v) => /^\d{1,3}$/.test(v) && Number(v) <= 365, 'Payment terms must be 0–365 days'),
    cash_bucket: z.string(),
  })
  .superRefine((v, ctx) => {
    if (v.anticipated_start_date && !YMD.test(v.anticipated_start_date)) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['anticipated_start_date'], message: 'Pick a valid date.' });
    }
    if (v.anticipated_end_date && !YMD.test(v.anticipated_end_date)) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['anticipated_end_date'], message: 'Pick a valid date.' });
    }
    if (v.anticipated_start_date && v.anticipated_end_date && v.anticipated_end_date < v.anticipated_start_date) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['anticipated_end_date'],
        message: 'The end date must be on or after the start date.',
      });
    }
  });

type LineFormValues = z.infer<typeof lineSchema>;

interface BudgetLineFormModalProps {
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
  budgetStatus: BudgetStatus;
  /** Edit this line; omit to add a new line. */
  line?: BudgetLine | null;
  /** Add mode: create an internal T&M portion under this line's heading. */
  parentLine?: BudgetLine | null;
}

export function BudgetLineFormModal({
  projectId,
  isOpen,
  onClose,
  budgetStatus,
  line,
  parentLine,
}: BudgetLineFormModalProps) {
  const { toast } = useToast();
  const addLine = useAddBudgetLine(projectId);
  const updateLine = useUpdateBudgetLine(projectId);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const isEdit = !!line;
  const isPending = addLine.isPending || updateLine.isPending;
  const baselined = budgetStatus === 'baselined';
  // Amounts are frozen after baseline, on locked lines, and on variances.
  const amountLocked = baselined || !!line?.is_locked || line?.line_type === 'variance';
  const nameLocked = !!line?.task_id;

  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors },
  } = useForm<LineFormValues>({
    resolver: zodResolver(lineSchema),
    mode: 'onChange',
    defaultValues: {
      line_type: 'soft_cost',
      line_subtype: '',
      name: '',
      section_name: '',
      budget_amount: '0',
      anticipated_start_date: '',
      anticipated_end_date: '',
      payment_terms_days: '30',
      cash_bucket: 'land',
    },
  });

  const lineType = useWatch({ control, name: 'line_type' }) as ManualLineType;
  const startDate = useWatch({ control, name: 'anticipated_start_date' });

  useEffect(() => {
    if (!isOpen) return;
    if (line) {
      reset({
        line_type: line.line_type,
        line_subtype: line.line_subtype ?? '',
        name: line.name,
        section_name: line.section_name ?? '',
        budget_amount: Number(line.budget_amount).toFixed(2),
        anticipated_start_date: line.anticipated_start_date ?? '',
        anticipated_end_date: line.anticipated_end_date ?? '',
        payment_terms_days: String(line.payment_terms_days ?? 30),
        cash_bucket: line.cash_bucket,
      });
    } else {
      reset({
        line_type: parentLine ? 'internal_tm' : 'soft_cost',
        line_subtype: '',
        name: parentLine ? `${parentLine.name} — T&M` : '',
        section_name: parentLine?.section_name ?? '',
        budget_amount: '0',
        anticipated_start_date: parentLine?.anticipated_start_date ?? '',
        anticipated_end_date: parentLine?.anticipated_end_date ?? '',
        payment_terms_days: String(parentLine?.payment_terms_days ?? 30),
        cash_bucket: parentLine?.cash_bucket ?? 'land',
      });
    }
  }, [isOpen, line, parentLine, reset]);

  const handleClose = () => {
    if (isPending) return;
    setSubmitError(null);
    onClose();
  };

  const onSubmit = (values: LineFormValues) => {
    setSubmitError(null);
    const amount = parseMoneyInput(values.budget_amount === '' ? '0' : values.budget_amount) ?? '0.00';
    const common: BudgetLineInput = {
      section_name: values.section_name.trim() || null,
      anticipated_start_date: values.anticipated_start_date || null,
      anticipated_end_date: values.anticipated_end_date || null,
      payment_terms_days: Number(values.payment_terms_days),
      cash_bucket: values.cash_bucket as CashBucket,
    };
    const onError = (error: unknown) => setSubmitError(errorMessage(error, 'Could not save the line. Please try again.'));

    if (isEdit && line) {
      const body: BudgetLineInput = { ...common };
      if (!nameLocked && values.name.trim() !== line.name) body.name = values.name.trim();
      if (!amountLocked && amount !== Number(line.budget_amount).toFixed(2)) body.budget_amount = amount;
      updateLine.mutate(
        { lineId: line.id, body },
        {
          onSuccess: () => {
            toast({ variant: 'success', message: `${line.name} updated.` });
            handleClose();
          },
          onError,
        },
      );
      return;
    }

    addLine.mutate(
      {
        ...common,
        line_type: values.line_type as ManualLineType,
        line_subtype: (values.line_subtype || null) as LineSubtype | null,
        name: values.name.trim(),
        parent_line_id: parentLine?.id ?? null,
        budget_amount: baselined ? '0.00' : amount,
      },
      {
        onSuccess: () => {
          toast({ variant: 'success', message: `${values.name.trim()} added.` });
          handleClose();
        },
        onError,
      },
    );
  };

  const subtypes = SUBTYPES_BY_TYPE[lineType] ?? [];
  const title = isEdit ? 'Edit budget line' : parentLine ? 'Add T&M portion' : 'Add budget line';

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={title}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose} disabled={isPending}>
            Cancel
          </Button>
          <Button type="submit" form="budget-line-form" isLoading={isPending}>
            {isEdit ? 'Save changes' : 'Add line'}
          </Button>
        </>
      }
    >
      <form id="budget-line-form" onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {submitError && (
          <Alert variant="danger" title="Could not save line">
            {submitError}
          </Alert>
        )}

        {!isEdit && !parentLine && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Type" htmlFor="line-type" required>
              <Select id="line-type" {...register('line_type')} options={MANUAL_LINE_TYPES} />
            </FormField>
            {subtypes.length > 0 && (
              <FormField label="Kind" htmlFor="line-subtype">
                <Select
                  id="line-subtype"
                  {...register('line_subtype')}
                  placeholder="Select…"
                  options={subtypes.map((s) => ({ value: s, label: LINE_SUBTYPE_LABELS[s] }))}
                />
              </FormField>
            )}
          </div>
        )}

        {isEdit && line && (
          <p className="text-sm text-secondary-600">
            {LINE_TYPE_LABELS[line.line_type]}
            {line.task_name ? ` · task “${line.task_name}”` : ''}
            {line.is_locked ? ' · locked (contract executed)' : ''}
          </p>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            label="Name"
            htmlFor="line-name"
            required
            error={errors.name?.message}
            hint={nameLocked ? 'Follows the task name. Rename the task to change it.' : undefined}
          >
            <TextInput id="line-name" {...register('name')} disabled={nameLocked} error={errors.name?.message} />
          </FormField>
          <FormField label="Heading" htmlFor="line-section" error={errors.section_name?.message} hint="e.g. Land, Soft costs, Site work">
            <TextInput id="line-section" {...register('section_name')} error={errors.section_name?.message} />
          </FormField>
        </div>

        <FormField
          label="Budget amount"
          htmlFor="line-amount"
          error={errors.budget_amount?.message}
          hint={
            amountLocked
              ? baselined
                ? 'The budget is baselined: amounts change through bids, variances and approved top-ups.'
                : 'This amount cannot be edited here.'
              : undefined
          }
        >
          <TextInput
            id="line-amount"
            {...register('budget_amount')}
            inputMode="decimal"
            leftAddon="$"
            className="tabular-nums"
            disabled={amountLocked}
            error={errors.budget_amount?.message}
          />
        </FormField>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField label="Start date" htmlFor="line-start" hint="Needed for cash flow">
            <DatePicker id="line-start" {...register('anticipated_start_date')} error={errors.anticipated_start_date?.message} />
          </FormField>
          <FormField label="End date" htmlFor="line-end" hint="Needed for cash flow">
            <DatePicker
              id="line-end"
              {...register('anticipated_end_date')}
              minDate={startDate || undefined}
              error={errors.anticipated_end_date?.message}
            />
          </FormField>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField label="Payment terms (days)" htmlFor="line-terms" required error={errors.payment_terms_days?.message}>
            <TextInput id="line-terms" {...register('payment_terms_days')} inputMode="numeric" error={errors.payment_terms_days?.message} />
          </FormField>
          <FormField label="Cash bucket" htmlFor="line-bucket" required>
            <Select id="line-bucket" {...register('cash_bucket')} options={CASH_BUCKET_OPTIONS} />
          </FormField>
        </div>
      </form>
    </Modal>
  );
}
