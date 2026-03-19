import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { reorderTasks } from '@/features/tasks/api/task.mutations';
import type { ReorderItem } from '@/features/tasks/api/task.mutations';

export function useReorderTasks(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (items: ReorderItem[]) => reorderTasks(projectId, items),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.lists() });
    },
  });
}
