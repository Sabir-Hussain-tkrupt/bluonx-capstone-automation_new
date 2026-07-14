import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchProjectTimelineMilestones } from '@/features/milestones/api/milestoneOverview.queries';

/** All milestones for one project (no pagination), ordered for the timeline. */
export function useProjectTimeline(projectId: string) {
  return useQuery({
    queryKey: queryKeys.milestones.timeline(projectId),
    queryFn: () => fetchProjectTimelineMilestones(projectId),
    enabled: !!projectId,
  });
}
