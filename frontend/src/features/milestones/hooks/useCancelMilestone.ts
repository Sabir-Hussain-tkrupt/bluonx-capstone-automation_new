import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { cancelMilestone } from '@/features/milestones/api/milestone.mutations';

export function useCancelMilestone() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => cancelMilestone(id),
    onSuccess: (milestone) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.detail(milestone.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.events(milestone.id) });
    },
  });
}
