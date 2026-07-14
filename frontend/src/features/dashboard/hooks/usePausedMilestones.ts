import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import {
  fetchPausedMilestones,
  fetchPausedMilestonesCount,
  type PausedMilestonesParams,
} from '@/features/milestones/api/milestoneOverview.queries';

/**
 * Paused (delayed/unresponsive) milestones across all projects, worst-stalled
 * first, limited to what the dashboard card renders. Optionally scoped to one
 * creator ("Mine only").
 */
export function usePausedMilestones(params: PausedMilestonesParams = {}) {
  return useQuery({
    queryKey: queryKeys.dashboard.pausedMilestones(params as Record<string, unknown>),
    queryFn: () => fetchPausedMilestones(params),
  });
}

/**
 * Exact count of paused milestones (optionally for one creator). Head-only, so
 * it is cheap and stays accurate at any scale. Shared by the sidebar badge and
 * the card's count — one query key, so React Query dedupes them.
 */
export function usePausedMilestonesCount(createdBy?: string) {
  const params = createdBy ? { createdBy } : undefined;
  return useQuery({
    queryKey: queryKeys.dashboard.pausedMilestonesCount(params),
    queryFn: () => fetchPausedMilestonesCount(createdBy ? { createdBy } : {}),
  });
}
