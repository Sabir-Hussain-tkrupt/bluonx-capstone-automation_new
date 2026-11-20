import { cn } from '@/utils/cn';

/** Same look as the other multi-line inputs in the app (AwardDialog). */
export const textareaClass = cn(
  'w-full rounded-lg border border-secondary-300 bg-white px-3 py-2 text-sm transition-colors',
  'focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none',
);

const DATE_TIME = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
});

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : DATE_TIME.format(d);
}

/** "12.5%" from a percent string; "—" for null. */
export function formatPercent(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—';
  const n = Number(value);
  return Number.isFinite(n) ? `${Number(n.toFixed(2))}%` : '—';
}

/** Accepts "12", "12.5", "12.75" between 0 and 100; null when invalid. */
export function parsePercentInput(raw: string): string | null {
  const v = raw.trim().replace(/%$/, '');
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(v) || Number(v) > 100) return null;
  return v;
}
