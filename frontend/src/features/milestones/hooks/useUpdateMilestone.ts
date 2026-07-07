import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { updateMilestone } from '@/features/milestones/api/milestone.mutations';
import type { UpdateMilestoneInput } from '@/features/milestones/api/milestone.mutations';

export function useUpdateMilestone() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UpdateMilestoneInput) => updateMilestone(input),
    onSuccess: (milestone) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.detail(milestone.id) });
    },
  });
}
