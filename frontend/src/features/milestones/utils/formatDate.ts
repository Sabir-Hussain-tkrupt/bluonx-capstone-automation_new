/** Format a 'YYYY-MM-DD' date string as a local calendar date (no TZ shift). */
export function formatMilestoneDate(value: string | null): string {
  if (!value) return '—';
  const [y, m, d] = value.split('-').map(Number);
  if (!y || !m || !d) return value;
  return new Date(y, m - 1, d).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}
