import { useMemo } from 'react';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { formatCurrency } from '@/lib/format';
import type { BudgetLine } from '../types';
import { formatDelta, formatMoney, toCents } from '../utils/money';

interface BidVsBudgetViewProps {
  lines: BudgetLine[];
}

const MAX_LABEL_CHARS = 16;
const truncate = (v: string) => (v.length <= MAX_LABEL_CHARS ? v : `${v.slice(0, MAX_LABEL_CHARS - 1)}…`);

/**
 * Task 2.7 — line-item variance view: original estimate → awarded / committed →
 * field variances → difference, per activity. The chart reuses the styling of
 * the bid comparison chart (BidAmountBarChart).
 */
export function BidVsBudgetView({ lines }: BidVsBudgetViewProps) {
  const rows = useMemo(
    () =>
      lines
        .filter((l) => l.line_type === 'bid_activity' || l.line_type === 'internal_tm')
        .map((l) => {
          const estimate = l.original_estimate ?? l.budget_amount;
          const finalCents = toCents(l.budget_amount) + toCents(l.variance_total);
          const diffCents = finalCents - toCents(estimate);
          const pct = toCents(estimate) > 0 ? (diffCents / toCents(estimate)) * 100 : null;
          return { line: l, estimate, finalCents, diffCents, pct };
        }),
    [lines],
  );

  if (rows.length === 0) {
    return <EmptyState title="No activities yet" description="Bid and internal activities appear here once tasks are in the budget." />;
  }

  const chartData = rows.map((r) => ({
    name: r.line.name,
    Estimate: Number(r.estimate),
    Committed: Number(r.line.committed),
  }));
  const chartHeight = Math.max(200, chartData.length * 48 + 60);

  return (
    <div className="space-y-4">
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-secondary-200">
                <th className="px-4 py-3 font-medium text-secondary-500">Activity</th>
                <th className="px-4 py-3 text-right font-medium text-secondary-500">Original estimate</th>
                <th className="px-4 py-3 text-right font-medium text-secondary-500">Budget (bid)</th>
                <th className="hidden px-4 py-3 text-right font-medium text-secondary-500 md:table-cell">Variances</th>
                <th className="hidden px-4 py-3 text-right font-medium text-secondary-500 md:table-cell">Committed</th>
                <th className="hidden px-4 py-3 text-right font-medium text-secondary-500 lg:table-cell">Spent</th>
                <th className="px-4 py-3 text-right font-medium text-secondary-500">Difference</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-secondary-100">
              {rows.map(({ line, estimate, diffCents, pct }) => (
                <tr key={line.id} className="hover:bg-secondary-50">
                  <td className="px-4 py-3">
                    <span className="font-medium text-secondary-900">{line.name}</span>
                    {line.vendor_name && <span className="ml-2 text-xs text-secondary-500">{line.vendor_name}</span>}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{formatMoney(estimate)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{formatMoney(line.budget_amount)}</td>
                  <td className="hidden px-4 py-3 text-right tabular-nums md:table-cell">
                    {toCents(line.variance_total) ? formatMoney(line.variance_total) : '—'}
                  </td>
                  <td className="hidden px-4 py-3 text-right tabular-nums md:table-cell">{formatMoney(line.committed)}</td>
                  <td className="hidden px-4 py-3 text-right tabular-nums lg:table-cell">{formatMoney(line.spent)}</td>
                  <td
                    className={`px-4 py-3 text-right font-medium tabular-nums ${
                      diffCents > 0 ? 'text-danger-600' : diffCents < 0 ? 'text-success-700' : 'text-secondary-700'
                    }`}
                  >
                    {formatDelta(diffCents / 100)}
                    {pct != null && diffCents !== 0 && (
                      <span className="ml-1 text-xs font-normal">({pct > 0 ? '+' : ''}{pct.toFixed(0)}%)</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="rounded-lg border border-secondary-200 bg-white p-6 shadow-sm">
        <h3 className="mb-4 text-sm font-semibold text-secondary-900">Estimate vs committed</h3>
        <div style={{ height: chartHeight }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical" margin={{ top: 8, right: 24, left: 16, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e2e8f0" />
              <XAxis type="number" tickFormatter={(v) => formatCurrency(v as number)} tick={{ fontSize: 11, fill: '#64748b' }} />
              <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 12, fill: '#334155' }}
                tickFormatter={(v: string) => truncate(v)} />
              <Tooltip formatter={(value: number, name: string) => [formatMoney(value), name]} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Estimate" fill="#94a3b8" radius={[0, 4, 4, 0]} />
              <Bar dataKey="Committed" fill="#0ea5e9" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
