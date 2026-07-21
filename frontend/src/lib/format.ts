/**
 * Coerce a numeric field to a real number or null. Postgres `numeric` reaches
 * the client as a number over PostgREST (Supabase reads) but as a JSON *string*
 * over FastAPI (Pydantic serializes Decimal as a string). Normalizing at the
 * fetch boundary keeps money/coordinate fields honestly typed `number | null`
 * on both paths, so arithmetic never silently concatenates strings.
 */
export function toNumberOrNull(value: unknown): number | null {
  if (value == null || value === '') return null;
  const n = Number(value);
  return Number.isNaN(n) ? null : n;
}

export function formatCurrency(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return Number(value).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

/**
 * Format an ISO date string ("YYYY-MM-DD") as "Mon D, YYYY".
 *
 * Built from Y/M/D parts on purpose: `new Date("YYYY-MM-DD")` parses as
 * UTC midnight, which renders as the previous day in negative-offset
 * zones. The parts constructor pins it to local midnight so the
 * displayed date matches the raw value.
 */
export function formatDateOnly(value: string | null | undefined): string {
  if (!value) return '—';
  const [y, m, d] = value.split('-').map(Number);
  if (!y || !m || !d) return value;
  return new Date(y, m - 1, d).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}
