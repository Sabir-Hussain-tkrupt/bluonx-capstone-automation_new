import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import type { InvitationSummary } from '@/features/bids/types';

interface SubmissionStatusPieProps {
  summary: InvitationSummary;
}

// The pie shows outcomes of delivered invitations only. Undelivered states
// (pending_send / send_failed) are excluded; send_failed is surfaced separately
// as a summary card + per-row badge. 'no_response' IS a delivered-then-timed-out
// outcome, so it is shown. 'expired' is retained only for legacy rows (no code
// path writes it anymore) and shares the neutral slice color.
type PieStatus = 'sent' | 'opened' | 'submitted' | 'declined' | 'no_response' | 'expired';

const STATUS_LABELS: Record<PieStatus, string> = {
  sent: 'Sent',
  opened: 'Opened',
  submitted: 'Submitted',
  declined: 'Declined',
  no_response: 'No Response',
  expired: 'Expired',
};

// Hex values pulled from the existing Tailwind palette tokens defined in
// frontend/src/index.css — no new colors are introduced.
const STATUS_COLORS: Record<PieStatus, string> = {
  sent: '#0ea5e9', // info-500
  opened: '#f59e0b', // warning-500
  submitted: '#22c55e', // success-500
  declined: '#ef4444', // danger-500
  no_response: '#64748b', // secondary-500
  expired: '#94a3b8', // secondary-400
};

const PIE_STATUSES: PieStatus[] = [
  'sent',
  'opened',
  'submitted',
  'declined',
  'no_response',
  'expired',
];

export function SubmissionStatusPie({ summary }: SubmissionStatusPieProps) {
  if (summary.total === 0) return null;

  const reachableTotal = PIE_STATUSES.reduce((acc, s) => acc + summary[s], 0);

  const data = PIE_STATUSES
    .filter((status) => summary[status] > 0)
    .map((status) => ({
      status,
      name: STATUS_LABELS[status],
      value: summary[status],
      fill: STATUS_COLORS[status],
    }));

  if (data.length === 0) return null;

  return (
    <div className="rounded-lg border border-secondary-200 bg-white p-6 shadow-sm">
      <h3 className="mb-4 text-sm font-semibold text-secondary-900">Invitation Status</h3>
      <div className="mx-auto h-56 max-w-md">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius={40}
              outerRadius={80}
              paddingAngle={1}
            >
              {data.map((entry) => (
                <Cell key={entry.status} fill={entry.fill} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value: number, name: string) => {
                const pct = reachableTotal > 0 ? Math.round((value / reachableTotal) * 100) : 0;
                return [`${value} (${pct}%)`, name];
              }}
            />
            <Legend
              verticalAlign="bottom"
              iconType="circle"
              wrapperStyle={{ fontSize: '12px' }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
