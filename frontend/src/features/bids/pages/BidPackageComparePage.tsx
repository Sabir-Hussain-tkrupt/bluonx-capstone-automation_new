import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useBidPackageDetail } from '@/features/bids/hooks/useBidPackageDetail';
import { useBidPackageScores } from '@/features/bids/hooks/useBidPackageScores';
import { useComputeBidPackageScores } from '@/features/bids/hooks/useComputeBidPackageScores';
import { useProject } from '@/features/projects/hooks/useProject';
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

  const { data: bp, isLoading: bpLoading, error: bpError } =
    useBidPackageDetail(bidPackageId!);
  const { data: task } = useTask(projectId!, taskId!);
  // Not rendered here; primes the cache so the breadcrumb can name the project.
  useProject(projectId!);
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
    instructions?: string;
    contract_valid_days?: number;
    work_duration_days?: number;
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
        <div className="rounded-lg border border-danger-200 bg-danger-50 p-6 text-sm text-danger-700">
          {detail}
        </div>
      </div>
    );
  }

  if (bpLoading || scoresLoading || !bp || !cohort) {
    return (
      <div className="space-y-4">
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
        <div className="min-w-0">
          <h1 className="truncate text-xl font-semibold text-secondary-900 sm:text-2xl">
            Compare bids: {bp.task_name} (Round {bp.round_number})
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
              // Suppress the recommendation's Award action once the task has a
              // live award (RecommendationPanel hides the button when onAward is
              // omitted). The winning-row "Awarded" state lives in the table.
              onAward={bp.award ? undefined : handleAward}
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
            award={bp.award ?? null}
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
