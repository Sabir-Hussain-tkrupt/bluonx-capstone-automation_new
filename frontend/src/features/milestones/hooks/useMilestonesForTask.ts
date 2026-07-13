import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchMilestonesForTask } from '@/features/milestones/api/milestone.queries';

export function useMilestonesForTask(taskId: string) {
  return useQuery({
    queryKey: queryKeys.milestones.list({ taskId }),
    queryFn: () => fetchMilestonesForTask(taskId),
    enabled: !!taskId,
  });
}
