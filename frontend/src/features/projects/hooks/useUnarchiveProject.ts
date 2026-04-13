import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { unarchiveProject } from '@/features/projects/api/project.mutations';

export function useUnarchiveProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: unarchiveProject,
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.detail(id) });
    },
  });
}
