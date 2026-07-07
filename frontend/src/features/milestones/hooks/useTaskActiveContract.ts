import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchTaskActiveContract } from '@/features/milestones/api/milestone.queries';

export function useTaskActiveContract(taskId: string) {
  return useQuery({
    queryKey: queryKeys.contracts.list({ taskId }),
    queryFn: () => fetchTaskActiveContract(taskId),
    enabled: !!taskId,
  });
}
