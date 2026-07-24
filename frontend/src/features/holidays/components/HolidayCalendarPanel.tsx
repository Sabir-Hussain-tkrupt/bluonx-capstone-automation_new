import { useMemo, useState } from 'react';
import { CalendarDays, Pencil, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { IconButton } from '@/components/ui/IconButton';
import { Select } from '@/components/ui/Select';
import { Alert } from '@/components/ui/Alert';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/Toast';
import { useAuth } from '@/contexts/AuthContext';
import { errorMessage } from '@/lib/api';
import { formatDateOnly } from '@/lib/format';
import { cn } from '@/utils/cn';
import { useHolidays } from '../hooks/useHolidays';
import { useDeleteHoliday } from '../hooks/useDeleteHoliday';
import { isPastYmd, weekdayShort } from '../utils/date';
import type { Holiday } from '../services/holidaysApi';
import { HolidayFormModal } from './HolidayFormModal';

const MAX_HOLIDAYS_PER_YEAR = 25;
const currentYear = new Date().getFullYear();
const YEAR_OPTIONS = Array.from({ length: 6 }, (_, i) => currentYear - 1 + i);

export function HolidayCalendarPanel() {
  const { profile } = useAuth();
  const isAdmin = profile?.role === 'admin';
  const { toast } = useToast();

  const [year, setYear] = useState(currentYear);
  const { data: holidays, isLoading, isError, error, refetch } = useHolidays(year);

  // Every date in a past year is unaddable, so offering "Add" there would only
  // ever error. Show the affordance solely where a holiday could actually land.
  const canAdd = isAdmin && year >= currentYear;

  // Badge only the manual exceptions, and only in a year that also has a seeded
  // baseline. A badge on every row (or on an all-manual year) carries no signal.
  const mixedSources = useMemo(() => {
    const rows = holidays ?? [];
    return rows.some((h) => h.source === 'seeded') && rows.some((h) => h.source === 'manual');
  }, [holidays]);

  const [formState, setFormState] = useState<{ isOpen: boolean; holiday: Holiday | null }>({
    isOpen: false,
    holiday: null,
  });
  const [deleteTarget, setDeleteTarget] = useState<Holiday | null>(null);
  const deleteHoliday = useDeleteHoliday();

  const yearOptions = useMemo(
    () => YEAR_OPTIONS.map((y) => ({ value: String(y), label: String(y) })),
    [],
  );

  const openAdd = () => setFormState({ isOpen: true, holiday: null });
  const openEdit = (holiday: Holiday) => setFormState({ isOpen: true, holiday });
  const closeForm = () => setFormState((prev) => ({ ...prev, isOpen: false }));

  const handleDelete = () => {
    if (!deleteTarget) return;
    deleteHoliday.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast({ variant: 'success', message: `${deleteTarget.name} removed.` });
        setDeleteTarget(null);
      },
      onError: (err) => {
        toast({ variant: 'danger', message: errorMessage(err, 'Could not delete the holiday.') });
        setDeleteTarget(null);
      },
    });
  };

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-end gap-4">
          <div className="w-32">
            <label
              htmlFor="holiday-year"
              className="mb-1 block text-sm font-medium text-secondary-900"
            >
              Year
            </label>
            <Select
              id="holiday-year"
              options={yearOptions}
              value={String(year)}
              onChange={(e) => setYear(Number(e.target.value))}
            />
          </div>
          {holidays && (
            <p className="pb-2 text-sm text-secondary-500">
              <span className="font-semibold text-secondary-700">{holidays.length}</span> of{' '}
              {MAX_HOLIDAYS_PER_YEAR} holidays
            </p>
          )}
        </div>
        {canAdd && (
          <Button
            variant="accent"
            leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />}
            onClick={openAdd}
          >
            Add holiday
          </Button>
        )}
      </div>

      {/* Body */}
      <div className="rounded-lg border border-secondary-200 bg-white shadow-sm">
        {isLoading ? (
          <div className="space-y-2 p-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} variant="rectangular" height="2.25rem" />
            ))}
          </div>
        ) : isError ? (
          <div className="p-4">
            <Alert variant="danger" title="Could not load holidays">
              <p>{errorMessage(error, 'Something went wrong. Please try again.')}</p>
              <Button variant="outline" size="sm" className="mt-3" onClick={() => refetch()}>
                Retry
              </Button>
            </Alert>
          </div>
        ) : !holidays || holidays.length === 0 ? (
          <EmptyState
            icon={<CalendarDays className="h-12 w-12 text-secondary-300" aria-hidden="true" />}
            title={`No holidays for ${year}`}
            description={
              canAdd
                ? 'Add the dates that should extend vendor response deadlines this year.'
                : 'No holidays have been recorded for this year.'
            }
            action={
              canAdd ? (
                <Button
                  variant="accent"
                  leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />}
                  onClick={openAdd}
                >
                  Add holiday
                </Button>
              ) : undefined
            }
          />
        ) : (
          <ul className="divide-y divide-secondary-100">
            {holidays.map((holiday) => {
              const past = isPastYmd(holiday.date);
              const canManage = isAdmin && !past;
              return (
                <li
                  key={holiday.id}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2 text-sm',
                    past ? 'text-secondary-400' : 'text-secondary-800 hover:bg-secondary-50',
                  )}
                >
                  <span
                    className={cn(
                      'w-36 shrink-0 tabular-nums text-xs',
                      past ? 'text-secondary-400' : 'text-secondary-500',
                    )}
                  >
                    {weekdayShort(holiday.date)}, {formatDateOnly(holiday.date)}
                  </span>
                  <span className="min-w-0 max-w-md truncate font-medium">{holiday.name}</span>
                  {mixedSources && holiday.source === 'manual' && (
                    <span
                      className={cn(
                        'rounded-full border border-accent-200 bg-accent-50 px-2 py-0.5 text-xs font-medium text-accent-700',
                        past && 'opacity-60',
                      )}
                    >
                      Custom
                    </span>
                  )}
                  {canManage && (
                    <span className="flex items-center gap-0.5">
                      <IconButton
                        size="sm"
                        aria-label={`Edit ${holiday.name}`}
                        icon={<Pencil className="h-4 w-4" aria-hidden="true" />}
                        onClick={() => openEdit(holiday)}
                      />
                      <IconButton
                        size="sm"
                        aria-label={`Delete ${holiday.name}`}
                        icon={<Trash2 className="h-4 w-4" aria-hidden="true" />}
                        onClick={() => setDeleteTarget(holiday)}
                      />
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <HolidayFormModal
        isOpen={formState.isOpen}
        holiday={formState.holiday}
        year={year}
        onClose={closeForm}
      />

      <ConfirmDialog
        isOpen={!!deleteTarget}
        title="Delete holiday"
        message={
          <>
            Remove <span className="font-semibold">{deleteTarget?.name}</span> (
            {deleteTarget ? formatDateOnly(deleteTarget.date) : ''}) from the calendar? Vendor
            response deadlines will no longer skip this date. This cannot be undone.
          </>
        }
        confirmText="Delete"
        confirmVariant="danger"
        isLoading={deleteHoliday.isPending}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
