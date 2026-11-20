import { useState } from 'react';
import { CheckCircle2, ListOrdered, Percent, PlusCircle, RotateCcw } from 'lucide-react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatCard } from '@/components/ui/StatCard';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { useAuth } from '@/contexts/AuthContext';
import { errorMessage } from '@/lib/api';
import { formatMoney, toCents } from '@/features/budgets/utils/money';
import { useCancelTopUp, useContingency, useReopenBidding } from '../hooks/useContingency';
import type { ContingencyOverview, TopUpRequest } from '../types';
import { BiddingCompleteModal } from './BiddingCompleteModal';
import { ContingencyPercentModal } from './ContingencyPercentModal';
import { TopUpDecisionModal } from './TopUpDecisionModal';
import { TopUpRequestModal } from './TopUpRequestModal';
import { formatDateTime, formatPercent } from './shared';

interface ContingencyPanelProps {
  projectId: string;
  readOnly?: boolean;
  onOpenLedger: () => void;
}

function leftAccent(o: ContingencyOverview): 'success' | 'warning' | 'info' {
  if (o.left_percent == null) return 'info';
  const left = Number(o.left_percent);
  if (left <= Number(o.escalation_percent) || toCents(o.contingency) < 0) return 'warning';
  if (left < Number(o.target_percent)) return 'warning';
  return 'success';
}

/**
 * Task 3.6 — contingency at a glance: starting amount, movements, remaining
 * and % per bucket, with quick links to the ledger, pending top-ups and the
 * bidding-complete checkpoint.
 */
export function ContingencyPanel({ projectId, readOnly = false, onOpenLedger }: ContingencyPanelProps) {
  const { toast } = useToast();
  const { profile } = useAuth();
  const query = useContingency(projectId);
  const cancelTopUp = useCancelTopUp(projectId);
  const reopen = useReopenBidding(projectId);

  const [showRequest, setShowRequest] = useState(false);
  const [showBidding, setShowBidding] = useState(false);
  const [showPercent, setShowPercent] = useState(false);
  const [showReopen, setShowReopen] = useState(false);
  const [deciding, setDeciding] = useState<TopUpRequest | null>(null);

  if (query.isLoading) return <Skeleton height="160px" />;
  if (query.isError || !query.data) {
    return (
      <Alert variant="danger" title="Could not load contingency">
        {errorMessage(query.error, 'Something went wrong. Please try again.')}
      </Alert>
    );
  }

  const o = query.data;
  const can = readOnly
    ? { set_percent: false, request_top_up: false, decide_top_up: false, complete_bidding: false, reopen_bidding: false, is_executive: false }
    : o.permissions;
  const baselined = o.budget_status === 'baselined';

  const handleCancel = (t: TopUpRequest) => {
    cancelTopUp.mutate(t.id, {
      onSuccess: () => toast({ variant: 'success', message: 'Top-up request withdrawn.' }),
      onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not withdraw the request.') }),
    });
  };

  const handleReopen = () => {
    reopen.mutate(undefined, {
      onSuccess: () => {
        setShowReopen(false);
        toast({ variant: 'success', message: 'Bidding reopened.' });
      },
      onError: (e) => {
        setShowReopen(false);
        toast({ variant: 'danger', message: errorMessage(e, 'Could not reopen bidding.') });
      },
    });
  };

  return (
    <Card
      title="Contingency"
      subtitle={`${formatPercent(o.effective_percent)} of the contingency base${o.contingency_percent == null ? ' (default)' : ''} · base = total − land − contingency`}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          {can.set_percent && (
            <Button size="sm" variant="outline" leftIcon={<Percent className="h-4 w-4" />} onClick={() => setShowPercent(true)}>
              Change %
            </Button>
          )}
          {baselined && (
            <Button size="sm" variant="outline" leftIcon={<ListOrdered className="h-4 w-4" />} onClick={onOpenLedger}>
              View ledger
            </Button>
          )}
          {can.request_top_up && (
            <Button size="sm" variant="outline" leftIcon={<PlusCircle className="h-4 w-4" />} onClick={() => setShowRequest(true)}>
              Request top-up
            </Button>
          )}
          {can.complete_bidding && (
            <Button size="sm" leftIcon={<CheckCircle2 className="h-4 w-4" />} onClick={() => setShowBidding(true)}>
              Mark bidding complete
            </Button>
          )}
        </div>
      }
      padding="md"
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Starting amount"
            value={formatMoney(o.starting_amount ?? o.contingency)}
            accent="primary"
            meta={
              baselined
                ? toCents(o.top_ups_approved_total) > 0
                  ? `At baseline · plus ${formatMoney(o.top_ups_approved_total)} in top-ups`
                  : 'At baseline'
                : 'Draft · recalculated as the base changes'
            }
          />
          <StatCard
            label="Movements"
            value={
              baselined
                ? (() => {
                    const net = (toCents(o.total_in) - toCents(o.total_out)) / 100;
                    return `${net < 0 ? '−' : net > 0 ? '+' : ''}${formatMoney(Math.abs(net))}`;
                  })()
                : '—'
            }
            accent="info"
            meta={
              baselined
                ? `${formatMoney(o.total_out)} out · ${formatMoney(o.total_in)} returned (savings, reversals) and top-ups`
                : 'The ledger starts at baseline'
            }
          />
          <StatCard
            label="Remaining"
            value={formatMoney(o.contingency)}
            accent={toCents(o.contingency) < 0 ? 'warning' : 'success'}
            meta={`Base ${formatMoney(o.base)}`}
          />
          <StatCard
            label="Left of the base"
            value={formatPercent(o.left_percent)}
            accent={leftAccent(o)}
            meta={`Target after bidding ${formatPercent(o.target_percent)} · escalates at ${formatPercent(o.escalation_percent)}`}
          />
        </div>

        {o.buckets.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-secondary-200">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-secondary-200 bg-secondary-50">
                  <th className="px-4 py-2 font-medium text-secondary-500">Bucket</th>
                  <th className="px-4 py-2 text-right font-medium text-secondary-500">Starting</th>
                  <th className="hidden px-4 py-2 text-right font-medium text-secondary-500 md:table-cell">Used</th>
                  <th className="hidden px-4 py-2 text-right font-medium text-secondary-500 md:table-cell">Returned</th>
                  <th className="px-4 py-2 text-right font-medium text-secondary-500">Remaining</th>
                  <th className="px-4 py-2 text-right font-medium text-secondary-500">%</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-secondary-100">
                {o.buckets.map((b) => (
                  <tr key={b.id}>
                    <td className="px-4 py-2">
                      <span className="font-medium text-secondary-900">{b.label}</span>
                      {b.kind === 'top_up' && b.decided_at && (
                        <span className="ml-2 text-xs text-secondary-500">{formatDateTime(b.decided_at)}</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{formatMoney(b.starting_amount)}</td>
                    <td className="hidden px-4 py-2 text-right tabular-nums md:table-cell">{formatMoney(b.drawn)}</td>
                    <td className="hidden px-4 py-2 text-right tabular-nums md:table-cell">{formatMoney(b.returned)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{formatMoney(b.remaining)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{formatPercent(b.remaining_percent)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {o.pending_top_ups.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold text-secondary-900">Pending top-up requests</h4>
            <ul className="divide-y divide-secondary-100 rounded-lg border border-secondary-200 text-sm">
              {o.pending_top_ups.map((t) => (
                <li key={t.id} className="flex flex-col gap-2 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <div className="font-medium tabular-nums text-secondary-900">{formatMoney(t.requested_amount)}</div>
                    <div className="truncate text-secondary-600">{t.reason}</div>
                    <div className="text-xs text-secondary-500">
                      {t.requested_by_name ?? '—'} · {formatDateTime(t.requested_at)}
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {can.decide_top_up && (
                      <Button size="sm" onClick={() => setDeciding(t)}>Review</Button>
                    )}
                    {!readOnly && (t.requested_by === profile?.id || profile?.role === 'admin') && (
                      <Button size="sm" variant="ghost" isLoading={cancelTopUp.isPending} onClick={() => handleCancel(t)}>
                        Withdraw
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            {!o.permissions.is_executive && (
              <p className="text-xs text-secondary-500">Only an executive can approve a contingency top-up.</p>
            )}
          </div>
        )}

        {o.bidding.completed_at ? (
          <Alert
            variant={o.bidding.outcome === 'escalated' ? 'danger' : o.bidding.outcome === 'below_target' ? 'warning' : 'success'}
            title={`Bidding complete · ${formatPercent(o.bidding.left_percent)} contingency left`}
          >
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span>
                Marked by {o.bidding.completed_by_name ?? '—'} on {formatDateTime(o.bidding.completed_at)}.{' '}
                {o.bidding.outcome === 'escalated' && 'Escalated to the executives and finance.'}
                {o.bidding.outcome === 'below_target' && `Below the ${formatPercent(o.target_percent)} target.`}
                {o.bidding.outcome === 'on_target' && 'On target. Nothing is released early.'}
                {o.bidding.note && <> Note: {o.bidding.note}</>}
              </span>
              {can.reopen_bidding && (
                <Button size="sm" variant="outline" leftIcon={<RotateCcw className="h-4 w-4" />} onClick={() => setShowReopen(true)}>
                  Reopen bidding
                </Button>
              )}
            </div>
          </Alert>
        ) : baselined ? (
          <div className="flex items-center gap-2 text-sm text-secondary-600">
            <StatusBadge status="bidding open" variant="info" />
            <span>When every bid is in, the project manager marks bidding complete to check contingency.</span>
          </div>
        ) : null}
      </div>

      <TopUpRequestModal projectId={projectId} isOpen={showRequest} onClose={() => setShowRequest(false)} />
      {deciding && (
        <TopUpDecisionModal key={deciding.id} projectId={projectId} request={deciding} onClose={() => setDeciding(null)} />
      )}
      {showBidding && (
        <BiddingCompleteModal projectId={projectId} isOpen onClose={() => setShowBidding(false)} />
      )}
      {showPercent && (
        <ContingencyPercentModal
          projectId={projectId}
          isOpen
          onClose={() => setShowPercent(false)}
          current={o.contingency_percent}
          defaultPercent={o.default_percent}
        />
      )}
      <ConfirmDialog
        isOpen={showReopen}
        title="Reopen bidding"
        message="Reopen bidding for this project? The checkpoint result is cleared and its alert resolved; the project manager can mark bidding complete again later."
        confirmText="Reopen bidding"
        confirmVariant="primary"
        isLoading={reopen.isPending}
        onConfirm={handleReopen}
        onCancel={() => setShowReopen(false)}
      />
    </Card>
  );
}
