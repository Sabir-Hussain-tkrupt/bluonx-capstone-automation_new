/**
 * Money helpers for the budget screens — exact to the cent.
 *
 * Totals that matter come pre-summed from the database views (NUMERIC). When
 * the UI must add amounts itself (section subtotals), it does so in integer
 * cents: 0.1 + 0.2 in floating point is 0.30000000000000004, but 10 + 20 cents
 * is exactly 30. Values arrive as numbers (Supabase) or strings (FastAPI).
 */

export function toCents(value: number | string | null | undefined): number {
  if (value == null || value === '') return 0;
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? Math.round(n * 100) : 0;
}

export function sumCents(values: (number | string | null | undefined)[]): number {
  return values.reduce<number>((acc, v) => acc + toCents(v), 0);
}

const MONEY = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** "$1,234.56" from a dollar amount; "—" for null. */
export function formatMoney(value: number | string | null | undefined): string {
  if (value == null || value === '') return '—';
  return MONEY.format(toCents(value) / 100);
}

/** "$1,234.56" from integer cents. */
export function formatCents(cents: number): string {
  return MONEY.format(cents / 100);
}

/** Signed difference, e.g. "+$2,000.00" / "−$500.00" / "$0.00". */
export function formatDelta(value: number | string | null | undefined): string {
  if (value == null || value === '') return '—';
  const cents = toCents(value);
  if (cents === 0) return MONEY.format(0);
  return `${cents > 0 ? '+' : '−'}${MONEY.format(Math.abs(cents) / 100)}`;
}

/** Normalise a user-typed amount ("$1,234.5") to "1234.50", or null if invalid. */
export function parseMoneyInput(raw: string): string | null {
  const cleaned = raw.trim().replace(/[$,\s]/g, '');
  if (cleaned === '') return null;
  if (!/^\d+(\.\d{0,2})?$/.test(cleaned)) return null;
  return Number(cleaned).toFixed(2);
}
