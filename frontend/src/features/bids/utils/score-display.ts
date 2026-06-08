/**
 * Pure presentation helpers for the Task 8.3 Compare route.
 *
 * Keeping derivation OUT of the JSX so the rules (score bands, tie-break, the
 * staleness signal) are testable and stay aligned with the backend's
 * boundaries (e.g. 75 marks the success threshold the recommendation builder
 * also uses for its leader highlights).
 */

import type {
  BidScoreRow,
  RankedVendor,
  WarningFlagCode,
} from '@/features/bids/types';

export type ScoreBandVariant = 'success' | 'warning' | 'danger' | 'neutral';

/** Score → traffic-light variant: ≥75 success, ≥50 warning, else danger.
 * Null / NaN → neutral (we don't have a score for that vendor on this axis). */
export function getScoreBandVariant(score: number | null | undefined): ScoreBandVariant {
  if (score == null || Number.isNaN(score)) return 'neutral';
  if (score >= 75) return 'success';
  if (score >= 50) return 'warning';
  return 'danger';
}

export const WARNING_FLAG_LABELS: Record<WarningFlagCode, string> = {
  over_budget: 'Over budget',
  late_start: 'Late start',
  insurance_window: 'Insurance window',
  onboarding_incomplete: 'Onboarding incomplete',
};

/** Decimal-as-string (Pydantic) → number. Returns null for null/empty/NaN. */
export function parseDecimal(value: string | null | undefined): number | null {
  if (value == null || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function getRowThisTotal(row: BidScoreRow): number | null {
  return parseDecimal(row.scoring_metadata?.inputs?.this_total ?? null);
}

export function maxScoredAt(scores: BidScoreRow[]): string | null {
  let max: string | null = null;
  for (const s of scores) {
    if (s.scored_at && (max === null || s.scored_at > max)) max = s.scored_at;
  }
  return max;
}

/** Short relative time (e.g., "5m ago", "2h ago", "3d ago"). Falls back to a
 * locale date for ages > 30d. */
export function formatRelativeTime(iso: string | null): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const diffSec = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (diffSec < 45) return 'just now';
  const mins = Math.round(diffSec / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export interface StalenessHint {
  scoredLabel: string;       // "5m ago"
  newBidsCount: number;      // 0 → no hint shown
  isStale: boolean;          // true when scores no longer reflect the cohort
}

/**
 * Staleness signal: either (a) more valid live submissions exist than scored
 * rows (a vendor submitted but scoring hasn't been re-run), OR (b) a
 * submission has been updated more recently than the latest scoring run (a
 * vendor revised). Either is enough.
 *
 * K = max(0, valid_submission_count - cohort_size). When K is 0 but the
 * timestamp signal fires, we show K=1 so the hint is visible.
 */
export function formatStalenessHint(
  scoredAt: string | null,
  latestSubmissionAt: string | null,
  validSubmissionCount: number | null,
  cohortSize: number,
): StalenessHint {
  const sizeGap = Math.max(0, (validSubmissionCount ?? 0) - cohortSize);

  let timestampStale = false;
  if (scoredAt && latestSubmissionAt) {
    timestampStale = new Date(latestSubmissionAt).getTime() > new Date(scoredAt).getTime();
  }

  const isStale = sizeGap > 0 || timestampStale;
  const newBidsCount = sizeGap > 0 ? sizeGap : timestampStale ? 1 : 0;

  return {
    scoredLabel: formatRelativeTime(scoredAt),
    newBidsCount,
    isStale,
  };
}

export type SortColumn = 'price' | 'total' | 'timeline';
export type SortDirection = 'asc' | 'desc';

/**
 * Comparator factory. Matches the backend recommendation tie-break for the
 * 'total' column (total_weighted_score desc; ties → this_total asc; final
 * stable by bid_submission_id) so the page and the recommendation agree.
 */
export function compareBy(
  column: SortColumn,
  direction: SortDirection,
): (a: BidScoreRow, b: BidScoreRow) => number {
  const dir = direction === 'asc' ? 1 : -1;
  return (a, b) => {
    let av: number | null;
    let bv: number | null;
    switch (column) {
      case 'price':
        av = getRowThisTotal(a);
        bv = getRowThisTotal(b);
        break;
      case 'timeline':
        av = a.scoring_metadata?.sub_scores?.timeline ?? null;
        bv = b.scoring_metadata?.sub_scores?.timeline ?? null;
        break;
      case 'total':
      default:
        av = parseDecimal(a.total_weighted_score);
        bv = parseDecimal(b.total_weighted_score);
        break;
    }
    if (av == null && bv == null) return tieBreak(a, b);
    if (av == null) return 1;                  // nulls always sort last
    if (bv == null) return -1;
    if (av !== bv) return (av - bv) * dir;
    return tieBreak(a, b);
  };
}

function tieBreak(a: BidScoreRow, b: BidScoreRow): number {
  // Mirror backend: secondary by this_total asc, then bid_submission_id stable
  const at = getRowThisTotal(a);
  const bt = getRowThisTotal(b);
  if (at != null && bt != null && at !== bt) return at - bt;
  if (at == null && bt != null) return 1;
  if (bt == null && at != null) return -1;
  return a.bid_submission_id.localeCompare(b.bid_submission_id);
}

/** Lookup a ranked vendor by submission ID — used to pull the canonical rank
 * + warning_flags from `recommendation.ranking` into the table. */
export function buildRankIndex(ranking: RankedVendor[]): Map<string, RankedVendor> {
  const map = new Map<string, RankedVendor>();
  for (const r of ranking) map.set(r.bid_submission_id, r);
  return map;
}
