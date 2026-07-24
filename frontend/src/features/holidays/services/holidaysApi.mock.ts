/**
 * In-memory mock for the holiday calendar.
 *
 * Never import from this file directly — import from `holidaysApi.ts`, which
 * chooses between this mock and the real backend.
 *
 * Holds a session-scoped `Holiday[]`, seeded with the US federal *observed*
 * dates for the current and next year (plus a couple of manual rows so the
 * demo shows both sources). It deliberately enforces the exact rules the real
 * backend will (see `HolidayValidationError`) and simulates network latency, so
 * the UI's loading and error paths are genuinely exercised rather than dead
 * code. Edits persist only until reload.
 */
import type {
  Holiday,
  HolidayErrorCode,
  HolidayValidationError,
  HolidaysApi,
} from './holidaysApi.types';
import { addDaysYmd, isPastYmd, isWeekendYmd, yearOf } from '../utils/date';

// ─── Rules ────────────────────────────────────────────────────────────────
const MAX_HOLIDAYS_PER_YEAR = 25;
const MAX_CONSECUTIVE_NON_WORKING_DAYS = 14;
// Defensive ceiling on a single range request (a holiday shutdown is days, not
// years); also bounds the day-by-day loop.
const MAX_RANGE_SPAN_DAYS = 366;

// ─── Latency simulation ─────────────────────────────────────────────────────
function delay(): Promise<void> {
  const ms = 250 + Math.floor(Math.random() * 250);
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ─── Error helper ────────────────────────────────────────────────────────────
function rejectRule(code: HolidayErrorCode, message: string): never {
  const status = code === 'DUPLICATE_DATE' ? 409 : 422;
  const error: HolidayValidationError = { code, message, status };
  throw error;
}

// ─── Seed data (US federal observed dates, verified) ─────────────────────────
type SeedRow = { date: string; name: string; source: Holiday['source'] };

const SEED_2026: SeedRow[] = [
  { date: '2026-01-01', name: "New Year's Day", source: 'seeded' },
  { date: '2026-01-19', name: 'Martin Luther King Jr. Day', source: 'seeded' },
  { date: '2026-02-16', name: "Washington's Birthday", source: 'seeded' },
  { date: '2026-05-25', name: 'Memorial Day', source: 'seeded' },
  { date: '2026-06-19', name: 'Juneteenth National Independence Day', source: 'seeded' },
  { date: '2026-07-03', name: 'Independence Day (observed)', source: 'seeded' },
  { date: '2026-09-07', name: 'Labor Day', source: 'seeded' },
  { date: '2026-10-12', name: 'Columbus Day', source: 'seeded' },
  { date: '2026-11-11', name: 'Veterans Day', source: 'seeded' },
  { date: '2026-11-26', name: 'Thanksgiving Day', source: 'seeded' },
  { date: '2026-12-25', name: 'Christmas Day', source: 'seeded' },
  // Manual rows so both sources (and the badge) appear in the demo.
  { date: '2026-11-27', name: 'Day After Thanksgiving', source: 'manual' },
  { date: '2026-12-24', name: 'Christmas Eve', source: 'manual' },
];

const SEED_2027: SeedRow[] = [
  { date: '2027-01-01', name: "New Year's Day", source: 'seeded' },
  { date: '2027-01-18', name: 'Martin Luther King Jr. Day', source: 'seeded' },
  { date: '2027-02-15', name: "Washington's Birthday", source: 'seeded' },
  { date: '2027-05-31', name: 'Memorial Day', source: 'seeded' },
  { date: '2027-06-18', name: 'Juneteenth National Independence Day (observed)', source: 'seeded' },
  { date: '2027-07-05', name: 'Independence Day (observed)', source: 'seeded' },
  { date: '2027-09-06', name: 'Labor Day', source: 'seeded' },
  { date: '2027-10-11', name: 'Columbus Day', source: 'seeded' },
  { date: '2027-11-11', name: 'Veterans Day', source: 'seeded' },
  { date: '2027-11-25', name: 'Thanksgiving Day', source: 'seeded' },
  { date: '2027-12-24', name: 'Christmas Day (observed)', source: 'seeded' },
];

function seed(): Holiday[] {
  const now = new Date().toISOString();
  return [...SEED_2026, ...SEED_2027].map((row) => ({
    id: crypto.randomUUID(),
    date: row.date,
    name: row.name,
    source: row.source,
    created_at: now,
    updated_at: now,
  }));
}

// Session-scoped store.
let holidays: Holiday[] = seed();

// ─── Validation ──────────────────────────────────────────────────────────────
/**
 * Length of the run of consecutive non-working days (weekends + holidays) that
 * would contain `candidate`, given the set of *other* holiday dates. The
 * candidate itself counts as day 1.
 */
function consecutiveRunLength(candidate: string, otherHolidays: Set<string>): number {
  const isNonWorking = (date: string) => isWeekendYmd(date) || otherHolidays.has(date);

  let count = 1;
  for (let cur = addDaysYmd(candidate, -1); isNonWorking(cur); cur = addDaysYmd(cur, -1)) {
    count += 1;
  }
  for (let cur = addDaysYmd(candidate, 1); isNonWorking(cur); cur = addDaysYmd(cur, 1)) {
    count += 1;
  }
  return count;
}

/**
 * Run every write rule against a candidate date, ignoring the row identified by
 * `excludeId` (set on edits so a row doesn't collide with itself). Throws a
 * `HolidayValidationError` on the first violation, in a stable order.
 */
function assertWritable(date: string, excludeId: string | null): void {
  const others = holidays.filter((h) => h.id !== excludeId);

  if (isPastYmd(date)) {
    rejectRule('PAST_DATE', 'Holidays in the past cannot be added or changed.');
  }

  if (isWeekendYmd(date)) {
    rejectRule(
      'WEEKEND',
      'Weekends are already non-working days, so adding one has no effect.',
    );
  }

  if (others.some((h) => h.date === date)) {
    rejectRule('DUPLICATE_DATE', 'A holiday already exists on this date.');
  }

  const year = yearOf(date);
  const countInYear = others.filter((h) => yearOf(h.date) === year).length;
  if (countInYear >= MAX_HOLIDAYS_PER_YEAR) {
    rejectRule(
      'YEAR_LIMIT',
      `A calendar year can hold at most ${MAX_HOLIDAYS_PER_YEAR} holidays. ${year} is already full.`,
    );
  }

  const run = consecutiveRunLength(date, new Set(others.map((h) => h.date)));
  if (run > MAX_CONSECUTIVE_NON_WORKING_DAYS) {
    rejectRule(
      'CONSECUTIVE_LIMIT',
      `This would create a run of ${run} consecutive non-working days (weekends included). The limit is ${MAX_CONSECUTIVE_NON_WORKING_DAYS}.`,
    );
  }
}

function makeRow(date: string, name: string, source: Holiday['source']): Holiday {
  const now = new Date().toISOString();
  return { id: crypto.randomUUID(), date, name, source, created_at: now, updated_at: now };
}

// ─── Implementation ──────────────────────────────────────────────────────────
export const mockHolidaysApi: HolidaysApi = {
  async listHolidays(year) {
    await delay();
    return holidays
      .filter((h) => yearOf(h.date) === year)
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((h) => ({ ...h }));
  },

  async createHoliday(input) {
    await delay();
    const date = input.date;
    const name = input.name.trim();
    assertWritable(date, null);

    const holiday = makeRow(date, name, 'manual');
    holidays = [...holidays, holiday];
    return { ...holiday };
  },

  async createHolidayRange(input) {
    await delay();
    const name = input.name.trim();
    const { startDate, endDate } = input;

    // Bound the loop; ordering/span validity is a form concern but backstopped.
    let span = 0;
    for (let cur = startDate; cur <= endDate; cur = addDaysYmd(cur, 1)) {
      span += 1;
      if (span > MAX_RANGE_SPAN_DAYS) {
        rejectRule('EMPTY_RANGE', 'That date range is too long to add at once.');
      }
    }

    // One candidate per weekday in the range; weekends are skipped silently.
    const candidates: string[] = [];
    for (let cur = startDate; cur <= endDate; cur = addDaysYmd(cur, 1)) {
      if (!isWeekendYmd(cur)) candidates.push(cur);
    }
    if (candidates.length === 0) {
      rejectRule('EMPTY_RANGE', 'That range contains only weekends, so there is nothing to add.');
    }

    // Validate the whole range atomically against the prospective final state.
    const existingDates = new Set(holidays.map((h) => h.date));
    const prospective = new Set([...existingDates, ...candidates]);

    for (const date of candidates) {
      if (isPastYmd(date)) {
        rejectRule('PAST_DATE', 'Holidays in the past cannot be added.');
      }
      if (existingDates.has(date)) {
        rejectRule('DUPLICATE_DATE', `A holiday already exists on ${date} within this range.`);
      }
    }

    const countByYear = new Map<number, number>();
    for (const date of prospective) {
      const y = yearOf(date);
      countByYear.set(y, (countByYear.get(y) ?? 0) + 1);
    }
    for (const [y, count] of countByYear) {
      if (count > MAX_HOLIDAYS_PER_YEAR) {
        rejectRule(
          'YEAR_LIMIT',
          `This range would push ${y} past the ${MAX_HOLIDAYS_PER_YEAR}-holiday limit for a calendar year.`,
        );
      }
    }

    for (const date of candidates) {
      const rest = new Set(prospective);
      rest.delete(date);
      const run = consecutiveRunLength(date, rest);
      if (run > MAX_CONSECUTIVE_NON_WORKING_DAYS) {
        rejectRule(
          'CONSECUTIVE_LIMIT',
          `This range would create a run of ${run} consecutive non-working days (weekends included). The limit is ${MAX_CONSECUTIVE_NON_WORKING_DAYS}.`,
        );
      }
    }

    const rows = candidates.map((date) => makeRow(date, name, 'manual'));
    holidays = [...holidays, ...rows];
    return rows.map((r) => ({ ...r }));
  },

  async updateHoliday(input) {
    await delay();
    const existing = holidays.find((h) => h.id === input.id);
    if (!existing) {
      const error: HolidayValidationError = {
        code: 'DUPLICATE_DATE',
        message: 'This holiday no longer exists.',
        status: 404,
      };
      throw error;
    }
    // A past holiday cannot be edited, regardless of the new date.
    if (isPastYmd(existing.date)) {
      rejectRule('PAST_DATE', 'Holidays in the past cannot be added or changed.');
    }
    assertWritable(input.date, input.id);

    const updated: Holiday = {
      ...existing,
      date: input.date,
      name: input.name.trim(),
      updated_at: new Date().toISOString(),
    };
    holidays = holidays.map((h) => (h.id === updated.id ? updated : h));
    return { ...updated };
  },

  async deleteHoliday(id) {
    await delay();
    const existing = holidays.find((h) => h.id === id);
    if (!existing) return;
    if (isPastYmd(existing.date)) {
      rejectRule('PAST_DATE', 'Holidays in the past cannot be deleted.');
    }
    holidays = holidays.filter((h) => h.id !== id);
  },
};
