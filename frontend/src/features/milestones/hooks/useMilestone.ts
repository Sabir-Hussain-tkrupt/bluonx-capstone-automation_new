import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchMilestone } from '@/features/milestones/api/milestone.queries';

export function useMilestone(id: string) {
  return useQuery({
    queryKey: queryKeys.milestones.detail(id),
    queryFn: () => fetchMilestone(id),
    enabled: !!id,
  });
}
