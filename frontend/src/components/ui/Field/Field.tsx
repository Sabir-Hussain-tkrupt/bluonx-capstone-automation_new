import type { ReactNode } from 'react';
import { cn } from '@/utils/cn';

export interface FieldProps {
  label: ReactNode;
  value: ReactNode;
  className?: string;
}

/**
 * A label/value pair rendered as a `<dt>`/`<dd>` row. Designed to sit inside a
 * `<dl>`. Extracted from the `InfoRow` that was duplicated across the detail pages.
 */
export function Field({ label, value, className }: FieldProps) {
  return (
    <div className={cn('flex justify-between gap-4 py-2 text-sm', className)}>
      <dt className="shrink-0 text-secondary-600">{label}</dt>
      <dd className="text-right text-secondary-900">{value || '—'}</dd>
    </div>
  );
}
