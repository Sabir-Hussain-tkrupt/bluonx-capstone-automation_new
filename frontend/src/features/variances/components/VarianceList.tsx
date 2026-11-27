import { useMemo, useState } from 'react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Select } from '@/components/ui/Select';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { errorMessage } from '@/lib/api';
import { formatDateTime } from '@/features/contingency/components/shared';
import { formatMoney } from '@/features/budgets/utils/money';
import { PAYMENT_STATUS, VARIANCE_STATUS_LABELS, VARIANCE_STATUS_VARIANT } from '../constants';
import { useVariances } from '../hooks/useVariances';
import type { Variance } from '../types';
import { VarianceDetailModal } from './VarianceDetailModal';

interface VarianceListProps {
  /** One project (Budget tab), or every project (Variances page). */
  projectId?: string;
  readOnly?: boolean;
}

/** Filter choices that occur in the rows, sorted by label. */
function optionsFrom(rows: Variance[], all: string, id: (v: Variance) => string | null, label: (v: Variance) => string | null) {
  const map = new Map<string, string>();
  for (const v of rows) {
    const key = id(v);
    if (key) map.set(key, label(v) ?? '—');
  }
  return [
    { value: '', label: all },
    ...[...map].map(([value, text]) => ({ value, label: text })).sort((a, b) => a.label.localeCompare(b.label)),
  ];
}

const TH = 'px-4 py-3 font-medium text-secondary-500';

/** Task 4.4 — variances with filters by project, line, trade and status. */
export function VarianceList({ projectId, readOnly = false }: VarianceListProps) {
  const query = useVariances(projectId);
  const [project, setProject] = useState('');
  const [line, setLine] = useState('');
  const [trade, setTrade] = useState('');
  const [status, setStatus] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);

  const rows = useMemo(() => query.data ?? [], [query.data]);
  const inProject = useMemo(() => rows.filter((v) => !project || v.project_id === project), [rows, project]);
  const shown = inProject.filter(
    (v) =>
      (!line || v.parent_budget_line_id === line) &&
      (!trade || v.trade_id === trade) &&
      (!status || v.status === status),
  );

  if (query.isLoading) return <Skeleton height="320px" />;
  if (query.isError) {
    return (
      <Alert variant="danger" title="Could not load the variances">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span>{errorMessage(query.error, 'Something went wrong. Please try again.')}</span>
          <Button variant="outline" size="sm" onClick={() => query.refetch()}>Retry</Button>
        </div>
      </Alert>
    );
  }

  const lineOptions = optionsFrom(
    inProject,
    'All lines',
    (v) => v.parent_budget_line_id,
    (v) => (projectId || project ? v.parent_line_name : `${v.parent_line_name} (${v.project_name})`),
  );

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {!projectId && (
          <Select
            aria-label="Filter by project"
            options={optionsFrom(rows, 'All projects', (v) => v.project_id, (v) => v.project_name)}
            value={project}
            onChange={(e) => {
              setProject(e.target.value);
              setLine('');
              setTrade('');
            }}
          />
        )}
        <Select aria-label="Filter by line" options={lineOptions} value={line} onChange={(e) => setLine(e.target.value)} />
        <Select
          aria-label="Filter by trade"
          options={optionsFrom(inProject, 'All trades', (v) => v.trade_id, (v) => v.trade_name)}
          value={trade}
          onChange={(e) => setTrade(e.target.value)}
        />
        <Select
          aria-label="Filter by status"
          options={[
            { value: '', label: 'All statuses' },
            ...Object.entries(VARIANCE_STATUS_LABELS).map(([value, label]) => ({ value, label })),
          ]}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        />
      </div>

      {shown.length === 0 ? (
        <EmptyState
          title={rows.length === 0 ? 'No variances yet' : 'No variances match the filters'}
          description={
            rows.length === 0
              ? 'On a baselined budget, use “Add variance” in a budget line’s actions menu.'
              : 'Change or clear the filters.'
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-secondary-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-secondary-200 bg-secondary-50">
                <th className={TH}>Variance</th>
                {!projectId && <th className={`${TH} hidden md:table-cell`}>Project</th>}
                <th className={`${TH} hidden md:table-cell`}>Line</th>
                <th className={`${TH} hidden lg:table-cell`}>Trade</th>
                <th className={`${TH} text-right`}>Amount</th>
                <th className={TH}>Status</th>
                <th className={`${TH} hidden lg:table-cell`}>Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-secondary-100">
              {shown.map((v) => {
                const payment = PAYMENT_STATUS[v.payment_status];
                return (
                  <tr key={v.id} className="align-top hover:bg-secondary-50">
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => setOpenId(v.id)}
                        className="max-w-xs text-left font-medium text-secondary-900 hover:text-primary-600 hover:underline"
                      >
                        {v.description}
                      </button>
                      {v.vendor_name && <div className="text-xs text-secondary-500">{v.vendor_name}</div>}
                    </td>
                    {!projectId && <td className="hidden px-4 py-3 text-secondary-700 md:table-cell">{v.project_name}</td>}
                    <td className="hidden px-4 py-3 text-secondary-700 md:table-cell">{v.parent_line_name}</td>
                    <td className="hidden px-4 py-3 text-secondary-700 lg:table-cell">{v.trade_name ?? '—'}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-secondary-900">
                      {formatMoney(v.amount)}
                      {Number(v.amount) !== Number(v.estimated_amount) && (
                        <div className="text-xs text-secondary-500">est. {formatMoney(v.estimated_amount)}</div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={v.status} variant={VARIANCE_STATUS_VARIANT[v.status]} size="sm" />
                      {v.status !== 'cancelled' && payment && (
                        <div className="mt-1 text-xs text-secondary-500">{payment.label}</div>
                      )}
                      {!readOnly && v.permissions.can_approve && (
                        <Button size="sm" variant="outline" className="mt-1" onClick={() => setOpenId(v.id)}>
                          Review
                        </Button>
                      )}
                    </td>
                    <td className="hidden whitespace-nowrap px-4 py-3 text-secondary-700 lg:table-cell">
                      {v.created_by_name ?? '—'}
                      <div className="text-xs text-secondary-500">{formatDateTime(v.created_at)}</div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {openId && (
        <VarianceDetailModal key={openId} varianceId={openId} readOnly={readOnly} onClose={() => setOpenId(null)} />
      )}
    </div>
  );
}
