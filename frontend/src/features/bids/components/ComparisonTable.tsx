import { Fragment } from 'react';
import { ArrowDown, ArrowUp, ChevronRight, ChevronsUpDown } from 'lucide-react';
import { cn } from '@/utils/cn';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { formatCurrency, formatDateOnly } from '@/lib/format';
import { useBidSubmissionDetail } from '@/features/bids/hooks/useBidSubmissionDetail';
import type {
  ActiveAward,
  BidScoreRow,
  RankedVendor,
  ScoreDimension,
} from '@/features/bids/types';
import {
  buildRankIndex,
  compareBy,
  getRowThisTotal,
  type SortColumn,
  type SortDirection,
} from '@/features/bids/utils/score-display';
import { ScoreBandChip } from './ScoreBandChip';
import { WarningFlagChip } from './WarningFlagChip';
import { BidLineItemsTable } from './BidLineItemsTable';

export interface ComparisonTableProps {
  scores: BidScoreRow[];
  ranking: RankedVendor[];
  recommendedId: string | null;
  sortColumn: SortColumn;
  sortDirection: SortDirection;
  onSortChange: (column: SortColumn) => void;
  expandedId: string | null;
  onToggleExpand: (id: string) => void;
  onViewBid: (submissionId: string) => void;
  /** Award this vendor's submission (Task 9.2). Omit to hide the action. */
  onAward?: (submissionId: string, vendorName: string) => void;
  /** The task's live award (or null). When present, the Award action is
   *  suppressed on every row and the winning row shows an "Awarded" state. */
  award?: ActiveAward | null;
}

const DIMENSION_COLUMNS: { key: ScoreDimension; label: string }[] = [
  { key: 'price', label: 'Price' },
  { key: 'compliance', label: 'Compliance' },
  { key: 'performance', label: 'Performance' },
  { key: 'capacity', label: 'Capacity' },
  { key: 'timeline', label: 'Timeline' },
];

/**
 * Side-by-side scored cohort. Built directly (rather than on the generic
 * Table primitive) because the column set is bespoke: chips, embedded score
 * bands, multi-flag cells, and inline expansion for line items.
 *
 * Mobile collapses to stacked cards via the `md:` Tailwind breakpoint,
 * matching the project's existing Table convention.
 */
export function ComparisonTable({
  scores,
  ranking,
  recommendedId,
  sortColumn,
  sortDirection,
  onSortChange,
  expandedId,
  onToggleExpand,
  onViewBid,
  onAward,
  award,
}: ComparisonTableProps) {
  const rankByIdx = buildRankIndex(ranking);
  const sorted = [...scores].sort(compareBy(sortColumn, sortDirection));

  return (
    <div className="comparison-table overflow-hidden rounded-lg border border-secondary-200 bg-white shadow-sm">
      {/* Mobile stacked cards */}
      <ul className="space-y-3 p-3 md:hidden">
        {sorted.map((row) => {
          const ranked = rankByIdx.get(row.bid_submission_id);
          const isRecommended = row.bid_submission_id === recommendedId;
          return (
            <li key={row.bid_submission_id}>
              <MobileVendorCard
                row={row}
                ranked={ranked}
                isRecommended={isRecommended}
                award={award}
                onViewBid={() => onViewBid(row.bid_submission_id)}
                onToggleExpand={() => onToggleExpand(row.bid_submission_id)}
                onAward={
                  onAward
                    ? () =>
                        onAward(
                          row.bid_submission_id,
                          row.vendor_company_name ?? 'Vendor',
                        )
                    : undefined
                }
                isExpanded={expandedId === row.bid_submission_id}
              />
              {expandedId === row.bid_submission_id && (
                <ExpandedLineItems submissionId={row.bid_submission_id} />
              )}
            </li>
          );
        })}
      </ul>

      {/* Desktop table */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-secondary-200 bg-secondary-50 text-xs uppercase tracking-wider text-secondary-500">
              <th className="w-8 px-3 py-3" aria-label="Expand row" />
              <th className="px-4 py-3 text-left font-medium">Vendor</th>
              <SortableTh
                label="Bid Total"
                column="price"
                active={sortColumn === 'price'}
                direction={sortDirection}
                onSort={onSortChange}
                align="right"
              />
              {DIMENSION_COLUMNS.map((d) => {
                const sortable = d.key === 'timeline';
                return sortable ? (
                  <SortableTh
                    key={d.key}
                    label={d.label}
                    column="timeline"
                    active={sortColumn === 'timeline'}
                    direction={sortDirection}
                    onSort={onSortChange}
                    align="center"
                  />
                ) : (
                  <th
                    key={d.key}
                    className="px-3 py-3 text-center font-medium"
                    scope="col"
                  >
                    {d.label}
                  </th>
                );
              })}
              <SortableTh
                label="Total Score"
                column="total"
                active={sortColumn === 'total'}
                direction={sortDirection}
                onSort={onSortChange}
                align="center"
              />
              <th className="px-4 py-3 text-left font-medium">Flags</th>
              <th
                className="px-3 py-3 text-right font-medium"
                data-no-print
                aria-label="Row actions"
              />
            </tr>
          </thead>
          <tbody className="divide-y divide-secondary-100">
            {sorted.map((row) => {
              const ranked = rankByIdx.get(row.bid_submission_id);
              const isRecommended = row.bid_submission_id === recommendedId;
              const isExpanded = expandedId === row.bid_submission_id;
              return (
                <Fragment key={row.bid_submission_id}>
                  <tr
                    className={cn(
                      'transition-colors',
                      isRecommended && 'bg-primary-50/60 ring-1 ring-primary-200',
                    )}
                  >
                    <td className="px-3 py-3" data-no-print>
                      <button
                        type="button"
                        onClick={() => onToggleExpand(row.bid_submission_id)}
                        aria-label={
                          isExpanded ? 'Collapse line items' : 'Expand line items'
                        }
                        aria-expanded={isExpanded}
                        className="rounded p-1 text-secondary-500 transition-colors hover:bg-secondary-100 hover:text-secondary-700"
                      >
                        <Chevron expanded={isExpanded} />
                      </button>
                    </td>
                    <td className="px-4 py-3 align-top">
                      <div className="flex items-center gap-2">
                        <RankPill rank={ranked?.rank ?? null} />
                        <span className="font-medium text-secondary-900">
                          {row.vendor_company_name ?? 'Vendor'}
                        </span>
                        {isRecommended && (
                          <span className="inline-flex items-center rounded-full bg-primary-600 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                            Recommended
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-medium text-secondary-900 tabular-nums">
                      {formatCurrency(getRowThisTotal(row) ?? 0)}
                    </td>
                    {DIMENSION_COLUMNS.map((d) => (
                      <td key={d.key} className="px-3 py-3 text-center">
                        <div className="inline-flex flex-col items-center gap-0.5">
                          <ScoreBandChip
                            score={row.scoring_metadata.sub_scores?.[d.key] ?? null}
                          />
                          {d.key === 'timeline' && (
                            <span className="text-[10px] text-secondary-500">
                              {formatDateOnly(
                                row.scoring_metadata.inputs.proposed_start_date,
                              )}
                            </span>
                          )}
                        </div>
                      </td>
                    ))}
                    <td className="px-3 py-3 text-center">
                      <div className="inline-flex flex-col items-center gap-0.5">
                        <ScoreBandChip score={row.total_weighted_score} />
                        <span className="text-[10px] font-medium text-secondary-700 tabular-nums">
                          {formatScoreDecimal(row.total_weighted_score)}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 align-top">
                      {ranked && ranked.warning_flags.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5">
                          {ranked.warning_flags.map((code) => (
                            <WarningFlagChip key={code} code={code} />
                          ))}
                        </div>
                      ) : (
                        <span className="text-xs text-secondary-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-right" data-no-print>
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => onViewBid(row.bid_submission_id)}
                        >
                          View Bid
                        </Button>
                        <AwardCell
                          row={row}
                          award={award}
                          onAwardClick={
                            onAward
                              ? () =>
                                  onAward(
                                    row.bid_submission_id,
                                    row.vendor_company_name ?? 'Vendor',
                                  )
                              : undefined
                          }
                        />
                      </div>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr>
                      <td
                        colSpan={5 + DIMENSION_COLUMNS.length}
                        className="bg-secondary-50/60 px-4 py-4"
                      >
                        <ExpandedLineItems submissionId={row.bid_submission_id} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Sub-components ──────────────────────────────────────────────────────

function SortableTh({
  label,
  column,
  active,
  direction,
  onSort,
  align,
}: {
  label: string;
  column: SortColumn;
  active: boolean;
  direction: SortDirection;
  onSort: (col: SortColumn) => void;
  align: 'left' | 'center' | 'right';
}) {
  const aria = active
    ? direction === 'asc'
      ? ('ascending' as const)
      : ('descending' as const)
    : ('none' as const);
  return (
    <th
      scope="col"
      className={cn(
        'px-3 py-3 font-medium',
        align === 'left' && 'text-left',
        align === 'center' && 'text-center',
        align === 'right' && 'text-right',
      )}
      aria-sort={aria}
    >
      <button
        type="button"
        onClick={() => onSort(column)}
        className="inline-flex items-center gap-1 hover:text-secondary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
      >
        <span>{label}</span>
        <SortIcon direction={active ? direction : undefined} />
      </button>
    </th>
  );
}

function SortIcon({ direction }: { direction?: SortDirection }) {
  const className = 'h-3.5 w-3.5';
  if (direction === 'asc') return <ArrowUp className={className} aria-hidden="true" />;
  if (direction === 'desc') return <ArrowDown className={className} aria-hidden="true" />;
  return <ChevronsUpDown className={className} aria-hidden="true" />;
}

function Chevron({ expanded }: { expanded: boolean }) {
  return (
    <ChevronRight
      className={cn('h-4 w-4 transition-transform', expanded && 'rotate-90')}
      aria-hidden="true"
    />
  );
}

function RankPill({ rank }: { rank: number | null }) {
  if (rank == null) return null;
  return (
    <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-secondary-100 text-[10px] font-semibold text-secondary-700">
      {rank}
    </span>
  );
}

/**
 * Award action cell, shared by desktop + mobile. Three states keyed on the
 * task's live award (Task 9.2/9.3b):
 *   - no live award        → the Award button (re-awardable; backend 409 is the net)
 *   - this is the winner   → an "Awarded" badge (pending_acceptance vs accepted)
 *   - another row won      → nothing (suppressed)
 */
function AwardCell({
  row,
  award,
  onAwardClick,
}: {
  row: BidScoreRow;
  award?: ActiveAward | null;
  onAwardClick?: () => void;
}) {
  if (award) {
    if (award.bid_submission_id === row.bid_submission_id) {
      return <AwardedBadge status={award.status} />;
    }
    return null;
  }
  if (!onAwardClick) return null;
  return (
    <Button variant="primary" size="sm" onClick={onAwardClick}>
      Award
    </Button>
  );
}

function AwardedBadge({ status }: { status: ActiveAward['status'] }) {
  const accepted = status === 'accepted';
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold whitespace-nowrap',
        accepted
          ? 'bg-success-100 text-success-700'
          : 'bg-warning-100 text-warning-700',
      )}
    >
      {accepted ? 'Awarded ✓' : 'Pending signature'}
    </span>
  );
}

function MobileVendorCard({
  row,
  ranked,
  isRecommended,
  isExpanded,
  award,
  onViewBid,
  onToggleExpand,
  onAward,
}: {
  row: BidScoreRow;
  ranked?: RankedVendor;
  isRecommended: boolean;
  isExpanded: boolean;
  award?: ActiveAward | null;
  onViewBid: () => void;
  onToggleExpand: () => void;
  onAward?: () => void;
}) {
  return (
    <div
      className={cn(
        'rounded-lg border border-secondary-200 bg-white p-4 shadow-sm',
        isRecommended && 'border-primary-300 ring-1 ring-primary-200 bg-primary-50/40',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <RankPill rank={ranked?.rank ?? null} />
            <p className="truncate text-sm font-semibold text-secondary-900">
              {row.vendor_company_name ?? 'Vendor'}
            </p>
          </div>
          {isRecommended && (
            <span className="mt-1 inline-flex items-center rounded-full bg-primary-600 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
              Recommended
            </span>
          )}
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-wide text-secondary-500">
            Total
          </p>
          <p className="text-sm font-semibold tabular-nums text-secondary-900">
            {formatScoreDecimal(row.total_weighted_score)}
          </p>
          <p className="text-xs tabular-nums text-secondary-500">
            {formatCurrency(getRowThisTotal(row) ?? 0)}
          </p>
        </div>
      </div>
      <dl className="mt-3 grid grid-cols-5 gap-2 text-center text-[10px]">
        {DIMENSION_COLUMNS.map((d) => (
          <div key={d.key} className="flex flex-col items-center gap-1">
            <dt className="text-secondary-500">{d.label.slice(0, 4)}</dt>
            <dd>
              <ScoreBandChip score={row.scoring_metadata.sub_scores?.[d.key] ?? null} />
            </dd>
          </div>
        ))}
      </dl>
      {ranked && ranked.warning_flags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {ranked.warning_flags.map((code) => (
            <WarningFlagChip key={code} code={code} />
          ))}
        </div>
      )}
      <div className="mt-3 flex items-center justify-between" data-no-print>
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleExpand}
          aria-expanded={isExpanded}
        >
          {isExpanded ? 'Hide line items' : 'Show line items'}
        </Button>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={onViewBid}>
            View Bid
          </Button>
          <AwardCell row={row} award={award} onAwardClick={onAward} />
        </div>
      </div>
    </div>
  );
}

function ExpandedLineItems({ submissionId }: { submissionId: string }) {
  const { data, isLoading, error } = useBidSubmissionDetail(submissionId);
  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton height="32px" />
        <Skeleton height="120px" />
      </div>
    );
  }
  if (error || !data) {
    return (
      <p className="text-xs text-danger-600">Failed to load line items.</p>
    );
  }
  return <BidLineItemsTable items={data.line_items} />;
}

function formatScoreDecimal(value: string | null): string {
  if (value == null || value === '') return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return n.toFixed(2);
}
