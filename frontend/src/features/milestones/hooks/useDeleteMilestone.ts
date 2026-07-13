import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { deleteMilestone } from '@/features/milestones/api/milestone.mutations';

export function useDeleteMilestone() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteMilestone(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.detail(id) });
    },
  });
}
