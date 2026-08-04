import { Card } from '@/components/ui/Card';

export interface StatCardProps {
  /** Small uppercase label rendered above the value. */
  label: string;
  /** Primary statistic. ReactNode so callers can pass numbers, strings, or skeleton elements. */
  value: React.ReactNode;
  /** Accent color for the left border. Maps to one of the project's semantic tokens. */
  accent?: 'primary' | 'success' | 'warning' | 'info';
  /** Optional small hint line rendered under the value (e.g. delta vs last week). */
  meta?: React.ReactNode;
}

const accentClass: Record<NonNullable<StatCardProps['accent']>, string> = {
  primary: 'border-l-4 border-l-primary-500',
  success: 'border-l-4 border-l-success-500',
  warning: 'border-l-4 border-l-warning-500',
  info: 'border-l-4 border-l-info-500',
};

export function StatCard({ label, value, accent = 'primary', meta }: StatCardProps) {
  return (
    <Card padding="md" className={accentClass[accent]}>
      <p className="text-xs uppercase tracking-wider text-secondary-500">{label}</p>
      <p className="mt-3 text-3xl font-semibold text-secondary-900 tabular-nums">{value}</p>
      {meta && <p className="mt-2 text-xs text-secondary-500">{meta}</p>}
    </Card>
  );
}
