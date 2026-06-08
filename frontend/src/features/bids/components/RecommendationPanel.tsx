import { cn } from '@/utils/cn';
import { formatCurrency } from '@/lib/format';
import type { BidRecommendation, RankedVendor } from '@/features/bids/types';
import { parseDecimal } from '@/features/bids/utils/score-display';
import { WarningFlagChip } from './WarningFlagChip';

export interface RecommendationPanelProps {
  recommendation: BidRecommendation;
}

/**
 * Task 8.4 verdict surface. Three sections:
 *  - Recommended (#1) — highlighted card with company, total, justification, flags.
 *  - Alternatives (#2/#3) — compact rows. Hidden for lone-bidder cohorts so we
 *    don't fabricate fake alternatives (task acceptance: "no false alternatives").
 */
export function RecommendationPanel({ recommendation }: RecommendationPanelProps) {
  const ranking = recommendation.ranking;
  if (ranking.length === 0) return null;

  const winner = ranking[0];
  const alternatives = ranking.slice(1, 3);

  return (
    <section
      aria-labelledby="recommendation-heading"
      className="recommendation-panel space-y-3"
    >
      <h2
        id="recommendation-heading"
        className="text-sm font-medium uppercase tracking-wider text-secondary-500"
      >
        Recommendation
      </h2>

      <div className="rounded-lg border-2 border-primary-300 bg-primary-50/60 p-5 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center rounded-full bg-primary-600 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-white">
                #1 Recommended
              </span>
              <span className="text-lg font-semibold text-secondary-900">
                {winner.vendor_company_name ?? 'Top-ranked vendor'}
              </span>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-secondary-700">
              {recommendation.justification}
            </p>
          </div>
          <div className="text-right sm:shrink-0">
            <div className="text-xs uppercase tracking-wide text-secondary-500">
              Weighted score
            </div>
            <div className="font-semibold text-secondary-900 tabular-nums text-2xl">
              {formatScore(winner.total_weighted_score)}
            </div>
            <div className="mt-1 text-xs text-secondary-600 tabular-nums">
              {formatCurrency(parseDecimal(winner.this_total) ?? 0)}
            </div>
          </div>
        </div>
        {winner.warning_flags.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {winner.warning_flags.map((code) => (
              <WarningFlagChip key={code} code={code} />
            ))}
          </div>
        )}
      </div>

      {alternatives.length > 0 && (
        <div className="rounded-lg border border-secondary-200 bg-white">
          <div className="border-b border-secondary-100 px-4 py-2 text-xs font-medium uppercase tracking-wider text-secondary-500">
            Alternatives
          </div>
          <ul className="divide-y divide-secondary-100">
            {alternatives.map((alt) => (
              <AlternativeRow key={alt.bid_submission_id} vendor={alt} />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function AlternativeRow({ vendor }: { vendor: RankedVendor }) {
  return (
    <li className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
      <span
        className={cn(
          'inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-secondary-100 text-xs font-semibold text-secondary-700',
        )}
      >
        #{vendor.rank}
      </span>
      <span className="min-w-0 flex-1 truncate font-medium text-secondary-900">
        {vendor.vendor_company_name ?? 'Vendor'}
      </span>
      <span className="tabular-nums text-secondary-700">
        {formatScore(vendor.total_weighted_score)}
      </span>
      <span className="tabular-nums text-secondary-500">
        {formatCurrency(parseDecimal(vendor.this_total) ?? 0)}
      </span>
      {vendor.warning_flags.length > 0 && (
        <div className="flex w-full flex-wrap gap-1.5 sm:w-auto">
          {vendor.warning_flags.map((code) => (
            <WarningFlagChip key={code} code={code} />
          ))}
        </div>
      )}
    </li>
  );
}

function formatScore(value: string | null): string {
  const n = parseDecimal(value);
  if (n == null) return '—';
  return n.toFixed(2);
}
