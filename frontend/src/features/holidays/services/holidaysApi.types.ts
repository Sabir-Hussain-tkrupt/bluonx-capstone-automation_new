/**
 * Contract for the holiday-calendar data layer.
 *
 * `holidaysApi.real.ts` implements `HolidaysApi`; consumers import the resolved
 * functions from `holidaysApi.ts` only, never from the implementation.
 *
 * Rule violations arrive as the app-wide `ApiError` and are surfaced through
 * `errorMessage()`, which shows the server's `message` verbatim. There is no
 * holiday-specific error type: the axios interceptor derives `code` from the
 * HTTP status, so a client-side rule enum could only ever be fiction.
 */

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
