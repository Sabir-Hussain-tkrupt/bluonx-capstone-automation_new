import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { createDefaultTasks } from '@/features/tasks/api/task.mutations';

export function useCreateDefaultTasks(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => createDefaultTasks(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.lists() });
    },
  });
}
