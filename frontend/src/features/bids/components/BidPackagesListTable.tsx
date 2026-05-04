import { useNavigate } from 'react-router-dom';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { ROUTES } from '@/constants/routes';
import { useCountdown } from '@/features/bids/hooks/useCountdown';
import type { BidPackagesListRow } from '@/features/bids/api/bid-packages-list.queries';
import { cn } from '@/utils/cn';

interface BidPackagesListTableProps {
  items: BidPackagesListRow[];
}

const dateFormatter = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
});

function formatDate(value: string): string {
  return dateFormatter.format(new Date(value));
}

function bidPackageHref(row: BidPackagesListRow): string {
  return ROUTES.BID_PACKAGE_DETAIL
    .replace(':id', row.project_id)
    .replace(':taskId', row.task_id)
    .replace(':bidPackageId', row.id);
}

function projectHref(row: BidPackagesListRow): string {
  return ROUTES.PROJECT_DETAIL.replace(':id', row.project_id);
}

function taskHref(row: BidPackagesListRow): string {
  return ROUTES.TASK_DETAIL
    .replace(':id', row.project_id)
    .replace(':taskId', row.task_id);
}

function DeadlineCell({ deadline }: { deadline: string }) {
  const { remaining, isPassed, passedLabel } = useCountdown(deadline);
  const label = isPassed ? (passedLabel ?? 'Deadline passed') : remaining;
  return (
    <span
      className={cn(
        'text-xs',
        isPassed ? 'font-medium text-danger-600' : 'text-secondary-700',
      )}
    >
      {label}
    </span>
  );
}

function ProgressCell({
  submitted,
  total,
}: {
  submitted: number;
  total: number;
}) {
  if (total === 0) {
    return <span className="text-secondary-400">&mdash;</span>;
  }
  const pct = Math.min(100, Math.round((submitted / total) * 100));
  return (
    <div className="space-y-1">
      <span className="text-xs text-secondary-700">
        {submitted} / {total}
      </span>
      <div
        className="h-1 w-24 overflow-hidden rounded-full bg-secondary-200"
        aria-hidden="true"
      >
        <div className="h-full bg-info-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function RoundBadge({ round }: { round: number }) {
  return (
    <span className="inline-flex items-center rounded-full bg-secondary-100 px-2 py-0.5 text-xs font-medium text-secondary-700">
      R{round}
    </span>
  );
}

function Row({ row }: { row: BidPackagesListRow }) {
  const navigate = useNavigate();
  const goDetail = () => navigate(bidPackageHref(row));

  const goProject = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    navigate(projectHref(row));
  };
  const goTask = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    navigate(taskHref(row));
  };

  return (
    <tr
      onClick={goDetail}
      className="cursor-pointer transition-colors hover:bg-secondary-50"
    >
      <td className="px-6 py-4 text-sm">
        <button
          type="button"
          onClick={goProject}
          className="text-left font-medium text-secondary-900 hover:text-primary-600 hover:underline"
        >
          {row.project_name}
        </button>
      </td>
      <td className="px-6 py-4 text-sm">
        <button
          type="button"
          onClick={goTask}
          className="text-left text-secondary-900 hover:text-primary-600 hover:underline"
        >
          {row.task_name}
        </button>
      </td>
      <td className="px-6 py-4 text-sm">
        <RoundBadge round={row.round_number} />
      </td>
      <td className="px-6 py-4 text-sm">
        <DeadlineCell deadline={row.deadline} />
      </td>
      <td className="px-6 py-4 text-sm">
        <StatusBadge status={row.status} size="sm" />
      </td>
      <td className="px-6 py-4 text-sm">
        <ProgressCell
          submitted={row.submitted_count}
          total={row.total_invitations}
        />
      </td>
      <td className="px-6 py-4 text-sm text-secondary-700">
        {formatDate(row.created_at)}
      </td>
    </tr>
  );
}

function MobileCard({ row }: { row: BidPackagesListRow }) {
  const navigate = useNavigate();
  const goDetail = () => navigate(bidPackageHref(row));

  return (
    <button
      type="button"
      onClick={goDetail}
      className="w-full rounded-lg border border-secondary-200 bg-white p-4 text-left shadow-sm transition-colors hover:bg-secondary-50 active:bg-secondary-100"
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-semibold text-secondary-900">
          {row.project_name} <span className="text-secondary-400">·</span>{' '}
          {row.task_name}
        </p>
        <RoundBadge round={row.round_number} />
      </div>
      <dl className="mt-3 space-y-1.5 text-sm">
        <div className="flex items-baseline justify-between gap-2">
          <dt className="text-secondary-500">Deadline</dt>
          <dd>
            <DeadlineCell deadline={row.deadline} />
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <dt className="text-secondary-500">Status</dt>
          <dd>
            <StatusBadge status={row.status} size="sm" />
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <dt className="text-secondary-500">Submitted</dt>
          <dd>
            <ProgressCell
              submitted={row.submitted_count}
              total={row.total_invitations}
            />
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <dt className="text-secondary-500">Created</dt>
          <dd className="text-secondary-700">{formatDate(row.created_at)}</dd>
        </div>
      </dl>
    </button>
  );
}

const HEADERS = ['Project', 'Task', 'Round', 'Deadline', 'Status', 'Progress', 'Created'];

export function BidPackagesListTable({ items }: BidPackagesListTableProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-secondary-200">
      {/* Mobile card view */}
      <div className="space-y-3 p-4 md:hidden">
        {items.map((row) => (
          <MobileCard key={row.id} row={row} />
        ))}
      </div>

      {/* Desktop table view */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full">
          <thead>
            <tr className="border-b border-secondary-200 bg-secondary-50">
              {HEADERS.map((h) => (
                <th
                  key={h}
                  className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-secondary-500"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-secondary-100 bg-white">
            {items.map((row) => (
              <Row key={row.id} row={row} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
