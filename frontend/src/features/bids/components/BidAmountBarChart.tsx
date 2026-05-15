import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { formatCurrency } from '@/lib/format';
import type { SubmittedBid } from '@/features/bids/types';

interface BidAmountBarChartProps {
  submittedBids: SubmittedBid[];
}

const MAX_LABEL_CHARS = 14;

function truncateLabel(value: string): string {
  if (value.length <= MAX_LABEL_CHARS) return value;
  return `${value.slice(0, MAX_LABEL_CHARS - 1)}…`;
}

export function BidAmountBarChart({ submittedBids }: BidAmountBarChartProps) {
  if (submittedBids.length === 0) return null;

  const data = submittedBids.map((bid) => ({
    name: bid.vendor_company_name,
    amount: bid.total_amount ?? 0,
  }));

  const chartHeight = Math.max(180, data.length * 44 + 40);

  return (
    <div className="rounded-lg border border-secondary-200 bg-white p-6 shadow-sm">
      <h3 className="mb-4 text-sm font-semibold text-secondary-900">Submitted Bid Amounts</h3>
      <div style={{ height: chartHeight }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 8, right: 24, left: 16, bottom: 8 }}
          >
            <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e2e8f0" />
            <XAxis
              type="number"
              tickFormatter={(v) => formatCurrency(v as number)}
              tick={{ fontSize: 11, fill: '#64748b' }}
            />
            <YAxis
              type="category"
              dataKey="name"
              width={140}
              tick={{ fontSize: 12, fill: '#334155' }}
              tickFormatter={(value: string) => truncateLabel(value)}
            />
            <Tooltip
              formatter={(value: number) => [formatCurrency(value), 'Total']}
            />
            <Bar dataKey="amount" fill="#0ea5e9" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
