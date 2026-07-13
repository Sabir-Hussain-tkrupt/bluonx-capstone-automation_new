import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchMilestoneEvents } from '@/features/milestones/api/milestone.queries';

export function useMilestoneEvents(id: string) {
  return useQuery({
    queryKey: queryKeys.milestones.events(id),
    queryFn: () => fetchMilestoneEvents(id),
    enabled: !!id,
  });
}
