import { Skeleton } from '@/components/ui/Skeleton';
import { Button } from '@/components/ui/Button';
import { useVendorVersionHistory } from '@/features/bids/hooks/useVendorVersionHistory';
import { formatCurrency } from '@/lib/format';
import { cn } from '@/utils/cn';
import type { BidRevisionRequest, BidSubmissionDetail } from '@/features/bids/types';

interface VendorVersionHistoryProps {
  /** Current (non-superseded) submission id for the vendor row. */
  currentSubmissionId: string;
  /** Most-recent non-cancelled revision request for this invitation, if any. */
  revisionRequest?: BidRevisionRequest;
  onViewBid: (submissionId: string) => void;
}

function formatDateTime(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleString('en-US', {
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function StateLabels({ submission }: { submission: BidSubmissionDetail }) {
  const versionType = submission.revision_number > 1 ? 'Revised' : 'Original';
  const isCurrent = !submission.is_superseded;
  return (
    <div className="flex flex-col gap-1">
      <span
        className={cn(
          'inline-flex w-fit rounded-full px-2 py-0.5 text-xs font-medium',
          versionType === 'Revised'
            ? 'bg-success-100 text-success-700'
            : 'bg-secondary-100 text-secondary-700',
        )}
      >
        {versionType}
      </span>
      <span
        className={cn(
          'inline-flex w-fit rounded-full px-2 py-0.5 text-xs font-medium',
          isCurrent
            ? 'bg-info-100 text-info-700'
            : 'bg-secondary-100 text-secondary-500',
        )}
      >
        {isCurrent ? 'Current' : 'Superseded'}
      </span>
    </div>
  );
}

function deltaLabel(
  current: number | null,
  previous: number | null,
): { text: string; tone: string } | null {
  if (current == null || previous == null) return null;
  const delta = current - previous;
  if (delta === 0) return { text: '$0', tone: 'text-secondary-500' };
  const sign = delta > 0 ? '+' : '-';
  return {
    text: `${sign}${formatCurrency(Math.abs(delta))}`,
    tone: delta > 0 ? 'text-danger-600' : 'text-success-600',
  };
}

export function VendorVersionHistory({
  currentSubmissionId,
  revisionRequest,
  onViewBid,
}: VendorVersionHistoryProps) {
  const { data: versions, isLoading, error } = useVendorVersionHistory(
    currentSubmissionId,
    true,
  );

  return (
    <div className="border-t border-secondary-200 bg-secondary-50 px-6 py-4">
      <h4 className="mb-3 text-xs font-semibold uppercase tracking-wide text-secondary-500">
        Version History
      </h4>

      {isLoading ? (
        <div className="space-y-2" data-testid="version-history-skeleton">
          <Skeleton height="32px" />
          <Skeleton height="32px" />
        </div>
      ) : error || !versions || versions.length === 0 ? (
        <p className="text-sm text-danger-600">
          Failed to load version history.
        </p>
      ) : (
        <div className="overflow-hidden rounded-md border border-secondary-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-secondary-50 text-xs uppercase tracking-wider text-secondary-500">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Version</th>
                <th className="px-4 py-2 text-left font-medium">Submitted At</th>
                <th className="px-4 py-2 text-right font-medium">
                  Total Amount
                </th>
                <th className="px-4 py-2 text-left font-medium">State</th>
                <th className="px-4 py-2 text-right font-medium">Delta</th>
                <th className="px-4 py-2 text-right font-medium">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-secondary-100">
              {versions.map((v, idx) => {
                const prev = idx > 0 ? versions[idx - 1] : null;
                const delta = prev
                  ? deltaLabel(v.total_amount, prev.total_amount)
                  : null;
                return (
                  <tr key={v.id}>
                    <td className="px-4 py-3 font-medium text-secondary-900">
                      {v.revision_number}
                    </td>
                    <td className="px-4 py-3 text-secondary-700">
                      {formatDateTime(v.submitted_at)}
                    </td>
                    <td className="px-4 py-3 text-right text-secondary-900">
                      {formatCurrency(v.total_amount)}
                    </td>
                    <td className="px-4 py-3">
                      <StateLabels submission={v} />
                    </td>
                    <td
                      className={cn(
                        'px-4 py-3 text-right font-medium',
                        delta ? delta.tone : 'text-secondary-400',
                      )}
                    >
                      {delta ? delta.text : '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onViewBid(v.id)}
                      >
                        View Full Bid
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {revisionRequest?.pm_note && (
        <div className="mt-3 rounded-md border border-secondary-200 bg-white p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-secondary-500">
            PM note
          </p>
          <p className="mt-1 whitespace-pre-line text-sm text-secondary-700">
            {revisionRequest.pm_note}
          </p>
        </div>
      )}

      {revisionRequest?.status === 'declined' &&
        revisionRequest.decline_reason && (
          <div className="mt-3 rounded-md border border-secondary-200 bg-white p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-secondary-500">
              Vendor decline reason
            </p>
            <p className="mt-1 whitespace-pre-line text-sm text-secondary-700">
              {revisionRequest.decline_reason}
            </p>
          </div>
        )}
    </div>
  );
}
