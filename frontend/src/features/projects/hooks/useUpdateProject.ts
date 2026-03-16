import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { updateProject } from '@/features/projects/api/project.mutations';
import type { UpdateProjectInput } from '@/features/projects/api/project.mutations';

/**
 * Update a project via FastAPI.
 */
export function useUpdateProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: updateProject,
    onSuccess: (_data, variables: UpdateProjectInput) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.detail(variables.id) });
    },
  });
}
