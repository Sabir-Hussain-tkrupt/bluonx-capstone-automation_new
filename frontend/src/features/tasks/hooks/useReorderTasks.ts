import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { reorderTasks } from '@/features/tasks/api/task.mutations';
import type { ReorderItem } from '@/features/tasks/api/task.mutations';
import type { PaginatedTasks, Task } from '@/features/tasks/api/task.queries';

export function useReorderTasks(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (items: ReorderItem[]) => reorderTasks(projectId, items),

    onMutate: async (items) => {
      // Cancel in-flight fetches so they don't overwrite our optimistic update
      await queryClient.cancelQueries({ queryKey: queryKeys.tasks.lists() });

      // Snapshot all task list queries for rollback
      const previousQueries = queryClient.getQueriesData<PaginatedTasks>({
        queryKey: queryKeys.tasks.lists(),
      });

      // Build a sort_order lookup from the reorder payload
      const orderMap = new Map(items.map((i) => [i.task_id, i.sort_order]));

      // Optimistically update every cached task list that matches
      queryClient.setQueriesData<PaginatedTasks>(
        { queryKey: queryKeys.tasks.lists() },
        (old) => {
          if (!old) return old;
          const updated = old.items
            .map((task: Task) => {
              const newOrder = orderMap.get(task.id);
              return newOrder != null ? { ...task, sort_order: newOrder } : task;
            })
            .sort((a: Task, b: Task) => a.sort_order - b.sort_order);
          return { ...old, items: updated };
        },
      );

      return { previousQueries };
    },

    onError: (_err, _items, context) => {
      // Rollback to snapshot on failure
      if (context?.previousQueries) {
        for (const [key, data] of context.previousQueries) {
          queryClient.setQueryData(key, data);
        }
      }
    },

    onSettled: () => {
      // Always refetch to sync with server truth
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.lists() });
    },
  });
}
