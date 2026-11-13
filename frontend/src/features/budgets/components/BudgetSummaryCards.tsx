import { StatCard } from '@/components/ui/StatCard';
import type { BudgetSummary } from '../types';
import { formatMoney, toCents } from '../utils/money';

interface BudgetSummaryCardsProps {
  summary: BudgetSummary;
}

/**
 * Task 2.7 — the five headline numbers. Every value is summed in the database
 * (NUMERIC), so the cards are exact to the cent; nothing is added up here.
 */
export function BudgetSummaryCards({ summary }: BudgetSummaryCardsProps) {
  const contingencyNow = toCents(summary.contingency_now);
  const contingencyStart = summary.contingency_at_baseline != null ? toCents(summary.contingency_at_baseline) : null;
  const contingencyPct =
    contingencyStart && contingencyStart > 0 ? Math.round((contingencyNow / contingencyStart) * 100) : null;
  const contingencyLow = contingencyNow < 0 || (contingencyPct != null && contingencyPct < 50);

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
      <StatCard
        label="Total Budget"
        value={formatMoney(summary.total_budget)}
        accent="primary"
        meta={
          summary.budget_status === 'baselined'
            ? `Approved ${formatMoney(summary.approved_budget_total)}`
            : summary.project_budget != null
              ? `Project budget ${formatMoney(summary.project_budget)} · draft`
              : 'Sum of the lines · draft'
        }
      />
      <StatCard
        label="Committed"
        value={formatMoney(summary.committed)}
        accent="info"
        meta="Awarded bids, approved variances and categorised invoices"
      />
      <StatCard
        label="Spent"
        value={formatMoney(summary.spent)}
        accent="info"
        meta={
          toCents(summary.pending_approval) > 0
            ? `${formatMoney(summary.pending_approval)} awaiting approval`
            : 'Payments approved or sent to finance'
        }
      />
      <StatCard
        label="Remaining"
        value={formatMoney(summary.remaining)}
        accent="success"
        meta="Total − contingency − committed"
      />
      <StatCard
        label="Contingency"
        value={formatMoney(summary.contingency_now)}
        accent={contingencyLow ? 'warning' : 'success'}
        meta={
          contingencyStart != null
            ? `${contingencyPct ?? 0}% of ${formatMoney(contingencyStart / 100)} at baseline`
            : `${summary.contingency_percent ?? 15}% of the contingency base`
        }
      />
    </div>
  );
}
