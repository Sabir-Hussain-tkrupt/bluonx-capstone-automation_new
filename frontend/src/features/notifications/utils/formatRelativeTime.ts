/**
 * Compact relative-time formatter ("2 hours ago", "just now", "3 days ago").
 *
 * No date-fns dependency — we use the built-in Intl.RelativeTimeFormat,
 * which ships with every modern browser.
 */
const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

const UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ['year', 60 * 60 * 24 * 365],
  ['month', 60 * 60 * 24 * 30],
  ['week', 60 * 60 * 24 * 7],
  ['day', 60 * 60 * 24],
  ['hour', 60 * 60],
  ['minute', 60],
  ['second', 1],
];

export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const target = new Date(iso);
  const diffSeconds = Math.round((target.getTime() - now.getTime()) / 1000);
  const abs = Math.abs(diffSeconds);

  if (abs < 30) return 'just now';

  for (const [unit, secondsPerUnit] of UNITS) {
    if (abs >= secondsPerUnit) {
      const value = Math.round(diffSeconds / secondsPerUnit);
      return rtf.format(value, unit);
    }
  }
  return 'just now';
}
