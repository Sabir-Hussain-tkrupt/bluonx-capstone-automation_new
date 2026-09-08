import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { makeApiError } from '@/test/api-error';
import { HolidayFormModal } from '../HolidayFormModal';

const createHolidayMutate = vi.fn();
const createRangeMutate = vi.fn();
const updateHolidayMutate = vi.fn();

vi.mock('../../hooks/useCreateHoliday', () => ({
  useCreateHoliday: () => ({ mutate: createHolidayMutate, isPending: false }),
}));
vi.mock('../../hooks/useCreateHolidayRange', () => ({
  useCreateHolidayRange: () => ({ mutate: createRangeMutate, isPending: false }),
}));
vi.mock('../../hooks/useUpdateHoliday', () => ({
  useUpdateHoliday: () => ({ mutate: updateHolidayMutate, isPending: false }),
}));

// The form sets min={today} on the date input, so jsdom's constraint
// validation refuses to submit any date before today and handleSubmit never
// fires. Pin "today" ahead of the fixtures below so they stay submittable.
// Only todayYmd is overridden: isWeekendYmd and hasWeekdayInRange from the
// same module drive the validation the other cases assert on.
vi.mock('../../utils/date', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/date')>()),
  todayYmd: () => '2026-09-01',
}));

// 2026-09-07 is a Monday, 2026-09-11 a Friday, 2026-09-05/06 the weekend before.
const MONDAY = '2026-09-07';
const FRIDAY = '2026-09-11';
const SATURDAY = '2026-09-05';
const SUNDAY = '2026-09-06';

// The required marker renders inside the label, so its text is "Date*".
const SINGLE_DATE = /^date\s*\*?$/i;

function setDate(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

async function fillName(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.clear(screen.getByLabelText(/name/i));
  await user.type(screen.getByLabelText(/name/i), name);
}

function renderModal() {
  return renderWithRouter(
    <HolidayFormModal isOpen onClose={vi.fn()} year={2026} />,
  );
}

describe('HolidayFormModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('creates a single holiday on a weekday', async () => {
    const user = userEvent.setup();
    renderModal();

    await fillName(user, 'Company Day');
    setDate(SINGLE_DATE,MONDAY);
    await user.click(screen.getByRole('button', { name: /add holiday/i }));

    await waitFor(() => expect(createHolidayMutate).toHaveBeenCalled());
    expect(createHolidayMutate.mock.calls[0][0]).toEqual({
      date: MONDAY,
      name: 'Company Day',
    });
    expect(createRangeMutate).not.toHaveBeenCalled();
  });

  it('blocks a single holiday on a weekend, which would be a no-op', async () => {
    const user = userEvent.setup();
    renderModal();

    await fillName(user, 'Weekend Day');
    setDate(SINGLE_DATE,SATURDAY);
    await user.click(screen.getByRole('button', { name: /add holiday/i }));

    expect(
      await screen.findByText(/Weekends are already non-working days/i),
    ).toBeInTheDocument();
    expect(createHolidayMutate).not.toHaveBeenCalled();
  });

  it('creates a range when "Add a range of days" is checked', async () => {
    const user = userEvent.setup();
    renderModal();

    await fillName(user, 'Shutdown Week');
    await user.click(screen.getByLabelText(/add a range of days/i));
    setDate(/start date/i, MONDAY);
    setDate(/end date/i, FRIDAY);
    await user.click(screen.getByRole('button', { name: /add holiday/i }));

    await waitFor(() => expect(createRangeMutate).toHaveBeenCalled());
    expect(createRangeMutate.mock.calls[0][0]).toEqual({
      startDate: MONDAY,
      endDate: FRIDAY,
      name: 'Shutdown Week',
    });
    expect(createHolidayMutate).not.toHaveBeenCalled();
  });

  it('rejects a range whose end is before its start', async () => {
    const user = userEvent.setup();
    renderModal();

    await fillName(user, 'Backwards');
    await user.click(screen.getByLabelText(/add a range of days/i));
    setDate(/start date/i, FRIDAY);
    setDate(/end date/i, MONDAY);
    await user.click(screen.getByRole('button', { name: /add holiday/i }));

    expect(
      await screen.findByText(/end date must be on or after the start date/i),
    ).toBeInTheDocument();
    expect(createRangeMutate).not.toHaveBeenCalled();
  });

  it('rejects a weekend-only range, which would add nothing', async () => {
    const user = userEvent.setup();
    renderModal();

    await fillName(user, 'Just The Weekend');
    await user.click(screen.getByLabelText(/add a range of days/i));
    setDate(/start date/i, SATURDAY);
    setDate(/end date/i, SUNDAY);
    await user.click(screen.getByRole('button', { name: /add holiday/i }));

    expect(
      await screen.findByText(/only weekends, so there is nothing to add/i),
    ).toBeInTheDocument();
    expect(createRangeMutate).not.toHaveBeenCalled();
  });

  it('requires a name of at least 2 characters', async () => {
    const user = userEvent.setup();
    renderModal();

    await fillName(user, 'x');
    setDate(SINGLE_DATE,MONDAY);
    await user.click(screen.getByRole('button', { name: /add holiday/i }));

    expect(await screen.findByText(/at least 2 characters/i)).toBeInTheDocument();
    expect(createHolidayMutate).not.toHaveBeenCalled();
  });

  it('surfaces the server message when the save is rejected', async () => {
    // The 409 guard names the conflict (e.g. a duplicate date), which is more
    // useful than the generic fallback.
    createHolidayMutate.mockImplementation((_input, opts) =>
      opts.onError?.(makeApiError('A holiday already exists on that date.', 409, 'CONFLICT')),
    );
    const user = userEvent.setup();
    renderModal();

    await fillName(user, 'Duplicate Day');
    setDate(SINGLE_DATE,MONDAY);
    await user.click(screen.getByRole('button', { name: /add holiday/i }));

    expect(
      await screen.findByText('A holiday already exists on that date.'),
    ).toBeInTheDocument();
  });
});
