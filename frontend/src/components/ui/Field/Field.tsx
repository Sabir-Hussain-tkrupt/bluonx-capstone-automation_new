import type { ReactNode } from 'react';
import { cn } from '@/utils/cn';

export interface FieldProps {
  label: ReactNode;
  value: ReactNode;
  className?: string;
}

/**
 * A label/value pair rendered as a `<dt>`/`<dd>` row. Designed to sit inside a
 * `<dl>`. The one label/value primitive: every detail page renders through it,
 * including the ones that used to keep their own `InfoRow` copy.
 *
 * The label column is bounded rather than flexed apart. `justify-between` hands
 * every spare pixel to the gap, and these rows sit in cards with no width cap
 * above them, so on a wide screen the value drifted hundreds of pixels from its
 * label. A fixed column keeps the pair together at any container width.
 */
export function Field({ label, value, className }: FieldProps) {
  return (
    <div
      className={cn(
        'grid grid-cols-1 gap-x-4 py-2 text-sm sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)]',
        className,
      )}
    >
      <dt className="text-secondary-500">{label}</dt>
      {/* min-w-0 is load-bearing: minmax(0,1fr) lets the track shrink, but the
          grid item still defaults to min-width:auto and a long unbroken value
          (an address, a URL) would push straight past the column. */}
      <dd className="min-w-0 text-secondary-900">{value || '—'}</dd>
    </div>
  );
}
