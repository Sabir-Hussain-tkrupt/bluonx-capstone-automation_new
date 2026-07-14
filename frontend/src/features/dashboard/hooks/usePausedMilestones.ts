import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchPausedMilestones } from '@/features/milestones/api/milestoneOverview.queries';

/**
 * Every paused (delayed/unresponsive) milestone across all projects, worst-stalled
 * first. Shared by the dashboard attention card and the sidebar badge — one query
 * key, so React Query dedupes the two consumers.
 */
export function usePausedMilestones() {
  return useQuery({
    queryKey: queryKeys.dashboard.pausedMilestones(),
    queryFn: () => fetchPausedMilestones(),
  });
}
