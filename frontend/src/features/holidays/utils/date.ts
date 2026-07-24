/**
 * Date helpers for the holiday calendar, all operating on plain
 * "YYYY-MM-DD" strings (never `Date` objects across boundaries) to sidestep
 * the UTC-midnight off-by-one that `new Date("YYYY-MM-DD")` causes in
 * negative-offset zones. Mirrors the reasoning behind `formatDateOnly` in
 * `@/lib/format`.
 */

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

/** Today's local date as "YYYY-MM-DD". */
export function todayYmd(): string {
  const now = new Date();
  return `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`;
}

/**
 * True when `ymd` is strictly before today (local). Zero-padded ISO dates
 * compare correctly as plain strings, so no `Date` parsing is needed.
 */
export function isPastYmd(ymd: string): boolean {
  return ymd < todayYmd();
}

/** The 4-digit calendar year of a "YYYY-MM-DD" string. */
export function yearOf(ymd: string): number {
  return Number(ymd.slice(0, 4));
}

/** Day of week for a "YYYY-MM-DD" string (0 = Sunday … 6 = Saturday), in local time. */
export function weekdayIndex(ymd: string): number {
  const [y, m, d] = ymd.split('-').map(Number);
  return new Date(y, m - 1, d).getDay();
}

/** Short weekday name, e.g. "Mon". */
export function weekdayShort(ymd: string): string {
  const [y, m, d] = ymd.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { weekday: 'short' });
}

/** Saturday or Sunday. */
export function isWeekendYmd(ymd: string): boolean {
  const day = weekdayIndex(ymd);
  return day === 0 || day === 6;
}

/** Shift a "YYYY-MM-DD" date by `days` (may be negative), returning "YYYY-MM-DD". */
export function addDaysYmd(ymd: string, days: number): string {
  const [y, m, d] = ymd.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  date.setDate(date.getDate() + days);
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

/** True when `[start, end]` (inclusive) contains at least one weekday. */
export function hasWeekdayInRange(start: string, end: string): boolean {
  if (end < start) return false;
  for (let cur = start; cur <= end; cur = addDaysYmd(cur, 1)) {
    if (!isWeekendYmd(cur)) return true;
  }
  return false;
}
