/**
 * Contract for the holiday-calendar data layer.
 *
 * The mock (`holidaysApi.mock.ts`) and the future real backend
 * (`holidaysApi.real.ts`) both implement `HolidaysApi`. Because both are typed
 * against this one interface, they cannot drift without a compile error — the
 * same drift-prevention net the vendor portal uses.
 *
 * Consumers import the resolved functions from `holidaysApi.ts` only, never
 * from a specific implementation.
 */
import type { ApiError } from '@/lib/api';

/** `'seeded'` rows come from the annual federal-holiday job; `'manual'` rows were added by an admin. Both are ordinary, editable, deletable rows. */
export type HolidaySource = 'seeded' | 'manual';

export interface Holiday {
  id: string;
  /** "YYYY-MM-DD". */
  date: string;
  name: string;
  source: HolidaySource;
  created_at: string;
  updated_at: string;
}

export interface CreateHolidayInput {
  /** "YYYY-MM-DD". */
  date: string;
  name: string;
}

export interface UpdateHolidayInput {
  id: string;
  /** "YYYY-MM-DD". */
  date: string;
  name: string;
}

export interface CreateHolidayRangeInput {
  /** Inclusive start, "YYYY-MM-DD". */
  startDate: string;
  /** Inclusive end, "YYYY-MM-DD". */
  endDate: string;
  name: string;
}

/**
 * The business rules the calendar enforces. The mock rejects with these codes
 * today; the real backend will return the same `{ code, message }` shape, so
 * the UI's error handling needs no change when the swap happens.
 */
export type HolidayErrorCode =
  | 'PAST_DATE'
  | 'WEEKEND'
  | 'YEAR_LIMIT'
  | 'CONSECUTIVE_LIMIT'
  | 'DUPLICATE_DATE'
  | 'EMPTY_RANGE';

/**
 * A rule violation. Extends the app-wide `ApiError` so `errorMessage()` and the
 * existing toast/alert paths surface `message` verbatim, while `code` lets
 * callers branch if they ever need to.
 */
export interface HolidayValidationError extends ApiError {
  code: HolidayErrorCode;
}

export interface HolidaysApi {
  /** Holidays whose date falls in `year`, ascending by date. */
  listHolidays(year: number): Promise<Holiday[]>;
  createHoliday(input: CreateHolidayInput): Promise<Holiday>;
  /**
   * Insert one holiday per weekday in `[startDate, endDate]`, skipping weekends
   * silently. Atomic: if any weekday would break a rule, nothing is inserted.
   */
  createHolidayRange(input: CreateHolidayRangeInput): Promise<Holiday[]>;
  updateHoliday(input: UpdateHolidayInput): Promise<Holiday>;
  deleteHoliday(id: string): Promise<void>;
}
