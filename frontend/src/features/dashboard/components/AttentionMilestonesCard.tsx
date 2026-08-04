import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Skeleton } from '@/components/ui/Skeleton';
import { MilestoneStatusBadge } from '@/features/milestones/components/MilestoneStatusBadge';
import { buildMilestonePath } from '@/features/milestones/utils/buildMilestonePath';
import { formatStalled } from '@/features/milestones/utils/pauseSeverity';
import {
  usePausedMilestones,
  usePausedMilestonesCount,
} from '@/features/dashboard/hooks/usePausedMilestones';
import type { MilestoneOverviewRow } from '@/features/milestones/api/milestoneOverview.queries';

const MAX_ROWS = 5;

/**
 * Left-border/days-text color, keyed off the milestone's real `status` (not a
 * day-count heuristic) so the row accent always agrees with the status pill
 * next to it. Any status outside the two paused states falls back to neutral
 * rather than an arbitrary color.
 */
const statusAccent: Record<string, { border: string; days: string }> = {
  delayed: { border: 'border-l-warning-400', days: 'text-warning-700' },
  unresponsive: { border: 'border-l-danger-500', days: 'text-danger-700' },
};
const defaultAccent = { border: 'border-l-secondary-200', days: 'text-secondary-600' };

function AttentionRow({
  row,
  isMine,
}: {
  row: MilestoneOverviewRow;
  isMine: boolean;
}) {
  const accent = statusAccent[row.status] ?? defaultAccent;
  return (
    <li>
      <Link
        to={buildMilestonePath(row.project_id, row.task_id, row.milestone_id)}
        className={`flex items-center gap-4 border-l-4 ${accent.border} px-4 py-3 transition-colors hover:bg-secondary-50`}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <MilestoneStatusBadge status={row.status} size="sm" minWidth />
            <p className="truncate text-sm font-medium text-secondary-900">
              {row.milestone_name}
            </p>
          </div>
          <p className="mt-0.5 truncate text-xs text-secondary-500">
            {row.project_name} &middot; {row.task_name} &middot; {row.vendor_company_name}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className={`text-sm font-semibold ${accent.days}`}>
            {formatStalled(row.days_paused)}
          </p>
          <p className="mt-0.5 text-xs text-secondary-500">
            {row.created_by_name ?? 'Unknown'}
            {isMine && (
              <span className="ml-1 rounded bg-primary-50 px-1 py-0.5 text-[10px] font-medium text-primary-600">
                You
              </span>
            )}
          </p>
        </div>
      </Link>
    </li>
  );
}

/**
 * "Needs your attention" dashboard card. Surfaces every paused
 * (delayed/unresponsive) milestone across ALL projects, worst-stalled first, so
 * a milestone whose creator is away cannot sit frozen unseen. The per-person
 * bell notification is the individual channel; this card is the team safety net.
 */
export function AttentionMilestonesCard() {
  const { profile } = useAuth();
  const [mineOnly, setMineOnly] = useState(false);

  // "Mine only" is a server-side filter so both the rows and the count stay
  // correct no matter how many milestones are stalled.
  const createdBy = mineOnly ? profile?.id : undefined;
  const { data: rows = [], isLoading } = usePausedMilestones({
    createdBy,
    limit: MAX_ROWS,
  });
  const { data: total = 0 } = usePausedMilestonesCount(createdBy);

  return (
    <section
      aria-label="Needs your attention"
      className="rounded-lg border border-secondary-200 bg-white shadow-sm"
    >
      <div className="flex items-center justify-between border-b border-secondary-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-secondary-900">Needs your attention</h2>
          {!isLoading && total > 0 && (
            <span className="rounded-full bg-danger-50 px-2 py-0.5 text-xs font-medium text-danger-700">
              {total}
            </span>
          )}
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-xs text-secondary-600">
          <input
            type="checkbox"
            checked={mineOnly}
            onChange={(e) => setMineOnly(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-secondary-300 text-primary-600 focus:ring-primary-500"
          />
          Mine only
        </label>
      </div>

      {isLoading ? (
        <div className="space-y-2 p-4">
          <Skeleton height="44px" />
          <Skeleton height="44px" />
          <Skeleton height="44px" />
        </div>
      ) : rows.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-secondary-500">
          {mineOnly
            ? 'Nothing is waiting on you.'
            : 'Nothing is waiting on you. All milestones are on track.'}
        </p>
      ) : (
        <>
          <ul className="divide-y divide-secondary-100">
            {rows.map((row) => (
              <AttentionRow
                key={row.milestone_id}
                row={row}
                isMine={row.created_by === profile?.id}
              />
            ))}
          </ul>
          {total > MAX_ROWS && (
            <div className="border-t border-secondary-100 px-4 py-2 text-right">
              <Link
                to="/milestones"
                className="text-xs font-medium text-primary-600 hover:text-primary-700"
              >
                View all {total}
              </Link>
            </div>
          )}
        </>
      )}
    </section>
  );
}
