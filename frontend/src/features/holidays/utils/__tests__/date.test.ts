import { describe, it, expect } from 'vitest';
import {
  addDaysYmd,
  hasWeekdayInRange,
  isPastYmd,
  isWeekendYmd,
  todayYmd,
  weekdayIndex,
  yearOf,
} from '../date';

// Reference dates, all local: 2026-06-06 is a Saturday, 2026-06-07 a Sunday,
// 2026-06-08 a Monday.
const SATURDAY = '2026-06-06';
const SUNDAY = '2026-06-07';
const MONDAY = '2026-06-08';
const FRIDAY = '2026-06-05';

describe('weekdayIndex', () => {
  it('reads the local weekday, not the UTC one', () => {
    // `new Date("2026-06-06")` parses as UTC midnight and lands on the previous
    // day in negative-offset zones. These helpers split the string instead,
    // which is the whole reason they exist.
    expect(weekdayIndex(SATURDAY)).toBe(6);
    expect(weekdayIndex(SUNDAY)).toBe(0);
    expect(weekdayIndex(MONDAY)).toBe(1);
  });
});

describe('isWeekendYmd', () => {
  it('counts Saturday and Sunday only', () => {
    expect(isWeekendYmd(SATURDAY)).toBe(true);
    expect(isWeekendYmd(SUNDAY)).toBe(true);
    expect(isWeekendYmd(MONDAY)).toBe(false);
    expect(isWeekendYmd(FRIDAY)).toBe(false);
  });
});

describe('addDaysYmd', () => {
  it('moves forward and backward, zero-padding the result', () => {
    expect(addDaysYmd('2026-06-08', 1)).toBe('2026-06-09');
    expect(addDaysYmd('2026-06-08', -1)).toBe('2026-06-07');
  });

  it('rolls over month and year boundaries', () => {
    expect(addDaysYmd('2026-06-30', 1)).toBe('2026-07-01');
    expect(addDaysYmd('2026-12-31', 1)).toBe('2027-01-01');
    expect(addDaysYmd('2026-01-01', -1)).toBe('2025-12-31');
  });

  it('handles a leap day', () => {
    expect(addDaysYmd('2028-02-28', 1)).toBe('2028-02-29');
    expect(addDaysYmd('2028-02-29', 1)).toBe('2028-03-01');
  });
});

describe('hasWeekdayInRange', () => {
  it('is false for a weekend-only range', () => {
    // A holiday spanning only Sat-Sun adds nothing: weekends are already
    // non-working, so the form blocks it.
    expect(hasWeekdayInRange(SATURDAY, SUNDAY)).toBe(false);
  });

  it('is true when the range contains a single weekday', () => {
    expect(hasWeekdayInRange(SATURDAY, MONDAY)).toBe(true);
    expect(hasWeekdayInRange(MONDAY, MONDAY)).toBe(true);
  });

  it('is false for a single weekend day', () => {
    expect(hasWeekdayInRange(SUNDAY, SUNDAY)).toBe(false);
  });

  it('is false when the range is inverted', () => {
    expect(hasWeekdayInRange(MONDAY, FRIDAY)).toBe(false);
  });

  it('spans month boundaries without looping forever', () => {
    expect(hasWeekdayInRange('2026-06-29', '2026-07-03')).toBe(true);
  });
});

describe('yearOf', () => {
  it('reads the calendar year off the string', () => {
    expect(yearOf('2026-06-08')).toBe(2026);
    expect(yearOf('1999-12-31')).toBe(1999);
  });
});

describe('todayYmd / isPastYmd', () => {
  it('formats today as a zero-padded YYYY-MM-DD', () => {
    expect(todayYmd()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('treats today as not past, and neighbours accordingly', () => {
    const today = todayYmd();

    expect(isPastYmd(today)).toBe(false);
    expect(isPastYmd(addDaysYmd(today, -1))).toBe(true);
    expect(isPastYmd(addDaysYmd(today, 1))).toBe(false);
  });
});
