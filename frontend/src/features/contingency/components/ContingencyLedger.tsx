import { useState } from 'react';
import { Upload } from 'lucide-react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { cn } from '@/utils/cn';
import { formatDelta, formatMoney } from '@/features/budgets/utils/money';
import { exportContingencyLedger } from '../api/contingency.api';
import { useContingencyLedger } from '../hooks/useContingency';
import { formatDateTime } from './shared';

interface ContingencyLedgerProps {
  projectId: string;
}

/**
 * Task 3.3 — every contingency movement: source line, amount, direction, who
 * and when, with the running balance overall and per bucket. Newest first.
 */
export function ContingencyLedger({ projectId }: ContingencyLedgerProps) {
  const { toast } = useToast();
  const query = useContingencyLedger(projectId);
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      await exportContingencyLedger(projectId);
    } catch (e) {
      toast({ variant: 'danger', message: errorMessage(e, 'Could not export the ledger.') });
    } finally {
      setExporting(false);
    }
  };

  if (query.isLoading) return <Skeleton height="320px" />;
  if (query.isError || !query.data) {
    return (
      <Alert variant="danger" title="Could not load the ledger">
        {errorMessage(query.error, 'Something went wrong. Please try again.')}
      </Alert>
    );
  }

  const entries = [...query.data.entries].reverse();

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-base font-semibold text-secondary-900">Contingency ledger</h3>
          <p className="text-sm text-secondary-500">
            {entries.length} movement{entries.length === 1 ? '' : 's'} · in {formatMoney(query.data.total_in)} · out{' '}
            {formatMoney(query.data.total_out)}. Entries can never be edited or deleted.
          </p>
        </div>
        <Button
          variant="outline"
          leftIcon={<Upload className="h-4 w-4" />}
          isLoading={exporting}
          onClick={handleExport}
          disabled={entries.length === 0}
        >
          Export CSV
        </Button>
      </div>

      {entries.length === 0 ? (
        <EmptyState title="No movements yet" description="The ledger starts when the budget is baselined." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-secondary-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-secondary-200 bg-secondary-50">
                <th className="px-4 py-3 font-medium text-secondary-500">#</th>
                <th className="px-4 py-3 font-medium text-secondary-500">When</th>
                <th className="px-4 py-3 font-medium text-secondary-500">Movement</th>
                <th className="hidden px-4 py-3 font-medium text-secondary-500 md:table-cell">Source line</th>
                <th className="px-4 py-3 text-right font-medium text-secondary-500">Amount</th>
                <th className="px-4 py-3 text-right font-medium text-secondary-500">Balance</th>
                <th className="hidden px-4 py-3 font-medium text-secondary-500 lg:table-cell">Bucket balance</th>
                <th className="hidden px-4 py-3 font-medium text-secondary-500 md:table-cell">By</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-secondary-100">
              {entries.map((e) => (
                <tr key={e.id} className="align-top hover:bg-secondary-50">
                  <td className="px-4 py-3 tabular-nums text-secondary-500">{e.entry_no}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-secondary-700">{formatDateTime(e.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-secondary-900">{e.movement_label}</div>
                    {e.reason && <div className="max-w-xs text-xs text-secondary-500">{e.reason}</div>}
                  </td>
                  <td className="hidden px-4 py-3 text-secondary-700 md:table-cell">{e.source_line_name ?? '—'}</td>
                  <td
                    className={cn(
                      'whitespace-nowrap px-4 py-3 text-right font-medium tabular-nums',
                      e.direction === 'in' && 'text-success-700',
                      e.direction === 'out' && 'text-danger-700',
                    )}
                  >
                    {formatDelta(e.amount)}
                    <div className="text-xs font-normal text-secondary-500">
                      {e.direction === 'in' ? 'into contingency' : e.direction === 'out' ? 'out of contingency' : ''}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-secondary-900">
                    {formatMoney(e.balance_after)}
                  </td>
                  <td className="hidden px-4 py-3 text-xs text-secondary-600 lg:table-cell">
                    {e.allocations.length === 0
                      ? '—'
                      : e.allocations.map((a) => (
                          <div key={a.bucket_id} className="whitespace-nowrap">
                            {a.bucket_label}: <span className="tabular-nums">{formatMoney(a.bucket_balance_after)}</span>
                          </div>
                        ))}
                  </td>
                  <td className="hidden px-4 py-3 text-secondary-700 md:table-cell">{e.actor_name ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
