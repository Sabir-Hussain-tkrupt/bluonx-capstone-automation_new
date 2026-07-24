import { useEffect, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { DatePicker } from '@/components/ui/DatePicker';
import { Checkbox } from '@/components/ui/Checkbox';
import { FormField } from '@/components/ui/FormField';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { useCreateHoliday } from '../hooks/useCreateHoliday';
import { useCreateHolidayRange } from '../hooks/useCreateHolidayRange';
import { useUpdateHoliday } from '../hooks/useUpdateHoliday';
import { hasWeekdayInRange, isWeekendYmd, todayYmd } from '../utils/date';
import type { Holiday } from '../services/holidaysApi';

const YMD = /^\d{4}-\d{2}-\d{2}$/;

const holidaySchema = z
  .object({
    multiDay: z.boolean(),
    date: z.string().regex(YMD, 'Pick a valid date.'),
    endDate: z.string().optional().default(''),
    name: z
      .string()
      .trim()
      .min(2, 'Name must be at least 2 characters')
      .max(100, 'Name must be 100 characters or fewer'),
  })
  .superRefine((val, ctx) => {
    if (!val.multiDay) {
      // Single day: a weekend holiday is a no-op, so surface it immediately.
      if (YMD.test(val.date) && isWeekendYmd(val.date)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['date'],
          message: 'Weekends are already non-working days, so adding one has no effect.',
        });
      }
      return;
    }
    // Range mode: weekends inside the range are skipped silently, so only the
    // shape of the range is validated here.
    if (!val.endDate || !YMD.test(val.endDate)) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['endDate'], message: 'Pick an end date.' });
    } else if (val.endDate < val.date) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['endDate'],
        message: 'The end date must be on or after the start date.',
      });
    } else if (!hasWeekdayInRange(val.date, val.endDate)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['endDate'],
        message: 'This range is only weekends, so there is nothing to add.',
      });
    }
  });

type HolidayFormValues = z.infer<typeof holidaySchema>;

interface HolidayFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** When set, the modal edits this holiday; otherwise it creates a new one. */
  holiday?: Holiday | null;
  /** Year the calendar is showing, used to prefill the date on a fresh add. */
  year: number;
}

export function HolidayFormModal({ isOpen, onClose, holiday, year }: HolidayFormModalProps) {
  const { toast } = useToast();
  const createHoliday = useCreateHoliday();
  const createRange = useCreateHolidayRange();
  const updateHoliday = useUpdateHoliday();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const isEdit = !!holiday;
  const isPending = createHoliday.isPending || createRange.isPending || updateHoliday.isPending;
  const today = todayYmd();

  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors },
  } = useForm<HolidayFormValues>({
    resolver: zodResolver(holidaySchema),
    mode: 'onChange',
    defaultValues: { multiDay: false, date: '', endDate: '', name: '' },
  });

  const multiDay = useWatch({ control, name: 'multiDay' });
  const startDate = useWatch({ control, name: 'date' });

  // Sync the form fields each time the modal opens or the target holiday
  // changes (the component stays mounted across opens, so defaultValues alone
  // won't refresh). On a fresh add, prefill the date to the first selectable
  // day of the viewed year (never in the past). `submitError` is cleared on
  // close, not here, to keep this effect free of cascading setState.
  useEffect(() => {
    if (!isOpen) return;
    const defaultAddDate = today > `${year}-01-01` ? today : `${year}-01-01`;
    reset({
      multiDay: false,
      date: holiday?.date ?? defaultAddDate,
      endDate: '',
      name: holiday?.name ?? '',
    });
  }, [isOpen, holiday, year, today, reset]);

  const handleClose = () => {
    setSubmitError(null);
    onClose();
  };

  const closeIfIdle = () => {
    if (isPending) return;
    handleClose();
  };

  const onSubmit = (values: HolidayFormValues) => {
    setSubmitError(null);
    const name = values.name.trim();
    const onError = (error: unknown) =>
      setSubmitError(errorMessage(error, 'Could not save the holiday. Please try again.'));

    if (isEdit && holiday) {
      updateHoliday.mutate(
        { id: holiday.id, date: values.date, name },
        {
          onSuccess: () => {
            toast({ variant: 'success', message: `${name} updated.` });
            handleClose();
          },
          onError,
        },
      );
      return;
    }

    if (values.multiDay && values.endDate) {
      createRange.mutate(
        { startDate: values.date, endDate: values.endDate, name },
        {
          onSuccess: (rows) => {
            toast({
              variant: 'success',
              message:
                rows.length === 1
                  ? `${name} added.`
                  : `${name} added across ${rows.length} working days.`,
            });
            handleClose();
          },
          onError,
        },
      );
      return;
    }

    createHoliday.mutate(
      { date: values.date, name },
      {
        onSuccess: () => {
          toast({ variant: 'success', message: `${name} added.` });
          handleClose();
        },
        onError,
      },
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={closeIfIdle}
      title={isEdit ? 'Edit holiday' : 'Add holiday'}
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={closeIfIdle} disabled={isPending}>
            Cancel
          </Button>
          <Button variant="accent" type="submit" form="holiday-form" isLoading={isPending}>
            {isEdit ? 'Save changes' : 'Add holiday'}
          </Button>
        </>
      }
    >
      <form id="holiday-form" onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {submitError && (
          <Alert variant="danger" title="Could not save holiday">
            {submitError}
          </Alert>
        )}

        <FormField label="Name" required error={errors.name?.message}>
          <TextInput
            {...register('name')}
            placeholder="e.g. Independence Day, Company Holiday"
            error={errors.name?.message}
            autoFocus
          />
        </FormField>

        {/* DatePicker renders its own error text, so FormField supplies only the
            label here — passing error to both would duplicate the message. */}
        <FormField label={multiDay ? 'Start date' : 'Date'} required>
          <DatePicker {...register('date')} minDate={today} error={errors.date?.message} />
        </FormField>

        {!isEdit && (
          <Checkbox
            {...register('multiDay')}
            label="Add a range of days"
            description="Creates one holiday per weekday in the range. Weekends are skipped."
          />
        )}

        {!isEdit && multiDay && (
          <FormField label="End date" required>
            <DatePicker
              {...register('endDate')}
              minDate={startDate || today}
              error={errors.endDate?.message}
            />
          </FormField>
        )}
      </form>
    </Modal>
  );
}
