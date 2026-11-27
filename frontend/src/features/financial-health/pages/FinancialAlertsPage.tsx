import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Select } from '@/components/ui/Select';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { errorMessage } from '@/lib/api';
import { formatDateTime } from '@/features/contingency/components/shared';
import { ALERT_STATUS, ALERT_TYPE_LABELS, SEVERITY_VARIANT, needsDecision } from '../constants';
import { useFinancialAlerts } from '../hooks/useFinancialHealth';

const TH = 'px-4 py-3 font-medium text-secondary-500';
const FILTERS = [
  { value: 'current', label: 'Current alerts' },
  { value: 'decide', label: 'Needs decision' },
  { value: 'on_hold', label: 'On hold' },
  { value: 'all', label: 'All alerts' },
];

/** Every project's contingency alerts (sidebar). */
export function FinancialAlertsPage() {
  const query = useFinancialAlerts();
  const [filter, setFilter] = useState('current');

  const rows = (query.data ?? []).filter((a) => {
    if (filter === 'decide') return needsDecision(a.status);
    if (filter === 'on_hold') return a.status === 'on_hold';
    if (filter === 'current') return a.status !== 'resolved' && a.status !== 'superseded';
    return true;
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-secondary-900">Financial Alerts</h1>
        <p className="mt-1 text-sm text-secondary-500">
          Contingency health, near-zero, negative and long-tail reserve alerts, with the manager's decision.
        </p>
      </div>

      <div className="max-w-xs">
        <Select aria-label="Filter alerts" options={FILTERS} value={filter} onChange={(e) => setFilter(e.target.value)} />
      </div>

      {query.isLoading ? (
        <Skeleton height="320px" />
      ) : query.isError ? (
        <Alert variant="danger" title="Could not load the alerts">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>{errorMessage(query.error, 'Something went wrong. Please try again.')}</span>
            <Button variant="outline" size="sm" onClick={() => query.refetch()}>Retry</Button>
          </div>
        </Alert>
      ) : rows.length === 0 ? (
        <EmptyState title="No alerts" description="Nothing matches this filter." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-secondary-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-secondary-200 bg-secondary-50">
                <th className={TH}>Project</th>
                <th className={TH}>Alert</th>
                <th className={TH}>Severity</th>
                <th className={TH}>Status</th>
                <th className={`${TH} hidden md:table-cell`}>Opened</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-secondary-100">
              {rows.map((a) => (
                <tr key={a.id} className="align-top hover:bg-secondary-50">
                  <td className="px-4 py-3">
                    <Link
                      to={`/financial-alerts/${a.id}`}
                      className="font-medium text-secondary-900 hover:text-primary-600 hover:underline"
                    >
                      {a.project_name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-secondary-700">
                    {ALERT_TYPE_LABELS[a.alert_type]}
                    <div className="max-w-md text-xs text-secondary-500">{a.message}</div>
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={a.severity} variant={SEVERITY_VARIANT[a.severity]} size="sm" /></td>
                  <td className="px-4 py-3">
                    <StatusBadge status={ALERT_STATUS[a.status].label} variant={ALERT_STATUS[a.status].variant} size="sm" />
                  </td>
                  <td className="hidden whitespace-nowrap px-4 py-3 text-secondary-700 md:table-cell">{formatDateTime(a.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
