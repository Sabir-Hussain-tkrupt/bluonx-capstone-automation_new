import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { archiveProject } from '@/features/projects/api/project.mutations';

export function useArchiveProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: archiveProject,
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.detail(id) });
    },
  });
}
