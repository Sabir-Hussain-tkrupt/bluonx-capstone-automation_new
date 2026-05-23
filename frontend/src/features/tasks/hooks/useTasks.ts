import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchTasks } from '@/features/tasks/api/task.queries';
import type { TaskListFilters } from '@/features/tasks/api/task.queries';

export function useTasks(filters: TaskListFilters) {
  return useQuery({
    queryKey: queryKeys.tasks.list(filters as unknown as { projectId?: string }),
    queryFn: () => fetchTasks(filters),
    enabled: !!filters.projectId,
  });
}
