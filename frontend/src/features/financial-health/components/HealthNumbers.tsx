import { StatCard } from '@/components/ui/StatCard';
import { formatMoney } from '@/features/budgets/utils/money';
import { formatPercent } from '@/features/contingency/components/shared';
import type { FinancialHealth } from '../types';

/** Both percentages, and what "spent" is made of. */
export function HealthNumbers({ health: h }: { health: FinancialHealth }) {
  const short =
    h.contingency_left_pct != null &&
    h.work_left_pct != null &&
    Number(h.contingency_left_pct) < Number(h.work_left_pct);
  const spentParts: [string, string][] = [
    ['Committed at award', h.spent_committed],
    ['Approved for payment', h.spent_approved],
    ['Sent to finance', h.spent_sent],
    ['Land closed', h.spent_land],
  ];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <StatCard
          label="Contingency left"
          value={formatPercent(h.contingency_left_pct)}
          accent={short ? 'warning' : 'success'}
          meta={`${formatMoney(h.contingency)} of ${formatMoney(h.contingency_base)} ${
            h.groundbreaking_at ? 'at groundbreaking' : 'at baseline (groundbreaking not recorded)'
          }`}
        />
        <StatCard
          label="Work left (dollars)"
          value={formatPercent(h.work_left_dollars_pct)}
          accent={h.work_left_basis === 'dollars' ? 'primary' : 'info'}
          meta={`${formatMoney(h.spent)} spent of ${formatMoney(h.total_budget)}`}
        />
        <StatCard
          label="Work left (physical)"
          value={formatPercent(h.work_left_physical_pct)}
          accent={h.work_left_basis === 'physical' ? 'primary' : 'info'}
          meta={
            h.milestones_total
              ? `${h.milestones_completed} of ${h.milestones_total} milestones complete`
              : 'No milestones yet, so only dollars are used'
          }
        />
      </div>
      <dl className="grid grid-cols-2 gap-3 rounded-lg border border-secondary-200 bg-secondary-50 px-3 py-2 text-sm md:grid-cols-4">
        {spentParts.map(([label, value]) => (
          <div key={label}>
            <dt className="text-secondary-500">{label}</dt>
            <dd className="tabular-nums text-secondary-900">{formatMoney(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
