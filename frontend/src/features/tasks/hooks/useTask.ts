import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchTaskById } from '@/features/tasks/api/task.queries';

export function useTask(projectId: string, taskId: string) {
  return useQuery({
    queryKey: queryKeys.tasks.detail(taskId),
    queryFn: () => fetchTaskById(projectId, taskId),
    enabled: !!projectId && !!taskId,
  });
}
