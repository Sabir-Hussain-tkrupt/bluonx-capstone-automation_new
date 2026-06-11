import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useBidPackageDetail } from '@/features/bids/hooks/useBidPackageDetail';
import { useBidPackageScores } from '@/features/bids/hooks/useBidPackageScores';
import { useComputeBidPackageScores } from '@/features/bids/hooks/useComputeBidPackageScores';
import { useTask } from '@/features/tasks/hooks/useTask';
import { useToast } from '@/components/ui/Toast/useToast';
import { useCreateAward } from '@/features/bids/hooks/useCreateAward';
import { AwardDialog } from '@/features/bids/components/AwardDialog';
import { BidAmountBarChart } from '@/features/bids/components/BidAmountBarChart';
import { BidSubmissionDetailModal } from '@/features/bids/components/BidSubmissionDetailModal';
import { ComparisonTable } from '@/features/bids/components/ComparisonTable';
import { ComputeRankingsCTA } from '@/features/bids/components/ComputeRankingsCTA';
import { OpenRoundBanner } from '@/features/bids/components/OpenRoundBanner';
import { RecommendationPanel } from '@/features/bids/components/RecommendationPanel';
import { StalenessHint } from '@/features/bids/components/StalenessHint';
import {
  formatStalenessHint,
  maxScoredAt,
  type SortColumn,
  type SortDirection,
} from '@/features/bids/utils/score-display';
import type { SubmittedBid } from '@/features/bids/types';
import { cn } from '@/utils/cn';

/**
 * Task 8.3: dedicated PM workspace for side-by-side comparison + the 8.4
 * recommendation. Reached from BidPackageDetailPage when gating passes:
 * competitive package + ≥1 valid submitted bid. Status & deadline never gate.
 *
 * Data: useBidPackageDetail (header / status / N-of-M counts), useTask
 * (bid_type gate), useBidPackageScores (the enriched + recommendation
 * envelope). POST is gated through useComputeBidPackageScores; it invalidates
 * the scores query on success so the page refetches the authoritative GET.
 */
export function BidPackageComparePage() {
  const { id: projectId, taskId, bidPackageId } = useParams<{
    id: string;
    taskId: string;
    bidPackageId: string;
  }>();
  const navigate = useNavigate();

  const { data: bp, isLoading: bpLoading, error: bpError } =
    useBidPackageDetail(bidPackageId!);
  const { data: task } = useTask(projectId!, taskId!);
  const {
    data: cohort,
    isLoading: scoresLoading,
    error: scoresError,
  } = useBidPackageScores(bidPackageId!);
  const recomputeMutation = useComputeBidPackageScores(bidPackageId!);
  const { toast } = useToast();
  const awardMutation = useCreateAward({
    bidPackageId: bidPackageId!,
    taskId: taskId!,
  });

  // Sort + UI state.
  const [sortColumn, setSortColumn] = useState<SortColumn>('total');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [viewSubmissionId, setViewSubmissionId] = useState<string | null>(null);
  const [awardTarget, setAwardTarget] = useState<{
    bidSubmissionId: string;
    vendorName: string;
  } | null>(null);
  const [awardError, setAwardError] = useState<string | null>(null);

  const handleAward = (bidSubmissionId: string, vendorName: string) => {
    setAwardError(null);
    setAwardTarget({ bidSubmissionId, vendorName });
  };

  const handleConfirmAward = (args: {
    has_override: boolean;
    override_justification?: string;
  }) => {
    if (!awardTarget) return;
    setAwardError(null);
    awardMutation.mutate(
      { bid_submission_id: awardTarget.bidSubmissionId, ...args },
      {
        onSuccess: () => {
          toast({
            variant: 'success',
            message: `Awarded ${awardTarget.vendorName}.`,
          });
          setAwardTarget(null);
        },
        onError: (err) => {
          setAwardError(
            (err as { message?: string })?.message ||
              'Failed to create the award. Please try again.',
          );
        },
      },
    );
  };

  const handleSortChange = (column: SortColumn) => {
    if (column === sortColumn) {
      setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortColumn(column);
      // Sensible defaults per column.
      setSortDirection(column === 'price' ? 'asc' : 'desc');
    }
  };

  const handleToggleExpand = (id: string) => {
    setExpandedId((current) => (current === id ? null : id));
  };

  const stalenessHint = useMemo(() => {
    if (!cohort) return null;
    return formatStalenessHint(
      maxScoredAt(cohort.scores),
      cohort.latest_submission_at,
      cohort.valid_submission_count,
      cohort.cohort_size,
    );
  }, [cohort]);

  // Derive the "Submitted Bid Amounts" chart data straight from the live
  // scored cohort — same source as the table, so the chart can never diverge
  // from the ranking.
  const submittedBids = useMemo<SubmittedBid[]>(() => {
    if (!cohort) return [];
    return cohort.scores
      .map((s) => ({
        vendor_company_name: s.vendor_company_name ?? 'Vendor',
        total_amount: Number(s.scoring_metadata?.inputs?.this_total ?? 0),
      }))
      .filter((b) => Number.isFinite(b.total_amount) && b.total_amount > 0);
  }, [cohort]);

  // ── Defensive guards ──────────────────────────────────────────────────
  if (task && task.bid_type !== 'competitive') {
    return (
      <div className="space-y-4">
        <BackHeader projectId={projectId!} taskId={taskId!} bidPackageId={bidPackageId!} />
        <div className="rounded-lg border border-secondary-200 bg-white p-6 text-sm text-secondary-700">
          Comparison is only available for competitive bid packages.
        </div>
      </div>
    );
  }

  if (bpError || scoresError) {
    const detail =
      (scoresError as { message?: string } | undefined)?.message ??
      (bpError as { message?: string } | undefined)?.message ??
      'Failed to load comparison.';
    return (
      <div className="space-y-4">
        <BackHeader projectId={projectId!} taskId={taskId!} bidPackageId={bidPackageId!} />
        <div className="rounded-lg border border-danger-200 bg-danger-50 p-6 text-sm text-danger-700">
          {detail}
        </div>
      </div>
    );
  }

  if (bpLoading || scoresLoading || !bp || !cohort) {
    return (
      <div className="space-y-4">
        <BackHeader projectId={projectId!} taskId={taskId!} bidPackageId={bidPackageId!} />
        <Skeleton height="80px" />
        <Skeleton height="240px" />
        <Skeleton height="320px" />
      </div>
    );
  }

  const showOpenRoundBanner =
    bp.status === 'open' &&
    bp.invitation_summary.submitted < bp.invitation_summary.total;

  const hasScores = cohort.scores.length > 0;

  return (
    <div className="compare-print-root space-y-6">
      <PrintStyles />

      {/* Header */}
      <div
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
        data-no-print
      >
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() =>
              navigate(
                `/projects/${projectId}/tasks/${taskId}/bid-packages/${bidPackageId}`,
              )
            }
            className="shrink-0 rounded-lg p-1 text-secondary-400 hover:bg-secondary-100 hover:text-secondary-600"
            aria-label="Back to bid package"
          >
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path
                fillRule="evenodd"
                d="M12.79 5.23a.75.75 0 01-.02 1.06L8.832 10l3.938 3.71a.75.75 0 11-1.04 1.08l-4.5-4.25a.75.75 0 010-1.08l4.5-4.25a.75.75 0 011.06.02z"
                clipRule="evenodd"
              />
            </svg>
          </button>
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold text-secondary-900 sm:text-2xl">
              Compare bids — {bp.task_name} (Round {bp.round_number})
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <StatusBadge status={bp.status} size="sm" />
              <span className="text-xs text-secondary-500">
                {cohort.cohort_size} scored ·{' '}
                {cohort.valid_submission_count ?? 0} valid live
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Open-round banner */}
      {showOpenRoundBanner && (
        <OpenRoundBanner
          respondedCount={bp.invitation_summary.submitted}
          invitedCount={bp.invitation_summary.total}
        />
      )}

      {/* Either the empty CTA OR (recommendation + table + chart). */}
      {!hasScores ? (
        <ComputeRankingsCTA
          onCompute={() => recomputeMutation.mutate()}
          isComputing={recomputeMutation.isPending}
          validSubmissionCount={cohort.valid_submission_count ?? 0}
        />
      ) : (
        <>
          {cohort.recommendation && (
            <RecommendationPanel
              recommendation={cohort.recommendation}
              onAward={handleAward}
            />
          )}

          {stalenessHint && (
            <StalenessHint
              hint={stalenessHint}
              onRecompute={() => recomputeMutation.mutate()}
              isRecomputing={recomputeMutation.isPending}
            />
          )}

          <ComparisonTable
            scores={cohort.scores}
            ranking={cohort.recommendation?.ranking ?? []}
            recommendedId={cohort.recommendation?.recommended_bid_submission_id ?? null}
            sortColumn={sortColumn}
            sortDirection={sortDirection}
            onSortChange={handleSortChange}
            expandedId={expandedId}
            onToggleExpand={handleToggleExpand}
            onViewBid={setViewSubmissionId}
            onAward={handleAward}
          />

          {submittedBids.length > 0 && (
            <div className={cn('print:break-inside-avoid')}>
              <BidAmountBarChart submittedBids={submittedBids} />
            </div>
          )}
        </>
      )}

      <BidSubmissionDetailModal
        submissionId={viewSubmissionId}
        isOpen={!!viewSubmissionId}
        onClose={() => setViewSubmissionId(null)}
      />

      <AwardDialog
        key={awardTarget?.bidSubmissionId ?? 'closed'}
        bidSubmissionId={awardTarget?.bidSubmissionId ?? null}
        vendorName={awardTarget?.vendorName ?? 'Vendor'}
        isOpen={!!awardTarget}
        onClose={() => {
          if (!awardMutation.isPending) {
            setAwardTarget(null);
            setAwardError(null);
          }
        }}
        onConfirm={handleConfirmAward}
        isSubmitting={awardMutation.isPending}
        serverError={awardError}
      />
    </div>
  );
}

function BackHeader({
  projectId,
  taskId,
  bidPackageId,
}: {
  projectId: string;
  taskId: string;
  bidPackageId: string;
}) {
  const navigate = useNavigate();
  return (
    <div className="flex items-center gap-2" data-no-print>
      <Button
        variant="ghost"
        size="sm"
        onClick={() =>
          navigate(
            `/projects/${projectId}/tasks/${taskId}/bid-packages/${bidPackageId}`,
          )
        }
      >
        ← Back to bid package
      </Button>
    </div>
  );
}

/**
 * Route-scoped print rules. No global print stylesheet exists in the codebase;
 * keeping this inline keeps the styles co-located with the only consumer.
 */
function PrintStyles() {
  return (
    <style>{`
      @media print {
        nav, header, [data-no-print], button[data-no-print] { display: none !important; }
        .compare-print-root { padding: 0 !important; max-width: none !important; }
        .recommendation-panel { break-inside: avoid; }
        .comparison-table { overflow: visible !important; }
        .comparison-table > .md\\:hidden { display: none !important; }
        .comparison-table > .hidden.md\\:block { display: block !important; }
        *:hover { background-color: transparent !important; }
      }
    `}</style>
  );
}
